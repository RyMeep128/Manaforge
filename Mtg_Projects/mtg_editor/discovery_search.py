"""Plain-language controls backed by the editor's local search controller."""
import json

from PyQt6 import QtWidgets as W
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_core.categorization import classify

from .canvas import CardCanvas
from .card_drop import CardDropPanel, CardSearchEdit
from .search import SearchController
from .organization import card_facts, in_deck_entries, update_candidate_quantities
from .recommendation_panel import CARD_TYPES


class CardSearchPanel(CardDropPanel):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.rows = []
        self.result_error = ''
        self.controller = SearchController(editor.service, self)
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        search = W.QHBoxLayout()
        self.name = CardSearchEdit()
        self.name.setPlaceholderText('Search cards by name or Scryfall syntax')
        self.name.setAccessibleName('Card name')
        self.name.setMinimumHeight(38)
        self.name.setClearButtonEnabled(True)
        self.name.textChanged.connect(self.query_changed)
        self.name.returnPressed.connect(self.search)
        search.addWidget(self.name, 1)
        button = W.QPushButton('Search')
        button.setProperty('buttonRole', 'primary')
        button.clicked.connect(self.search)
        search.addWidget(button)
        self.cancel = W.QPushButton('Cancel')
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.controller.cancel)
        search.addWidget(self.cancel)
        layout.addLayout(search)
        filters = W.QHBoxLayout()
        self.color = W.QComboBox()
        for label, value in [('Any color', ''), ('White', 'w'), ('Blue', 'u'),
                             ('Black', 'b'), ('Red', 'r'), ('Green', 'g'), ('Colorless', 'c')]:
            self.color.addItem(label, value)
        self.kind = W.QComboBox()
        self.kind.addItems(['All card types', *CARD_TYPES])
        self.mana = W.QSpinBox()
        self.mana.setRange(-1, 100)
        self.mana.setSpecialValueText('Any mana value')
        self.mana.setValue(-1)
        self.mana.setAccessibleName('Mana value')
        self.membership = W.QComboBox()
        self.membership.addItems(['All cards', 'Not in deck', 'In deck'])
        self.membership.setCurrentIndex(1)
        for control in (self.color, self.kind, self.mana, self.membership):
            filters.addWidget(control)
        layout.addLayout(filters)
        include_illegal = W.QCheckBox('Include illegal cards')
        include_illegal.setAccessibleDescription('Ignore deck format and commander color identity defaults')
        include_illegal.setChecked(editor.document.editor_preferences.get('include_illegal_cards', False))
        include_illegal.toggled.connect(editor.set_include_illegal)
        self.include_illegal = include_illegal
        layout.addWidget(include_illegal)
        self.color.setAccessibleName('Card color')
        self.kind.setAccessibleName('Card type')
        self.color.currentIndexChanged.connect(self.query_changed)
        self.kind.currentIndexChanged.connect(self.query_changed)
        self.mana.valueChanged.connect(self.query_changed)
        self.membership.currentIndexChanged.connect(self.update_quantities)
        self.status = W.QLabel('Search your local card catalog by name or choose filters.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.canvas = CardCanvas(DeckDocument(), editor.thumbnails, search=True)
        self.canvas.card_width = 190
        self.canvas.quantityRequested.connect(self.add)
        self.canvas.detailsRequested.connect(lambda key: editor.candidate_details(self.canvas, key))
        self.canvas.menuRequested.connect(
            lambda key, point: editor.candidate_menu(self.canvas, key, point, self.add))
        layout.addWidget(self.canvas, 1)
        self.more = W.QPushButton('Load More')
        self.more.hide()
        self.more.clicked.connect(self.controller.load_more)
        layout.addWidget(self.more)
        self.controller.pageStateChanged.connect(self.more.setVisible)
        self.controller.busyChanged.connect(lambda busy: self.more.setEnabled(not busy))
        self.controller.resultsReady.connect(self.completed)
        self.controller.cleared.connect(self.clear)
        self.controller.statusChanged.connect(self.status.setText)
        self.controller.busyChanged.connect(self.cancel.setEnabled)

    def query(self):
        parts = []
        if self.name.text().strip():
            value = self.name.text().strip()
            parts.append('(' + value + ')' if self.editor.search_draft.syntax else
                         'name:' + json.dumps(value, ensure_ascii=False))
        if self.color.currentData():
            parts.append('c:' + self.color.currentData())
        if self.kind.currentIndex():
            parts.append('t:' + self.kind.currentText().lower())
        if self.mana.value() >= 0:
            parts.append('mv=' + str(self.mana.value()))
        from mtg_core.card_pool import deck_query
        return deck_query(' '.join(parts), self.editor.document)

    def query_changed(self, *_):
        if self.name.text() != self.editor.search_draft.text:
            self.editor.search_draft.set_text(self.name.text())
            return
        self.controller.change_query(self.query())

    def search(self):
        self.controller.search(self.query())

    def completed(self, query, results, error):
        if query != self.query():
            return
        self.result_error = error
        previous = {entry.card_id: entry for entry in self.rows}
        self.rows = [previous.get(r.card_id) or DeckEntry(r.card_id, r.name, card_id=r.card_id, oracle_id=r.oracle_id,
                              set_code=r.set_code, collector_number=r.collector_number,
                              pre_cropped=True, extras={'facts': card_facts(getattr(r, 'payload', {}) or {}),
                                  'category_suggestion': (getattr(r, 'payload', {}) or {}).get(
                                      '_category_evidence', classify(getattr(r, 'payload', {}) or {}))})
                     for r in results]
        self.update_quantities()
        self.status.setText(error or (f'Showing {len(self.canvas.document.deck.entries)} results. ' +
            ('Load More for additional results.' if self.controller.has_more else 'All available results loaded.')))

    def clear(self):
        self.rows = []
        self.result_error = ''
        self.update_quantities()

    def update_quantities(self, *_):
        from PyQt6.QtCore import QSignalBlocker
        with QSignalBlocker(self.include_illegal):
            self.include_illegal.setChecked(self.editor.document.editor_preferences.get('include_illegal_cards', False))
        present = in_deck_entries(self.editor.document, self.rows)
        membership = self.membership.currentIndex()
        self.canvas.document.deck.entries = [entry for entry in self.rows
            if membership == 0 or (entry.entry_id in present) == (membership == 2)]
        update_candidate_quantities(self.editor.document, self.canvas)
        self.canvas.refresh()
        if self.rows and not self.result_error:
            self.status.setText(f'Showing {len(self.canvas.document.deck.entries)} results. ' +
                ('Load More for additional results.' if self.controller.has_more else 'All available results loaded.'))

    def add(self, entry_id, delta=1):
        entry = next((entry for entry in self.rows if entry.entry_id == entry_id), None)
        if entry:
            self.editor.change_candidate_quantity(entry, delta)

    def hideEvent(self, event):
        self.controller.cancel()
        self.canvas.hover_timer.stop()
        self.canvas.preview.hide()
        self.editor.thumbnails.set_visible(id(self.canvas), [])
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self.query() and not self.rows and not self.editor.closing:
            self.search()
