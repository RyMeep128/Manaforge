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
    panel.membership.setCurrentIndex(0)
    editor.syntax_membership.setCurrentIndex(0)
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


def test_recommendation_filters_preserve_order_and_follow_deck_edits(editor):
    panel = editor.recommendation_panel
    panel.rows = [recommendation(2), recommendation(1), recommendation(3)]
    panel.rows[2]["roles"] = [dict(name="Draw")]
    panel.role_filter.addItems(["Ramp", "Draw"])
    panel.role_filter.setCurrentText("Ramp")
    assert [entry.entry_id for entry in panel.canvas.document.deck.entries] == [
        "e2",
        "e1",
    ]
    panel.text_filter.setText("Card 1")
    assert [entry.entry_id for entry in panel.canvas.document.deck.entries] == ["e1"]
    panel.membership.setCurrentIndex(1)
    panel.add("e1")
    assert not panel.canvas.document.deck.entries
    editor.undo()
    assert [entry.entry_id for entry in panel.canvas.document.deck.entries] == ["e1"]
    assert panel.text_filter.text() == "Card 1"


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
    assert len(first_row) == 1
    assert first_row[0].width() >= 250
    assert abs(first_row[0].height() / first_row[0].width() - 1.4) < 0.01
    assert 0 < len(thumbs.requested) < 20
    adds = []
    assert not hasattr(canvas, "whyRequested")
    canvas.quantityRequested.connect(lambda entry, delta: adds.append(entry))
    rect = canvas.items[0][1]
    QtTest.QTest.mouseClick(
        canvas.viewport(),
        C.Qt.MouseButton.LeftButton,
        pos=dict(canvas.quantity_buttons(rect))[1].center(),
    )
    assert adds == ["e0"]
    canvas.resize(700, 330)
    app.processEvents()
    assert len([r for _, r, _ in canvas.items if r.y() == canvas.items[0][1].y()]) == 2
    canvas.resize(1600, 600)
    app.processEvents()
    assert len([r for _, r, _ in canvas.items if r.y() == canvas.items[0][1].y()]) == 5
    details = []
    canvas.detailsRequested.connect(details.append)
    QtTest.QTest.mouseClick(
        canvas.viewport(), C.Qt.MouseButton.LeftButton, pos=canvas.items[0][1].center()
    )
    assert canvas.detail_timer.isActive()
    canvas.detail_timer.stop()
    canvas.open_details()
    assert details == ["e0"]
    assert adds == ["e0"]
    canvas.verticalScrollBar().setValue(canvas.verticalScrollBar().maximum())
    app.processEvents()
    assert "p99" in thumbs.requested
    canvas.hide()
    assert thumbs.visible[id(canvas)] == set()
    canvas.preview.close()
    canvas.close()


def test_category_browsing_does_not_consume_card_undo_and_repeat_add_is_ignored(editor):
    panel = editor.recommendation_panel
    panel.rows = [recommendation(1, "Creature"), recommendation(2, "Instant")]
    panel.change_category("Creatures")
    panel.add("e1")
    panel.add("e1")
    assert len(editor.document.deck.entries) == 1
    assert editor.document.deck.entries[0].quantity == 1
    panel.change_category("Instants")
    assert panel.selected_category == "Instants"
    editor.undo()
    assert not editor.document.deck.entries
    assert panel.selected_category == "Instants"
    editor.redo()
    assert editor.document.deck.entries[0].quantity == 1


def test_compact_recommendations_prioritize_grid_and_use_responsive_categories(
    editor, monkeypatch
):
    panel = editor.recommendation_panel
    monkeypatch.setattr(panel, "active", lambda: False)
    panel.rows = [recommendation(i) for i in range(50)]
    panel.filter_rows()
    panel.setParent(None)
    panel.resize(1300, 800)
    panel.show()
    W.QApplication.processEvents()
    assert panel.canvas.card_width == 270
    assert panel.canvas.height() >= panel.height() * 0.75
    assert not hasattr(panel, "commander_art")
    assert not panel.type_tabs.isHidden()
    assert panel.category_combo.isHidden()
    assert not hasattr(panel, "categories")
    assert not hasattr(panel, "cohort_status")
    assert panel.selected_category == "Top Cards"
    panel.resize(500, 700)
    W.QApplication.processEvents()
    assert not panel.type_tabs.isHidden()
    assert panel.category_combo.isHidden()
    assert panel.canvas.width() <= panel.width()
    assert panel.audience.width() <= panel.width()
    panel.hide()
    panel.setParent(editor)


def test_modes_preserve_categories_and_filter_role_overlap_in_ranked_order(editor):
    panel = editor.recommendation_panel
    panel.deck_changed()
    panel.rows = [recommendation(2), recommendation(1), recommendation(3, "Instant")]
    panel.rows[0]["roles"].append(dict(name="Draw"))
    panel.rows[2]["roles"] = [dict(name="Draw")]
    panel.available_roles = ["Draw", "Ramp"]
    panel.change_category("Creatures")
    panel.shown_limit = 100
    panel.browse_modes.setCurrentIndex(1)
    assert panel.selected_category == "Top Cards"
    panel.change_category("Role: Draw")
    assert [entry.entry_id for entry in panel.canvas.document.deck.entries] == [
        "e2",
        "e3",
    ]
    panel.browse_modes.setCurrentIndex(0)
    assert panel.selected_category == "Creatures"
    assert panel.shown_limit == 100
    panel.browse_modes.setCurrentIndex(1)
    assert panel.selected_category == "Role: Draw"
    saved = deepcopy(editor.document.editor_preferences["recommendation_browse"])
    panel.view_snapshot = None
    assert panel.restore_view()
    assert panel.browse_mode == "roles"
    assert panel.selected_category == "Role: Draw"
    assert editor.document.editor_preferences["recommendation_browse"] == saved


def test_legacy_filters_and_missing_audience_are_preserved(editor):
    panel = editor.recommendation_panel
    editor.document.editor_preferences.update(
        recommendation_browse=dict(
            category="Utility Lands",
            kind="Land",
            role="Ramp",
            positions={"Utility Lands": [20, 100]},
            sidebar=False,
        ),
        edhrec_cohort="theme:missing-theme",
    )
    panel.restore_view()
    panel.sync_audience()
    assert panel.selected_category == "Top Cards"
    assert panel.special_category.currentData() == "Utility Lands"
    assert panel.type_filter.currentText() == "Land"
    assert panel.role_filter.currentText() == "Ramp"
    assert panel.audience.currentData() == "theme:missing-theme"
    panel.save_view()
    assert (
        editor.document.editor_preferences["recommendation_browse"]["sidebar"] is False
    )
    assert editor.document.editor_preferences["edhrec_cohort"] == "theme:missing-theme"


def test_inline_audience_applies_immediately_and_undo_restores_selection(editor):
    panel = editor.recommendation_panel
    panel.deck_changed()
    assert panel.audience.currentData() == "auto"
    panel.audience.setCurrentIndex(panel.audience.findData("general"))
    assert editor.document.editor_preferences["edhrec_cohort"] == "general"
    editor.undo()
    assert panel.audience.currentData() == "auto"
    panel.suspend()


def test_audience_loading_handles_missing_cache_and_rejects_stale_results(
    editor, monkeypatch
):
    from mtg_editor.tasks import Task
    from mtg_core import edhrec_cohorts
    import sqlite3

    panel = editor.recommendation_panel
    monkeypatch.setattr(Task, "start", lambda self: None)
    monkeypatch.setattr(
        edhrec_cohorts,
        "cohort_options",
        lambda path: [
            ("theme", "tokens", "Tokens"),
            ("bracket", "core", "Bracket 2: Core"),
        ],
    )
    panel.load_audiences(("first",))
    worker = panel.audience_worker
    options = worker.work()
    worker.completed.emit(options, "")
    assert panel.audience.findData("theme:tokens") >= 0
    assert panel.audience.findData("bracket:core") >= 0
    panel.audiences_finished()

    def locked(path):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(edhrec_cohorts, "cohort_options", locked)
    panel.load_audiences(("second",))
    worker = panel.audience_worker
    assert worker.work() == []
    panel.audience_generation += 1
    worker.completed.emit([], "")
    assert panel.audience.findData("theme:tokens") >= 0
    panel.audience_generation -= 1
    worker.completed.emit([], "")
    assert panel.audience.findData("theme:tokens") < 0
    assert panel.audience.findData("auto") >= 0
    panel.audiences_finished()


def test_workspace_card_size_survives_return_to_quick_panel(editor, monkeypatch):
    workspace = editor.add_cards_workspace
    panel = editor.recommendation_panel
    monkeypatch.setattr(panel, "active", lambda: False)
    panel.deck_changed()
    workspace.expanded = True
    assert workspace.zoom.minimum() == 180
    assert workspace.zoom.maximum() == 360
    workspace.zoom.setValue(320)
    assert panel.canvas.card_width == 320
    workspace.expanded = False
    panel.set_expanded(False)
    assert panel.canvas.card_width == 320
    assert (
        editor.document.editor_preferences["recommendation_browse"]["card_width"] == 320
    )


def test_view_metadata_does_not_invalidate_ranked_candidates(editor):
    before = context_key(editor.document)
    editor.document.deck.name = "Renamed deck"
    editor.document.deck.extras["library_association"] = {"id": "friends"}
    editor.document.editor_preferences["recommendation_browse"] = {"mode": "roles"}
    assert context_key(editor.document) == before


def test_completed_candidates_are_not_reloaded_for_a_pending_page(editor, monkeypatch):
    panel = editor.recommendation_panel
    monkeypatch.setattr(panel, "active", lambda: True)
    panel.key = panel.loaded_key = ("same",)
    panel.pending = panel.pending_page = True
    requested = []
    monkeypatch.setattr(panel, "request_page", lambda: requested.append(True))
    panel.refresh()
    assert not panel.pending
    assert requested == [True]


def test_recommendation_context_batches_card_reads():
    from mtg_core.decks import DeckDocument
    from mtg_editor.recommendations import recommendation_context

    calls = []

    class Database:
        def categorization_data(self, card_ids, oracle_ids):
            calls.append(list(card_ids))
            return {
                "cards": {key: {"type_line": "Creature", "cmc": 3} for key in card_ids}
            }

    class Service:
        database = Database()

        def analyze_entries(self, entries):
            return {}

        def get_card(self, **kwargs):
            raise AssertionError("Context must not read one card at a time")

    document = DeckDocument()
    document.deck.entries = [
        DeckEntry(str(i), "Card", card_id="printing") for i in range(100)
    ]
    recommendation_context(Service(), document)
    assert calls == [["printing"]]


def test_read_only_canvas_does_not_emit_edit_actions():
    from mtg_core.decks import DeckDocument

    app = W.QApplication.instance() or W.QApplication([])

    class Thumbnails(C.QObject):
        updated = C.pyqtSignal()

        def set_visible(self, *args):
            pass

        def get(self, *args):
            return None

    from mtg_editor.canvas import CardCanvas

    document = DeckDocument()
    document.deck.entries = [DeckEntry("card", "Shared card")]
    canvas = CardCanvas(document, Thumbnails())
    canvas.read_only = True
    canvas.selected = {"card"}
    actions = []
    canvas.quantityRequested.connect(lambda *args: actions.append(args))
    canvas.quickTagRequested.connect(lambda *args: actions.append(args))
    for key in (C.Qt.Key.Key_Delete, C.Qt.Key.Key_Backspace, C.Qt.Key.Key_T):
        QtTest.QTest.keyClick(canvas, key)
    assert actions == []
    assert document.deck.entries[0].quantity == 1
    canvas.close()
    canvas.preview.close()
    app.processEvents()
