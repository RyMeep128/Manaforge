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
