"""Image-first commander discovery over local rules and explicit EDHREC themes."""

import json
from datetime import datetime

from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_core.commander_discovery import search_commanders
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_core.edhrec_discovery import DiscoveryStore
from mtg_core.paths import core_data_root

from .canvas import CardCanvas
from .commander_selection import commanders, select_commander
from .organization import card_facts, update_candidate_quantities
from .search import SearchController


class DiscoverySearch:
    """Adapt discovery to the shared debounce/cache/cancellation controller."""

    def __init__(self, service):
        self.service = service
        self.store = DiscoveryStore(core_data_root() / "recommendations" / "edhrec-discovery.sqlite3")

    def search_editor_cards(self, query, *, should_cancel=None):
        return search_commanders(self.service, json.loads(query), self.store, should_cancel=should_cancel)


class DiscoveryCanvas(CardCanvas):
    def __init__(self, document, thumbnails, parent):
        super().__init__(document, thumbnails, parent, search=True)
        self.theme_name = ""

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.theme_name:
            return
        painter = G.QPainter(self.viewport())
        offset = self.verticalScrollBar().value()
        painter.translate(0, -offset)
        visible = C.QRect(0, offset, self.viewport().width(), self.viewport().height())
        for entry, rect, _ in self.items:
            if not rect.intersects(visible):
                continue
            badge = C.QRect(rect.x()+4, rect.y()+4, rect.width()-8, 24)
            painter.fillRect(badge, G.QColor("#20352f"))
            painter.setPen(G.QColor("white"))
            painter.drawText(badge, C.Qt.AlignmentFlag.AlignCenter,
                             painter.fontMetrics().elidedText(self.theme_name, C.Qt.TextElideMode.ElideRight, badge.width()-6))
        painter.end()


class CommanderDiscovery(W.QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.rows = {}
        self.limit = 200
        self.loaded_query = None
        self.result_status = ""
        self.context = None
        self.theme_slug = ""
        self.theme_catalog = []
        self.controller = SearchController(DiscoverySearch(editor.service), self)
        layout = W.QVBoxLayout(self)
        theme_row = W.QHBoxLayout()
        label = W.QLabel("Theme")
        label.setProperty("role", "title")
        theme_row.addWidget(label)
        self.theme = W.QComboBox()
        self.theme.setEditable(True)
        self.theme.setInsertPolicy(W.QComboBox.InsertPolicy.NoInsert)
        self.theme.addItem("All themes / local discovery", "")
        self.theme.setMinimumWidth(220)
        self.theme.setToolTip("Type to find an imported theme, then choose a match.")
        self.theme.completer().setFilterMode(C.Qt.MatchFlag.MatchContains)
        self.theme.completer().setCaseSensitivity(C.Qt.CaseSensitivity.CaseInsensitive)
        self.theme.completer().setCompletionMode(W.QCompleter.CompletionMode.PopupCompletion)
        theme_row.addWidget(self.theme, 1)
        refresh = W.QPushButton("Refresh local data")
        refresh.clicked.connect(lambda: self.search(refresh=True))
        theme_row.addWidget(refresh)
        layout.addLayout(theme_row)
        self.theme_status = W.QLabel("EDHREC themes load from the local snapshot. No collection runs in the editor.")
        self.theme_status.setWordWrap(True)
        layout.addWidget(self.theme_status)
        self.import_themes_button = W.QPushButton("Import cached themes")
        self.import_themes_button.setToolTip("Build the theme index from previously collected EDHREC responses. No downloads.")
        self.import_themes_button.clicked.connect(self.import_themes)
        layout.addWidget(self.import_themes_button, 0, C.Qt.AlignmentFlag.AlignLeft)
        fields = W.QHBoxLayout()
        self.name = W.QLineEdit()
        self.name.setPlaceholderText("Commander name")
        self.type = W.QLineEdit()
        self.type.setPlaceholderText("Type / creature type")
        self.text = W.QLineEdit()
        self.text.setPlaceholderText("Oracle text contains…")
        for field in (self.name, self.type, self.text):
            field.setClearButtonEnabled(True)
            fields.addWidget(field, 1)
            field.textChanged.connect(self.filters_changed)
        layout.addLayout(fields)
        options = W.QHBoxLayout()
        self.capability = W.QComboBox()
        for label, value in [("Any capability", ""), ("Partner / Partner with", "partner"),
                             ("Friends Forever", "friends forever"), ("Choose a Background", "choose a background"),
                             ("Background cards", "background"), ("Doctor's companion", "doctor's companion")]:
            self.capability.addItem(label, value)
        options.addWidget(self.capability)
        self.legal = W.QCheckBox("Locally legal in Commander")
        self.legal.setChecked(True)
        options.addWidget(self.legal)
        options.addStretch()
        layout.addLayout(options)
        pairing = W.QHBoxLayout()
        self.partner = W.QCheckBox("Compatible with current commander")
        self.partner.setToolTip("Use existing pairing rules. With a theme selected, require explicit membership for this exact pair.")
        pairing.addWidget(self.partner)
        pairing.addStretch()
        self.cancel = W.QPushButton("Cancel")
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.controller.cancel)
        pairing.addWidget(self.cancel)
        layout.addLayout(pairing)
        self.status = W.QLabel("Browse local commanders, or choose an imported theme.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.canvas = DiscoveryCanvas(DeckDocument(), editor.thumbnails, self)
        self.canvas.search_action_text = "Set commander"
        self.canvas.card_width = 190
        self.canvas.setAccessibleName("Commander discovery results")
        self.canvas.setToolTip("Select for theme evidence. Double-click to set as commander.")
        self.canvas.quantityRequested.connect(self.set_commander)
        self.canvas.selectionChanged.connect(self.selection_changed)
        self.canvas.menuRequested.connect(self.card_menu)
        layout.addWidget(self.canvas, 1)
        self.details = W.QLabel("Select a card to see its theme evidence.")
        self.details.setTextFormat(C.Qt.TextFormat.PlainText)
        self.details.setWordWrap(True)
        self.details.setMaximumHeight(100)
        layout.addWidget(self.details)
        actions = W.QHBoxLayout()
        self.set_button = W.QPushButton("Set as Commander")
        self.set_button.setProperty("buttonRole", "primary")
        self.set_button.clicked.connect(lambda: self.set_commander())
        actions.addWidget(self.set_button)
        self.second_button = W.QPushButton("Add as Second Commander")
        self.second_button.clicked.connect(lambda: self.set_commander(second=True))
        actions.addWidget(self.second_button)
        actions.addStretch()
        layout.addLayout(actions)
        secondary = W.QHBoxLayout()
        checks = W.QPushButton("Commander / deck checks")
        checks.clicked.connect(editor.commander_checks)
        secondary.addWidget(checks)
        secondary.addStretch()
        self.more = W.QPushButton("Show more")
        self.more.clicked.connect(self.show_more)
        self.more.hide()
        secondary.addWidget(self.more)
        layout.addLayout(secondary)
        self.theme.currentIndexChanged.connect(self.theme_selected)
        self.theme.activated.connect(self.theme_selected)
        self.theme.completer().activated[str].connect(self.complete_theme)
        self.capability.currentIndexChanged.connect(self.filters_changed)
        self.partner.toggled.connect(self.filters_changed)
        self.legal.toggled.connect(self.filters_changed)
        self.controller.resultsReady.connect(self.completed)
        self.controller.statusChanged.connect(self.status.setText)
        self.controller.busyChanged.connect(self.cancel.setEnabled)
        self.selection_changed()

    def filters(self):
        selected = commanders(self.editor.document)
        return dict(theme=self.theme_slug, name=self.name.text(), type=self.type.text(),
                    text=self.text.text(), capability=self.capability.currentData(),
                    legal_only=self.legal.isChecked(), limit=self.limit,
                    partner_card_id=selected[0].card_id if self.partner.isChecked() and len(selected) == 1 else None)

    def query(self):
        return json.dumps(self.filters(), sort_keys=True)

    def theme_selected(self, index):
        if index < 0:
            return
        slug = self.theme.itemData(index) or ""
        if slug != self.theme_slug:
            self.theme_slug = slug
            self.filters_changed()

    def complete_theme(self, text):
        index = self.theme.findText(text, C.Qt.MatchFlag.MatchFixedString)
        if index >= 0:
            self.theme.setCurrentIndex(index)
            self.theme_selected(index)

    def import_themes(self):
        from threading import Event
        from mtg_core.edhrec_discovery_ingest import import_cached_discovery

        if self.editor.closing or self.editor.task is not None:
            return
        self.controller.cancel()
        self.loaded_query = None
        cancelled = Event()
        progress = W.QProgressDialog("Importing cached EDHREC themes…", "Cancel", 0, 0, self.editor)
        progress.canceled.connect(cancelled.set)
        self.editor.task_runner.failed.connect(progress.close)
        self.editor.task_runner.failed.connect(progress.deleteLater)
        progress.show()

        def imported(result):
            progress.close()
            progress.deleteLater()
            # Replace rather than mutate a cache an exiting search worker may
            # still hold. All subsequent searches see the newly published data.
            from .search import SearchCache

            self.controller.cache = SearchCache()
            if result["status"] == "cancelled":
                self.editor.statusBar().showMessage("Theme import cancelled. The previous snapshot is preserved.")
            else:
                self.editor.statusBar().showMessage(
                    f"Imported {result['themes']} themes from {result['cohorts']} commander cohorts.")
            self.search(refresh=True)

        self.editor.run_task(lambda: import_cached_discovery(should_cancel=cancelled.is_set), imported)
        self.editor.statusBar().showMessage("Importing cached EDHREC themes…")

    def filters_changed(self, *_):
        self.limit = 200
        self.loaded_query = None
        self.rows.clear()
        self.canvas.document.deck.entries.clear()
        self.more.hide()
        self.canvas.refresh()
        self.selection_changed()
        if self.isVisible():
            self.controller.change_query(self.query())

    def search(self, *, refresh=False):
        if self.isVisible() and not self.editor.closing:
            self.controller.search(self.query(), refresh=refresh)

    def completed(self, query, snapshot, error):
        if not self.isVisible() or self.editor.closing or query != self.query():
            return
        if error:
            self.status.setText("Commander discovery failed. Refresh local data to retry.")
            self.status.setToolTip(error)
            return
        self.loaded_query = query
        catalog = [(theme["slug"], theme["name"]) for theme in snapshot["themes"]]
        if catalog != self.theme_catalog:
            typed = self.theme.currentText()
            editing = typed != self.theme.itemText(self.theme.currentIndex())
            with C.QSignalBlocker(self.theme):
                self.theme.clear()
                self.theme.addItem("All themes / local discovery", "")
                for slug, name in catalog:
                    self.theme.addItem(name, slug)
                self.theme.setCurrentIndex(max(0, self.theme.findData(self.theme_slug)))
                if editing:
                    self.theme.setEditText(typed)
            self.theme_catalog = catalog
        self.theme.setEnabled(bool(snapshot["themes"]))
        self.theme_status.setText(snapshot["status"])
        if self.theme_slug and self.theme.findData(self.theme_slug) < 0:
            # A removed/unavailable snapshot must not leave a hidden theme filter
            # blocking the local fallback.
            self.theme_slug = ""
            self.filters_changed()
            return
        self.canvas.theme_name = dict(catalog).get(self.theme_slug, "")
        self.rows = {}
        entries = []
        for row in snapshot["results"]:
            card = row["card"]
            entry = DeckEntry(card.card_id, card.name, card_id=card.card_id, oracle_id=card.oracle_id,
                              set_code=card.set_code, collector_number=card.collector_number, pre_cropped=True,
                              extras={"facts": card_facts(card.payload or {})})
            self.rows[entry.entry_id] = dict(row, entry=entry)
            entries.append(entry)
        self.canvas.document.deck.entries = entries
        update_candidate_quantities(self.editor.document, self.canvas)
        self.canvas.refresh()
        self.status.setToolTip("")
        if entries:
            if snapshot["more"]:
                suffix = "Narrow the filters to see other matches." if self.limit >= 2000 else "More matches are available."
            else:
                suffix = "Select a card to inspect or set as commander."
            self.status.setText(f"{len(entries)} commanders / Backgrounds. {suffix}")
        else:
            self.status.setText("No commanders match these filters. Try broader text or a different theme.")
        self.more.setVisible(snapshot["more"] and self.limit < 2000)
        self.result_status = self.status.text()
        self.selection_changed()

    def selected(self):
        return next((self.rows[key] for key in self.canvas.selected if key in self.rows), None)

    def selection_changed(self):
        row = self.selected()
        self.set_button.setEnabled(row is not None)
        self.second_button.setEnabled(row is not None and len(commanders(self.editor.document)) == 1)
        if not row:
            self.details.setText("Select a card to see its theme evidence.")
            return
        entry = row["entry"]
        lines = [entry.name]
        for association in row["associations"][:3]:
            stamp = datetime.fromtimestamp(association["imported"]).strftime("%Y-%m-%d")
            lines.append(f"{self.canvas.theme_name}: {association['num_decks']} of {association['sample']} decks "
                         f"in {association['name']} cohort (cached {stamp})")
        self.details.setText("\n".join(lines))
        if len(row["associations"]) > 3:
            lines.append(f"Plus {len(row['associations']) - 3} other cached cohorts.")
        self.details.setToolTip("\n".join(lines + ["https://edhrec.com/commanders/" + a["slug"] for a in row["associations"][:3]]))

    def set_commander(self, entry_id=None, _delta=1, *, second=False):
        row = self.rows.get(entry_id) if entry_id else self.selected()
        if row:
            self.canvas.preview.hide()
            select_commander(self.editor, row["entry"], second=second)

    def card_menu(self, entry_id, position):
        menu = W.QMenu(self)
        menu.addAction("Set as Commander", lambda: self.set_commander(entry_id))
        second = menu.addAction("Add as Second Commander", lambda: self.set_commander(entry_id, second=True))
        second.setEnabled(len(commanders(self.editor.document)) == 1)
        menu.exec(position)

    def show_more(self):
        self.limit = min(2000, self.limit + 200)
        self.search()

    def deck_changed(self):
        selected = commanders(self.editor.document)
        context = (self.editor.document.deck.deck_id, tuple((e.entry_id, e.card_id) for e in selected))
        changed = context != self.context
        self.context = context
        self.partner.setEnabled(len(selected) == 1 and bool(selected[0].card_id))
        if not self.partner.isEnabled():
            self.partner.setChecked(False)
        update_candidate_quantities(self.editor.document, self.canvas)
        self.selection_changed()
        if changed and self.partner.isChecked():
            self.filters_changed()

    def showEvent(self, event):
        super().showEvent(event)
        self.deck_changed()
        if self.loaded_query != self.query():
            self.search()
        else:
            self.status.setText(self.result_status)

    def hideEvent(self, event):
        self.controller.cancel()
        super().hideEvent(event)
