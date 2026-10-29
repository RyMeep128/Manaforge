"""Serialized, asynchronous public-contract boundary for the local Play workspace.

Only the worker queue touches the adapter/session. Qt consumers receive a single
seat's immutable snapshot; epochs invalidate queued replies after leaving a view.
"""

from PyQt6 import QtCore as C
from mtg_ui.jobs import JobQueue


def local_adapter():
    # Import and start the optional runtime only after an explicit Start Game.
    from .adapter import LocalGameAdapter

    return LocalGameAdapter()


class SessionController(C.QObject):
    snapshotChanged = C.pyqtSignal(object)
    statusChanged = C.pyqtSignal(str)
    viewCleared = C.pyqtSignal()
    commandFinished = C.pyqtSignal(object)
    stopped = C.pyqtSignal()

    def __init__(self, parent=None, *, adapter_factory=local_adapter):
        super().__init__(parent)
        self.jobs = JobQueue(self)
        self.jobs.status.connect(self._completed)
        self.adapter_factory = adapter_factory
        self._owner = self._session = None  # Worker-owned, never exposed to widgets.
        self._operations = {}
        self._epoch = 0
        self._viewer = None
        self._seats = set()
        self._revision = -1
        self._snapshot = None
        self._submitted = {}
        self._blocked = False
        self.active = self.closing = False
        self.timer = C.QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.refresh)

    @property
    def busy(self):
        return self.jobs.busy

    def _close_owner(self):
        """Close on the worker; a failed game can still have confirmed cleanup."""
        if self._owner is None:
            return
        try:
            self._owner.close()
        except Exception as exc:
            report = getattr(self._owner, "result", None)
            if (
                getattr(exc, "code", None) != "ENGINE_RUNTIME_FAILED"
                or report is None
                or any(code is None for _, code in report.process_exit_codes)
            ):
                raise
        self._owner = self._session = None

    def _queue(self, kind, work):
        epoch = self._epoch

        def run(cancel, report):
            try:
                return work()
            except Exception as exc:
                # Never surface bridge payloads, engine identifiers or deck entry IDs.
                from mtg_core.diagnostics import get_logger

                get_logger(__name__).exception("Play operation failed: %s", kind)
                code = getattr(exc, "code", "")
                if code == "SNAPSHOT_NOT_READY":
                    return "waiting", None
                from .decks import DeckTranslationError

                if isinstance(exc, DeckTranslationError):
                    return (
                        "error",
                        "A selected deck contains unsupported cards or printing information. Review it in Deck Editor; no cards were replaced.",
                    )
                if kind == "start":
                    return (
                        "error",
                        "Could not start the game. Check that the compatible local Play runtime is installed and both decks are supported.",
                    )
                return (
                    "error",
                    "The game connection could not finish this request. Its outcome may be unknown. Close the game before starting again.",
                )

        job = self.jobs.submit(run)
        self._operations[job] = kind, epoch

    def start(self, setup, decks, *, oracle_lookup=None):
        if self.active or self.busy or self.closing:
            return False
        if len(setup.seats) != 2 or len(decks) != 2:
            raise ValueError("Choose two local seats and decks.")
        self._epoch += 1
        self._viewer = setup.seats[0].seat_id
        self._seats = {seat.seat_id for seat in setup.seats}
        self._revision = -1
        self._submitted.clear()
        self._blocked = False
        self.active = True
        self.statusChanged.emit("Starting your local game…")

        def create():
            self._owner = self.adapter_factory()
            try:
                self._owner.__enter__()
                self._session = self._owner.create_game(
                    setup, decks, oracle_lookup=oracle_lookup
                )
            except Exception:
                # Preserve the owner on unconfirmed cleanup for an explicit retry.
                self._close_owner()
                raise
            return "started", None

        self._queue("start", create)
        return True

    def conceal(self):
        self._epoch += 1
        self.timer.stop()
        self._viewer = self._snapshot = None
        self._revision = -1
        self.viewCleared.emit()

    def reveal(self, seat_id):
        if (
            not self.active
            or self.closing
            or self._blocked
            or seat_id not in self._seats
        ):
            return
        self.conceal()
        self._viewer = seat_id
        self.timer.start()
        self.refresh()

    def refresh(self):
        if (
            not self.active
            or self.closing
            or self._blocked
            or self.busy
            or self._viewer is None
        ):
            return
        viewer = self._viewer

        def read():
            self._session.poll(viewer, timeout=0)
            return "snapshot", self._session.snapshot(viewer)

        self._queue("refresh", read)

    def submit(self, view, method, *args):
        """Require the exact displayed snapshot, invalidating obsolete handlers."""
        allowed = {
            "perform",
            "choose",
            "select_mana_source",
            "choose_number",
            "choose_amounts",
            "finish_selection",
            "cancel",
        }
        if (
            method not in allowed
            or self.busy
            or self.closing
            or self._blocked
            or view is None
            or view is not self._snapshot
            or view.decision is None
            or self._viewer in self._submitted
        ):
            return False
        decision = view.decision.decision_id
        viewer = self._viewer
        self._submitted[viewer] = decision
        self._snapshot = None
        self.viewCleared.emit()
        self.statusChanged.emit("Submitting your decision…")
        self._queue(
            "command",
            lambda: (
                "command",
                getattr(self._session, method)(viewer, decision, *args),
            ),
        )
        return True

    def stop(self):
        if self.closing:
            return
        self.closing = True
        self.conceal()
        self.statusChanged.emit("Closing the local game…")

        def close():
            self._close_owner()
            return "stopped", None

        # Do not cancel an in-flight engine call or retry uncertain commands.
        self._queue("stop", close)

    @C.pyqtSlot(str, str, object)
    def _completed(self, job, state, value):
        if state not in ("completed", "failed", "cancelled"):
            return
        operation = self._operations.pop(job, None)
        if operation is None:
            return
        kind, epoch = operation
        if epoch != self._epoch:
            return
        outcome, payload = (
            value
            if state == "completed"
            else ("error", "The local game could not finish its background request.")
        )
        if outcome == "started":
            self.timer.start()
            self.statusChanged.emit("Waiting for the opening game state…")
        elif outcome == "snapshot":
            if payload.viewer_id != self._viewer:
                return
            if payload.revision < self._revision:
                return
            self._revision = payload.revision
            if payload.status == "failed":
                self._blocked = True
                self.timer.stop()
                self._snapshot = None
                self.viewCleared.emit()
                self.statusChanged.emit(
                    "The local game connection failed. Close this game to recover."
                )
                return
            if payload.decision and payload.decision.decision_id == self._submitted.get(
                self._viewer
            ):
                return
            self._submitted.pop(self._viewer, None)
            if payload == self._snapshot:
                return
            self._snapshot = payload
            self.snapshotChanged.emit(payload)
            self.statusChanged.emit(payload.result or "Local game connected")
        elif outcome == "waiting":
            self._snapshot = None
            self.viewCleared.emit()
            self.statusChanged.emit("Waiting for the current game state…")
        elif outcome == "command":
            self.commandFinished.emit(payload)
            if payload.outcome == "rejected":
                self._submitted.pop(self._viewer, None)
                self.statusChanged.emit(
                    "That decision is no longer available. Refreshing the game…"
                )
            elif payload.outcome == "uncertain":
                self._blocked = True
                self.timer.stop()
                self.statusChanged.emit(
                    "The decision outcome is unknown. Close this game before starting again."
                )
            else:
                self.statusChanged.emit("Decision sent. Waiting for the game…")
        elif outcome == "stopped":
            self.active = self.closing = False
            self.statusChanged.emit("Ready for a new game")
            self.stopped.emit()
        elif outcome == "error":
            self._blocked = True
            self.timer.stop()
            self._snapshot = None
            self.viewCleared.emit()
            if kind == "start":
                self.active = self._owner is not None
            if kind == "stop":
                self.closing = False
            self.statusChanged.emit(payload)
