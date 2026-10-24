"""Visual discovery inside Add Card, using the existing engine and card canvas."""

from copy import deepcopy

from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_core.decks import DeckDocument
from mtg_core.recommendation_scoring import settings
from mtg_ui.theme import COLORS

from .canvas import CardCanvas
from .recommendations import (
    load_recommendations,
    rank_recommendations,
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
            if switched:
                self.rows = []
                self.filter_rows()
        self.filter_rows()
        if self.active() and self.loaded_key != key:
            self.pending = True
            self.timer.start()

    def request_refresh(self):
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

        # All store/card resolution and scoring stays off the GUI thread.
        def load():
            snapshot = load_recommendations(
                service,
                document,
                self.editor.recommendation_store(),
                include_present=True,
            )
            snapshot["ranked"] = rank_recommendations(
                snapshot["results"], snapshot["deck_context"], settings(document)
            )
            return snapshot

        self.status.setText("Updating recommendations…")
        self.worker = Task(load, self, operation="sidebar recommendations")
        self.worker.completed.connect(
            lambda result, error: self.completed(generation, key, result, error)
        )
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
        self.rows = snapshot["ranked"]
        current = self.role_filter.currentText()
        roles = sorted({role["name"] for row in self.rows for role in row["roles"]})
        with C.QSignalBlocker(self.role_filter):
            self.role_filter.clear()
            self.role_filter.addItems(["All roles", *roles])
            self.role_filter.setCurrentText(current if current in roles else "All roles")
        self.filter_rows()

    def finished(self):
        self.worker.deleteLater()
        self.worker = None
        if self.pending and self.active() and self.loaded_key != self.key:
            self.timer.start()

    def filter_rows(self):
        for row in self.rows:
            row['entry'].extras['category_suggestion'] = row['roles']
        kind = self.type_filter.currentText()
        from .organization import in_deck_entries
        present = in_deck_entries(self.editor.document, [row["entry"] for row in self.rows])
        text = self.text_filter.text().strip().casefold()
        role = self.role_filter.currentText()
        membership = self.membership.currentIndex()
        dismissed = settings(self.editor.document)["dismissed"]
        self.canvas.document.deck.entries = [
            row["entry"]
            for row in self.rows
            if row["oracle_id"] not in dismissed
            and (kind == "All Card Types" or kind in card_types(row["entry"]))
            and (not text or text in (row["entry"].name + " " + str(row["entry"].extras.get("facts", {}).get("oracle_text") or "")).casefold())
            and (role == "All roles" or any(item["name"] == role for item in row["roles"]))
            and (membership == 0 or (row["entry"].entry_id in present) == (membership == 2))
        ]
        count = len(self.canvas.document.deck.entries)
        self.status.setText(
            f"{count} recommendations · quantities show mainboard + commander"
            if count
            else "No recommendations for this type or deck. Check the cache/source settings or refresh."
        )
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
        self.editor.candidate_menu(self.canvas, entry_id, position, self.add)

    def suspend(self):
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
