"""Serialized, asynchronous public-contract boundary for the local Play workspace.

Only the worker queue touches the adapter/session. Qt consumers receive a single
seat's immutable snapshot; epochs invalidate queued replies after leaving a view.
"""

from math import isfinite
import time
import threading

from PyQt6 import QtCore as C
from mtg_ui.jobs import JobQueue
from .diagnostics import LifecycleDiagnostics, STAGE_LABELS

OPENING_STATE_TIMEOUT = 60


def local_adapter():
    # Import the optional runtime only for an explicit match or deck preflight.
    from .adapter import LocalGameAdapter

    return LocalGameAdapter()


class _SetupFailure(RuntimeError):
    """Safe, presentation-owned startup text containing no engine identifiers."""


class _SessionFailure(RuntimeError):
    def __init__(self, code, cause=None):
        self.code = code
        self.cause = cause
        super().__init__(code)


SETUP_CAUSES = {
    "SERVER_RESPONSE_INVALID": "The local engine returned an unreadable deck response.",
    "SERVER_CONTROL_TIMEOUT": "The local engine did not answer the deck request in time.",
    "SERVER_RESPONSE_ACCESS_TIMEOUT": "Windows kept the local engine response file locked.",
    "ENGINE_CONTROL_LOST": "The local engine control connection was lost.",
    "ENGINE_EXITED": "The local engine exited during preparation.",
    "ENGINE_UNAVAILABLE": "The local engine is no longer available.",
    "LOCAL_CARD_DATABASE_BUSY": "The local card database is busy. Let other library operations finish, then retry.",
    "LOCAL_CARD_DATABASE_ERROR": "The local card database could not resolve the selected cards.",
    "PYTHON_NAME_ERROR": "An internal deck-preparation variable was undefined.",
    "RUNTIME_CANCELLED": "Runtime preparation was cancelled.",
    "PYTHON_TYPE_ERROR": "An internal deck-preparation type error occurred.",
    "PYTHON_ATTRIBUTE_ERROR": "An internal deck-preparation interface error occurred.",
    "PYTHON_KEY_ERROR": "The deck response was missing a required field.",
    "PYTHON_VALUE_ERROR": "Deck preparation received an invalid value.",
    "DECK_TRANSLATION_FAILED": "Selected deck entries could not be translated for the engine.",
    "UNCLASSIFIED_SETUP_ERROR": "An internal preparation error occurred.",
}


def _setup_cause(error):
    """Fixed codes only: never retain exception text, prompts or deck payloads."""
    import sqlite3
    from .decks import DeckTranslationError

    code = getattr(error, "code", None)
    if isinstance(code, str) and code in SETUP_CAUSES:
        return code
    if isinstance(error, DeckTranslationError):
        return "DECK_TRANSLATION_FAILED"
    if isinstance(error, sqlite3.Error):
        return (
            "LOCAL_CARD_DATABASE_BUSY"
            if getattr(error, "sqlite_errorcode", None)
            in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
            else "LOCAL_CARD_DATABASE_ERROR"
        )
    for kind, label in (
        (NameError, "NAME"),
        (TypeError, "TYPE"),
        (AttributeError, "ATTRIBUTE"),
        (KeyError, "KEY"),
        (ValueError, "VALUE"),
    ):
        if isinstance(error, kind):
            return "PYTHON_" + label + "_ERROR"
    return "UNCLASSIFIED_SETUP_ERROR"


class SessionController(C.QObject):
    snapshotChanged = C.pyqtSignal(object)
    statusChanged = C.pyqtSignal(str)
    startupProgress = C.pyqtSignal(object)
    _lifecycleProgress = C.pyqtSignal(int, object)
    viewCleared = C.pyqtSignal()
    interactionPending = C.pyqtSignal()
    commandFinished = C.pyqtSignal(object)
    stopped = C.pyqtSignal()

    def __init__(
        self, parent=None, *, adapter_factory=local_adapter, authorized_viewer_id=None
    ):
        super().__init__(parent)
        self.jobs = JobQueue(self)
        self.jobs.status.connect(self._completed)
        self._lifecycleProgress.connect(
            self._lifecycle_progress, C.Qt.ConnectionType.QueuedConnection
        )
        self.adapter_factory = adapter_factory
        self._authorized_viewer = authorized_viewer_id
        self._startup_cancel = threading.Event()
        self._owner = self._session = None  # Worker-owned, never exposed to widgets.
        self._opening_stage = None  # Worker-owned readiness deadline and stage token.
        self._operations = {}
        self._epoch = 0
        self._viewer = None
        self._session_id = None
        self._seats = set()
        self._revision = -1
        self._snapshot = None
        self._submitted = {}
        self._blocked = False
        self.concession_pending = False
        self.active = self.closing = False
        self.timer = C.QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.refresh)

    @C.pyqtSlot(int, object)
    def _lifecycle_progress(self, epoch, value):
        if epoch != self._epoch or not self.active or self.closing:
            return
        if not isinstance(value, dict):
            return
        stage, state = value.get("stage"), value.get("state")
        if not isinstance(stage, str) or stage not in STAGE_LABELS:
            return
        if not isinstance(state, str) or state not in {
            "started",
            "completed",
            "failed",
            "cancelled",
        }:
            return
        elapsed = value.get("elapsed_ms")
        if type(elapsed) not in (int, float) or not isfinite(elapsed) or elapsed < 0:
            return
        code = value.get("code")
        if code is not None and not isinstance(code, str):
            return
        if code not in {
            None,
            *(
                "PLAY_" + stage.upper() + "_" + suffix
                for suffix in ("FAILED", "TIMEOUT", "UNCERTAIN")
            ),
        }:
            return
        # Forward only fixed stage data, never an arbitrary adapter payload.
        progress = {
            key: value.get(key) for key in ("stage", "state", "elapsed_ms", "code")
        }
        self.startupProgress.emit(progress)
        if state == "started":
            self.statusChanged.emit(STAGE_LABELS[stage] + "...")
        elif state == "failed":
            from mtg_core.diagnostics import get_logger

            get_logger(__name__).warning(
                "Play lifecycle failed stage=%s elapsed_ms=%s code=%s",
                stage,
                progress["elapsed_ms"],
                code,
            )

    @property
    def busy(self):
        return self.jobs.busy

    def _close_owner(self):
        """Close on the worker; a failed game can still have confirmed cleanup."""
        if self._owner is None:
            return
        if self._opening_stage is not None:
            tracker, token, _ = self._opening_stage
            tracker.end(token, cancelled=True)
            self._opening_stage = None
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

                code = getattr(exc, "code", "")
                if code == "SNAPSHOT_NOT_READY":
                    return "waiting", None
                get_logger(__name__).warning(
                    "Play operation failed operation=%s type=%s",
                    kind,
                    type(exc).__name__,
                )
                if code.startswith("UNSUPPORTED_DECISION"):
                    return (
                        "error",
                        "This game requires a decision that this Play preview cannot display. Close the game to recover.",
                    )
                from .decks import DeckTranslationError

                if isinstance(exc, _SetupFailure):
                    return "error", str(exc)
                if isinstance(exc, DeckTranslationError):
                    return (
                        "error",
                        "A selected deck contains unsupported cards or printing information. Review it in Deck Editor; no cards were replaced.",
                    )
                if kind == "start" or code.startswith("PLAY_OPENING_STATE_"):
                    stage = next(
                        (
                            stage
                            for stage in STAGE_LABELS
                            if code
                            in {
                                "PLAY_" + stage.upper() + "_" + suffix
                                for suffix in ("FAILED", "TIMEOUT", "UNCERTAIN")
                            }
                        ),
                        None,
                    )
                    if stage is not None:
                        label = STAGE_LABELS[stage].lower()
                        cause = getattr(exc, "cause", None)
                        detail = (
                            " "
                            + SETUP_CAUSES[cause]
                            + " Details: "
                            + code
                            + " / "
                            + cause
                            + "."
                            if cause in SETUP_CAUSES
                            else " Check the local runtime or selected decks, then try again."
                        )
                        return "error", (
                            "Could not start the game while " + label + "." + detail
                        )
                    return (
                        "error",
                        "Could not start the game. Check that the compatible local Play runtime is installed and both decks are supported.",
                    )
                return (
                    "error",
                    "The game connection could not finish this request. Its outcome may be unknown. Close the game before starting again.",
                )

        job = self.jobs.submit(run, quiet=kind == "refresh")
        self._operations[job] = kind, epoch, self._viewer

    def start(self, setup, decks, *, oracle_lookup=None):
        if self.active or self.busy or self.closing:
            return False
        if len(setup.seats) != 2 or len(decks) != 2:
            raise ValueError("Choose two local seats and decks.")
        if self._authorized_viewer is not None and (
            setup.seats[0].seat_id != self._authorized_viewer
            or setup.seats[0].controller != "local_human"
            or setup.seats[1].controller != "engine_ai"
        ):
            raise ValueError("Offline Play requires your seat and one AI opponent.")
        self._epoch += 1
        self._viewer = self._authorized_viewer or setup.seats[0].seat_id
        self._session_id = None
        self._seats = {
            seat.seat_id for seat in setup.seats if seat.controller == "local_human"
        }
        self._revision = -1
        self._submitted.clear()
        self._blocked = False
        self.concession_pending = False
        self._startup_cancel = threading.Event()
        startup_cancel = self._startup_cancel
        self.active = True
        self.statusChanged.emit("Starting your local game…")

        epoch = self._epoch

        def create():
            from copy import deepcopy

            # Preserve canonical identities and isolate both pilots from saved decks.
            documents = tuple(deepcopy(document) for document in decks)
            self._owner = self.adapter_factory()
            try:
                observer = getattr(self._owner, "set_progress_callback", None)
                if observer is not None:
                    observer(lambda value: self._lifecycleProgress.emit(epoch, value))
                bind_cancel = getattr(self._owner, "set_cancel_event", None)
                if bind_cancel is not None:
                    bind_cancel(startup_cancel)
                self._owner.__enter__()
                self._session = self._owner.create_game(
                    setup, documents, oracle_lookup=oracle_lookup
                )
            except Exception as error:
                lifecycle = getattr(self._owner, "lifecycle", None)
                failure = lifecycle.failure if lifecycle is not None else None
                cause = _setup_cause(error)
                from mtg_core.diagnostics import get_logger

                get_logger(__name__).warning(
                    "Play setup failed stage=%s cause=%s",
                    failure["stage"] if failure is not None else "setup",
                    cause,
                )
                # Preserve the owner on unconfirmed cleanup for an explicit retry.
                self._close_owner()
                from .decks import DeckTranslationError

                if isinstance(error, DeckTranslationError):
                    identifiers = {issue.entry_id for issue in error.issues}
                    names = sorted(
                        {
                            entry.name
                            for document in decks
                            for entry in document.deck.entries
                            if entry.entry_id in identifiers and entry.name
                        }
                    )
                    detail = (
                        ", ".join(names[:8])
                        or "commander selection or deck configuration"
                    )
                    raise _SetupFailure(
                        "Review these deck entries in Deck Editor: "
                        + detail
                        + ". Their cards, selected printings, or configuration could not be loaded. No cards were replaced."
                    ) from error
                if failure is not None:
                    raise _SessionFailure(failure["code"], cause=cause) from error
                raise
            tracker = getattr(self._owner, "lifecycle", None) or LifecycleDiagnostics(
                lambda value: self._lifecycleProgress.emit(epoch, value)
            )
            self._opening_stage = (
                tracker,
                tracker.begin("opening_state"),
                time.monotonic() + OPENING_STATE_TIMEOUT,
            )
            return "started", self._session.session_id

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
            or self._authorized_viewer is not None
            and seat_id != self._authorized_viewer
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
            try:
                events = self._session.poll(viewer, timeout=0)
                for event in events:
                    if event.kind == "session_failed":
                        raise _SessionFailure(event.code or "ENGINE_UNAVAILABLE")
                view = self._session.snapshot(viewer)
            except Exception as error:
                if self._opening_stage is None:
                    raise
                tracker, token, deadline = self._opening_stage
                waiting = getattr(error, "code", None) == "SNAPSHOT_NOT_READY"
                if waiting and time.monotonic() < deadline:
                    raise
                tracker.end(token, failure="TIMEOUT" if waiting else "FAILED")
                self._opening_stage = None
                self._close_owner()
                raise _SessionFailure(
                    "PLAY_OPENING_STATE_TIMEOUT"
                    if waiting
                    else "PLAY_OPENING_STATE_FAILED"
                ) from error
            if self._opening_stage is not None:
                tracker, token, _ = self._opening_stage
                tracker.end(token)
                self._opening_stage = None
            return "snapshot", view

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
            or view.viewer_id != self._viewer
            or view.result is not None
            or view.decision is None
            or self._viewer in self._submitted
        ):
            return False
        decision = view.decision.decision_id
        viewer = self._viewer
        self._submitted[viewer] = decision
        self._snapshot = None
        self.interactionPending.emit()
        self.statusChanged.emit("Submitting your decision…")
        self._queue(
            "command",
            lambda: (
                "command",
                getattr(self._session, method)(viewer, decision, *args),
            ),
        )
        return True

    def concede(self, view):
        if (
            self.busy
            or self.concession_pending
            or self.closing
            or self._blocked
            or view is None
            or view is not self._snapshot
            or view.viewer_id != self._viewer
            or view.result
        ):
            return False
        viewer = view.viewer_id
        self.concession_pending = True
        self._snapshot = None
        self.interactionPending.emit()
        self.statusChanged.emit("Submitting concession…")
        self._queue("concede", lambda: ("command", self._session.concede(viewer)))
        return True

    def stop(self):
        if self.closing:
            return
        self.closing = True
        if self._session_id is None:
            self._startup_cancel.set()
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
        kind, epoch, viewer = operation
        outcome, payload = (
            value
            if state == "completed"
            else ("error", "The local game could not finish its background request.")
        )
        if outcome == "started" and self.active and not self.closing:
            self._session_id = payload
        if epoch != self._epoch:
            if (
                kind in ("command", "concede")
                and outcome == "command"
                and payload.outcome == "rejected"
            ):
                self._submitted.pop(viewer, None)
                if kind == "concede":
                    self.concession_pending = False
            if kind in ("command", "concede") and (
                outcome == "error"
                or outcome == "command"
                and payload.outcome == "uncertain"
            ):
                self._blocked = True
                self.timer.stop()
                self._snapshot = None
                self.viewCleared.emit()
                self.statusChanged.emit(
                    "The previous decision outcome is unknown. Close this game before starting again."
                )
            return
        if outcome == "started":
            self.timer.start()
            self.statusChanged.emit("Waiting for the opening game state…")
        elif outcome == "snapshot":
            if payload.viewer_id != self._viewer:
                return
            if payload.session_id != self._session_id:
                self._blocked = True
                self.timer.stop()
                self._snapshot = None
                self.viewCleared.emit()
                self.statusChanged.emit(
                    "The game state did not match this session. Close the game to recover."
                )
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
                if kind == "concede":
                    self.concession_pending = False
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
            if kind == "start" or self._owner is None:
                self.active = self._owner is not None
            if kind == "stop":
                self.closing = False
            self.statusChanged.emit(payload)
