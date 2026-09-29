from copy import deepcopy

import pytest
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W, QtTest
from mtg_core.decks import DeckEntry
from mtg_editor.gui import EditorWindow
from mtg_editor.recommendation_panel import (
    RecommendationCanvas,
    card_types,
    context_key,
)
from mtg_editor.recommendations import rank_recommendations
from mtg_core.recommendation_scoring import settings


@pytest.fixture
def editor(tmp_path):
    app = W.QApplication.instance() or W.QApplication([])
    window = EditorWindow(service=object(), root=tmp_path)
    yield window
    window.recommendation_panel.suspend()
    window.close()
    app.processEvents()


def recommendation(number, line="Legendary Artifact Creature — Golem"):
    return dict(
        oracle_id=f"o{number}",
        entry=DeckEntry(
            f"e{number}",
            f"Card {number}",
            card_id=f"p{number}",
            oracle_id=f"o{number}",
            extras={"facts": {"type_line": line}},
        ),
        roles=[dict(name="Ramp", reason="fixture")],
        score=1,
        primary_score=1,
        baseline=0.1,
        inclusion=0.5,
        synergy=0.4,
        sample=20,
    )


def test_search_and_recommendation_add_share_history_and_quantity(editor):
    panel = editor.recommendation_panel
    row = recommendation(1)
    panel.rows = [row]
    panel.filter_rows()
    editor.search_document.deck.entries = [deepcopy(row["entry"])]
    assert row["entry"].quantity == 0
    panel.add("e1")
    assert editor.document.deck.entries[0].quantity == 1
    assert row["entry"].quantity == 1
    assert editor.session.dirty and editor.autosave.isActive()
    editor.add_result("e1")
    assert row["entry"].quantity == 2
    assert len(editor.grid.items) == 1
    editor.undo()
    assert row["entry"].quantity == 1
    editor.redo()
    assert row["entry"].quantity == 2
    assert editor.save()
    path = editor.path
    editor.new()
    editor.open_path(path)
    assert editor.document.deck.entries[0].quantity == 2


def test_multitype_and_faces_filter_without_reordering_or_changing_search(editor):
    panel = editor.recommendation_panel
    panel.rows = [
        recommendation(1),
        recommendation(2, "Instant"),
        recommendation(3, "Creature — Elf Druid"),
    ]
    panel.rows[1]["entry"].extras["facts"]["card_faces"] = [{"type_line": "Land"}]
    assert card_types(panel.rows[0]["entry"]) == {"Artifact", "Creature"}
    editor.search_document.deck.entries = [DeckEntry("search", "Untouched")]
    for kind, expected in [
        ("Creature", ["e1", "e3"]),
        ("Artifact", ["e1"]),
        ("Land", ["e2"]),
    ]:
        panel.type_filter.setCurrentText(kind)
        assert [e.entry_id for e in panel.canvas.document.deck.entries] == expected
    assert editor.search_document.deck.entries[0].entry_id == "search"
    editor.document.editor_preferences["recommendations"] = {"dismissed": ["o1"]}
    panel.type_filter.setCurrentText("All Card Types")
    assert [e.entry_id for e in panel.canvas.document.deck.entries] == ["e2", "e3"]


def test_shared_ranking_and_stale_completion_after_deck_change(editor, monkeypatch):
    panel = editor.recommendation_panel
    ctx = dict(gaps={}, themes=[], archetypes=[], average=None, known=0)
    rows = [recommendation(2), recommendation(1)]
    rows[0]["score"] = 0.5
    ranked = rank_recommendations(rows, ctx, settings(editor.document))
    assert [r["oracle_id"] for r in ranked] == ["o1", "o2"]
    panel.deck_changed()
    key, generation = deepcopy(panel.key), panel.generation
    editor.document.deck.entries.append(DeckEntry("changed", "New card"))
    editor.changed()
    monkeypatch.setattr(panel, "active", lambda: True)
    panel.completed(generation, key, {"ranked": ranked}, "")
    assert not panel.rows
    assert context_key(editor.document) != key
    panel.suspend()
    assert not panel.timer.isActive()


def test_virtual_grid_resizes_and_only_requests_visible_thumbnails():
    app = W.QApplication.instance() or W.QApplication([])

    class Thumbnails(C.QObject):
        updated = C.pyqtSignal()

        def __init__(self):
            super().__init__()
            self.requested, self.visible = set(), {}
            self.pixmap = G.QPixmap(150, 210)
            self.pixmap.fill(G.QColor("green"))

        def set_visible(self, owner, keys):
            self.visible[owner] = set(keys)

        def get(self, card_id, asset_id=None):
            self.requested.add(card_id)
            return self.pixmap

    thumbs = Thumbnails()
    canvas = RecommendationCanvas(thumbs)
    canvas.document.deck.entries = [recommendation(i)["entry"] for i in range(100)]
    canvas.resize(330, 330)
    canvas.show()
    app.processEvents()
    first_row = [r for _, r, _ in canvas.items if r.y() == canvas.items[0][1].y()]
    assert len(first_row) == 2
    assert abs(first_row[0].height() / first_row[0].width() - 1.4) < 0.01
    assert 0 < len(thumbs.requested) < 20
    reasons, adds = [], []
    canvas.whyRequested.connect(lambda entry, point: reasons.append(entry))
    canvas.quantityRequested.connect(lambda entry, delta: adds.append(entry))
    rect = canvas.items[0][1]
    QtTest.QTest.mouseClick(
        canvas.viewport(),
        C.Qt.MouseButton.LeftButton,
        pos=canvas.why_rect(rect).center(),
    )
    assert reasons == ["e0"] and not adds
    QtTest.QTest.mouseClick(
        canvas.viewport(),
        C.Qt.MouseButton.LeftButton,
        pos=canvas.control_rect(rect).center(),
    )
    assert adds == ["e0"]
    canvas.resize(700, 330)
    app.processEvents()
    assert len([r for _, r, _ in canvas.items if r.y() == canvas.items[0][1].y()]) >= 3
    canvas.verticalScrollBar().setValue(canvas.verticalScrollBar().maximum())
    app.processEvents()
    assert "p99" in thumbs.requested
    canvas.hide()
    assert thumbs.visible[id(canvas)] == set()
    canvas.preview.close()
    canvas.close()
