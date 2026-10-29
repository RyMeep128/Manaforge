"""Exercise the same UI pilot as pinned-engine CI using a prescribed session."""

from dataclasses import replace
from PyQt6 import QtWidgets as W
from mtg_core.decks import DeckDocument
from mtg_play.contracts import (
    CardCharacteristics,
    ChoiceOption,
    ChoiceRequest,
    GameObject,
    LegalAction,
)
from mtg_play.fake import ScriptedGameSession
from mtg_play.ui_acceptance import UIAdapter
from mtg_play.tests.test_presentation import Owner, snapshot


class PrescribedMatch(ScriptedGameSession):
    """Fixture frames and expected clicks, without simulating any Magic rules."""

    def __init__(self):
        super().__init__(
            (
                replace(snapshot(), decision=None),
                replace(snapshot("two"), decision=None),
            )
        )
        self.index = 0
        self.land = GameObject(
            "land",
            "hand",
            "one",
            "one",
            False,
            CardCharacteristics(name="Forest", type_line="Basic Land — Forest"),
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
            (
                "one",
                "choose",
                "keep-one",
                "boolean",
                (ChoiceOption("keep-one", "Keep hand"),),
                (),
            ),
            (
                "two",
                "choose",
                "keep-two",
                "boolean",
                (ChoiceOption("keep-two", "Keep hand"),),
                (),
            ),
            (
                "one",
                "perform",
                "play-land",
                "selection",
                (),
                (LegalAction("play-land", "play_land", "land", "Forest"),),
            ),
            (
                "one",
                "perform",
                "cast",
                "selection",
                (),
                (LegalAction("cast", "cast_spell", "creature", "Memnite"),),
            ),
            (
                "two",
                "perform",
                "respond",
                "selection",
                (),
                (LegalAction("respond", "pass", None, "Pass"),),
            ),
            (
                "one",
                "perform",
                "attack",
                "selection",
                (),
                (LegalAction("attack", "declare_attacker", "creature", "Memnite"),),
            ),
            (
                "two",
                "perform",
                "block",
                "selection",
                (),
                (LegalAction("block", "declare_blocker", "blocker", "Memnite"),),
            ),
        )
        self._frame()

    def _frame(self):
        stage = self.steps[self.index] if self.index < len(self.steps) else None
        for player in ("one", "two"):
            land = replace(self.land, zone="battlefield" if self.index >= 3 else "hand")
            creature = replace(
                self.creature,
                zone="battlefield"
                if self.index >= 5
                else "stack"
                if self.index >= 4
                else "hand",
            )
            blocker = replace(
                creature,
                object_id="blocker",
                owner_id="two",
                controller_id="two",
                zone="battlefield",
            )
            objects = tuple(
                obj
                for obj in (land, creature, blocker)
                if obj.zone != "hand" or obj.owner_id == player
            )
            previous = self._snapshots[player]
            decision = (
                ChoiceRequest(
                    f"step-{self.index}", player, stage[3], "Fixture choice", stage[4]
                )
                if stage and stage[0] == player
                else None
            )
            self.publish(
                replace(
                    previous,
                    revision=previous.revision + 1,
                    turn=1 if self.index < 5 else 2,
                    objects=objects,
                    decision=decision,
                    actions=stage[5] if decision else (),
                    priority_player_id=stage[0] if stage else None,
                )
            )

    def _advance(self, player, decision, identifier, method):
        expected = self.steps[self.index]
        assert (player, method, identifier) == expected[:3]
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
        result = super().concede(player)
        for seat in ("one", "two"):
            view = self._snapshots[seat]
            self.publish(
                replace(
                    view,
                    revision=view.revision + 1,
                    status="finished",
                    decision=None,
                    actions=(),
                    result="You win" if seat == "one" else "You conceded",
                )
            )
        return result


def test_saved_decks_to_authoritative_result_through_real_workspace_controls(
    tmp_path, monkeypatch
):
    from mtg_play.contracts import GameSetup, MatchSeat

    monkeypatch.setenv("MANAFORGE_ENABLE_LOCAL_PLAY", "1")
    monkeypatch.setenv("PRINT_PROXY_PREP_DATA_DIR", str(tmp_path))
    app = W.QApplication.instance() or W.QApplication([])
    game = PrescribedMatch()
    owner = Owner(game)
    pilot = UIAdapter(app, owner, tmp_path)
    docs = (DeckDocument(), DeckDocument())
    originals = [doc.to_dict() for doc in docs]
    setup = GameSetup((MatchSeat("one", "First"), MatchSeat("two", "Second")))
    try:
        pilot.create_game(setup, docs)
        for player, method, identifier, *_ in game.steps:
            pilot.poll(player)
            view = pilot.snapshot(player)
            result = getattr(pilot, method)(
                player, view.decision.decision_id, identifier
            )
            assert result.outcome == "submitted"
        assert pilot.concede("two").outcome == "submitted"
        pilot.poll("one")
        assert pilot.snapshot("one").result == "You win"
        assert pilot.workspace.game_heading.text() == "You win"
        assert pilot.handoffs >= 4
        assert [doc.to_dict() for doc in docs] == originals
    finally:
        pilot.close()
    assert owner.closed
