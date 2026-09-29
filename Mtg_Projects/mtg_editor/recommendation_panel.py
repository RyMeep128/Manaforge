"""Visual discovery inside Add Card, using the existing engine and card canvas."""

from copy import deepcopy
from datetime import datetime

from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_core.decks import DeckDocument
from mtg_core.recommendation_scoring import settings
from mtg_core.sections import DeckSection
from mtg_ui.theme import COLORS

from .canvas import CardCanvas
from .recommendations import (
    load_recommendations,
    rank_recommendations,
    recommendation_reason,
)
from .tasks import Task


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
    )


class RecommendationCanvas(CardCanvas):
    whyRequested = C.pyqtSignal(str, object)

    def __init__(self, thumbnails, parent=None):
        super().__init__(DeckDocument(), thumbnails, parent, search=True)
        self.card_width = 150
        self.setAccessibleName("Recommended cards")
        self.setToolTip("Double-click or + to add. Why? explains the recommendation.")

    def why_rect(self, rect):
        return C.QRect(rect.x() + 4, rect.y() + 4, 42, 23)

    def paintEvent(self, event):
        if not self.document.deck.entries:
            p = G.QPainter(self.viewport())
            p.fillRect(self.viewport().rect(), G.QColor(COLORS["canvas"]))
            p.end()
            self.thumbnails.set_visible(id(self), [])
            return
        super().paintEvent(event)
        p = G.QPainter(self.viewport())
        offset = self.verticalScrollBar().value()
        p.translate(0, -offset)
        visible = C.QRect(0, offset, self.viewport().width(), self.viewport().height())
        for entry, rect, _ in self.items:
            if not rect.intersects(visible):
                continue
            for control, text in (
                (self.why_rect(rect), "Why?"),
                (self.control_rect(rect), "+ Add"),
            ):
                p.fillRect(control, G.QColor("#20352f"))
                p.setPen(G.QColor("white"))
                p.drawText(control, C.Qt.AlignmentFlag.AlignCenter, text)
        p.end()

    def mousePressEvent(self, event):
        item = self.hit(event.position().toPoint())
        point = event.position().toPoint() + C.QPoint(
            0, self.verticalScrollBar().value()
        )
        if (
            item
            and event.button() == C.Qt.MouseButton.LeftButton
            and self.why_rect(item[1]).contains(point)
        ):
            self.hover_timer.stop()
            self.preview.hide()
            self.whyRequested.emit(item[0].entry_id, event.globalPosition().toPoint())
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        item = self.hit(event.position().toPoint())
        point = event.position().toPoint() + C.QPoint(
            0, self.verticalScrollBar().value()
        )
        if item and self.why_rect(item[1]).contains(point):
            return
        super().mouseDoubleClickEvent(event)

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
        self.provenance = ""
        self.pending = False
        self.timer = C.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(750)
        self.timer.timeout.connect(self.refresh)
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        line = W.QFrame()
        line.setFrameShape(W.QFrame.Shape.HLine)
        layout.addWidget(line)
        header = W.QHBoxLayout()
        self.toggle = W.QToolButton()
        self.toggle.setText("Recommendations")
        self.toggle.setToolButtonStyle(C.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(True)
        self.toggle.setArrowType(C.Qt.ArrowType.DownArrow)
        header.addWidget(self.toggle, 1)
        refresh = W.QToolButton()
        refresh.setText("Refresh")
        refresh.setToolTip("Refresh recommendations from local caches")
        refresh.clicked.connect(self.request_refresh)
        header.addWidget(refresh)
        layout.addLayout(header)
        self.content = W.QWidget()
        body = W.QVBoxLayout(self.content)
        body.setContentsMargins(0, 0, 0, 0)
        self.type_filter = W.QComboBox()
        self.type_filter.setAccessibleName("Recommendation card type")
        self.type_filter.addItems(["All Card Types", *CARD_TYPES])
        self.type_filter.currentTextChanged.connect(self.filter_rows)
        body.addWidget(self.type_filter)
        self.status = W.QLabel("Recommendations load from your local dataset.")
        self.status.setWordWrap(True)
        body.addWidget(self.status)
        self.canvas = RecommendationCanvas(editor.thumbnails, self)
        self.canvas.quantityRequested.connect(self.add)
        self.canvas.whyRequested.connect(self.why)
        body.addWidget(self.canvas, 1)
        layout.addWidget(self.content, 1)
        self.toggle.toggled.connect(self.expand)

    def expand(self, expanded):
        self.content.setVisible(expanded)
        self.setMaximumHeight(
            16777215 if expanded else self.toggle.sizeHint().height() + 20
        )
        self.toggle.setArrowType(
            C.Qt.ArrowType.DownArrow if expanded else C.Qt.ArrowType.RightArrow
        )
        if expanded:
            self.deck_changed()
        else:
            self.suspend()

    def active(self):
        return self.isVisible() and self.toggle.isChecked() and not self.editor.closing

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
        self.update_quantities()
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
        latest = max(
            (source["imported"] for source in snapshot["sources"]), default=None
        )
        stamp = (
            datetime.fromtimestamp(latest).isoformat(timespec="minutes")
            if latest
            else "never"
        )
        self.provenance = (
            f"{snapshot['source']} · {snapshot['decks']} decks · updated {stamp}\n"
            + "\n".join(
                f"{s['source']}: {s['status']}" for s in snapshot["source_status"]
            )
            + "\n"
            + snapshot["formula"]
        )
        self.provenance += "\nCommander color identity " + (
            "applied."
            if snapshot["color_filtered"]
            else "unavailable; no color restriction applied."
        )
        self.status.setToolTip(self.provenance)
        self.filter_rows()

    def finished(self):
        self.worker.deleteLater()
        self.worker = None
        if self.pending and self.active() and self.loaded_key != self.key:
            self.timer.start()

    def filter_rows(self):
        kind = self.type_filter.currentText()
        dismissed = settings(self.editor.document)["dismissed"]
        self.canvas.document.deck.entries = [
            row["entry"]
            for row in self.rows
            if row["oracle_id"] not in dismissed
            and (kind == "All Card Types" or kind in card_types(row["entry"]))
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
        quantities = {}
        for entry in self.editor.document.deck.entries:
            if entry.section in (DeckSection.MAINBOARD, DeckSection.COMMANDER):
                identity = entry.oracle_id or entry.card_id
                quantities[identity] = quantities.get(identity, 0) + entry.quantity
        for row in self.rows:
            entry = row["entry"]
            entry.quantity = quantities.get(entry.oracle_id or entry.card_id, 0)
        self.canvas.viewport().update()

    def add(self, entry_id, _delta=1):
        row = next((r for r in self.rows if r["entry"].entry_id == entry_id), None)
        if row:
            entry = deepcopy(row["entry"])
            entry.extras["category_suggestion"] = row["roles"]
            self.editor.add_card(entry)

    def why(self, entry_id, position):
        row = next((r for r in self.rows if r["entry"].entry_id == entry_id), None)
        if not row:
            return
        menu = W.QMenu(self)
        info = W.QLabel(recommendation_reason(row) + "\n\n" + self.provenance)
        info.setTextFormat(C.Qt.TextFormat.PlainText)
        info.setWordWrap(True)
        info.setMaximumWidth(360)
        info.setMargin(10)
        scroll = W.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedSize(380, 280)
        scroll.setWidget(info)
        action = W.QWidgetAction(menu)
        action.setDefaultWidget(scroll)
        menu.addAction(action)
        dismiss = menu.addAction("Dismiss recommendation")
        if menu.exec(position) is dismiss:
            prefs = settings(self.editor.document)
            prefs["dismissed"].append(row["oracle_id"])
            self.editor.edit(
                lambda d: d.editor_preferences.update(recommendations=prefs)
            )
            self.filter_rows()

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
