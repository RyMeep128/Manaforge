"""Fixed human-view UI coverage using prescribed frames, never independent AI."""

from dataclasses import replace
from PyQt6 import QtWidgets as W
import pytest

from mtg_core.decks import DeckDocument
from mtg_play.adapter import AdapterError
from mtg_play.contracts import (
    CardCharacteristics,
    ChoiceOption,
    ChoiceRequest,
    CombatAssignment,
    GameObject,
    GameSetup,
    LegalAction,
    MatchSeat,
)
from mtg_play.fake import ScriptedGameSession
from mtg_play.ui_acceptance import UIAdapter
from mtg_play.tests.test_presentation import Owner, snapshot


class PrescribedMatch(ScriptedGameSession):
    """Human controls and permitted AI battlefield frames; contains no Magic rules."""

    def __init__(self):
        super().__init__((replace(snapshot(), decision=None),))
        self.index = 0
        self.land = GameObject(
            "land",
            "hand",
            "one",
            "one",
            False,
            CardCharacteristics(name="Forest", type_line="Basic Land"),
        )
        self.creature = GameObject(
            "creature",
            "hand",
            "one",
            "one",
            False,
            CardCharacteristics(
                name="Memnite", type_line="Artifact Creature", power="1", toughness="1"
            ),
        )
        self.steps = (
            ("choose", "keep", "boolean", (ChoiceOption("keep", "Keep hand"),), ()),
            (
                "perform",
                "play-land",
                "selection",
                (),
                (LegalAction("play-land", "play_land", "land", "Forest"),),
            ),
            (
                "perform",
                "cast",
                "selection",
                (),
                (LegalAction("cast", "cast_spell", "creature", "Memnite"),),
            ),
            (
                "perform",
                "respond",
                "selection",
                (),
                (LegalAction("respond", "pass", None, "Pass"),),
            ),
            (
                "perform",
                "attack",
                "selection",
                (),
                (LegalAction("attack", "declare_attacker", "creature", "Memnite"),),
            ),
            (
                "perform",
                "block",
                "selection",
                (),
                (LegalAction("block", "declare_blocker", "creature", "Memnite"),),
            ),
            (
                "choose",
                "discard",
                "target",
                (
                    ChoiceOption(
                        "discard", "Discard this card", object_id="discard-card"
                    ),
                ),
                (),
            ),
        )
        self._frame()

    def _frame(self):
        stage = self.steps[self.index] if self.index < len(self.steps) else None
        land = replace(self.land, zone="battlefield" if self.index >= 2 else "hand")
        creature = replace(
            self.creature,
            zone="battlefield"
            if self.index >= 4
            else "stack"
            if self.index >= 3
            else "hand",
        )
        opponent = replace(
            self.creature,
            object_id="opponent",
            owner_id="two",
            controller_id="two",
            zone="battlefield",
        )
        previous = self._snapshots["one"]
        decision = (
            ChoiceRequest(
                f"step-{self.index}",
                "one",
                stage[2],
                "Discard a card" if stage[1] == "discard" else "Fixture choice",
                stage[3],
            )
            if stage
            else None
        )
        combat = (
            (CombatAssignment(("opponent",), ("creature",), "one", True),)
            if self.index >= 5
            else ()
        )
        self.publish(
            replace(
                previous,
                revision=previous.revision + 1,
                turn=1 if self.index < 4 else 2,
                objects=(land, creature, opponent)
                + (
                    (replace(self.creature, object_id="discard-card"),)
                    if self.index < len(self.steps)
                    else ()
                ),
                decision=decision,
                actions=stage[4] if stage else (),
                combat=combat,
                active_player_id="two" if self.index >= 5 else "one",
                priority_player_id="one" if stage else None,
            )
        )

    def _advance(self, player, decision, identifier, method):
        expected = self.steps[self.index]
        assert player == "one" and (method, identifier) == expected[:2]
        result = (
            super().choose(player, decision, identifier)
            if method == "choose"
            else super().perform(player, decision, identifier)
        )
        assert result.outcome == "submitted"
        self.index += 1
        self._frame()
        return result

    def choose(self, player, decision, identifier):
        return self._advance(player, decision, identifier, "choose")

    def perform(self, player, decision, identifier):
        return self._advance(player, decision, identifier, "perform")

    def concede(self, player):
        assert player == "one"
        result = super().concede(player)
        view = self._snapshots[player]
        self.publish(
            replace(
                view,
                revision=view.revision + 1,
                status="finished",
                decision=None,
                actions=(),
                result="did_not_win",
            )
        )
        return result


def test_offline_ai_setup_to_result_through_fixed_human_controls(tmp_path, monkeypatch):
    monkeypatch.setenv("MANAFORGE_ENABLE_LOCAL_PLAY", "1")
    monkeypatch.setenv("PRINT_PROXY_PREP_DATA_DIR", str(tmp_path))
    app = W.QApplication.instance() or W.QApplication([])
    game = PrescribedMatch()
    owner = Owner(game)
    pilot = UIAdapter(app, owner, tmp_path)
    docs = (DeckDocument(), DeckDocument())
    originals = [doc.to_dict() for doc in docs]
    setup = GameSetup(
        (MatchSeat("one", "You"), MatchSeat("two", "Opponent", "engine_ai"))
    )
    try:
        pilot.create_game(setup, docs)
        assert [seat.controller for seat in owner.setup.seats] == [
            "local_human",
            "engine_ai",
        ]
        assert not hasattr(pilot.workspace, "handoff_button")
        assert not pilot.workspace.invite_friend.isEnabled()
        for method, identifier, *_ in game.steps:
            pilot.poll("one")
            view = pilot.snapshot("one")
            result = getattr(pilot, method)(
                "one", view.decision.decision_id, identifier
            )
            assert result.outcome == "submitted"
        with pytest.raises(AdapterError, match="UNAUTHORIZED_SEAT"):
            pilot.snapshot("two")
        with pytest.raises(AdapterError, match="UNAUTHORIZED_SEAT"):
            pilot.concede("two")
        assert pilot.concede("one").outcome == "submitted"
        pilot.poll("one")
        assert pilot.snapshot("one").result == "did_not_win"
        assert pilot.workspace.game_heading.text() == "did_not_win"
        assert [doc.to_dict() for doc in docs] == originals
    finally:
        pilot.close()
    assert owner.closed
