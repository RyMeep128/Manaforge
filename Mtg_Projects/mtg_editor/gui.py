from __future__ import annotations

import json
from pathlib import Path
import uuid

from PyQt6 import QtCore, QtGui, QtWidgets as W
from mtg_core.decks import DeckDocument, DeckEntry, DeckHistory, DeckStore
from mtg_core.paths import data_root
from mtg_core import get_default_card_service
from mtg_editor.card_views import Thumbnails
from mtg_editor.canvas import CardCanvas
from mtg_editor.organization import SECTIONS, GROUPS, SORTS, card_facts, assign, remove_category, move_entries
from mtg_core.decks import DeckCategory
from mtg_ui.theme import application_stylesheet
from copy import deepcopy
from dataclasses import replace
from mtg_core.categorization import classify, analyze_entries, apply_categories


class Task(QtCore.QThread):
    completed = QtCore.pyqtSignal(object, str)

    def __init__(self, work, parent=None):
        super().__init__(parent)
        self.work = work

    def run(self):
        try:
            self.completed.emit(self.work(), '')
        except Exception as exc:
            self.completed.emit(None, str(exc))


class SearchWorker(QtCore.QThread):
    completed = QtCore.pyqtSignal(str, object, str)

    def __init__(self, query, service, parent=None):
        super().__init__(parent)
        self.query, self.service = query, service

    def run(self):
        try:
            results = self.service.search_cards(self.query, {
                'scryfall_syntax': True, 'allow_remote': False, 'limit': 100})
            data = self.service.database.categorization_data([], [r.oracle_id for r in results])
            results = [replace(r, payload={**(r.payload or {}), '_category_evidence':
                classify(r.payload or {}, data['tags'].get(r.oracle_id, []))}) for r in results]
            self.completed.emit(self.query, results, '')
        except Exception as exc:
            self.completed.emit(self.query, [], str(exc))


class DeckTable(QtCore.QAbstractTableModel):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.document.deck.entries)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else 4

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role == QtCore.Qt.ItemDataRole.UserRole:
            return self.document.deck.entries[index.row()]
        if index.isValid() and role == QtCore.Qt.ItemDataRole.DisplayRole:
            entry = self.document.deck.entries[index.row()]
            return (entry.quantity, entry.name, entry.section, entry.set_code or '')[index.column()]

    def headerData(self, section, orientation, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if role == QtCore.Qt.ItemDataRole.DisplayRole and orientation == QtCore.Qt.Orientation.Horizontal:
            return ('Quantity', 'Card', 'Section', 'Set')[section]

    def refresh(self):
        self.beginResetModel()
        self.endResetModel()



class EditorWindow(W.QMainWindow):
    def __init__(self, service=None, root=None):
        super().__init__()
        self.service = service or get_default_card_service()
        self.root = Path(root) if root else data_root() / 'decks'
        self.store, self.path = DeckStore(), None
        self.document = DeckDocument()
        self.history = DeckHistory(self.document)
        self.saved = self.document.to_dict()
        self.worker = self.task = None
        self.thumbnails = Thumbnails(self.service, self)
        self.setStyleSheet(application_stylesheet())
        self.setWindowIcon(QtGui.QIcon(str(Path(__file__).resolve().parents[1] / 'mtg_proxy' / 'proxy.png')))
        self.resize(1280, 820)
        self.setMinimumSize(640, 360)
        self.autosave = QtCore.QTimer(self)
        self.autosave.setSingleShot(True)
        self.autosave.setInterval(2000)
        self.autosave.timeout.connect(self.save)
        self.search_timer = QtCore.QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(350)
        self.search_timer.timeout.connect(self.search)
        body = W.QWidget()
        layout = W.QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = W.QFrame()
        header.setProperty('role', 'toolbar')
        header.setSizePolicy(W.QSizePolicy.Policy.Expanding, W.QSizePolicy.Policy.Fixed)
        header_layout = W.QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        bar = W.QHBoxLayout()
        header_layout.addLayout(bar)
        self.header_extra = W.QHBoxLayout()
        self.header_extra.setContentsMargins(14, 0, 14, 6)
        header_layout.addLayout(self.header_extra)
        self.header_bar = bar
        bar.setContentsMargins(14, 10, 14, 10)
        decks = W.QToolButton()
        decks.setText('< Decks')
        decks.setPopupMode(W.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.recent = W.QMenu(decks)
        self.recent.aboutToShow.connect(self.refresh_recent)
        decks.setMenu(self.recent)
        bar.addWidget(decks)
        self.name = W.QLineEdit(self.document.deck.name)
        self.name.setMinimumWidth(130)
        self.name.editingFinished.connect(self.edit_metadata)
        bar.addWidget(self.name, 1)
        self.format = W.QComboBox()
        self.format.addItems(['Custom', 'Commander', 'Modern', 'Standard', 'Pauper', 'Legacy', 'Vintage'])
        self.format.currentTextChanged.connect(self.edit_metadata)
        bar.addWidget(self.format)
        self.count = W.QLabel('0 cards')
        bar.addWidget(self.count)
        self.save_status = W.QLabel('Saved')
        self.save_status.setProperty('role', 'muted')
        bar.addWidget(self.save_status)
        self.button(bar, 'Save', self.save)
        self.add_button = self.button(bar, '+ Add Cards', self.toggle_search, True)
        self.button(bar, 'Import', self.import_decklist)
        self.button(bar, 'Print Deck', self.print_deck, True)
        more = W.QToolButton()
        more.setText('More')
        more.setPopupMode(W.QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = W.QMenu(more)
        menu.addAction('Compact table', self.show_table)
        menu.addAction('Export decklist…', self.export_decklist)
        menu.addAction('Commander / format deck checks…', self.commander_checks)
        menu.addAction('Manage categories…', self.manage_categories)
        menu.addAction('Category templates…', self.category_templates)
        menu.addAction('Auto Categorize…', self.auto_categorize)
        menu.addAction('Quick category / tags (hold T)', lambda: self.quick_tag(QtGui.QCursor.pos()))
        self.show_empty_categories = menu.addAction('Show empty categories')
        self.show_empty_categories.setCheckable(True)
        self.show_empty_categories.toggled.connect(self.toggle_empty_categories)
        menu.addAction('Deck description…', self.edit_description)
        menu.addAction('Restore recovery snapshot…', self.recover)
        menu.addAction('Open deck…', self.open)
        more.setMenu(menu)
        bar.addWidget(more)
        self.header_actions = [bar.itemAt(i).widget() for i in range(3, bar.count())]
        layout.addWidget(header)
        controls = W.QFrame()
        controls.setProperty('role', 'toolbar')
        controls.setSizePolicy(W.QSizePolicy.Policy.Expanding, W.QSizePolicy.Policy.Fixed)
        control_layout = W.QVBoxLayout(controls)
        control_layout.setContentsMargins(0, 0, 0, 0)
        row = W.QHBoxLayout()
        control_layout.addLayout(row)
        self.control_extra = W.QHBoxLayout()
        self.control_extra.setContentsMargins(14, 0, 14, 6)
        control_layout.addLayout(self.control_extra)
        self.control_bar = row
        row.setContentsMargins(14, 8, 14, 8)
        self.undo_button = self.button(row, 'Undo', self.undo)
        self.redo_button = self.button(row, 'Redo', self.redo)
        self.view_mode = W.QComboBox()
        self.view_mode.addItems(['Grid', 'Stacks'])
        row.addWidget(self.view_mode)
        self.group = W.QComboBox()
        self.group.addItems(GROUPS)
        self.group.setToolTip('Group cards by')
        row.addWidget(self.group)
        self.sort = W.QComboBox()
        self.sort.addItems(SORTS)
        self.sort.setToolTip('Sort cards within groups')
        row.addWidget(self.sort)
        self.filter = W.QLineEdit()
        self.filter.setPlaceholderText('Filter this deck…')
        row.addWidget(self.filter, 1)
        self.zoom = W.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.zoom.setRange(120, 260)
        self.zoom.setValue(180)
        self.zoom.setMaximumWidth(135)
        self.zoom.setToolTip('Card size')
        row.addWidget(self.zoom)
        self.selection_label = W.QLabel('')
        row.addWidget(self.selection_label)
        self.quick_tag_button = self.button(row, 'Quick tags', lambda: self.quick_tag(QtGui.QCursor.pos()))
        self.quick_tag_button.setToolTip('Replace primary category or toggle secondary tags for selected cards')
        self.control_overflow = [self.filter, self.zoom, self.selection_label]
        layout.addWidget(controls)
        self.splitter = W.QSplitter()
        self.search_panel = W.QWidget()
        self.search_panel.setMinimumWidth(270)
        search_layout = W.QVBoxLayout(self.search_panel)
        search_header = W.QHBoxLayout()
        label = W.QLabel('Add Cards')
        self.search_heading = label
        label.setProperty('role', 'title')
        search_header.addWidget(label, 1)
        self.search_close = self.button(search_header, '×', self.toggle_search)
        search_layout.addLayout(search_header)
        self.query = W.QLineEdit()
        self.query.setPlaceholderText('Local search: o:flying c=g')
        self.query.textChanged.connect(lambda: self.search_timer.start())
        self.query.returnPressed.connect(self.search)
        search_layout.addWidget(self.query)
        self.search_status = W.QLabel('Search by name or Scryfall syntax')
        self.search_status.setWordWrap(True)
        search_layout.addWidget(self.search_status)
        self.search_document = DeckDocument()
        self.results = CardCanvas(self.search_document, self.thumbnails, search=True)
        self.results.card_width = 130
        self.results.quantityRequested.connect(self.add_result)
        self.results.menuRequested.connect(self.search_menu)
        search_layout.addWidget(self.results, 1)
        self.splitter.addWidget(self.search_panel)
        self.grid = CardCanvas(self.document, self.thumbnails)
        self.grid.selectionChanged.connect(self.selection_changed)
        self.grid.quantityRequested.connect(self.change_quantity)
        self.grid.artworkRequested.connect(self.replace_artwork)
        self.grid.detailsRequested.connect(self.card_details)
        self.grid.menuRequested.connect(self.card_menu)
        self.grid.quickTagRequested.connect(self.quick_tag)
        self.grid.setToolTip('Hold right mouse or T: quick category / tags. Right-click: card actions.')
        self.grid.moveRequested.connect(self.move_cards)
        self.grid.preferencesChanged.connect(self.preferences_changed)
        self.grid.addRequested.connect(self.open_search)
        self.model = DeckTable(self.document, self)
        self.table = W.QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(W.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(W.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.selectionModel().selectionChanged.connect(self.table_selection_changed)
        self.table.installEventFilter(self)
        self.table.viewport().installEventFilter(self)
        from .quick_tags import HoldTagGesture
        self.tag_gestures = [HoldTagGesture(view,
            lambda position, v=view: self.select_tag_target(v, position),
            lambda entry_id, position: self.card_menu(entry_id, position), self.quick_tag)
            for view in (self.grid, self.table)]
        self.table.setToolTip(self.grid.toolTip())
        self._refreshing_table = False
        self.table.horizontalHeader().setSectionResizeMode(1, W.QHeaderView.ResizeMode.Stretch)
        self.views = W.QStackedWidget()
        self.views.addWidget(self.grid)
        self.views.addWidget(self.table)
        self.splitter.addWidget(self.views)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([330, 920])
        self.splitter.splitterMoved.connect(self.preferences_changed)
        self.search_panel.hide()
        layout.addWidget(self.splitter, 1)
        self.setCentralWidget(body)
        for combo in (self.view_mode, self.group, self.sort):
            combo.currentTextChanged.connect(self.preferences_changed)
        self.zoom.valueChanged.connect(self.preferences_changed)
        self.filter.textChanged.connect(self.filter_changed)
        self.shortcuts = []
        for sequence, callback in [('Ctrl+S', self.save), ('Ctrl+N', self.new), ('Ctrl+O', self.open),
                                   ('Ctrl+Z', self.undo), ('Ctrl+Y', self.redo), ('Ctrl+Shift+Z', self.redo),
                                   ('Ctrl+F', self.focus_filter), ('Ctrl+K', self.open_search)]:
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
        self.sync_fields()
        self.changed()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, 'control_overflow'):
            return
        narrow = self.width() < 1050
        short = self.height() < 560
        self.search_heading.setVisible(not short)
        self.search_close.setVisible(not short)
        self.search_status.setVisible(not short)
        for widgets, primary, overflow in ((self.header_actions, self.header_bar, self.header_extra),
                                           (self.control_overflow, self.control_bar, self.control_extra)):
            target = overflow if narrow else primary
            for widget in widgets:
                if target.indexOf(widget) < 0:
                    primary.removeWidget(widget)
                    overflow.removeWidget(widget)
                    target.addWidget(widget, 1 if widget in (self.filter, self.count) else 0)

    def button(self, layout, text, callback, primary=False):
        button = W.QPushButton(text)
        if primary:
            button.setProperty('buttonRole', 'primary')
        button.clicked.connect(lambda checked=False: callback())
        layout.addWidget(button)
        return button

    def focus_filter(self):
        self.filter.setFocus()
        self.filter.selectAll()

    def open_search(self):
        self.search_panel.show()
        self.splitter.setSizes([self.document.editor_preferences.get('panel_width', 330), max(400, self.width()-330)])
        self.query.setFocus()

    def toggle_search(self):
        if self.search_panel.isHidden():
            self.open_search()
        else:
            self.search_panel.hide()
            self.results.preview.hide()
            self.thumbnails.set_visible(id(self.results), [])

    def filter_changed(self):
        self.grid.query = self.filter.text()
        self.grid.relayout()

    def preferences_changed(self, *_):
        self.views.setCurrentWidget(self.grid)
        self.grid.mode = self.view_mode.currentText()
        self.grid.grouping = self.group.currentText()
        self.grid.sort = self.sort.currentText()
        self.grid.card_width = self.zoom.value()
        self.document.editor_preferences.update(view=self.grid.mode, group=self.grid.grouping,
            sort=self.grid.sort, card_width=self.grid.card_width, collapsed=sorted(self.grid.collapsed))
        if not self.search_panel.isHidden():
            self.document.editor_preferences['panel_width'] = self.splitter.sizes()[0]
        self.changed()

    def selection_changed(self):
        count = len(self.grid.selected)
        self.selection_label.setText(f'{count} selected' if count else '')
        self.quick_tag_button.setEnabled(bool(count))

    def eventFilter(self, watched, event):
        if watched in (self.table, self.table.viewport()):
            if (event.type() == QtCore.QEvent.Type.KeyPress and event.key() == QtCore.Qt.Key.Key_T
                    and not event.modifiers() and self.grid.selected):
                if not event.isAutoRepeat():
                    self.quick_tag(QtGui.QCursor.pos())
                return True
        return super().eventFilter(watched, event)

    def select_tag_target(self, view, position):
        self.grid.detail_timer.stop()
        view.setFocus()
        self.grid.hover_timer.stop()
        self.grid.preview.hide()
        point = view.viewport().mapFromGlobal(position)
        if view is self.table:
            index = self.table.indexAt(point)
            if not index.isValid():
                return None
            entry_id = self.document.deck.entries[index.row()].entry_id
            if entry_id not in self.grid.selected:
                self.table.selectRow(index.row())
        else:
            item = self.grid.hit(point)
            if not item:
                return None
            entry_id = item[0].entry_id
            if entry_id not in self.grid.selected:
                self.grid.selected = {entry_id}
            self.grid.selectionChanged.emit()
            self.grid.viewport().update()
        return entry_id

    def show_table(self):
        self.views.setCurrentWidget(self.table)
        self.restore_table_selection()

    def table_selection_changed(self, *_):
        if self._refreshing_table or self.views.currentWidget() is not self.table:
            return
        self.grid.selected = {self.document.deck.entries[index.row()].entry_id
                              for index in self.table.selectionModel().selectedRows()}
        self.selection_changed()

    def restore_table_selection(self):
        self._refreshing_table = True
        self.table.clearSelection()
        flags = QtCore.QItemSelectionModel.SelectionFlag.Select | QtCore.QItemSelectionModel.SelectionFlag.Rows
        for row, entry in enumerate(self.document.deck.entries):
            if entry.entry_id in self.grid.selected:
                index = self.model.index(row, 0)
                self.table.selectionModel().select(index, flags)
                self.table.selectionModel().setCurrentIndex(index, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)
        self._refreshing_table = False

    def edit(self, action):
        if self.history.execute(action):
            self.changed()

    def changed(self):
        self._refreshing_table = True
        self.model.refresh()
        self._refreshing_table = False
        self.grid.refresh()
        if self.views.currentWidget() is self.table:
            self.restore_table_selection()
        dirty = self.document.to_dict() != self.saved
        self.setWindowTitle(f'{self.document.deck.name}{"*" if dirty else ""} — Manaforge Deck Editor')
        total = sum(e.quantity for e in self.document.deck.entries if e.section in ('mainboard', 'commander'))
        self.count.setText(f'{total} cards')
        self.save_status.setText('Unsaved' if dirty else 'Saved')
        self.undo_button.setEnabled(self.history.can_undo)
        self.redo_button.setEnabled(self.history.can_redo)
        self.selection_changed()
        if dirty:
            self.autosave.start()

    def edit_metadata(self):
        def action(document):
            document.deck.name = self.name.text().strip() or 'Untitled Deck'
            document.deck.format = self.format.currentText()
        self.edit(action)

    def edit_description(self):
        text, ok = W.QInputDialog.getMultiLineText(self, 'Deck description', 'Description:', self.document.deck.description)
        if ok:
            self.edit(lambda d: setattr(d.deck, 'description', text))

    def search(self):
        if self.worker is not None:
            return
        query = self.query.text().strip()
        if not query:
            self.search_document.deck.entries.clear()
            self.results.refresh()
            return
        self.search_status.setText('Searching local database…')
        self.worker = SearchWorker(query, self.service, self)
        self.worker.completed.connect(self.show_results)
        self.worker.finished.connect(self.search_finished)
        self.worker.start()

    def show_results(self, query, results, error):
        if query != self.query.text().strip():
            return
        self.search_document.deck.entries = [DeckEntry(entry_id=r.card_id, name=r.name,
            card_id=r.card_id, oracle_id=r.oracle_id, set_code=r.set_code,
            collector_number=r.collector_number, extras={'pre_cropped': True, 'facts': card_facts(getattr(r, 'payload', {}) or {}),
                'category_suggestion': (getattr(r, 'payload', {}) or {}).get('_category_evidence',
                    classify(getattr(r, 'payload', {}) or {}))}) for r in results]
        self.results.refresh()
        self.search_status.setText(error or f'{len(results)} local matches (up to 100). Double-click or + to add.')

    def search_finished(self):
        query = self.worker.query
        self.worker.deleteLater()
        self.worker = None
        if query != self.query.text().strip():
            self.search_timer.start()

    def add_result(self, entry_id, delta=1):
        result = next((e for e in self.search_document.deck.entries if e.entry_id == entry_id), None)
        if result is None:
            return
        def action(document):
            existing = next((e for e in document.deck.entries if e.card_id == result.card_id and e.section == 'mainboard' and not e.extras.get('art_override')), None)
            if existing:
                existing.quantity += 1
            else:
                entry = deepcopy(result)
                entry.entry_id = str(uuid.uuid4())
                entry.sort_order = max((e.sort_order for e in document.deck.entries), default=-1)+1
                document.deck.entries.append(entry)
                apply_categories(document, {entry.entry_id: entry.extras.pop('category_suggestion', [])})
        self.edit(action)

    def change_quantity(self, entry_id, delta):
        if not entry_id and delta == 0:
            self.remove_selected()
            return
        ids = self.grid.selected if entry_id in self.grid.selected else {entry_id}
        def action(document):
            for entry in document.deck.entries:
                if entry.entry_id in ids:
                    entry.quantity = max(1, entry.quantity+delta)
        self.edit(action)

    def remove_selected(self):
        ids = set(self.grid.selected)
        def action(document):
            document.deck.entries = [e for e in document.deck.entries if e.entry_id not in ids]
            document.deck.commander_entry_ids = [i for i in document.deck.commander_entry_ids if i not in ids]
        self.edit(action)

    def move_cards(self, ids, target, before):
        self.edit(lambda d: move_entries(d, ids, self.grid.grouping, target, before))

    def quick_tag(self, position, *, hold=False):
        from .quick_tags import QuickTagMenu, apply_quick_role
        ids = set(self.grid.selected)
        if not ids:
            self.statusBar().showMessage('Select cards to categorize or tag.', 4000)
            return
        self.grid.hover_timer.stop()
        self.grid.preview.hide()
        previous = getattr(self, 'quick_menu', None)
        if previous is not None:
            previous.close()
            previous.deleteLater()
        self.quick_menu = QuickTagMenu(self.document, ids, self, hold=hold)
        def apply(name, tags):
            self.edit(lambda d: apply_quick_role(d, ids, name, tags))
            self.statusBar().showMessage(f'Updated {len(ids)} cards: ' +
                ('secondary tags' if tags else 'manual primary category') + '. Undo is available.', 5000)
        self.quick_menu.chosen.connect(apply)
        self.quick_menu.popup(position)

    def card_menu(self, entry_id, position):
        ids = set(self.grid.selected) or {entry_id}
        entry = next(e for e in self.document.deck.entries if e.entry_id == entry_id)
        menu = W.QMenu(self)
        menu.addAction('Quick category / tags', lambda: self.quick_tag(position))
        menu.addAction('Replace artwork…', lambda: self.replace_artwork(entry_id)).setEnabled(len(ids) == 1)
        menu.addAction('View Oracle tags…', lambda: self.view_tags(entry))
        menu.addAction('Edit user tags…', lambda: self.edit_tags(ids, entry.tags))
        sections = menu.addMenu('Move to section')
        for key, label in SECTIONS.items():
            sections.addAction(label, lambda checked=False, k=key: self.edit(lambda d: assign(d, ids, 'section', k)))
        categories = menu.addMenu('Primary category')
        categories.addAction('Uncategorized', lambda: self.edit(lambda d: assign(d, ids, 'category', None)))
        for category in self.document.deck.categories:
            categories.addAction(category.name, lambda checked=False, cid=category.category_id: self.edit(lambda d: assign(d, ids, 'category', cid)))
        categories.addSeparator()
        categories.addAction('Manage categories…', self.manage_categories)
        menu.addAction('Make commander', lambda: self.edit(lambda d: assign(d, ids, 'section', 'commander')))
        for label, field, value in [('Make oversized', 'oversized', True), ('Make normal size', 'oversized', False),
                                    ('Owned / do not print', 'do_not_print', True), ('Include in printing', 'do_not_print', False)]:
            menu.addAction(label, lambda checked=False, f=field, v=value: self.edit(lambda d: assign(d, ids, f, v)))
        menu.addAction('Retry artwork', lambda: self.thumbnails.retry(entry.card_id, entry.image_asset_id))
        menu.addSeparator()
        menu.addAction(f'Remove {len(ids)} selected', self.remove_selected)
        self.grid.preview.hide()
        menu.exec(position)

    def search_menu(self, entry_id, position):
        entry = next(e for e in self.search_document.deck.entries if e.entry_id == entry_id)
        menu = W.QMenu(self)
        menu.addAction('Add card', lambda: self.add_result(entry_id))
        menu.addAction('View Oracle tags…', lambda: self.view_tags(entry))
        menu.addAction('Retry artwork', lambda: self.thumbnails.retry(entry.card_id, entry.image_asset_id))
        menu.exec(position)

    def edit_tags(self, ids, tags):
        text, ok = W.QInputDialog.getText(self, 'User tags', 'Comma-separated tags (applies to selected cards):', text=', '.join(tags))
        if ok:
            self.edit(lambda d: assign(d, ids, 'tags', list(dict.fromkeys(t.strip() for t in text.split(',') if t.strip()))))

    def view_tags(self, entry):
        from .proxy_adapter import enable_proxy_imports
        enable_proxy_imports()
        from dialogs import CardTagsDialog
        def show(tags):
            dialog = CardTagsDialog(self, entry.name, tags)
            if dialog.exec() == W.QDialog.DialogCode.Accepted and dialog.selected_tag:
                self.open_search()
                self.query.setText('otag:' + dialog.selected_tag)
        self.run_task(lambda: self.service.database.oracle_tags_for_card(entry.oracle_id) if entry.oracle_id else [], show)

    def commander_checks(self):
        from .commander_dialog import CommanderDialog
        from mtg_core.commander import set_commanders
        ids = [e.card_id for e in self.document.deck.entries]
        def show(records):
            dialog = CommanderDialog(self.document, records, self)
            if dialog.exec() == W.QDialog.DialogCode.Accepted:
                self.edit(dialog.apply_selections)
        self.run_task(lambda: self.service.database.legality_data(ids), show)

    def import_decklist(self):
        from .decklist_dialogs import ImportDecklist
        from mtg_core.decklists import apply_decklist
        if self.task is not None:
            return
        dialog = ImportDecklist(self.service, self)
        if dialog.exec() == W.QDialog.DialogCode.Accepted and dialog.result:
            self.edit(lambda d: apply_decklist(d, dialog.result))
            self.group.setCurrentText('Category')
            self.statusBar().showMessage('Decklist imported and categorized. Undo is available.', 6000)

    def export_decklist(self):
        from .decklist_dialogs import ExportDecklist
        ExportDecklist(self.document, self).exec()

    def category_templates(self):
        from .category_templates import CategoryTemplates, TemplateStore, apply_template
        try:
            dialog = CategoryTemplates(self.document, TemplateStore(self.root / 'category_templates.json'), self)
        except (OSError, ValueError) as exc:
            W.QMessageBox.warning(self, 'Could not load templates', str(exc))
            return
        if dialog.exec() == W.QDialog.DialogCode.Accepted:
            names = dialog.selected_names()
            self.edit(lambda d: apply_template(d, names))
            self.group.setCurrentText('Category')
            self.show_empty_categories.setChecked(True)
            self.statusBar().showMessage('Category template applied. Card assignments preserved; Undo is available.', 6000)

    def manage_categories(self):
        dialog = W.QDialog(self)
        dialog.setWindowTitle('Deck categories')
        dialog.resize(420, 430)
        layout = W.QVBoxLayout(dialog)
        listing = W.QListWidget()
        categories = deepcopy(sorted(self.document.deck.categories, key=lambda c: c.sort_order))
        def refresh():
            row = listing.currentRow()
            listing.clear()
            listing.addItems([c.name for c in categories])
            listing.setCurrentRow(max(0, min(row, len(categories)-1)))
        refresh()
        layout.addWidget(listing, 1)
        buttons = W.QHBoxLayout()
        def change(action):
            row = listing.currentRow()
            if action == 'Add' or (action == 'Rename' and row >= 0):
                name, ok = W.QInputDialog.getText(dialog, action+' category', 'Name:', text=categories[row].name if action == 'Rename' else '')
                if ok and name.strip():
                    if action == 'Add':
                        categories.append(DeckCategory(str(uuid.uuid4()), name.strip()))
                    else:
                        categories[row].name = name.strip()
            elif row >= 0:
                if action == 'Delete':
                    categories.pop(row)
                else:
                    target = row + (-1 if action == 'Up' else 1)
                    if 0 <= target < len(categories):
                        categories[row], categories[target] = categories[target], categories[row]
            refresh()
        for action in ('Add', 'Rename', 'Delete', 'Up', 'Down'):
            self.button(buttons, action, lambda a=action: change(a))
        layout.addLayout(buttons)
        box = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Ok | W.QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(dialog.accept)
        box.rejected.connect(dialog.reject)
        layout.addWidget(box)
        if dialog.exec() == W.QDialog.DialogCode.Accepted:
            def apply(document):
                keep = {c.category_id for c in categories}
                for old in list(document.deck.categories):
                    if old.category_id not in keep:
                        remove_category(document, old.category_id)
                for i, category in enumerate(categories):
                    category.sort_order = i
                document.deck.categories = categories
            self.edit(apply)

    def auto_categorize(self):
        from .category_review import CategoryReview
        entries = deepcopy(self.document.deck.entries)
        def review(proposals):
            dialog = CategoryReview(self.document, proposals, self)
            if dialog.exec() == W.QDialog.DialogCode.Accepted:
                selected = dialog.selected_proposals()
                self.edit(lambda document: apply_categories(document, selected,
                          reconsider_manual=dialog.reconsider.isChecked()))
                self.group.setCurrentText('Category')
                self.statusBar().showMessage(f'Categorized {len(selected)} entries. Undo is available.', 8000)
        self.run_task(lambda: analyze_entries(self.service.database, entries), review)

    def run_task(self, work, callback):
        if self.task is not None:
            return
        self.autosave.stop()
        self.centralWidget().setEnabled(False)
        self.statusBar().showMessage('Working…')
        self.task = Task(work, self)
        def completed(result, error):
            self.centralWidget().setEnabled(True)
            if error:
                self.statusBar().showMessage(error)
                W.QMessageBox.warning(self, 'Could not complete operation', error)
            else:
                try:
                    callback(result)
                except (OSError, ValueError, TypeError) as exc:
                    W.QMessageBox.warning(self, 'Could not complete operation', str(exc))
            if self.document.to_dict() != self.saved:
                self.autosave.start()
        self.task.completed.connect(completed)
        self.task.finished.connect(self.task_finished)
        self.task.start()

    def task_finished(self):
        self.task.deleteLater()
        self.task = None

    def card_details(self, entry_id):
        from .card_details import CardDetails, apply_printing
        entry = next((e for e in self.document.deck.entries if e.entry_id == entry_id), None)
        if entry is None:
            return
        previous = getattr(self, 'details_dialog', None)
        if previous is not None:
            previous.close()
            previous.deleteLater()
        document = self.document
        self.details_dialog = CardDetails(self.service, entry, self)
        def choose(target, payload):
            if self.document is document:
                self.edit(lambda d: apply_printing(d, target, payload))
        self.details_dialog.printingChosen.connect(choose)
        self.details_dialog.show()

    def replace_artwork(self, entry_id):
        from .proxy_adapter import choose_art, apply_art
        selection = choose_art(self, self.document, entry_id)
        if selection is None:
            return
        def apply(result):
            def action(document):
                entry = next(e for e in document.deck.entries if e.entry_id == entry_id)
                entry.image_asset_id = result.pop('image_asset_id')
                entry.extras.update({k: v for k, v in result.items() if v is not None})
            self.edit(action)
        self.run_task(lambda: apply_art(selection), apply)

    def print_deck(self):
        from .proxy_adapter import prepare_print, launch_print
        dialog = W.QDialog(self)
        dialog.setWindowTitle('Print Deck — sections')
        layout = W.QVBoxLayout(dialog)
        layout.addWidget(W.QLabel('Choose sections. Cards marked do not print are excluded.'))
        checks = {}
        for key, label in SECTIONS.items():
            check = W.QCheckBox(label)
            check.setChecked(key in ('mainboard', 'commander'))
            layout.addWidget(check)
            checks[key] = check
        buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Ok | W.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != W.QDialog.DialogCode.Accepted or not self.save():
            return
        snapshot = DeckDocument.from_dict(self.document.to_dict())
        sections = {key for key, check in checks.items() if check.isChecked()}
        def launch(project):
            self.document.extras['proxy_project_id'] = project['id']
            self.changed()
            if self.save():
                try:
                    launch_print(project)
                    relocated = project.get('relocated_copies', 0)
                    self.statusBar().showMessage('Deck opened in Proxy.' +
                        (f' {relocated} copies relocated to fit the sheet.' if relocated else ''))
                except OSError as exc:
                    W.QMessageBox.warning(self, 'Could not launch Proxy', str(exc))
        self.run_task(lambda: prepare_print(snapshot, self.service, sections), launch)

    def undo(self):
        if self.task is not None:
            return
        prefs, link = deepcopy(self.document.editor_preferences), self.document.extras.get('proxy_project_id')
        self.history.undo()
        self.document.editor_preferences = prefs
        if link:
            self.document.extras['proxy_project_id'] = link
        self.sync_fields()
        self.changed()

    def redo(self):
        if self.task is not None:
            return
        prefs, link = deepcopy(self.document.editor_preferences), self.document.extras.get('proxy_project_id')
        self.history.redo()
        self.document.editor_preferences = prefs
        if link:
            self.document.extras['proxy_project_id'] = link
        self.sync_fields()
        self.changed()

    def toggle_empty_categories(self, visible):
        self.document.editor_preferences['show_empty_categories'] = visible
        self.changed()

    def sync_fields(self):
        blockers = [QtCore.QSignalBlocker(w) for w in (self.name, self.format, self.view_mode, self.group, self.sort, self.zoom, self.show_empty_categories)]
        self.name.setText(self.document.deck.name)
        if self.format.findText(self.document.deck.format) < 0:
            self.format.addItem(self.document.deck.format)
        self.format.setCurrentText(self.document.deck.format)
        prefs = self.document.editor_preferences
        self.show_empty_categories.setChecked(prefs.get('show_empty_categories', False))
        self.view_mode.setCurrentText(prefs.get('view', 'Stacks'))
        self.group.setCurrentText(prefs.get('group', 'Category'))
        self.sort.setCurrentText(prefs.get('sort', 'Name'))
        self.zoom.setValue(prefs.get('card_width', 180))
        self.grid.mode, self.grid.grouping, self.grid.sort = self.view_mode.currentText(), self.group.currentText(), self.sort.currentText()
        self.grid.card_width = self.zoom.value()
        self.grid.collapsed = set(prefs.get('collapsed', []))
        del blockers

    def save(self):
        if (self.name.text().strip() or 'Untitled Deck') != self.document.deck.name or self.format.currentText() != self.document.deck.format:
            self.edit_metadata()
        self.autosave.stop()
        if self.document.to_dict() == self.saved and self.path:
            return True
        destination = self.path or self.root / f'{self.document.deck.deck_id}.manaforge.json'
        try:
            self.store.save(destination, self.document)
        except (OSError, ValueError, TypeError) as exc:
            self.statusBar().showMessage(f'Save failed; changes remain unsaved: {exc}')
            self.autosave.start(10000)
            return False
        self.path, self.saved = destination, self.document.to_dict()
        self.changed()
        self.statusBar().showMessage(f'Saved: {destination}')
        return True

    def replace_document(self, document, path=None):
        self.document, self.path = document, path
        self.history, self.saved = DeckHistory(document), document.to_dict()
        self.model.document = self.grid.document = document
        self.grid.selected.clear()
        self.grid.verticalScrollBar().setValue(0)
        self.sync_fields()
        self.changed()
        # Legacy entries have no grouping facts; hydrate local metadata off the UI thread.
        legacy_folder = document.print_settings.get('proxy_project', {}).get('image_dir')
        missing = [(e.entry_id, e.card_id, e.extras.get('proxy_front_name'), e.image_asset_id)
                   for e in document.deck.entries if (e.card_id and not e.extras.get('facts')) or (legacy_folder and not e.image_asset_id)]
        uncategorized = [deepcopy(e) for e in document.deck.entries
                         if not e.category_ids and not e.extras.get('auto_categories')]
        can_analyze = hasattr(getattr(self.service, 'database', None), 'categorization_data')
        if (missing and hasattr(self.service, 'get_card')) or (uncategorized and can_analyze):
            def resolve():
                result = {}
                for eid, cid, front_name, asset in missing:
                    facts = card_facts(self.service.get_card(card_id=cid) or {}) if cid and hasattr(self.service, 'get_card') else {}
                    if not asset and legacy_folder and front_name:
                        path = Path(legacy_folder) / Path(front_name).name
                        if path.is_file():
                            asset = self.service.store_image_bytes(path.read_bytes(),
                                extension=path.suffix.lstrip('.') or 'png', source='editor_legacy')
                    result[eid] = facts, asset
                proposals = analyze_entries(self.service.database, uncategorized) if can_analyze else {}
                return result, proposals
            def apply(resolved):
                resolved, proposals = resolved
                for entry in self.document.deck.entries:
                    if entry.entry_id in resolved:
                        facts, asset = resolved[entry.entry_id]
                        entry.extras['facts'] = facts
                        entry.image_asset_id = asset
                self.edit(lambda d: apply_categories(d, proposals))
                self.changed()
            self.run_task(resolve, apply)

    def new(self):
        if self.task is not None or (self.document.to_dict() != self.saved and not self.save()):
            return
        self.replace_document(DeckDocument())

    def open(self):
        path, _ = W.QFileDialog.getOpenFileName(self, 'Open deck or proxy project', str(self.root), 'JSON projects (*.json)')
        if path:
            self.open_path(Path(path))

    def open_path(self, path):
        if self.task is not None or (self.document.to_dict() != self.saved and not self.save()):
            return
        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
            if 'schema_version' in raw and 'deck' in raw:
                document, destination = DeckDocument.from_dict(raw), path
            else:
                document = DeckDocument.from_legacy_proxy(raw, name=path.stem)
                if isinstance(raw.get('deck_document'), dict):
                    embedded = DeckDocument.from_dict(raw['deck_document'])
                    embedded.print_settings['proxy_project'] = raw
                    document = embedded
                destination = None
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            W.QMessageBox.warning(self, 'Open failed', str(exc))
            return
        self.replace_document(document, destination)
        if destination is None:
            self.save()

    def recover(self):
        if not self.path:
            return
        paths = self.store.recovery_paths(self.path)
        if not paths:
            W.QMessageBox.information(self, 'Recovery', 'No recovery snapshots yet.')
            return
        value, ok = W.QInputDialog.getItem(self, 'Recovery', 'Restore a snapshot into a new deck:', [p.name for p in paths], 0, False)
        if ok:
            if self.document.to_dict() != self.saved and not self.save():
                return
            try:
                document = self.store.load(next(p for p in paths if p.name == value))
            except (OSError, ValueError) as exc:
                W.QMessageBox.warning(self, 'Recovery failed', str(exc))
                return
            document.deck.deck_id = str(uuid.uuid4())
            document.deck.name += ' (Recovered)'
            document.extras.pop('proxy_project_id', None)
            self.replace_document(document)
            self.save()

    def refresh_recent(self):
        self.recent.clear()
        self.recent.addAction('Decks and print projects…', self.project_browser)
        self.recent.addAction('New deck', self.new)
        self.recent.addAction('Open deck / proxy project…', self.open)
        self.recent.addSeparator()
        paths = sorted(self.root.glob('*.manaforge.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:15]
        for path in paths:
            try:
                name = self.store.load(path).deck.name
            except (OSError, ValueError, TypeError):
                continue
            self.recent.addAction(name, lambda checked=False, p=path: self.open_path(p))

    def project_browser(self):
        from .project_browser import ProjectBrowser
        if self.task is not None:
            return
        dialog = ProjectBrowser(self.root, data_root() / 'projects', self)
        if dialog.exec() == W.QDialog.DialogCode.Accepted:
            if dialog.new_deck:
                self.new()
            elif dialog.path:
                self.open_path(dialog.path)

    def closeEvent(self, event):
        if self.worker is not None or self.task is not None or self.thumbnails.worker is not None:
            self.thumbnails.stopping = True
            self.thumbnails.pending.clear()
            self.statusBar().showMessage('Finishing background work before closing…')
            QtCore.QTimer.singleShot(150, self.close)
            event.ignore()
            return
        if self.document.to_dict() != self.saved and not self.save():
            self.thumbnails.stopping = False
            event.ignore()
            return
        self.autosave.stop()
        self.search_timer.stop()
        self.thumbnails.stop()
        self.grid.preview.close()
        self.results.preview.close()
        super().closeEvent(event)


def main():
    app = W.QApplication.instance() or W.QApplication([])
    app.setApplicationName('Manaforge Deck Editor')
    app.setStyle('Fusion')
    app.setStyleSheet(application_stylesheet())
    window = EditorWindow()
    window.show()
    app.exec()
