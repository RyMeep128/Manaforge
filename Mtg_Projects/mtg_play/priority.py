"""Seat-local priority preferences; only explicit engine opportunities can pass.

This module reads contracts, never cards, labels, rules text or opponent secrets.
It returns an offered action; the asynchronous session boundary submits it.
"""

from dataclasses import dataclass, field


STEPS = (
    ("UPKEEP", "Upkeep"),
    ("DRAW", "Draw"),
    ("PRECOMBAT_MAIN", "Main 1"),
    ("BEGIN_COMBAT", "Combat"),
    ("DECLARE_ATTACKERS", "Attack"),
    ("DECLARE_BLOCKERS", "Block"),
    ("FIRST_COMBAT_DAMAGE", "First damage"),
    ("COMBAT_DAMAGE", "Damage"),
    ("END_COMBAT", "End combat"),
    ("POSTCOMBAT_MAIN", "Main 2"),
    ("END_TURN", "End step"),
)
KNOWN_STEPS = {step for step, _ in STEPS} | {"CLEANUP"}


def opportunity(view):
    request = view.decision
    if (
        view.status != "active"
        or view.result
        or not request
        or not request.is_priority
        or request.family != "selection"
        or request.player_id != view.viewer_id
        or view.priority_player_id != view.viewer_id
    ):
        return None
    passes = [
        action
        for action in view.actions
        if action.kind == "pass" and action.object_id is None
    ]
    return passes[0] if len(passes) == 1 else None


def turn_boundary(view):
    """Never automatically leave the local postcombat main or empty end step."""
    return (
        view.active_player_id == view.viewer_id
        and view.step in {"POSTCOMBAT_MAIN", "END_TURN", "CLEANUP"}
        and not any(obj.zone == "stack" for obj in view.objects)
    )


@dataclass
class SeatPriority:
    automatic: bool = True
    full_control: bool = False
    temporary: bool = False
    until_turn: tuple | None = None
    stops: set = field(default_factory=set)  # (own/other, engine step, recurring)
    blocked: bool = False
    reason: str = "Waiting for priority"
    session: str | None = None
    revision: int = -1
    window: tuple | None = None
    stopped_window: tuple | None = None
    temporary_key: tuple | None = None
    temporary_submitted: bool = False
    attempted: set = field(default_factory=set)


class PriorityController:
    def __init__(self):
        self.seats = {}

    def seat(self, player):
        return self.seats.setdefault(player, SeatPriority())

    @staticmethod
    def key(view):
        return (view.session_id, view.viewer_id, view.decision.decision_id)

    @staticmethod
    def turn(view):
        return (view.session_id, view.turn, view.active_player_id)

    def reset(self):
        """Retain defaults only; never carry holds, stops or passes into a new match."""
        self.seats = {
            player: SeatPriority(state.automatic, state.full_control)
            for player, state in self.seats.items()
        }

    def stop(self, player, scope, step, recurring=False):
        if scope not in {"own", "other"} or step not in KNOWN_STEPS:
            raise ValueError("Unsupported priority stop")
        state = self.seat(player)
        item = (scope, step, recurring)
        existing = {entry for entry in state.stops if entry[:2] == item[:2]}
        if existing:
            state.stops.difference_update(existing)
        else:
            state.stops.add(item)

    def observe(self, view):
        state = self.seat(view.viewer_id)
        if state.session is None:
            state.session = view.session_id
        elif state.session != view.session_id:
            state = self.seats[view.viewer_id] = SeatPriority(
                state.automatic, state.full_control, session=view.session_id
            )
        if view.revision < state.revision:
            state.reason = "Waiting for current state"
            return None
        state.revision = view.revision
        turn = self.turn(view)
        if state.until_turn and state.until_turn != turn:
            state.until_turn = None
        window = turn + (view.step,)
        if window != state.window:
            state.window, state.stopped_window = window, None
        action = opportunity(view)
        if action is None:
            state.reason = (
                "Decision requires input" if view.decision else "Waiting for priority"
            )
            state.until_turn = None
            return None
        key = self.key(view)
        if state.temporary_submitted and key != state.temporary_key:
            state.temporary = state.temporary_submitted = False
            state.temporary_key = None
        if state.temporary and state.temporary_key is None:
            state.temporary_key = key
        scope = "own" if view.active_player_id == view.viewer_id else "other"
        matches = {item for item in state.stops if item[:2] == (scope, view.step)}
        if matches:
            state.stopped_window = window
            state.stops.difference_update(item for item in matches if not item[2])
        reason = None
        if state.blocked:
            reason = "Automation paused after a command failure"
        elif state.full_control:
            reason = "Full Control"
        elif state.temporary:
            reason = "Temporary Full Control"
        elif state.stopped_window == window:
            reason = "Phase stop"
        elif turn_boundary(view):
            reason = (
                "Choose End Turn"
                if view.step == "POSTCOMBAT_MAIN"
                else "Pass explicitly to finish your turn"
            )
        elif not state.automatic and not state.until_turn:
            reason = "Manual priority"
        elif (
            not view.actions_complete
            or view.unsupported_fields
            or view.turn is None
            or view.active_player_id is None
            or view.step not in KNOWN_STEPS
        ):
            reason = "Action information unavailable; holding priority"
        elif view.decision.options or any(
            item.kind != "pass" and item.priority_class != "basic_mana"
            for item in view.actions
        ):
            reason = "Playable action; your priority"
        elif any(
            player.player_id == view.viewer_id
            and (player.eliminated or player.left_game)
            for player in view.players
        ):
            reason = "Player has left the game"
        if reason:
            state.reason = reason
            state.until_turn = None
            return None
        if key in state.attempted:
            state.reason = "Waiting for engine confirmation"
            return None
        state.reason = "Automatic priority"
        return action

    def claimed(self, view):
        state = self.seat(view.viewer_id)
        state.attempted.add(self.key(view))

    def manual_submitted(self, view):
        state = self.seat(view.viewer_id)
        if opportunity(view) and state.temporary:
            state.temporary_key = self.key(view)
            state.temporary_submitted = True

    def command_result(self, player, result):
        if result.outcome in {"rejected", "uncertain"}:
            state = self.seat(player)
            state.blocked = True
            state.reason = "Automation paused after a command failure"
            state.until_turn = None
