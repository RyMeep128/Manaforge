"""One draft-based setup surface shared by creation and deck settings."""
from copy import deepcopy
import json

from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_core.card_metadata import card_facts
from mtg_core.commander import eligible, set_commanders
from mtg_core.discovery_themes import theme_catalog, theme_matches
from .commander_selection import commanders, apply_selection
from .commander_discovery import DiscoveryController, DiscoverySearch, DiscoveryCanvas
from .themes import ThemesDialog


class DeckSetupDialog(W.QDialog):
    def __init__(self, editor, document, *, creating=False, seed=None):
        super().__init__(editor)
        self.editor = editor
        self.draft = deepcopy(document)
        self.selected = deepcopy(commanders(document))
        self.original_ids = [e.entry_id for e in self.selected]
        self.creating = creating
        self.stage = 0
        self.precon_loaded = False
        self.rows = {}
        self.catalog = theme_catalog([], {})
        self.catalog_loaded = False
        self.setWindowTitle('New deck' if creating else 'Deck settings')
        available = self.screen().availableGeometry()
        self.resize(min(700, available.width()), min(650, available.height()))
        outer = W.QVBoxLayout(self)
        outer.setSpacing(12)
        title = self.title = W.QLabel('Make room for your next idea' if creating else 'Deck settings')
        title.setProperty('role', 'title')
        outer.addWidget(title)
        form = W.QFormLayout()
        self.name = W.QLineEdit('' if creating else document.deck.name)
        self.name.setPlaceholderText('Deck name · optional')
        form.addRow('&Name', self.name)
        self.format = W.QComboBox()
        self.format.addItems([editor.format.itemText(i) for i in range(editor.format.count())])
        self.format.setCurrentText(document.deck.format)
        form.addRow('&Format', self.format)
        self.start = W.QComboBox()
        self.start.addItems(['Blank deck', 'Import decklist', 'From a precon'])
        if creating:
            form.addRow('Start with', self.start)
        outer.addLayout(form)
        self.tabs = W.QTabWidget()
        outer.addWidget(self.tabs, 1)
        self.commander_page = W.QWidget()
        layout = W.QVBoxLayout(self.commander_page)
        self.current = W.QLabel()
        self.current.setWordWrap(True)
        layout.addWidget(self.current)
        row = W.QHBoxLayout()
        self.mode = W.QComboBox()
        self.mode.addItems(['Commander', 'Partner / Background'])
        row.addWidget(self.mode)
        self.search = W.QLineEdit()
        self.search.setPlaceholderText('Search commanders by name')
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName('Search commanders')
        row.addWidget(self.search, 1)
        layout.addLayout(row)
        self.controller = DiscoveryController(DiscoverySearch(editor.service), self)
        self.canvas = DiscoveryCanvas(DeckDocument(), editor.thumbnails, self)
        self.canvas.card_width = 150
        self.canvas.minimum_search_card_width = 1
        self.canvas.fit_height = True
        self.canvas.commanderRequested.connect(self.pick)
        self.canvas.selectionChanged.connect(self.selection_changed)
        layout.addWidget(self.canvas, 1)
        self.status = W.QLabel('Optional — choose a commander now or add one later.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = W.QHBoxLayout()
        self.choose = W.QPushButton('Use selected commander')
        self.choose.setAutoDefault(False)
        self.choose.setEnabled(False)
        self.choose.clicked.connect(self.pick_current)
        actions.addWidget(self.choose)
        clear = W.QPushButton('Clear commanders')
        clear.setAutoDefault(False)
        clear.clicked.connect(self.clear_commanders)
        actions.addWidget(clear)
        layout.addLayout(actions)
        self.tabs.addTab(self.commander_page, 'Commander · optional')
        self.themes = ThemesDialog(self.draft, self.catalog, [], self, compact=True)
        self.themes.setWindowFlags(C.Qt.WindowType.Widget)
        self.themes.buttons.hide()
        self.themes.current_themes.hide()
        self.themes.setMinimumSize(0, 0)
        self.theme_summary = W.QLabel()
        self.theme_summary.setWordWrap(True)
        self.themes.layout().insertWidget(0, self.theme_summary)
        self.tabs.addTab(self.themes, 'Themes · optional')
        self.themes.list.itemChanged.connect(self.update_summary)
        library_page = W.QWidget()
        library_layout = W.QVBoxLayout(library_page)
        self.library = W.QComboBox()
        self.library.setAccessibleName('Deck library association')
        self.library.addItem('Keep on this computer', None)
        saved = document.deck.extras.get('library_association')
        provider = getattr(editor, 'deck_libraries_provider', None)
        try:
            libraries = provider() if callable(provider) else []
        except (OSError, ValueError):
            libraries = []
        for connection in libraries:
            self.library.addItem(connection['name'], connection)
        if saved:
            index = next((i for i in range(1, self.library.count())
                          if self.library.itemData(i)['id'] == saved.get('id')), -1)
            if index < 0:
                self.library.addItem(saved.get('name', 'Saved library') + ' · unavailable', saved)
                index = self.library.count() - 1
            self.library.setCurrentIndex(index)
        library_layout.addWidget(self.library)
        note = W.QLabel('Choose a library to upload your deck when you create it.'
                       if libraries else 'No signed-in libraries available. You can connect one in Browse Online later.')
        note.setWordWrap(True)
        library_layout.addWidget(note)
        library_layout.addStretch()
        self.tabs.addTab(library_page, 'Library · optional')
        self.summary = W.QLabel()
        self.summary.setWordWrap(True)
        outer.addWidget(self.summary)
        buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Ok | W.QDialogButtonBox.StandardButton.Cancel)
        self.submit = buttons.button(W.QDialogButtonBox.StandardButton.Ok)
        self.submit.setText('Create Deck' if creating else 'Save changes')
        self.submit.setProperty('buttonRole', 'primary')
        self.submit.setAutoDefault(False)
        self.submit.setDefault(False)
        self.back = buttons.addButton('Back', W.QDialogButtonBox.ButtonRole.ActionRole)
        self.back.setAutoDefault(False)
        self.back.clicked.connect(self.previous_step)
        buttons.accepted.connect(self.next_step)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        self.format.currentTextChanged.connect(self.format_changed)
        self.start.currentIndexChanged.connect(self.start_changed)
        self.library.currentIndexChanged.connect(lambda *_: self.update_stage())
        self.search.textChanged.connect(self.search_commanders)
        self.mode.currentIndexChanged.connect(self.search_commanders)
        self.controller.resultsReady.connect(self.completed)
        self.controller.statusChanged.connect(self.status.setText)
        self.tabs.currentChanged.connect(self.search_commanders)
        if seed is not None and eligible(seed.extras.get('facts') or {}) is True:
            self.selected = [deepcopy(seed)]
            self.format.setCurrentText('Commander')
        self.format_changed()
        self.update_summary()
        self.update_stage()
        self.name.setFocus()

    def keyPressEvent(self, event):
        if event.key() in (C.Qt.Key.Key_Return, C.Qt.Key.Key_Enter):
            if self.search.hasFocus():
                self.search_commanders()
            # Search fields must never submit the deck setup dialog.
            event.accept()
            return
        super().keyPressEvent(event)

    def update_stage(self):
        if not self.creating:
            self.back.hide()
            return
        commander = self.format.currentText() in ('Commander', 'Custom')
        self.title.setText(('1. Choose your starting point',
                            '2. Choose your commander',
                            '3. Choose themes and a library')[self.stage])
        self.tabs.setVisible(self.stage > 0)
        self.tabs.setTabVisible(0, self.stage == 1 and commander)
        self.tabs.setTabVisible(1, self.stage == 2)
        self.tabs.setTabVisible(2, self.stage == 2)
        self.back.setVisible(self.stage > 0)
        self.start.setEnabled(self.stage == 0)
        self.format.setEnabled(self.stage == 0 and self.start.currentIndex() != 2)
        if self.stage == 0:
            self.submit.setText('Next: choose precon' if self.start.currentIndex() == 2 else
                                'Next: commander' if commander else 'Next: themes and library')
        elif self.stage == 1:
            self.tabs.setCurrentIndex(0)
            self.submit.setText('Next: themes and library')
            self.search_commanders()
        else:
            self.tabs.setCurrentIndex(1)
            self.submit.setText('Create Deck and Upload' if self.library.currentData() else 'Create Deck')

    def previous_step(self):
        self.stage = 0 if self.stage == 1 else (1 if self.format.currentText() in ('Commander', 'Custom') else 0)
        self.update_stage()

    def next_step(self):
        if not self.creating or self.stage == 2:
            self.accept()
            return
        if self.stage == 0 and self.start.currentIndex() == 2 and not self.precon_loaded:
            from .precon_browser import PreconBrowser
            from mtg_core.precons import apply_precon
            browser = PreconBrowser(self.editor.service, self.editor.thumbnails, self)
            browser.resolve_button.setText('Next: use selected precon')
            if browser.exec() != W.QDialog.DialogCode.Accepted or not browser.result:
                return
            apply_precon(self.draft, browser.record, browser.result,
                         self.name.text() or browser.deck_name.text(), browser.cover_asset_id)
            self.selected = deepcopy(commanders(self.draft))
            self.original_ids = [entry.entry_id for entry in self.selected]
            self.name.setText(self.draft.deck.name)
            self.format.setCurrentText(self.draft.deck.format)
            self.precon_loaded = True
            self.update_summary()
            self.refresh_themes()
        self.stage = (1 if self.format.currentText() in ('Commander', 'Custom') else 2) if self.stage == 0 else 2
        self.update_stage()

    def start_changed(self, *_):
        if self.precon_loaded:
            self.selected = []
            self.original_ids = []
        self.precon_loaded = False
        self.draft.deck.entries = []
        self.draft.deck.extras.pop('precon_origin', None)
        self.draft.deck.extras.pop('cover_image_asset_id', None)
        self.update_stage()
        self.format_changed()

    def format_changed(self, *_):
        precon = self.creating and self.start.currentIndex() == 2
        enabled = self.format.currentText() in ('Commander', 'Custom')
        self.tabs.setTabVisible(0, enabled)
        self.format.setEnabled(not precon)
        self.draft.deck.format = self.format.currentText()
        self.update_summary()
        self.search_commanders()
        if self.creating:
            self.update_stage()

    def query(self):
        partner = (self.selected[0].card_id if self.mode.currentIndex() == 1 and self.selected else None)
        return json.dumps(dict(name=self.search.text(), partner_card_id=partner, legal_only=True,
                               deck_format='commander', limit=50))

    def search_commanders(self, *_):
        self.controller.cancel()
        self.rows.clear()
        self.canvas.document.deck.entries = []
        self.canvas.refresh()
        self.choose.setEnabled(False)
        if (self.tabs.currentIndex() == 0 and self.tabs.isTabVisible(0)) or not self.catalog_loaded:
            self.controller.change_query(self.query())

    def completed(self, query, snapshot, error):
        if query != self.query():
            return
        if error:
            self.status.setText('Local commander data unavailable. You can add a commander later.')
            return
        self.catalog = snapshot['themes']
        self.catalog_loaded = True
        self.rows.clear()
        for row in snapshot['results']:
            card = row['card']
            facts = card_facts(card.payload or {})
            if self.mode.currentIndex() == 0 and eligible(card.payload or {}) is not True:
                continue
            entry = DeckEntry(card.card_id, card.name, card_id=card.card_id, oracle_id=card.oracle_id,
                              set_code=card.set_code, collector_number=card.collector_number,
                              pre_cropped=True, extras={'facts': facts})
            self.rows[entry.entry_id] = entry
        self.canvas.document.deck.entries = list(self.rows.values())
        self.canvas.refresh()
        self.status.setText('Select artwork, then Use selected commander. Double-click also selects.'
                            if self.rows else 'No matches. Try another name, or add a commander later.')
        self.refresh_themes()

    def selection_changed(self):
        self.choose.setEnabled(bool(self.canvas.selected & self.rows.keys()))
        key = next(iter(self.canvas.selected & self.rows.keys()), None)
        if key:
            entry = self.rows[key]
            facts = entry.extras.get('facts') or {}
            self.status.setText(' · '.join(filter(None, (entry.name, facts.get('mana_cost'),
                                                       facts.get('type_line'),
                                                       ''.join(facts.get('color_identity') or []) or 'Colorless'))))

    def pick_current(self):
        key = next(iter(self.canvas.selected & self.rows.keys()), None)
        if key:
            self.pick(key)

    def pick(self, key):
        entry = self.rows.get(key)
        if entry is None:
            return
        self.selected = ([self.selected[0], deepcopy(entry)] if self.mode.currentIndex() == 1
                         and self.selected else [deepcopy(entry)])
        self.update_summary()
        self.refresh_themes()
        self.search_commanders()

    def clear_commanders(self):
        self.selected = []
        self.update_summary()
        self.refresh_themes()
        self.search_commanders()

    def refresh_themes(self):
        # Keep checked and imported themes while adding newly available catalog options.
        checked = self.themes.selections()
        from mtg_core.discovery_themes import oracle_tag_theme
        options = {t['slug']: t for t in [*self.themes.catalog.values(), *self.catalog, *checked]
                   if not t.get('companion')}
        for entry in self.selected:
            for tag in (entry.extras.get('facts') or {}).get('oracle_tags') or []:
                option = oracle_tag_theme(tag)
                options[option['slug']] = option
        self.themes.catalog = options
        selected = {t['slug'] for t in checked}
        from mtg_core.categorization import classify
        rows = [{'entry': entry, 'roles': classify(entry.extras.get('facts') or {})} for entry in self.selected]
        suggestions = {key for key, option in options.items() if any(theme_matches(row, option) for row in rows)}
        with C.QSignalBlocker(self.themes.list):
            self.themes.list.clear()
            for key, option in sorted(options.items(), key=lambda pair: (pair[0] not in suggestions, pair[1]['name'].casefold())):
                item = W.QListWidgetItem(option['name'] + (' · Suggested' if key in suggestions else ''))
                item.setData(C.Qt.ItemDataRole.UserRole, key)
                item.setFlags(item.flags() | C.Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(C.Qt.CheckState.Checked if key in selected else C.Qt.CheckState.Unchecked)
                self.themes.list.addItem(item)
        self.themes.filter()
        self.update_summary()

    def update_summary(self, *_):
        active = self.selected if self.format.currentText() in ('Commander', 'Custom') else []
        self.current.setText(' + '.join(e.name for e in active) or 'No commander selected')
        self.mode.model().item(1).setEnabled(bool(active and active[0].card_id))
        if not active and self.mode.currentIndex():
            self.mode.setCurrentIndex(0)
        names = ', '.join(t['name'] for t in self.themes.selections())
        self.theme_summary.setText('Selected: ' + (names or 'None — choose any themes you enjoy'))
        commander_summary = (', '.join(e.name for e in active) or 'Commander later') if self.format.currentText() in ('Commander', 'Custom') else 'Ready to build'
        self.summary.setText(self.format.currentText() + ' · ' + commander_summary +
                             (' · ' + names if names else ''))

    def apply_to(self, document):
        document.deck.name = self.name.text().strip() or ('Untitled Deck' if self.creating else document.deck.name)
        if self.name.text().strip():
            document.deck.extras['manual_name'] = True
        document.deck.format = self.format.currentText()
        chosen = self.selected if document.deck.format in ('Commander', 'Custom') else []
        if [e.entry_id for e in chosen] != self.original_ids:
            set_commanders(document, [])
            for index, entry in enumerate(chosen):
                apply_selection(document, entry, second=index > 0)
        themes = self.themes.selections()
        document.editor_preferences['manual_themes'] = themes
        # Explicit themes guide ranking independently of discovery's optional browse filter.
        discovery = document.editor_preferences.setdefault('discovery', {})
        discovery.update(theme='', theme_option={})
        association = self.library.currentData()
        if association:
            document.deck.extras['library_association'] = deepcopy(association)
        else:
            document.deck.extras.pop('library_association', None)

    def done(self, result):
        self.controller.shutdown()
        self.canvas.preview.hide()
        # Keep the dialog alive until the cancellable worker has exited.
        if self.controller.worker is not None:
            C.QTimer.singleShot(30, lambda: self.done(result))
            return
        super().done(result)


def prompt_commander_themes(editor, document, signature):
    """Wait for an existing selection task to settle before opening theme editing."""
    if editor.closing or editor.document is not document:
        return
    if tuple(e.entry_id for e in commanders(document)) != signature:
        return
    if editor.task is not None:
        C.QTimer.singleShot(50, lambda: prompt_commander_themes(editor, document, signature))
        return
    from .themes import edit_themes
    edit_themes(editor, commander_changed=True)
