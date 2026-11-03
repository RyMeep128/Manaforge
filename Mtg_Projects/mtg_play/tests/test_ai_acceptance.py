"""AI acceptance evidence regressions; execution belongs to GitHub Actions."""

from copy import deepcopy
import json
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
from mtg_play.diagnostics import diagnostic_category


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


def discard_view(
    *,
    prompt="Discard a card",
    owner="human",
    hidden=False,
    selected=False,
    option_object="hand-card",
    family="target",
):
    return NS(
        viewer_id="human",
        step="CLEANUP",
        decision=NS(
            family=family,
            prompt=prompt,
            decision_id="current-token",
            options=(
                ChoiceOption(
                    "offered-discard",
                    "PRIVATE_OPTION_LABEL",
                    object_id=option_object,
                    selected=selected,
                ),
            ),
        ),
        objects=(
            NS(object_id="hand-card", zone="hand", owner_id=owner, hidden=hidden),
        ),
    )


def test_fixture_discards_only_an_engine_offered_card_from_the_visible_human_hand():
    calls = []
    game = NS(
        choose=lambda *args: calls.append(args) or CommandResult("command", "submitted")
    )
    result = ai_acceptance._human_choice(game, discard_view(), lambda view: None)
    assert result.outcome == "submitted"
    assert calls == [("human", "current-token", "offered-discard")]


@pytest.mark.parametrize(
    "changes",
    [
        dict(owner="ai"),
        dict(hidden=True),
        dict(selected=True),
        dict(option_object="unoffered-card"),
    ],
)
def test_fixture_never_discards_a_foreign_hidden_selected_or_unoffered_card(changes):
    with pytest.raises(ai_acceptance.AIAcceptanceError) as failure:
        ai_acceptance._human_choice(NS(), discard_view(**changes), lambda view: None)
    assert failure.value.context["decision_family"] == "target"
    assert "PRIVATE" not in json.dumps(failure.value.context)


def test_fixture_does_not_treat_other_target_choices_as_discard():
    view = discard_view(prompt="Choose a PRIVATE_OPTION_LABEL target")
    with pytest.raises(ai_acceptance.AIAcceptanceError) as failure:
        ai_acceptance._human_choice(NS(), view, lambda view: None)
    assert failure.value.context == dict(
        decision_family="target", choice_count=1, hand_option_count=1
    )
    assert "PRIVATE" not in json.dumps(failure.value.context)


def test_freeform_fixture_continues_after_cleanup_discard_to_a_natural_result(
    monkeypatch,
):
    calls = []
    hand = tuple(
        NS(
            object_id=f"hand-{index}",
            zone="hand",
            owner_id="human",
            hidden=False,
            controller_id="human",
            characteristics=None,
        )
        for index in range(7)
    )
    battlefield = tuple(
        NS(
            object_id=player + name,
            zone="battlefield",
            owner_id=player,
            controller_id=player,
            hidden=False,
            characteristics=NS(name=name),
        )
        for player in ("human", "ai")
        for name in ("Forest", "Memnite")
    )
    keep = NS(
        family="boolean",
        prompt="Mulligan?",
        decision_id="keep",
        options=(ChoiceOption("no", "No"),),
    )
    discard = NS(
        family="target",
        prompt="Discard a card",
        decision_id="discard",
        options=(ChoiceOption("discard-option", "Discard", object_id="hand-0"),),
    )
    views = iter(
        NS(
            viewer_id="human",
            objects=hand + battlefield,
            active_player_id="ai",
            turn=2,
            combat=(CombatAssignment(("aiMemnite",), (), "human", False),),
            status=status,
            decision=decision,
            result=result,
        )
        for status, decision, result in (
            ("active", keep, None),
            ("active", discard, None),
            ("finished", None, "did_not_win"),
        )
    )

    def snapshot(player):
        if player == "ai":
            raise AdapterError("UNAUTHORIZED_SEAT")
        assert player == "human"
        return next(views)

    def concede(player):
        assert player == "ai", (
            "Natural completion must not be replaced by human concession"
        )
        raise AdapterError("UNAUTHORIZED_SEAT")

    def choose(*args):
        calls.append(args)
        return CommandResult("command", "submitted")

    game = NS(snapshot=snapshot, concede=concede, choose=choose, poll=lambda player: ())
    adapter = NS(create_game=lambda setup, documents: game)
    monkeypatch.setattr(ai_acceptance.time, "sleep", lambda seconds: None)
    report = ai_acceptance.freeform(adapter)
    assert report["natural_result"] and report["human_keep"]
    assert calls == [("human", "keep", "no"), ("human", "discard", "discard-option")]


def test_unhandled_fixture_decision_is_not_reported_as_unsupported_engine_rules():
    assert (
        diagnostic_category("AI_ACCEPTANCE_UNSUPPORTED_DECISION")
        == "acceptance_pilot_gap"
    )


@pytest.mark.parametrize(
    "enabled,viewer,count,accepted",
    [
        (True, "human", 1, True),
        (False, "human", 1, False),
        (True, "ai", 1, False),
        (True, "human", 0, False),
        (True, "human", 2, False),
    ],
)
def test_blockers_single_ability_policy_is_explicit_and_uses_current_option(
    enabled, viewer, count, accepted
):
    calls = []
    view = NS(
        viewer_id=viewer,
        objects=(),
        step="PRECOMBAT_MAIN",
        decision=NS(
            family="ability",
            prompt="Private ability prompt",
            decision_id="current-decision",
            options=tuple(
                ChoiceOption(f"option-{i}", "Private label") for i in range(count)
            ),
        ),
    )
    game = NS(
        choose=lambda *args: calls.append(args) or CommandResult("cmd", "submitted")
    )
    if accepted:
        result = ai_acceptance._human_choice(
            game, view, lambda v: None, single_ability=enabled
        )
        assert result.outcome == "submitted"
        assert calls == [("human", "current-decision", "option-0")]
    else:
        with pytest.raises(ai_acceptance.AIAcceptanceError):
            ai_acceptance._human_choice(
                game, view, lambda v: None, single_ability=enabled
            )
        assert not calls


def test_blockers_enables_single_ability_policy_for_both_acceptance_drivers(
    monkeypatch,
):
    def drive(adapter, documents, inspect, select, **options):
        assert options == {"single_ability": True}
        assert [doc.deck.entries[0].name for doc in documents] == [
            "Memnite",
            "Ornithopter",
        ]
        return {"fixture_driver_called": True}

    monkeypatch.setattr(ai_acceptance, "_drive_to_evidence", drive)
    assert ai_acceptance.blockers(object())["fixture_driver_called"]
