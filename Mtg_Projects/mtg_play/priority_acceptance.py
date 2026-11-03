"""Real pinned-engine priority acceptance, executed by CI only.

The explicit fixture pilot handles pregame/combat and End Turn. Only the
production policy decides which real priority opportunities to pass automatically.
"""

import time
from .adapter import AdapterError
from .acceptance_scenarios import deck, drive
from .priority import PriorityController, opportunity, turn_boundary


def run(adapter):
    policy = PriorityController()
    report = dict(
        automatic_pass=False,
        engine_advanced=False,
        mana_only=False,
        full_control=False,
        temporary=False,
        phase_stop=False,
        meaningful_held=False,
        end_turn_held=False,
        end_step_held=False,
    )
    submitted = {}

    def inspect(view):
        previous = submitted.get(view.viewer_id)
        if previous and (
            view.decision is None or view.decision.decision_id != previous
        ):
            report["engine_advanced"] = True
        return all(report.values())

    def select(view):
        return next(
            (action for action in view.actions if action.kind == "play_land"), None
        )

    def stable(game, view):
        """A retained decision remains unchanged in the actual engine, not a fake."""
        for _ in range(3):
            time.sleep(0.01)
            game.poll(view.viewer_id)
            current = game.snapshot(view.viewer_id)
            if (
                not current.decision
                or current.decision.decision_id != view.decision.decision_id
            ):
                raise AdapterError("PRIORITY_HOLD_ADVANCED_ENGINE")

    def respond(game, view):
        action = opportunity(view)
        if not action:
            return None  # existing explicit fixture pilot handles other decisions
        policy.observe(view)
        state = policy.seat(view.viewer_id)
        if any(item.kind == "play_land" for item in view.actions):
            if policy.observe(view) is not None:
                raise AdapterError("PRIORITY_LOST_PLAYABLE_ACTION")
            stable(game, view)
            report["meaningful_held"] = True
            return None
        if turn_boundary(view):
            if policy.observe(view) is not None:
                raise AdapterError("PRIORITY_CROSSED_TURN_BOUNDARY")
            stable(game, view)
            report[
                "end_turn_held" if view.step == "POSTCOMBAT_MAIN" else "end_step_held"
            ] = True
            # Explicit fixture End Turn / final pass, never production automation.
            return game.perform(
                view.viewer_id, view.decision.decision_id, action.action_id
            )
        if not report["full_control"]:
            state.full_control = True
            if policy.observe(view) is not None:
                raise AdapterError("FULL_CONTROL_AUTO_PASSED")
            stable(game, view)
            report["full_control"] = True
            state.full_control = False
        if not report["temporary"]:
            state.temporary = True
            if policy.observe(view) is not None:
                raise AdapterError("TEMPORARY_CONTROL_AUTO_PASSED")
            stable(game, view)
            report["temporary"] = True
            policy.manual_submitted(view)
            return game.perform(
                view.viewer_id, view.decision.decision_id, action.action_id
            )
        if not report["phase_stop"]:
            scope = "own" if view.active_player_id == view.viewer_id else "other"
            policy.stop(view.viewer_id, scope, view.step)
            if policy.observe(view) is not None:
                raise AdapterError("PHASE_STOP_AUTO_PASSED")
            stable(game, view)
            report["phase_stop"] = True
            return game.perform(
                view.viewer_id, view.decision.decision_id, action.action_id
            )
        automatic = policy.observe(view)
        if automatic:
            report["mana_only"] |= any(
                item.priority_class == "basic_mana" for item in view.actions
            )
            policy.claimed(view)
            result = game.perform(
                view.viewer_id, view.decision.decision_id, automatic.action_id
            )
            policy.command_result(view.viewer_id, result)
            submitted[view.viewer_id] = view.decision.decision_id
            report["automatic_pass"] = True
            return result
        return None  # explicit pilot advances held opportunities

    report.update(
        drive(
            adapter,
            (deck(("Island", 60)), deck(("Plains", 60))),
            inspect,
            select,
            decision_handler=respond,
        )
    )
    return report
