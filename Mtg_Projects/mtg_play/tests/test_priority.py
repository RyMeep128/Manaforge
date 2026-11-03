"""Conservative priority policy coverage. Routine execution belongs to CI."""

from dataclasses import replace
import pytest
from mtg_play.contracts import ChoiceRequest, CommandResult, LegalAction, PlayerView
from mtg_play.priority import PriorityController, opportunity
from mtg_play.decisions import pass_label
from mtg_play.tests.test_presentation import snapshot


def priority_view(seat="one", revision=1, **kwargs):
    return replace(
        snapshot(seat, revision),
        status="active",
        step="UPKEEP",
        priority_player_id=seat,
        actions_complete=True,
        actions=(LegalAction("pass", "pass", None, "Pass"),),
        decision=ChoiceRequest(
            f"priority-{revision}", seat, "selection", "", (), is_priority=True
        ),
        **kwargs,
    )


def test_default_automatic_passes_only_current_explicit_priority_once():
    policy = PriorityController()
    view = priority_view()
    action = policy.observe(view)
    assert action.action_id == "pass"
    policy.claimed(view)
    assert policy.observe(replace(view, revision=2)) is None  # same decision
    assert policy.observe(priority_view(revision=3))
    assert policy.observe(view) is None  # older revision


@pytest.mark.parametrize(
    "classification", ["unknown", "meaningful", "mana", "special_action"]
)
def test_every_nonbasic_or_unknown_action_holds(classification):
    view = priority_view()
    action = LegalAction("object", "activate", "obj", "arbitrary label", classification)
    assert (
        PriorityController().observe(replace(view, actions=view.actions + (action,)))
        is None
    )


def test_basic_mana_uses_engine_classification_without_reading_labels():
    view = priority_view()
    action = LegalAction("mana", "activate", "obj", "not parsed", "basic_mana")
    assert PriorityController().observe(replace(view, actions=view.actions + (action,)))


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "failed"},
        {"result": "won"},
        {"priority_player_id": "two"},
        {"actions_complete": False},
        {"unsupported_fields": ("physical_printing",)},
        {"turn": None},
        {"step": "NEW_STEP"},
        {"active_player_id": None},
        {"actions": ()},
    ],
)
def test_missing_ambiguous_or_failed_state_holds(changes):
    assert PriorityController().observe(replace(priority_view(), **changes)) is None


@pytest.mark.parametrize(
    "family",
    ["boolean", "target", "ability", "mana", "options", "amounts", "piles", "number"],
)
def test_automation_never_answers_optional_or_mandatory_choices(family):
    view = priority_view()
    assert (
        PriorityController().observe(
            replace(view, decision=replace(view.decision, family=family))
        )
        is None
    )
    assert (
        PriorityController().observe(
            replace(view, decision=replace(view.decision, is_priority=False))
        )
        is None
    )


def test_full_control_and_temporary_hold_until_explicit_opportunity_handled():
    policy = PriorityController()
    view = priority_view()
    policy.observe(view)
    state = policy.seat("one")
    state.full_control = True
    assert policy.observe(view) is None
    state.full_control = False
    state.temporary = True
    assert policy.observe(view) is None
    assert policy.observe(priority_view(revision=2)) is None  # no explicit handling yet
    policy.manual_submitted(priority_view(revision=2))
    policy.command_result("one", CommandResult("cmd", "submitted"))
    assert (
        policy.observe(priority_view(revision=2)) is None
    )  # submitted isn't confirmation
    assert policy.observe(priority_view(revision=3))
    assert not state.temporary and state.automatic


@pytest.mark.parametrize("recurring", [False, True])
def test_stops_hold_whole_window_and_one_time_stops_expire(recurring):
    policy = PriorityController()
    view = priority_view()
    policy.observe(view)
    policy.stop("one", "own", "UPKEEP", recurring)
    assert policy.observe(view) is None
    assert policy.observe(priority_view(revision=2)) is None
    assert policy.observe(replace(priority_view(revision=3), step="DRAW"))
    next_turn = replace(priority_view(revision=4), turn=3)
    assert bool(policy.observe(next_turn)) is (not recurring)


def test_opponent_stop_does_not_stop_own_turn():
    policy = PriorityController()
    view = priority_view()
    policy.observe(view)
    policy.stop("one", "other", "UPKEEP")
    assert policy.observe(view)
    assert policy.observe(replace(view, revision=2, active_player_id="two")) is None


@pytest.mark.parametrize("step", ["POSTCOMBAT_MAIN", "END_TURN", "CLEANUP"])
def test_turn_boundary_always_requires_explicit_input_even_pass_until_response(step):
    policy = PriorityController()
    view = replace(priority_view(), step=step)
    policy.observe(view)
    policy.seat("one").until_turn = policy.turn(view)
    assert policy.observe(view) is None
    assert opportunity(view)
    if step == "POSTCOMBAT_MAIN":
        assert pass_label(view) == "End Turn"


def test_until_response_expires_on_turn_change_and_meaningful_action():
    policy = PriorityController()
    view = priority_view()
    policy.observe(view)
    state = policy.seat("one")
    state.automatic = False
    state.until_turn = policy.turn(view)
    assert policy.observe(view)
    assert policy.observe(replace(priority_view(revision=2), turn=2)) is None
    assert state.until_turn is None
    state.until_turn = policy.turn(view)
    state.automatic = True
    action = LegalAction("spell", "cast_spell", "obj", "", "meaningful")
    assert (
        policy.observe(
            replace(priority_view(revision=3), actions=view.actions + (action,))
        )
        is None
    )
    assert state.until_turn is None


@pytest.mark.parametrize("outcome", ["rejected", "uncertain"])
def test_failed_commands_pause_automation(outcome):
    policy = PriorityController()
    view = priority_view()
    policy.observe(view)
    policy.command_result("one", CommandResult("cmd", outcome))
    assert policy.observe(priority_view(revision=2)) is None


@pytest.mark.parametrize("count", [2, 3, 4, 5])
def test_independent_seat_preferences_without_private_state(count):
    policy = PriorityController()
    players = tuple(PlayerView(str(i), str(i), 20, 0, 0, False) for i in range(count))
    for index in range(count):
        seat = str(index)
        view = replace(priority_view(seat), players=players)
        policy.observe(view)
        policy.seat(seat).full_control = index % 2 == 1
        assert bool(policy.observe(view)) is (index % 2 == 0)
        assert not view.objects  # no hands, names or labels are needed


def test_reset_retains_preferences_only():
    policy = PriorityController()
    policy.observe(priority_view())
    state = policy.seat("one")
    state.full_control = state.temporary = True
    policy.stop("one", "own", "DRAW")
    policy.reset()
    assert policy.seat("one").full_control
    assert not policy.seat("one").temporary and not policy.seat("one").stops


def test_hold_registered_before_first_snapshot_is_not_lost():
    policy = PriorityController()
    policy.seat("one").temporary = True
    assert policy.observe(priority_view()) is None
    assert policy.seat("one").temporary


@pytest.mark.parametrize("step", ["DECLARE_ATTACKERS", "DECLARE_BLOCKERS"])
def test_real_combat_priority_is_not_mislabeled_as_a_declaration(step):
    view = replace(priority_view(), step=step)
    assert pass_label(view) == "Pass priority"
