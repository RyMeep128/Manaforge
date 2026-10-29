"""Scripted contract fake for consumers. It contains no game rules or opponent logic."""

from dataclasses import replace
from uuid import uuid4
from .contracts import CommandResult, GameEvent, GameSnapshot


class ScriptedGameSession:
    def __init__(self, snapshots: tuple[GameSnapshot, ...]):
        if not snapshots or len({view.session_id for view in snapshots}) != 1:
            raise ValueError("One session is required")
        self.session_id = snapshots[0].session_id
        self._snapshots = {view.viewer_id: view for view in snapshots}
        self._events = {view.viewer_id: [] for view in snapshots}

    def publish(self, snapshot: GameSnapshot):
        previous = self._snapshots[snapshot.viewer_id]
        if (
            snapshot.session_id != self.session_id
            or snapshot.revision <= previous.revision
        ):
            raise ValueError("Obsolete or foreign snapshot")
        self._snapshots[snapshot.viewer_id] = snapshot
        self._events[snapshot.viewer_id].append(
            GameEvent("snapshot_changed", snapshot.viewer_id, snapshot.revision)
        )

    def snapshot(self, player_id):
        return self._snapshots[player_id]

    def poll(self, player_id, timeout=0):
        result = tuple(self._events[player_id])
        self._events[player_id].clear()
        return result

    def _submit(
        self, player_id, decision_id, identifier, *, numeric=False, action=False
    ):
        view = self.snapshot(player_id)
        decision = view.decision
        valid = decision is not None and decision.decision_id == decision_id
        if valid and numeric:
            valid = (
                decision.family == "number"
                and type(identifier) is int
                and decision.minimum <= identifier <= decision.maximum
            )
        elif valid:
            valid = identifier in (
                {item.action_id for item in view.actions}
                if action
                else {item.option_id for item in decision.options}
            )
        if not valid:
            return CommandResult(uuid4().hex, "rejected", "STALE_OR_INVALID_DECISION")
        self.publish(
            replace(view, decision=None, actions=(), revision=view.revision + 1)
        )
        return CommandResult(uuid4().hex, "submitted")

    def perform(self, player_id, decision_id, action_id):
        return self._submit(player_id, decision_id, action_id, action=True)

    def choose(self, player_id, decision_id, option_id):
        return self._submit(player_id, decision_id, option_id)

    def select_mana_source(self, player_id, decision_id, object_id):
        view = self.snapshot(player_id)
        if (
            view.decision is None
            or view.decision.family != "mana"
            or view.decision.decision_id != decision_id
            or object_id not in {obj.object_id for obj in view.objects}
        ):
            return CommandResult(uuid4().hex, "rejected", "STALE_OR_INVALID_DECISION")
        self.publish(
            replace(view, decision=None, actions=(), revision=view.revision + 1)
        )
        return CommandResult(uuid4().hex, "submitted")

    def choose_number(self, player_id, decision_id, value):
        return self._submit(player_id, decision_id, value, numeric=True)

    def choose_amounts(self, player_id, decision_id, values):
        view = self.snapshot(player_id)
        request = view.decision
        if (
            request is None
            or request.decision_id != decision_id
            or request.family != "amounts"
            or len(values) != len(request.amounts)
            or any(
                type(value) is not int or not row.minimum <= value <= row.maximum
                for value, row in zip(values, request.amounts)
            )
            or not request.minimum <= sum(values) <= request.maximum
        ):
            return CommandResult(uuid4().hex, "rejected", "AMOUNT_OUT_OF_RANGE")
        self.publish(
            replace(view, decision=None, actions=(), revision=view.revision + 1)
        )
        return CommandResult(uuid4().hex, "submitted")

    def cancel(self, player_id, decision_id):
        view = self.snapshot(player_id)
        if (
            view.decision is None
            or view.decision.decision_id != decision_id
            or not view.decision.cancellable
        ):
            return CommandResult(uuid4().hex, "rejected", "CANCELLATION_UNSUPPORTED")
        self.publish(
            replace(view, decision=None, actions=(), revision=view.revision + 1)
        )
        return CommandResult(uuid4().hex, "submitted")

    def concede(self, player_id):
        self.snapshot(player_id)  # Validate seat, without inventing an engine result.
        return CommandResult(uuid4().hex, "submitted")
