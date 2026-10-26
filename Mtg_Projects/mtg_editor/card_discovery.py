"""Reusable card-drop discovery dialog over the existing cancellable search UI."""
from copy import deepcopy
import json

from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_core.card_discovery import similar_cards, popular_commanders
from mtg_core.recommendation_sources import default_sources
from .commander_discovery import DiscoveryController
from .canvas import CardCanvas
from .organization import card_facts, update_candidate_quantities


class CardDiscoveryService:
    def __init__(self, service, store):
        self.service, self.store = service, store

    def search_editor_cards(self, query, *, should_cancel=None):
        options = json.loads(query)
        document = DeckDocument.from_dict(options['document'])
        entry = DeckEntry.from_dict(options['seed'])
        seed = self.service.get_card(card_id=entry.card_id) if entry.card_id else None
        seed = seed or dict(entry.extras.get('facts') or {}, name=entry.name, oracle_id=entry.oracle_id)
        if options['mode'] == 0:
            return similar_cards(self.service, seed, document, should_cancel=should_cancel)
        return popular_commanders(self.service, seed, document, default_sources(self.store, document=document),
                                  should_cancel=should_cancel)


class CardDiscoveryDialog(W.QDialog):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.seed = None
        self.request_context = None
        self.setWindowTitle('Discover cards')
        self.resize(880, 700)
        self.controller = DiscoveryController(CardDiscoveryService(editor.service, editor.recommendation_store()), self)
        layout = W.QVBoxLayout(self)
        self.title = W.QLabel()
        self.title.setWordWrap(True)
        layout.addWidget(self.title)
        self.tabs = W.QTabBar()
        self.tabs.addTab('Similar Cards')
        self.tabs.addTab('Popular Commanders')
        self.tabs.currentChanged.connect(self.search)
        layout.addWidget(self.tabs)
        self.illegal = W.QCheckBox('Include illegal cards')
        self.illegal.setAccessibleDescription('Ignore deck format and commander color identity defaults')
        self.illegal.toggled.connect(editor.set_include_illegal)
        layout.addWidget(self.illegal)
        self.status = W.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.canvas = CardCanvas(DeckDocument(), editor.thumbnails, self, search=True)
        self.canvas.minimum_search_card_width = 1
        self.canvas.fit_height = True
        self.canvas.card_width = 180
        self.canvas.quantityRequested.connect(self.add)
        self.canvas.detailsRequested.connect(lambda key: editor.candidate_details(self.canvas, key))
        self.canvas.menuRequested.connect(lambda key, point: editor.candidate_menu(self.canvas, key, point, self.add))
        self.canvas.discoverRequested.connect(self.open_card)
        self.canvas.selectionChanged.connect(self.selection_changed)
        layout.addWidget(self.canvas, 1)
        self.reason = W.QLabel('Select a card to see the evidence.')
        self.reason.setWordWrap(True)
        layout.addWidget(self.reason)
        actions = W.QGridLayout()
        details = W.QPushButton('Inspect selected card')
        details.clicked.connect(self.details)
        actions.addWidget(details, 0, 0)
        self.new_deck = W.QPushButton('Start new deck with commander')
        self.new_deck.clicked.connect(self.start_deck)
        actions.addWidget(self.new_deck, 0, 1, 1, 2)
        refresh = W.QPushButton('Search again')
        refresh.clicked.connect(self.search)
        actions.addWidget(refresh, 1, 0)
        cancel = W.QPushButton('Cancel search')
        cancel.clicked.connect(self.controller.cancel)
        actions.addWidget(cancel, 1, 1)
        close = W.QPushButton('Close')
        close.clicked.connect(self.reject)
        actions.addWidget(close, 1, 2)
        layout.addLayout(actions)
        self.controller.resultsReady.connect(self.completed)
        self.controller.statusChanged.connect(self.status.setText)
        self.controller.busyChanged.connect(cancel.setEnabled)
        self.controller.busyChanged.connect(self.set_busy_cursor)

    def set_busy_cursor(self, busy):
        if busy:
            self.setCursor(C.Qt.CursorShape.BusyCursor)
            self.canvas.viewport().setCursor(C.Qt.CursorShape.BusyCursor)
        else:
            self.unsetCursor()
            self.canvas.viewport().unsetCursor()

    def open_card(self, entry):
        self.seed = deepcopy(entry)
        self.controller.resume()
        self.title.setText('Discover from ' + entry.name)
        self.canvas.document.deck.entries = []
        self.canvas.refresh()
        with C.QSignalBlocker(self.illegal):
            self.illegal.setChecked(self.editor.document.editor_preferences.get('include_illegal_cards', False))
        self.show()
        self.raise_()
        self.search()

    def query(self):
        return json.dumps(dict(seed=self.seed.to_dict(), document=self.editor.document.to_dict(), mode=self.tabs.currentIndex()), sort_keys=True)

    def context(self):
        from mtg_core.card_pool import pool_context
        return (json.dumps(self.seed.to_dict(), sort_keys=True), self.tabs.currentIndex(),
                self.editor.document.deck.deck_id, pool_context(self.editor.document),
                self.editor.document.editor_preferences.get('edhrec_cohort'))

    def search(self, *_):
        if self.seed is None or self.editor.closing or not self.isVisible():
            return
        self.canvas.document.deck.entries = []
        self.canvas.refresh()
        self.selection_changed()
        self.request_context = self.context()
        self.controller.search(self.query())

    def deck_changed(self):
        with C.QSignalBlocker(self.illegal):
            self.illegal.setChecked(self.editor.document.editor_preferences.get('include_illegal_cards', False))
        if self.seed is not None and self.isVisible():
            if self.request_context != self.context():
                self.search()
            else:
                update_candidate_quantities(self.editor.document, self.canvas)

    def completed(self, query, snapshot, error):
        if not self.isVisible() or query != self.controller.query or self.request_context != self.context():
            return
        entries = []
        for index, row in enumerate(snapshot.get('results', [])):
            payload = row['payload']
            entries.append(DeckEntry(f"{payload['id']}:{index}", payload['name'], card_id=payload['id'],
                oracle_id=payload.get('oracle_id'), set_code=payload.get('set'),
                collector_number=payload.get('collector_number'), pre_cropped=True,
                extras={'facts': card_facts(payload), 'discovery_reason': row['reason']}))
        self.canvas.document.deck.entries = entries
        update_candidate_quantities(self.editor.document, self.canvas)
        self.canvas.refresh()
        self.status.setText(error or snapshot.get('status', 'No matches are available.'))
        self.selection_changed()

    def selected(self):
        return next((e for e in self.canvas.document.deck.entries if e.entry_id in self.canvas.selected), None)

    def selection_changed(self):
        entry = self.selected()
        self.reason.setText(entry.extras['discovery_reason'] if entry else 'Select a card to see the evidence.')
        self.new_deck.setVisible(self.tabs.currentIndex() == 1)
        self.new_deck.setEnabled(entry is not None)

    def add(self, key, delta=1):
        entry = next((e for e in self.canvas.document.deck.entries if e.entry_id == key), None)
        if entry:
            self.editor.change_candidate_quantity(entry, delta)

    def details(self):
        entry = self.selected()
        if entry:
            self.editor.candidate_details(self.canvas, entry.entry_id)

    def start_deck(self):
        entry = deepcopy(self.selected())
        if entry is None:
            return
        previous = self.editor.document.deck.deck_id
        self.editor.new()
        if previous == self.editor.document.deck.deck_id:
            return
        from .commander_selection import select_commander
        self.editor.edit(lambda d: setattr(d.deck, 'format', 'Commander'))
        self.reject()
        select_commander(self.editor, entry)

    def reject(self):
        self.controller.shutdown()
        self.canvas.preview.hide()
        super().reject()

    def closeEvent(self, event):
        self.controller.shutdown()
        self.canvas.preview.hide()
        super().closeEvent(event)
