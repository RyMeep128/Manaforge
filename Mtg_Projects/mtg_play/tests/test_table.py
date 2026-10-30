"""Deterministic widget acceptance without a runtime or artwork downloads."""

from dataclasses import replace
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
import pytest

from mtg_play.artwork import PlayArtwork
from mtg_play.contracts import (
    AmountConstraint,
    CardCharacteristics,
    CardIdentity,
    CardObservation,
    ChoiceOption,
    ChoiceRequest,
    CombatAssignment,
    GameObject,
    LegalAction,
)
from mtg_play.decisions import DecisionPanel
from mtg_play.table import GameTable
from mtg_play.tests.test_presentation import snapshot


@pytest.fixture
def app():
    return W.QApplication.instance() or W.QApplication([])


class SilentArtwork(C.QObject):
    updated = C.pyqtSignal()

    def __init__(self, service, parent):
        super().__init__(parent)
        self.allowed = ()

    def show_objects(self, objects):
        self.allowed = tuple(objects)

    def get(self, *args, **kwargs):
        return None

    def conceal(self):
        self.allowed = ()


def card(identifier, zone="battlefield", owner="one", name="Bear", **kwargs):
    return GameObject(
        identifier,
        zone,
        owner,
        owner,
        False,
        CardCharacteristics(name=name, type_line="Creature", power="3", toughness="3"),
        **kwargs,
    )


def button(panel, text):
    return next(
        item for item in panel.findChildren(W.QPushButton) if item.text() == text
    )


def test_distinct_objects_live_stats_and_replacement_invalidate_controls(app):
    table = GameTable(object(), artwork_factory=SilentArtwork)
    one, two = card("one-card"), card("two-card")
    view = replace(
        snapshot(),
        objects=(one, two),
        actions=(LegalAction("cast", "cast_spell", one.object_id, "Bear"),),
    )
    calls = []
    table.command.connect(lambda *args: calls.append(args))
    table.present(view)
    assert len(table.player.cards) == 2
    table.player.cards[one.object_id].click()
    assert calls == [(view, "perform", ("cast",))]
    assert "3/3" in table.inspection.toPlainText()
    old_button = button(table.object_actions, "Cast spell")
    table.present(replace(view, revision=2, objects=(two,), actions=()))
    assert set(table.player.cards) == {two.object_id}
    assert not old_button.isEnabled()
    assert not table.inspection.toPlainText()
    table.clear()


def test_hidden_hands_faces_and_artwork_are_concealed_before_next_view(app):
    table = GameTable(object(), artwork_factory=SilentArtwork)
    own = card("own", "hand", name="Private own spell")
    opponent = card("opponent", "hand", "two", "Prohibited identity")
    face_down = replace(
        card("face-down", name="Prohibited face"), hidden=True, face_down=True
    )
    table.present(
        replace(
            snapshot(),
            objects=(own, opponent, face_down),
            observations=(
                CardObservation("observation", "reveal", False, "Private observation"),
            ),
        )
    )
    assert set(table.hand.cards) == {"own"}
    assert table.player.cards["face-down"].accessibleName() == "Face-down card"
    table.select_object("own", interact=False)
    assert "Private own spell" in table.inspection.toPlainText()
    previous_card = table.hand.cards["own"]
    table.clear()
    assert previous_card.obj is None and not previous_card.accessibleName()
    assert not table.inspection.toPlainText()
    assert not table.observations.toPlainText()
    assert not table.artwork.allowed
    assert all(not lane.cards for lane in table.lanes)
    table.present(replace(snapshot("two"), objects=(own, opponent)))
    assert set(table.hand.cards) == {"opponent"}
    assert "Private own spell" not in table.inspection.toPlainText()
    table.clear()


@pytest.mark.parametrize("family", ["boolean", "target", "ability", "options", "piles"])
def test_explicit_choices_use_engine_tokens_and_do_not_auto_answer(app, family):
    panel = DecisionPanel()
    request = ChoiceRequest(
        "decision",
        "one",
        family,
        "Choose a result",
        (ChoiceOption("engine-option", "Choice"),),
    )
    view = replace(snapshot(), decision=request)
    calls = []
    panel.command.connect(lambda *args: calls.append(args))
    panel.present(view)
    assert not calls
    button(panel, "Choice").click()
    assert calls == [(view, "choose", ("engine-option",))]
    assert not any(
        item.text() == "Cancel" for item in panel.findChildren(W.QPushButton)
    )
    panel.clear()


def test_number_amounts_finish_and_cancel_preserve_constraints(app):
    panel = DecisionPanel()
    calls = []
    panel.command.connect(lambda *args: calls.append(args))
    view = replace(
        snapshot(), decision=ChoiceRequest("n", "one", "number", "Pick X", (), 2, 6)
    )
    panel.present(view)
    number = panel.findChild(W.QSpinBox)
    assert (number.minimum(), number.maximum()) == (2, 6)
    number.setValue(5)
    button(panel, "Confirm number").click()
    assert calls[-1] == (view, "choose_number", (5,))
    panel.clear()
    # Process deferred deletion before querying newly-created amount controls.
    C.QCoreApplication.sendPostedEvents(None, C.QEvent.Type.DeferredDelete)
    view = replace(
        view,
        decision=ChoiceRequest(
            "a",
            "one",
            "amounts",
            "Distribute",
            (),
            3,
            3,
            True,
            (AmountConstraint("First", 0, 3), AmountConstraint("Second", 0, 3)),
            True,
        ),
    )
    panel.present(view)
    amounts = panel.findChildren(W.QSpinBox)
    assert not button(panel, "Confirm amounts").isEnabled()
    amounts[0].setValue(2)
    amounts[1].setValue(1)
    button(panel, "Confirm amounts").click()
    assert calls[-1] == (view, "choose_amounts", ((2, 1),))
    button(panel, "Finish selection").click()
    assert calls[-1] == (view, "finish_selection", ())
    button(panel, "Cancel").click()
    assert calls[-1] == (view, "cancel", ())
    panel.clear()


def test_combat_choices_are_card_interactions_and_assignments_are_inspectable(app):
    table = GameTable(object(), artwork_factory=SilentArtwork)
    attacker, blocker = card("attack"), card("block", owner="two")
    view = replace(
        snapshot(),
        step="DECLARE_ATTACKERS",
        objects=(attacker, blocker),
        actions=(
            LegalAction("attack-action", "declare_attacker", "attack", "Bear"),
            LegalAction("done", "pass", None, "Pass / finish selection"),
        ),
    )
    calls = []
    table.command.connect(lambda *args: calls.append(args))
    table.present(view)
    table.player.cards["attack"].click()
    assert calls[-1] == (view, "perform", ("attack-action",))
    assert button(table.decisions, "Finish attackers")
    combat = CombatAssignment(("attack",), ("block",), "two", True)
    table.present(replace(view, revision=2, actions=(), combat=(combat,)))
    table.select_object("attack", interact=False)
    assert "Blocked by: Bear" in table.inspection.toPlainText()
    assert table.opponent.cards["block"].combat == "Blocking"
    table.clear()


def test_missing_artwork_and_double_face_keys_preserve_selected_printing(app):
    identity = CardIdentity("oracle", "selected-showcase", "entry")
    obj = card("physical", card_identity=identity)
    assert PlayArtwork.key(obj)[0] == "selected-showcase"
    transformed = replace(
        obj, characteristics=replace(obj.characteristics, transformed=True)
    )
    assert PlayArtwork.key(transformed)[3] == 1
    assert PlayArtwork.key(replace(obj, hidden=True)) is None
    assert PlayArtwork.key(replace(obj, face_down=True)) is None
    artwork = PlayArtwork(object())
    artwork.show_objects((obj,))
    artwork.cache[artwork.key(obj)] = G.QPixmap()
    assert artwork.get(obj).isNull()
    artwork.conceal()
    assert not artwork.cache and artwork.get(obj) is None


def test_unknown_decision_is_explicit_and_stack_objects_remain_distinct(app):
    table = GameTable(object(), artwork_factory=SilentArtwork)
    view = replace(
        snapshot(),
        objects=(card("spell-one", "stack"), card("spell-two", "stack")),
        decision=ChoiceRequest("new", "one", "unsupported", "New choice", ()),
    )
    table.present(view)
    assert len(table.zone_lanes["stack"].cards) == 2
    assert not table.decisions.isEnabled()
    assert any(
        "not supported" in label.text()
        for label in table.decisions.findChildren(W.QLabel)
    )
    table.clear()


@pytest.mark.parametrize("width,height", [(1000, 610), (1200, 730)])
@pytest.mark.parametrize("stack", [False, True])
def test_focused_board_keeps_battlefields_hand_and_decisions_in_view(
    app, width, height, stack
):
    table = GameTable(object(), artwork_factory=SilentArtwork)
    objects = (
        (card("mine"), card("theirs", owner="two"))
        + tuple(card(f"hand-{index}", "hand") for index in range(7))
        + ((card("spell", "stack"),) if stack else ())
    )
    table.resize(width, height)
    table.show()
    try:
        table.present(
            replace(
                snapshot(),
                objects=objects,
                decision=ChoiceRequest(
                    "priority", "one", "selection", "Select an action", ()
                ),
            )
        )
        app.processEvents()
        assert table.view_mode == "focused"
        assert table.board.parentWidget() is table
        assert table.inspection_dialog.isHidden() and table.zones_dialog.isHidden()
        positions = [
            lane.mapTo(table, C.QPoint(0, 0)).y()
            for lane in (table.opponent, table.player, table.hand)
        ]
        assert positions[0] < positions[1] < positions[2]
        assert positions[-1] + table.hand.height() <= table.height()
        assert table.decision_dock.isVisible()
        assert (
            table.decision_dock.mapTo(table, C.QPoint(0, 0)).x()
            > table.player.mapTo(table, C.QPoint(0, 0)).x()
        )
        assert table.zone_lanes["stack"].isVisible() == stack
        with pytest.raises(ValueError):
            table.set_view_mode("overview")
    finally:
        table.clear()
        table.close()


def test_contextual_zones_and_inspection_do_not_submit_or_reopen_after_dismissal(app):
    table = GameTable(object(), artwork_factory=SilentArtwork)
    obj = card("mine")
    view = replace(snapshot(), objects=(obj,))
    calls = []
    table.command.connect(lambda *args: calls.append(args))
    table.show()
    try:
        table.present(view)
        table.zone_button.click()
        assert table.zones_dialog.isVisible()
        table.select_object(obj.object_id, interact=False)
        assert table.inspection_dialog.isVisible() and not calls
        table.inspection_dialog.close()
        table.present(replace(view, revision=2))
        assert not table.inspection_dialog.isVisible() and not calls
        table.clear()
        assert table.zones_dialog.isHidden() and table.inspection_dialog.isHidden()
        assert not table.inspection.toPlainText()
    finally:
        table.close()


def test_hover_is_delayed_transient_and_uses_current_snapshot_without_actions(app):
    table = GameTable(object(), artwork_factory=SilentArtwork)
    obj = card("hovered")
    view = replace(snapshot(), objects=(obj,))
    calls = []
    table.command.connect(lambda *args: calls.append(args))
    table.present(view)
    try:
        table._schedule_hover(obj.object_id)
        assert table.hover_timer.isActive() and table.hover_preview.isHidden()
        assert table.hover_timer.interval() == 300
        table._show_hover()
        assert "3/3" in table.hover_text.toPlainText()
        assert "original printing" in table.hover_text.toPlainText()
        assert (
            table.inspected is None and table.inspection_dialog.isHidden() and not calls
        )
        changed = replace(
            obj,
            characteristics=replace(
                obj.characteristics,
                power="8",
                toughness="9",
                current_abilities=("Engine-reported ability",),
            ),
        )
        table.present(replace(view, revision=2, objects=(changed,)))
        assert "8/9" in table.hover_text.toPlainText()
        assert "Engine-reported ability" in table.hover_text.toPlainText()
        table.pending()
        assert table.hover_preview.isHidden() and not table.hover_text.toPlainText()
        table._schedule_hover(obj.object_id)
        assert not table.hover_timer.isActive() and not calls
    finally:
        table.clear()
        table.close()


@pytest.mark.parametrize("kind", ["hidden", "face_down", "foreign_hand", "removed"])
def test_hover_cannot_expose_concealed_or_removed_card_details(app, kind):
    table = GameTable(object(), artwork_factory=SilentArtwork)
    obj = card("private", name="PRIVATE NAME")
    if kind == "hidden":
        obj = replace(obj, hidden=True)
    elif kind == "face_down":
        obj = replace(obj, face_down=True)
    elif kind == "foreign_hand":
        obj = replace(obj, zone="hand", owner_id="two")
    table.present(replace(snapshot(), objects=() if kind == "removed" else (obj,)))
    table._schedule_hover(obj.object_id)
    table._show_hover()
    assert table.hover_preview.isHidden() and not table.hover_text.toPlainText()
    assert table.inspected is None
    table.clear()


def test_multiple_actions_use_explicit_menu_and_are_invalidated_by_next_view(app):
    table = GameTable(object(), artwork_factory=SilentArtwork)
    obj = card("choice")
    view = replace(
        snapshot(),
        objects=(obj,),
        actions=(
            LegalAction("first", "activate_ability", obj.object_id, "First ability"),
            LegalAction("second", "activate_ability", obj.object_id, "Second ability"),
        ),
    )
    calls = []
    table.command.connect(lambda *args: calls.append(args))
    table.present(view)
    try:
        table.select_object(obj.object_id)
        assert table.inspection_dialog.isHidden() and not calls
        assert len(table.action_menu.actions()) == 2
        table.action_menu.actions()[1].trigger()
        assert calls == [(view, "perform", ("second",))]
        table.present(replace(view, revision=2, actions=()))
        assert not table.action_menu.actions() and table.action_menu.isHidden()
        table.select_object(obj.object_id, interact=False)
        assert len(calls) == 1 and not table.inspection_dialog.isHidden()
    finally:
        table.clear()
        table.close()


@pytest.mark.parametrize(
    "prompt,keep_token,mulligan_token",
    [
        ("Mulligan?", "no", "yes"),
        ("Keep your hand?", "yes", "no"),
    ],
)
def test_opening_overlay_has_readable_own_hand_and_explicit_engine_choices(
    app, prompt, keep_token, mulligan_token
):
    table = GameTable(object(), artwork_factory=SilentArtwork)
    own = tuple(card(f"hand-{i}", "hand") for i in range(7))
    foreign = card("private-opponent", "hand", owner="two", name="PRIVATE")
    request = ChoiceRequest(
        "opening-current",
        "one",
        "boolean",
        prompt,
        (ChoiceOption("yes", "Yes"), ChoiceOption("no", "No")),
    )
    view = replace(snapshot(), objects=own + (foreign,), decision=request)
    calls = []
    table.command.connect(lambda *args: calls.append(args))
    table.resize(1000, 610)
    table.show()
    try:
        table.present(view)
        app.processEvents()
        assert table.opening_overlay.isVisible() and table.decision_dock.isHidden()
        assert (
            len(table.opening_hand.cards) == 7
            and "private-opponent" not in table.opening_hand.cards
        )
        assert "7 cards" in table.opening_status.text()
        assert table.opening_controls.widget() is table.decisions and not calls
        assert all(
            widget.height() >= 185 for widget in table.opening_hand.cards.values()
        )
        assert button(table.decisions, "Mulligan").play_args == (mulligan_token,)
        button(table.decisions, "Keep").click()
        assert calls == [(view, "choose", (keep_token,))]
        table.pending()
        assert not table.opening_hand.isEnabled() and not table.decisions.isEnabled()
        table.clear()
        assert table.opening_overlay.isHidden() and not table.opening_hand.cards
    finally:
        table.close()


def test_bottom_selection_is_engine_authorized_and_overlay_returns_controls_to_board(
    app,
):
    table = GameTable(object(), artwork_factory=SilentArtwork)
    obj = card("bottom-card", "hand")
    request = ChoiceRequest(
        "bottom-current",
        "one",
        "target",
        "Put a card on the bottom of your library",
        (ChoiceOption("select-card", "Card", object_id=obj.object_id),),
        minimum=1,
        maximum=1,
    )
    view = replace(snapshot(), objects=(obj,), decision=request)
    calls = []
    table.command.connect(lambda *args: calls.append(args))
    table.present(view)
    try:
        assert not table.opening_overlay.isHidden()
        assert "Required selection: 1 to 1" in table.opening_status.text()
        assert not any(
            item.text() == "Finish selection"
            for item in table.decisions.findChildren(W.QPushButton)
        )
        table.opening_hand.cards[obj.object_id].click()
        assert calls == [(view, "choose", ("select-card",))]
        old = table.opening_hand.cards[obj.object_id]
        table.present(
            replace(
                view,
                revision=2,
                decision=ChoiceRequest(
                    "priority", "one", "selection", "Select an action", ()
                ),
            )
        )
        assert (
            table.opening_overlay.isHidden()
            and table.decision_dock.widget() is table.decisions
        )
        old.click()
        assert len(calls) == 1 and old.obj is None
    finally:
        table.clear()
        table.close()


def test_ai_or_non_hand_bottom_choices_do_not_open_human_opening_overlay(app):
    from mtg_play.decisions import opening_hand_request

    view = replace(
        snapshot(),
        decision=ChoiceRequest(
            "ai", "two", "boolean", "Mulligan?", (ChoiceOption("yes", "Yes"),)
        ),
    )
    assert not opening_hand_request(view)
    view = replace(
        view,
        decision=ChoiceRequest(
            "foreign",
            "one",
            "target",
            "Bottom of library",
            (ChoiceOption("foreign-option", "PRIVATE", object_id="not-your-hand"),),
        ),
    )
    assert not opening_hand_request(view)
