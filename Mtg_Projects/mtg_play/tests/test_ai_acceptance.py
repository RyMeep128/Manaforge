"""AI acceptance evidence regressions; execution belongs to GitHub Actions."""

from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mtg_core"))
from mtg_play import ai_acceptance
from mtg_play.adapter import AdapterError
from mtg_play.contracts import ChoiceOption, CombatAssignment, CommandResult
from mtg_play.decks import prepare_deck


def test_commander_ai_fixture_preserves_canonical_deck_and_printing_bindings():
    document = ai_acceptance.commander_deck()
    before = deepcopy(document.to_dict())

    def resolve(queries):
        return [
            dict(row, set="FIX", number=str(index)) for index, row in enumerate(queries)
        ]

    prepared = prepare_deck(document, resolve, commander=True)
    assert document.deck.commander_entry_ids == ["commander"]
    assert sum(row["quantity"] for row in prepared.cards) == 99
    assert sum(row["quantity"] for row in prepared.sideboard) == 1
    assert prepared.sideboard[0]["name"] == "Isamaru, Hound of Konda"
    assert any(
        binding.printing_id == "selected-commander"
        for binding in prepared.bindings.values()
    )
    assert document.to_dict() == before


@pytest.mark.parametrize(
    "attackers, blockers, blocked, expected",
    [
        (("human-card",), ("ai-card",), True, True),
        (("human-card",), (), True, False),
        (("human-card",), ("ai-card",), False, False),
        (("ai-card",), ("human-card",), True, False),
        (("unrelated",), ("ai-card",), True, False),
    ],
)
def test_blocking_evidence_requires_ai_blocker_against_human(
    attackers, blockers, blocked, expected
):
    view = NS(
        objects=(
            NS(object_id="human-card", zone="battlefield", controller_id="human"),
            NS(object_id="ai-card", zone="battlefield", controller_id="ai"),
        ),
        combat=(CombatAssignment(attackers, blockers, "ai", blocked),),
    )
    assert ai_acceptance._ai_blocks_human(view) is expected


@pytest.mark.parametrize(
    "family", ["boolean", "options", "number", "amounts", "piles", "target"]
)
def test_ai_fixture_pilot_rejects_unknown_human_decisions(family):
    view = NS(decision=NS(family=family, prompt="Unknown decision"), step="MAIN")
    with pytest.raises(AdapterError, match="AI_ACCEPTANCE_UNSUPPORTED_DECISION"):
        ai_acceptance._human_choice(NS(), view, lambda view: None)


def test_additional_ai_driver_controls_only_human_and_concedes_after_evidence(
    monkeypatch,
):
    calls = []
    keep = NS(
        family="boolean",
        prompt="Mulligan?",
        decision_id="keep",
        options=(ChoiceOption("no", "No"),),
    )
    views = iter(
        (
            NS(status="active", decision=keep, objects=(), result=None),
            NS(status="active", decision=None, objects=(), result=None),
            NS(status="finished", decision=None, objects=(), result="did_not_win"),
        )
    )

    def checked_player(player):
        assert player == "human"

    def choose(player, decision, option):
        checked_player(player)
        calls.append(("keep", decision, option))
        return CommandResult("keep-command", "submitted")

    def concede(player):
        checked_player(player)
        assert calls[-1] == ("inspect", True)
        calls.append(("concede",))
        return CommandResult("concede-command", "submitted")

    game = NS(
        poll=lambda player: checked_player(player) or (),
        snapshot=lambda player: checked_player(player) or next(views),
        choose=choose,
        concede=concede,
    )
    setups = []
    adapter = NS(create_game=lambda setup, documents: setups.append(setup) or game)

    def inspect(view):
        ready = view.decision is None
        calls.append(("inspect", ready))
        return ready

    monkeypatch.setattr(ai_acceptance.time, "sleep", lambda seconds: None)
    report = ai_acceptance._drive_to_evidence(
        adapter,
        (ai_acceptance.commander_deck(), ai_acceptance.commander_deck()),
        inspect,
        lambda view: None,
        format="commander",
    )
    assert report["conceded_after_evidence"] and report["source_decks_unchanged"]
    assert calls == [
        ("inspect", False),
        ("keep", "keep", "no"),
        ("inspect", True),
        ("concede",),
    ]
    assert [seat.controller for seat in setups[0].seats] == ["local_human", "engine_ai"]


@pytest.mark.parametrize("result", ["won", "did_not_win"])
def test_additional_ai_driver_cannot_accept_result_without_evidence(result):
    game = NS(
        poll=lambda player: (),
        snapshot=lambda player: NS(
            status="finished", decision=None, objects=(), result=result
        ),
    )
    adapter = NS(create_game=lambda setup, documents: game)
    with pytest.raises(AdapterError, match="AI_ACCEPTANCE_EVIDENCE_MISSING"):
        ai_acceptance._drive_to_evidence(
            adapter, (), lambda view: False, lambda view: None
        )
