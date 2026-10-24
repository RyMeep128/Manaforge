"""Visual discovery inside Add Card, using the existing engine and card canvas."""

from copy import deepcopy
from threading import Event

from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_core.decks import DeckDocument
from mtg_core.recommendation_scoring import settings
from mtg_ui.theme import COLORS

from .canvas import CardCanvas
from .recommendations import (
    load_recommendations,
)
from .tasks import Task
from .organization import update_candidate_quantities


CARD_TYPES = (
    "Artifact",
    "Creature",
    "Enchantment",
    "Instant",
    "Land",
    "Planeswalker",
    "Sorcery",
)


def card_types(entry):
    facts = entry.extras.get("facts") or {}
    lines = [facts.get("type_line") or ""] + [
        face.get("type_line") or "" for face in facts.get("card_faces") or []
    ]
    return {
        word
        for line in lines
        for half in line.split("//")
        for word in half.split("—")[0].split()
    } & set(CARD_TYPES)


def context_key(document):
    data = document.to_dict()
    return (
        data["deck"],
        deepcopy(document.editor_preferences.get("guidance")),
        deepcopy(document.editor_preferences.get("recommendations")),
        deepcopy(data.get("artwork_preferences")),
    )


class RecommendationCanvas(CardCanvas):
    def __init__(self, thumbnails, parent=None):
        super().__init__(DeckDocument(), thumbnails, parent, search=True)
        self.card_width = 190
        self.setAccessibleName("Recommended cards")

    def paintEvent(self, event):
        if self.document.deck.entries:
            super().paintEvent(event)
        else:
            painter = G.QPainter(self.viewport())
            painter.fillRect(self.viewport().rect(), G.QColor(COLORS["canvas"]))
            painter.end()
            self.thumbnails.set_visible(id(self), [])

    def hideEvent(self, event):
        self.hover_timer.stop()
        self.preview.hide()
        self.thumbnails.set_visible(id(self), [])
        super().hideEvent(event)


class RecommendationPanel(W.QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.worker = None
        self.generation = 0
        self.key = None
        self.loaded_key = None
        self.rows = []
        self.pages = None
        self.shown_limit = 50
        self.page_generation = 0
        self.pending_page = False
        self.cancelled = Event()
        self.pending = False
        self.timer = C.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(750)
        self.timer.timeout.connect(self.refresh)
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        header = W.QHBoxLayout()
        self.filter_layout = header
        header.setDirection(W.QBoxLayout.Direction.TopToBottom)
        refresh = W.QToolButton()
        refresh.setText("Refresh")
        refresh.setToolTip("Refresh recommendations from local caches")
        refresh.clicked.connect(self.request_refresh)
        self.content = W.QWidget()
        body = W.QVBoxLayout(self.content)
        body.setContentsMargins(0, 0, 0, 0)
        self.type_filter = W.QComboBox()
        self.type_filter.setAccessibleName("Recommendation card type")
        self.type_filter.addItems(["All Card Types", *CARD_TYPES])
        self.type_filter.currentTextChanged.connect(self.filter_rows)
        header.addWidget(self.type_filter, 1)
        header.addWidget(refresh)
        body.addLayout(header)
        self.text_filter = W.QLineEdit()
        self.text_filter.setPlaceholderText("Find a recommended card")
        self.text_filter.setMinimumHeight(38)
        self.text_filter.setClearButtonEnabled(True)
        self.text_filter.textChanged.connect(self.filter_rows)
        body.insertWidget(0, self.text_filter)
        self.membership = W.QComboBox()
        self.membership.addItems(["All cards", "Not in deck", "In deck"])
        self.membership.setCurrentIndex(1)
        self.membership.currentIndexChanged.connect(self.filter_rows)
        header.insertWidget(1, self.membership)
        self.role_filter = W.QComboBox()
        self.role_filter.addItem("All roles")
        self.role_filter.currentTextChanged.connect(self.filter_rows)
        header.insertWidget(2, self.role_filter)
        self.type_tabs = W.QTabBar()
        self.type_tabs.setExpanding(False)
        self.type_tabs.setUsesScrollButtons(True)
        for title in ["All Card Types", *CARD_TYPES]:
            self.type_tabs.addTab(title)
        self.type_tabs.currentChanged.connect(self.type_filter.setCurrentIndex)
        self.type_filter.currentIndexChanged.connect(self.type_tabs.setCurrentIndex)
        self.type_tabs.hide()
        body.addWidget(self.type_tabs)
        self.status = W.QLabel("Recommendations load from your local dataset.")
        self.status.setWordWrap(True)
        body.addWidget(self.status)
        self.canvas = RecommendationCanvas(editor.thumbnails, self)
        self.canvas.quantityRequested.connect(self.add)
        self.canvas.detailsRequested.connect(lambda key: self.inspect(key))
        self.canvas.menuRequested.connect(self.card_menu)
        body.addWidget(self.canvas, 1)
        self.more = W.QPushButton('Load More')
        self.more.hide()
        self.more.clicked.connect(self.load_more)
        body.addWidget(self.more)
        layout.addWidget(self.content, 1)

    def active(self):
        return self.isVisible() and not self.editor.closing

    def set_expanded(self, expanded):
        self.type_tabs.hide()
        self.type_filter.show()
        self.filter_layout.setDirection(W.QBoxLayout.Direction.LeftToRight if expanded
                                        else W.QBoxLayout.Direction.TopToBottom)

    def deck_changed(self):
        key = context_key(self.editor.document)
        if key != self.key:
            switched = (
                self.key is not None and key[0]["deck_id"] != self.key[0]["deck_id"]
            )
            self.key = key
            self.generation += 1
            self.cancelled.set()
            if switched:
                self.pages = None
                self.shown_limit = 50
                self.rows = []
        self.filter_rows(reset=False)
        if self.active() and self.loaded_key != key:
            self.pending = True
            self.timer.start()

    def request_refresh(self):
        self.cancelled.set()
        self.loaded_key = None
        self.generation += 1
        self.deck_changed()

    def refresh(self):
        if not self.active():
            return
        if self.worker is not None:
            self.pending = True
            return
        self.pending = False
        generation, key = self.generation, deepcopy(self.key)
        document = deepcopy(self.editor.document)
        service = self.editor.service

        from .recommendation_pages import RecommendationPages
        self.cancelled = Event()
        cancelled = self.cancelled

        def load():
            pages = RecommendationPages()
            load_recommendations(service, document, self.editor.recommendation_store(),
                                 include_present=True, sink=pages.append,
                                 should_cancel=cancelled.is_set)
            return {'pages': pages, 'roles': pages.roles()}

        self.status.setText("Loading recommendations...")
        self.more.setEnabled(False)
        self.worker = Task(load, self, operation="recommendation pages")
        self.worker.completed.connect(
            lambda result, error: self.completed(generation, key, result, error))
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def completed(self, generation, key, snapshot, error):
        if (
            generation != self.generation
            or not self.active()
            or key != context_key(self.editor.document)
        ):
            return
        if error:
            self.status.setText("Could not load recommendations. Use Refresh to retry.")
            self.status.setToolTip(error)
            return
        self.loaded_key = key
        self.pages = snapshot["pages"]
        current = self.role_filter.currentText()
        roles = snapshot["roles"]
        with C.QSignalBlocker(self.role_filter):
            self.role_filter.clear()
            self.role_filter.addItems(["All roles", *roles])
            self.role_filter.setCurrentText(current if current in roles else "All roles")
        self.filter_rows(reset=False)

    def finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.more.setEnabled(True)
        if self.pending and self.active() and self.loaded_key != self.key:
            self.timer.start()
        elif self.pending_page:
            self.request_page()

    def load_more(self):
        if self.worker is not None:
            return
        self.shown_limit += 50
        self.filter_rows(reset=False)

    def filter_rows(self, *_, reset=True):
        if reset:
            self.shown_limit = 50
        self.page_generation += 1
        self.render_rows()
        if self.pages is not None:
            self.pending_page = True
            self.request_page()
        if self.worker is not None:
            self.status.setText('Loading recommendations...')

    def request_page(self):
        if not self.active() or self.worker is not None or self.pages is None:
            return
        self.pending_page = False
        pages, generation = self.pages, self.page_generation
        document = deepcopy(self.editor.document)
        options = dict(limit=self.shown_limit, kind=self.type_filter.currentText(),
                       text=self.text_filter.text(), role=self.role_filter.currentText(),
                       membership=self.membership.currentIndex(),
                       dismissed=settings(document)['dismissed'])
        self.more.setEnabled(False)
        self.status.setText('Loading recommendations...')
        self.worker = Task(lambda: pages.page(document, **options), self, operation='recommendation page')
        def completed(result, error):
            if generation != self.page_generation or pages is not self.pages or not self.active():
                return
            if error:
                self.status.setText('Could not load recommendations. Use Refresh to retry.')
                return
            rows, more = result
            previous = {row['oracle_id']: row['entry'] for row in self.rows}
            for row in rows:
                row['entry'] = previous.get(row['oracle_id'], row['entry'])
            self.rows = rows
            self.render_rows(more)
        self.worker.completed.connect(completed)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def render_rows(self, more=None):
        for row in self.rows:
            row['entry'].extras['category_suggestion'] = row['roles']
        kind = self.type_filter.currentText()
        from .organization import in_deck_entries
        present = in_deck_entries(self.editor.document, [row["entry"] for row in self.rows])
        text = self.text_filter.text().strip().casefold()
        role = self.role_filter.currentText()
        membership = self.membership.currentIndex()
        dismissed = settings(self.editor.document)["dismissed"]
        entries = [
            row["entry"]
            for row in self.rows
            if row["oracle_id"] not in dismissed
            and (kind == "All Card Types" or kind in card_types(row["entry"]))
            and (not text or text in (row["entry"].name + " " + str(row["entry"].extras.get("facts", {}).get("oracle_text") or "")).casefold())
            and (role == "All roles" or any(item["name"] == role for item in row["roles"]))
            and (membership == 0 or (row["entry"].entry_id in present) == (membership == 2))
        ]
        if more is None:
            more = len(entries) > self.shown_limit or (self.pages is not None and not self.more.isHidden())
        self.canvas.document.deck.entries = entries[:self.shown_limit]
        self.more.setVisible(more)
        count = len(self.canvas.document.deck.entries)
        self.status.setText(f'Showing {count} recommendations. ' +
                            ('Load More for additional results.' if more else 'All available results loaded.'))
        if self.pages is None and not self.rows:
            self.status.setText('No recommendations loaded. Use Refresh to search local data.')
        self.update_quantities()
        self.canvas.refresh()

    def update_quantities(self):
        update_candidate_quantities(self.editor.document, self.canvas)

    def add(self, entry_id, _delta=1):
        row = next((r for r in self.rows if r["entry"].entry_id == entry_id), None)
        if row:
            entry = deepcopy(row["entry"])
            entry.extras["category_suggestion"] = row["roles"]
            self.editor.change_candidate_quantity(entry, _delta)

    def inspect(self, entry_id):
        self.editor.candidate_details(self.canvas, entry_id)

    def card_menu(self, entry_id, position):
        self.editor.candidate_menu(self.canvas, entry_id, position, self.add, self.dismiss)

    def dismiss(self, entry_id):
        row = next((row for row in self.rows if row['entry'].entry_id == entry_id), None)
        if row is None:
            return
        preferences = settings(self.editor.document)
        preferences['dismissed'].append(row['oracle_id'])
        self.editor.edit(lambda document: document.editor_preferences.update(recommendations=preferences))

    def suspend(self):
        self.cancelled.set()
        self.page_generation += 1
        self.timer.stop()
        self.pending = False
        self.generation += 1
        self.canvas.preview.hide()
        self.editor.thumbnails.set_visible(id(self.canvas), [])

    def showEvent(self, event):
        super().showEvent(event)
        self.deck_changed()

    def hideEvent(self, event):
        self.suspend()
        super().hideEvent(event)
