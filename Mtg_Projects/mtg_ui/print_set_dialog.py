"""Guided set printing using the standard Print Studio project workflow."""

import logging
import os
import threading
from dataclasses import replace

from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W

from mtg_core import get_default_card_service
from mtg_core.set_catalog import (
    discover_sets,
    filter_sets,
    load_set_cards,
    download_set_data,
    set_artwork_favorites,
)
from mtg_print import library, deck_import, card_layouts
from mtg_print.config import CFG
from mtg_print.models import ProjectState
from mtg_print.set_inventory import (
    InventorySettings,
    RARITIES,
    eligible_cards,
    inventory,
    totals,
    rarity,
    rarity_counts,
)
from mtg_print.services.set_print_service import (
    generate_project,
    SetPrintCancelled,
    SetPrintError,
)
from mtg_ui.loading import LoadingThread, LoadingRunnable
from mtg_ui.theme import COLORS

logger = logging.getLogger(__name__)


class _SymbolSignals(C.QObject):
    ready = C.pyqtSignal(str, bytes)
    done = C.pyqtSignal()


class _Symbols(LoadingRunnable):
    def __init__(self, items, ready, done):
        super().__init__()
        self.items = items
        self.cancelled = threading.Event()
        self.signals = _SymbolSignals()
        self.signals.ready.connect(ready, C.Qt.ConnectionType.QueuedConnection)
        self.signals.done.connect(done, C.Qt.ConnectionType.QueuedConnection)

    def run(self):
        from mtg_print.high_res import fetch_preview_bytes

        try:
            for code, url in self.items:
                if self.cancelled.is_set():
                    break
                try:
                    self.signals.ready.emit(
                        code, fetch_preview_bytes(url, cache_kind="thumbnail")
                    )
                except Exception:
                    logger.debug("Set symbol unavailable", exc_info=True)
        finally:
            self.signals.done.emit()


class _Work(LoadingThread):
    progress = C.pyqtSignal(str, int, int)

    def __init__(self, fn, parent):
        super().__init__(parent)
        self.fn, self.result, self.error = fn, None, None
        self.cancelled = threading.Event()

    def run(self):
        try:
            self.result = self.fn(self)
        except SetPrintCancelled:
            self.cancelled.set()
        except Exception as exc:
            logger.exception("Print Set task failed")
            self.error = exc


class _CopiesDelegate(W.QStyledItemDelegate):
    """Create just the active editor, rather than hundreds of spin widgets."""

    def createEditor(self, parent, option, index):
        card_index = index.siblingAtColumn(0)
        if index.column() != 2 or not card_index.data(C.Qt.ItemDataRole.UserRole):
            return None
        spin = W.QSpinBox(parent)
        spin.setRange(0, 999)
        spin.setAccessibleName(f"Copies of {card_index.data()}")
        return spin

    def setEditorData(self, editor, index):
        editor.setValue(int(index.data(C.Qt.ItemDataRole.EditRole) or 0))

    def setModelData(self, editor, model, index):
        editor.interpretText()
        model.setData(index, editor.value(), C.Qt.ItemDataRole.EditRole)


def _heading(text):
    label = W.QLabel(text)
    label.setProperty("role", "title")
    label.setWordWrap(True)
    return label


class PrintSetDialog(W.QDialog):
    def __init__(self, parent=None, *, service=None):
        super().__init__(parent)
        self.setWindowTitle("Print Set")
        self.setStyleSheet(
            f"QPushButton:focus, QToolButton:focus {{ border: 2px solid {COLORS['accent_hover']}; }}"
        )
        self.resize(820, 780)
        self.setMinimumSize(540, 440)
        if self.screen():
            available = self.screen().availableGeometry()
            self.resize(
                min(820, max(540, available.width() - 48)),
                min(780, max(440, available.height() - 80)),
            )
        self.service = service or get_default_card_service()
        self.settings = InventorySettings()
        self.sets, self.payloads, self.cards = [], [], []
        self.selected = None
        self.project_entry = None
        self.worker = None
        self._callback = None
        self._cache = {}
        self._symbols, self._symbol_requests = {}, set()
        self._symbols_busy = False
        self._symbol_task = None
        self._complete_codes = set()
        self._art_statuses = {}
        self._rules, self._favorites, self._images = None, {}, {}
        self.defaults = {}
        root = W.QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(8)
        root.addWidget(_heading("Print a set"))
        intro = W.QLabel(
            "Build a reusable collection for Draft and Sealed, then preview and export in Print Studio."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)
        self.steps = W.QLabel()
        root.addWidget(self.steps)
        self.pages = W.QStackedWidget()
        root.addWidget(self.pages, 1)
        self._build_browser()
        self._build_options()
        self._build_review()
        self.summary = W.QLabel("Choose a set to begin.")
        self.summary.setFrameShape(W.QFrame.Shape.StyledPanel)
        self.summary.setProperty("role", "panel")
        self.summary.setMargin(12)
        self.summary.setWordWrap(True)
        self.summary.setAccessibleName("Your Print Set summary")
        self.summary.setToolTip(
            "Unique cards count different card identities. Physical cards count every copy you will print. When all artwork versions are included, each version is a separate selection. Estimates cover front sheets; printing backs needs additional sides."
        )
        root.addWidget(self.summary)
        self.status = W.QLabel()
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(
            C.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        root.addWidget(self.status)
        self.progress = W.QProgressBar()
        self.progress.hide()
        root.addWidget(self.progress)
        row = W.QHBoxLayout()
        self.back = W.QPushButton("Back")
        self.back.clicked.connect(
            lambda: self._page(max(0, self.pages.currentIndex() - 1))
        )
        row.addWidget(self.back)
        row.addWidget(self.review_button)
        row.addStretch()
        self.cancel = W.QPushButton("Cancel")
        self.cancel.clicked.connect(self.reject)
        row.addWidget(self.cancel)
        self.next = W.QPushButton("Choose what to print")
        self.next.setProperty("buttonRole", "primary")
        self.next.clicked.connect(self._advance)
        row.addWidget(self.next)
        root.addLayout(row)
        self._page(0)
        C.QTimer.singleShot(0, self._discover)

    def _build_browser(self):
        page = W.QWidget()
        layout = W.QVBoxLayout(page)
        self.search = W.QLineEdit()
        self.search.setPlaceholderText("Search set name or code")
        self.search.setAccessibleName("Search sets by name or code")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)
        self.set_list = W.QListWidget()
        self.set_list.setSpacing(8)
        self.set_list.setIconSize(C.QSize(48, 48))
        self.set_list.setWordWrap(True)
        self.set_list.setVerticalScrollMode(
            W.QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.set_list.setAccessibleName("Available sets")
        self.set_list.setStyleSheet(
            f"QListWidget::item {{ padding: 8px; border: 1px solid {COLORS['border']}; border-radius: 8px; }} QListWidget::item:selected {{ background: {COLORS['surface_selected']}; border-color: {COLORS['accent']}; }}"
        )
        self.set_list.currentItemChanged.connect(self._select)
        self.symbol_timer = C.QTimer(self)
        self.symbol_timer.setSingleShot(True)
        self.symbol_timer.setInterval(120)
        self.symbol_timer.timeout.connect(self._visible_symbols)
        self.set_list.verticalScrollBar().valueChanged.connect(
            lambda _: self.symbol_timer.start()
        )
        layout.addWidget(self.set_list, 1)
        self.empty = W.QLabel("Loading available sets…")
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)
        self.availability = W.QLabel()
        self.availability.setWordWrap(True)
        layout.addWidget(self.availability)
        self.refresh = W.QPushButton("Refresh set list")
        self.refresh.clicked.connect(self._discover)
        layout.addWidget(self.refresh)
        self.pages.addWidget(page)

    def _build_options(self):
        scroll = W.QScrollArea()
        scroll.setWidgetResizable(True)
        content = W.QWidget()
        layout = W.QVBoxLayout(content)
        self.preset = W.QComboBox()
        self.preset.addItems(["Set Cube", "One of Each", "Custom"])
        self.preset.setAccessibleName("Collection preset")
        self.preset.currentTextChanged.connect(self._preset_changed)
        layout.addWidget(self.preset)
        self.description = W.QLabel()
        self.description.setWordWrap(True)
        self.description.setToolTip(
            "Individual card changes stay in place until you reset them in Review cards."
        )
        layout.addWidget(self.description)
        grid = W.QGridLayout()
        grid.setHorizontalSpacing(12)
        for column, text in enumerate(
            ("Rarity", "Unique cards", "Copies per card", "Total cards")
        ):
            grid.addWidget(W.QLabel(text), 0, column)
        self.spins, self.count_labels, self.total_labels, self.rarity_labels = (
            {},
            {},
            {},
            {},
        )
        self.step_controls = {}
        for row, value in enumerate(RARITIES, 1):
            label = self.rarity_labels[value] = W.QLabel(
                f"{value.title()} ({dict(common='C', uncommon='U', rare='R', mythic='M', special='S', bonus='B', other='O')[value]})"
            )
            grid.addWidget(label, row, 0)
            count = self.count_labels[value] = W.QLabel("0")
            grid.addWidget(count, row, 1)
            spin = self.spins[value] = W.QSpinBox()
            spin.setRange(0, 999)
            spin.setMaximumWidth(90)
            spin.setButtonSymbols(W.QAbstractSpinBox.ButtonSymbols.NoButtons)
            spin.setValue(self.settings.quantities[value])
            spin.setAccessibleName(f"{value.title()} copies per card")
            spin.setToolTip(
                "Copies of each card. Set to zero to leave this rarity out. Individual review changes take priority."
            )
            label.setBuddy(spin)
            spin.valueChanged.connect(self._quantities_changed)
            control = self.step_controls[value] = W.QWidget()
            step_row = W.QHBoxLayout(control)
            step_row.setContentsMargins(0, 0, 0, 0)
            step_row.setSpacing(4)
            minus, plus = W.QToolButton(), W.QToolButton()
            for button, text, direction in (
                (minus, "−", "Decrease"),
                (plus, "+", "Increase"),
            ):
                button.setText(text)
                button.setFixedWidth(30)
                button.setStyleSheet("QToolButton { padding: 0; }")
                button.setAccessibleName(f"{direction} {value} copies per card")
                button.setToolTip(f"{direction} {value} copies per card")
            minus.clicked.connect(spin.stepDown)
            plus.clicked.connect(spin.stepUp)
            step_row.addWidget(minus)
            step_row.addWidget(spin)
            step_row.addWidget(plus)
            step_row.addStretch()
            grid.addWidget(control, row, 2)
            total = self.total_labels[value] = W.QLabel("0")
            grid.addWidget(total, row, 3)
        layout.addLayout(grid)
        self.advanced_toggle = W.QToolButton()
        self.advanced_toggle.setText("Additional options")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setToolButtonStyle(
            C.Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.advanced_toggle.setArrowType(C.Qt.ArrowType.RightArrow)
        layout.addWidget(self.advanced_toggle)
        self.advanced = W.QWidget()
        extra = W.QVBoxLayout(self.advanced)
        self.options = {}
        for key, text in [
            ("basic_lands", "Include basic lands"),
            ("tokens", "Include tokens and emblems"),
            ("alternate_printings", "Include every artwork and special version"),
        ]:
            box = self.options[key] = W.QCheckBox(text)
            box.setToolTip(text)
            box.toggled.connect(self._options_changed)
            extra.addWidget(box)
        self.related = W.QListWidget()
        self.related.setMaximumHeight(120)
        self.related.setAccessibleName("Select related bonus sheets and token sets")
        self.related.itemChanged.connect(self._related_changed)
        extra.addWidget(
            W.QLabel("Related cards (only confirmed set relationships are listed):")
        )
        extra.addWidget(self.related)
        self.related_hint = W.QLabel(
            "Normally, one version of each card is included, including each basic land name. Including every artwork adds more versions. Tokens follow rarity quantities; unknown rarities appear as Other. Choose a related token set above when available."
        )
        self.related_hint.setWordWrap(True)
        extra.addWidget(self.related_hint)
        self.advanced.hide()
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        layout.addWidget(self.advanced)
        self.data_notice = W.QLabel()
        self.data_notice.setWordWrap(True)
        self.data_notice.setProperty("role", "warning")
        layout.addWidget(self.data_notice)
        self.partial = W.QCheckBox("Print the available cards only")
        self.partial.setToolTip(
            "Refresh the set data to check for missing cards before generating a complete collection."
        )
        self.partial.toggled.connect(self._update)
        layout.addWidget(self.partial)
        self.download = W.QPushButton("Download / refresh set data")
        self.download.clicked.connect(self._download)
        layout.addWidget(self.download)
        self.review_button = W.QPushButton("Review cards")
        self.review_button.setToolTip(
            "Optional: inspect, exclude, or change copies of individual cards"
        )
        self.review_button.clicked.connect(lambda: self._page(2))
        layout.addStretch()
        scroll.setWidget(content)
        self.pages.addWidget(scroll)
        self._preset_changed("Set Cube")

    def _build_review(self):
        page = W.QWidget()
        layout = W.QVBoxLayout(page)
        hint = W.QLabel(
            "Double-click a card’s copies, or select it and press F2, to change the quantity. Zero excludes it. Individual changes override rarity defaults. This review is optional."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        row = W.QHBoxLayout()
        self.card_search = W.QLineEdit()
        self.card_search.setPlaceholderText("Find a card")
        self.card_search.setAccessibleName("Find a card to review")
        self.card_search.textChanged.connect(self._filter_review)
        row.addWidget(self.card_search)
        self.rarity_filter = W.QComboBox()
        self.rarity_filter.addItems(["All rarities"] + [r.title() for r in RARITIES])
        self.rarity_filter.setAccessibleName("Filter review by rarity")
        self.rarity_filter.currentIndexChanged.connect(self._filter_review)
        row.addWidget(self.rarity_filter)
        layout.addLayout(row)
        self.tree = W.QTreeWidget()
        self.tree.setHeaderLabels(["Card / rarity", "Artwork", "Copies"])
        self.tree.setColumnWidth(0, 330)
        self.tree.setColumnWidth(1, 170)
        self.tree.setItemDelegate(_CopiesDelegate(self.tree))
        self.tree.installEventFilter(self)
        self.tree.itemChanged.connect(self._review_changed)
        self.tree.setAccessibleName(
            "Cards grouped by rarity; edit copies to exclude or override"
        )
        self.tree.setStyleSheet(
            f"QTreeWidget {{ background: {COLORS['canvas']}; color: {COLORS['text']}; }} QTreeWidget::item:selected {{ background: {COLORS['surface_selected']}; }}"
        )
        self.tree.currentItemChanged.connect(self._preview)
        layout.addWidget(self.tree, 1)
        self.preview = W.QLabel("Select a card to see cached artwork.")
        self.preview.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
        self.preview.setMaximumHeight(125)
        layout.addWidget(self.preview)
        reset = W.QPushButton("Reset individual changes")
        reset.clicked.connect(self._reset_overrides)
        layout.addWidget(reset)
        self.pages.addWidget(page)

    def _start(self, fn, callback, message):
        if self.worker:
            return
        self.status.setText(message)
        self.status.show()
        self.pages.setEnabled(False)
        self.review_button.setEnabled(False)
        self.back.setEnabled(False)
        self.next.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self._callback = callback
        self.worker = _Work(fn, self)
        self.worker.progress.connect(self._progress)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    @C.pyqtSlot(str, int, int)
    def _progress(self, text, value, maximum):
        self.status.setText(text)
        self.status.show()
        self.progress.setRange(0, maximum)
        self.progress.setValue(value)

    @C.pyqtSlot()
    def _finished(self):
        worker, callback = self.worker, self._callback
        self.worker = None
        self.progress.hide()
        self.pages.setEnabled(True)
        self.cancel.setText("Cancel")
        self.cancel.setEnabled(True)
        if worker.error:
            self.status.setText(
                str(worker.error)
                if isinstance(worker.error, SetPrintError)
                else "We couldn’t finish this step. Check your connection and catalog, then try again. Your existing projects are safe."
            )
        elif worker.cancelled.is_set() and not (
            isinstance(worker.result, dict) and worker.result.get("id")
        ):
            self.status.setText(
                "Stopped safely. Prepared artwork is cached; you can try again."
            )
        else:
            self.status.clear()
            callback(worker.result)
        worker.deleteLater()
        self._update()

    def _discover(self):
        def read(worker):
            defaults = library._initial_project_dict(None)
            sets, notice = discover_sets(self.service, online=CFG.OnlineMode)
            return sets, notice, defaults, self.service.get_artwork_preferences()

        def ready(result):
            self.sets, notice, self.defaults, self._rules = result
            self.availability.setText(
                notice
                or "Choose a set. Counts show unique cards available in your local catalog."
            )
            self._filter()

        self._start(read, ready, "Finding sets in your catalog")

    def _filter(self):
        previous = self.selected.code if self.selected else None
        self.set_list.clear()
        matches = filter_sets(self.sets, self.search.text())
        for info in matches:
            item = W.QListWidgetItem(
                f"{info.code.upper()}  ·  {info.name}\n{info.released_at or 'Release date unavailable'}  ·  {info.available:,} unique cards available locally"
            )
            item.setData(C.Qt.ItemDataRole.UserRole, info)
            if info.code in self._symbols:
                item.setIcon(self._symbols[info.code])
            else:
                badge = G.QPixmap(48, 48)
                badge.fill(G.QColor(COLORS["surface_raised"]))
                painter = G.QPainter(badge)
                painter.setPen(G.QColor(COLORS["text_secondary"]))
                painter.drawText(
                    badge.rect(), C.Qt.AlignmentFlag.AlignCenter, info.code.upper()
                )
                painter.end()
                item.setIcon(G.QIcon(badge))
            item.setSizeHint(C.QSize(0, 66))
            self.set_list.addItem(item)
            if info.code == previous:
                self.set_list.setCurrentItem(item)
        self.empty.setText(
            ""
            if matches
            else "No matching sets. Try another name or code, or refresh the set list. Download the card catalog in Data Management if it is empty."
        )
        self._update()
        self.symbol_timer.start()

    def _visible_symbols(self):
        if self._symbols_busy or not self.isVisible():
            return
        items = []
        viewport = self.set_list.viewport().rect()
        for row in range(self.set_list.count()):
            item = self.set_list.item(row)
            info = item.data(C.Qt.ItemDataRole.UserRole)
            if (
                info.symbol_url
                and info.code not in self._symbol_requests
                and self.set_list.visualItemRect(item).intersects(viewport)
            ):
                self._symbol_requests.add(info.code)
                items.append((info.code, info.symbol_url))
        if items:
            self._symbols_busy = True
            self._symbol_task = _Symbols(items, self._symbol_ready, self._symbols_done)
            C.QThreadPool.globalInstance().start(self._symbol_task)

    @C.pyqtSlot(str, bytes)
    def _symbol_ready(self, code, data):
        pixmap = G.QPixmap()
        if not pixmap.loadFromData(data):
            return
        painter = G.QPainter(pixmap)
        painter.setCompositionMode(G.QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), G.QColor(COLORS["text"]))
        painter.end()
        self._symbols[code] = G.QIcon(pixmap)
        for row in range(self.set_list.count()):
            item = self.set_list.item(row)
            if item.data(C.Qt.ItemDataRole.UserRole).code == code:
                item.setIcon(self._symbols[code])

    @C.pyqtSlot()
    def _symbols_done(self):
        self._symbols_busy = False
        self._symbol_task = None
        self.symbol_timer.start()

    def _select(self, item, previous=None):
        for candidate, selected in ((previous, False), (item, True)):
            if candidate is not None:
                info = candidate.data(C.Qt.ItemDataRole.UserRole)
                candidate.setText(
                    f"{'Selected · ' if selected else ''}{info.code.upper()} · {info.name}\n"
                    f"{info.released_at or 'Release date unavailable'} · {info.available:,} unique cards available locally"
                )
        self.selected = item.data(C.Qt.ItemDataRole.UserRole) if item else None
        self._update()

    def _advance(self):
        if self.pages.currentIndex() == 0:
            if self.selected:
                self.settings.overrides.clear()
                self.partial.setChecked(False)
                blocker = C.QSignalBlocker(self.related)
                self.related.clear()
                for info in self.sets:
                    if info.parent == self.selected.code:
                        item = W.QListWidgetItem(f"{info.name} ({info.code.upper()})")
                        item.setData(C.Qt.ItemDataRole.UserRole, info.code)
                        item.setFlags(item.flags() | C.Qt.ItemFlag.ItemIsUserCheckable)
                        item.setCheckState(C.Qt.CheckState.Unchecked)
                        self.related.addItem(item)
                self.related.setVisible(self.related.count() > 0)
                if not self.related.count():
                    self.related_hint.setText(
                        "No confirmed related sets are listed. Refresh the set list online to check for bonus sheets and token sets. Basic lands and artwork versions apply to the selected set."
                    )
                else:
                    self.related_hint.setText(
                        "Select related sets above to include bonus cards or tokens. Enable tokens to include token cards. Cards shared across sets are included once; including every artwork adds more versions."
                    )
                del blocker
                self.settings.related_codes = []
                self._load_cards(lambda: self._page(1))
        else:
            self._generate()

    def _load_cards(self, then=lambda: None, refresh=False):
        codes = [self.selected.code] + self.settings.related_codes

        def read(worker):
            if refresh:
                self._cache = {
                    key: value
                    for key, value in self._cache.items()
                    if not set(key).intersection(codes)
                }
                for code in codes:
                    if not download_set_data(
                        self.service,
                        code,
                        cancelled=worker.cancelled.is_set,
                        progress=lambda text: worker.progress.emit(text, 0, 0),
                    ):
                        worker.cancelled.set()
                        return None
                self._complete_codes.update(codes)
            key = tuple(codes)
            payloads = self._cache.get(key) if not refresh else None
            if payloads is None:
                payloads = load_set_cards(self.service, codes)
                self._cache[key] = payloads
            ids = [p["id"] for p in payloads if p.get("id")]
            images = self.service.database.get_image_records_for_cards(ids)
            for key, record in list(images.items()):
                if worker.cancelled.is_set():
                    return None
                if record.asset_id and (
                    not record.path or not os.path.exists(record.path)
                ):
                    path = self.service.get_image_path(*key)
                    if path:
                        images[key] = replace(record, path=path)
            favorites = set_artwork_favorites(self.service, payloads)
            statuses = {
                p["id"]: self._calculate_art_status(p, images)
                for p in payloads
                if p.get("id")
            }
            return payloads, images, favorites, statuses

        def ready(result):
            self.payloads, self._images, self._favorites, self._art_statuses = result
            self._options_changed()
            then()
            if not self.payloads:
                self.status.setText(
                    "This set has no local card data. Download its data to continue, or choose another set."
                )

        self._start(read, ready, "Preparing available cards")

    def _download(self):
        self._load_cards(refresh=True)

    def _related_changed(self, *_):
        self.settings.related_codes = [
            self.related.item(i).data(C.Qt.ItemDataRole.UserRole)
            for i in range(self.related.count())
            if self.related.item(i).checkState() == C.Qt.CheckState.Checked
        ]
        if self.selected:
            self._load_cards()

    def _toggle_advanced(self, expanded):
        self.advanced.setVisible(expanded)
        self.advanced_toggle.setArrowType(
            C.Qt.ArrowType.DownArrow if expanded else C.Qt.ArrowType.RightArrow
        )

    def _options_changed(self):
        for key, box in self.options.items():
            setattr(self.settings, key, box.isChecked())
        self.cards = eligible_cards(
            self.payloads, self.settings, rules=self._rules, favorites=self._favorites
        )
        self._update()

    def _preset_changed(self, name):
        self.settings.apply_preset(name)
        for key, spin in self.spins.items():
            blocker = C.QSignalBlocker(spin)
            spin.setValue(self.settings.quantities[key])
            del blocker
        self.description.setText(
            {
                "Set Cube": "Great for building a reusable collection for Draft and Sealed games.",
                "One of Each": "Explore a set with a single copy of every eligible card.",
                "Custom": "Choose how many copies of each rarity you want.",
            }[name]
        )
        if hasattr(self, "summary"):
            self._update()

    def _quantities_changed(self):
        self.settings.quantities = {
            key: spin.value() for key, spin in self.spins.items()
        }
        blocker = C.QSignalBlocker(self.preset)
        self.preset.setCurrentText("Custom")
        del blocker
        self.settings.preset = "Custom"
        self.description.setText(
            "Custom quantities. Individual card changes stay in place until reset."
        )
        self._update()

    def _page(self, index):
        self.pages.setCurrentIndex(index)
        self.steps.setText(
            [
                "1 · Choose a set",
                "2 · Choose what to print",
                "3 · Review cards (optional)",
            ][index]
        )
        if index == 2:
            self._populate_review()
        self._update()

    def _art_status(self, card):
        return self._art_statuses.get(card["id"], "Missing artwork")

    @staticmethod
    def _calculate_art_status(card, images):
        record = images.get((card["id"], "default"))
        back = images.get((card["id"], "back"))
        cached = bool(record and record.path and os.path.exists(record.path))
        if card_layouts.has_printed_back(card):
            cached = cached and bool(back and back.path and os.path.exists(back.path))
            available = len(deck_import.extract_face_image_urls(card)) >= 2
        else:
            available = bool(deck_import.extract_image_url(card))
        return (
            "Ready (cached)"
            if cached
            else ("Download needed" if available else "Missing artwork")
        )

    def _update(self, *_):
        if not hasattr(self, "next"):
            return
        index = self.pages.currentIndex()
        busy = self.worker is not None
        self.status.setVisible(bool(self.status.text()))
        self.review_button.setVisible(index == 1)
        self.review_button.setEnabled(not busy)
        self.back.setEnabled(index > 0 and not busy)
        self.next.setText(
            "Choose what to print" if index == 0 else "Generate Print Project"
        )
        if not self.selected:
            self.summary.setText("Choose a set to begin.")
            self.next.setEnabled(False)
            return
        if index == 0:
            self.summary.setText(
                f"{self.selected.name}\n{self.selected.available:,} unique cards available locally · {self.selected.code.upper()}"
            )
            self.next.setEnabled(not busy)
            return
        unique, total = totals(self.cards, self.settings)
        counts = rarity_counts(self.cards)
        physical = {r: 0 for r in RARITIES}
        statuses = []
        for card, count in inventory(self.cards, self.settings):
            physical[rarity(card)] += count
            if count:
                statuses.append(self._art_status(card))
        for r in RARITIES:
            self.count_labels[r].setText(str(counts[r]))
            self.total_labels[r].setText(str(physical[r]))
            for widget in (
                self.rarity_labels[r],
                self.count_labels[r],
                self.total_labels[r],
                self.step_controls[r],
            ):
                widget.setVisible(r in RARITIES[:4] or counts[r] > 0)
        from mtg_print.geometry import sheet_capacity

        state = ProjectState.from_dict(self.defaults)
        columns, rows = sheet_capacity(state)
        capacity = columns * rows
        sheets = (total + capacity - 1) // capacity if capacity else 0
        local_ids = {
            p.get("collector_number") or p.get("id")
            for p in self.payloads
            if p.get("set") == self.selected.code
        }
        # Directory counts include print versions, not just Oracle identities.
        uncertain = self.selected.code not in self._complete_codes and (
            self.selected.expected is None or len(local_ids) < self.selected.expected
        )
        for code in self.settings.related_codes:
            related = next((s for s in self.sets if s.code == code), None)
            available = {
                p.get("collector_number") or p.get("id")
                for p in self.payloads
                if p.get("set") == code
            }
            uncertain |= code not in self._complete_codes and (
                related is None
                or related.expected is None
                or len(available) < related.expected
            )
        missing = statuses.count("Missing artwork")
        downloads = statuses.count("Download needed")
        incomplete = sum(not p.get("id") or not p.get("name") for p in self.payloads)
        uncertain |= bool(incomplete)
        self.partial.setVisible(uncertain)
        warning = (
            "Set data may be incomplete. Refresh it to find missing cards, or print the available cards only."
            if uncertain
            else ""
        )
        if incomplete:
            warning += f" {incomplete} records are missing card details and cannot be included. Refresh the set data."
        if missing:
            warning += " Some card artwork is missing. Refresh set data, or use Review cards to exclude those cards before generating."
        self.data_notice.setText(warning)
        self.data_notice.setVisible(bool(warning))
        label = (
            "unique versions" if self.settings.alternate_printings else "unique cards"
        )
        self.summary.setText(
            f"Your Print Set · {self.selected.name}\n{unique:,} {label} · {total:,} physical cards · approximately {sheets:,} front sheets\n"
            f"{state.pagesize} · {state.orient.lower()} · {capacity} cards per sheet · backs need additional sides\n"
            f"Artwork: {downloads} to download · {missing} missing"
            + (" · Catalog needs review" if uncertain or incomplete else "")
        )
        self.next.setEnabled(
            not busy
            and total > 0
            and capacity > 0
            and not missing
            and (not uncertain or self.partial.isChecked())
        )

    def _populate_review(self):
        blocker = C.QSignalBlocker(self.tree)
        self.tree.clear()
        groups = {r: W.QTreeWidgetItem(self.tree, [r.title()]) for r in RARITIES}
        for card, count in inventory(self.cards, self.settings):
            item = W.QTreeWidgetItem(
                groups[rarity(card)],
                [
                    f"{card['name']} · {card.get('collector_number', '')}",
                    self._art_status(card),
                ],
            )
            item.setData(0, C.Qt.ItemDataRole.UserRole, card)
            item.setFlags(item.flags() | C.Qt.ItemFlag.ItemIsEditable)
            item.setData(2, C.Qt.ItemDataRole.EditRole, count)
            item.setToolTip(
                2, "Double-click or press F2 to change copies. Zero excludes this card."
            )
        self.tree.expandAll()
        del blocker
        self._filter_review()

    def _review_changed(self, item, column):
        card = item.data(0, C.Qt.ItemDataRole.UserRole)
        if column == 2 and card:
            self._override(card["id"], int(item.data(2, C.Qt.ItemDataRole.EditRole)))

    def eventFilter(self, watched, event):
        if (
            watched is self.tree
            and event.type() == C.QEvent.Type.KeyPress
            and event.key() == C.Qt.Key.Key_F2
        ):
            item = self.tree.currentItem()
            if item and item.data(0, C.Qt.ItemDataRole.UserRole):
                self.tree.setCurrentItem(item, 2)
                self.tree.editItem(item, 2)
                return True
        return super().eventFilter(watched, event)

    def _override(self, key, value):
        self.settings.overrides[key] = value
        self._update()

    def _reset_overrides(self):
        self.settings.overrides.clear()
        self._populate_review()
        self._update()

    def _filter_review(self):
        query = self.card_search.text().casefold()
        selected = self.rarity_filter.currentText().casefold()
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            visible = 0
            for j in range(group.childCount()):
                child = group.child(j)
                show = query in child.text(0).casefold() and (
                    selected == "all rarities" or selected == group.text(0).casefold()
                )
                child.setHidden(not show)
                visible += show
            group.setHidden(not visible)

    def _preview(self, item, previous=None):
        self.preview.clear()
        card = item.data(0, C.Qt.ItemDataRole.UserRole) if item else None
        record = self._images.get((card["id"], "default")) if card else None
        if record and record.path and os.path.exists(record.path):
            reader = G.QImageReader(record.path)
            reader.setScaledSize(C.QSize(86, 120))
            self.preview.setPixmap(G.QPixmap.fromImage(reader.read()))
        else:
            self.preview.setText(
                "Artwork will be downloaded during generation."
                if card
                else "Select a card to preview cached artwork."
            )

    def _generate(self):
        self.settings.available_only = (
            self.partial.isVisible() and self.partial.isChecked()
        )

        def work(worker):
            return generate_project(
                self.service,
                self.selected,
                self.cards,
                self.settings,
                cancelled=worker.cancelled.is_set,
                progress=worker.progress.emit,
                defaults=self.defaults,
            )

        def ready(entry):
            self.project_entry = entry
            self.accept()

        self._start(work, ready, "Preparing your cards")

    def reject(self):
        if self._symbol_task:
            self._symbol_task.cancelled.set()
        if self.worker:
            self.worker.cancelled.set()
            self.cancel.setText("Stopping…")
            self.cancel.setEnabled(False)
            self.status.setText(
                "Stopping after the current request. Your existing projects are safe."
            )
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)
