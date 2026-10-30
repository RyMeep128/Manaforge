"""Explicit offline opponent preflight; only workers own the optional runtime."""

from copy import deepcopy
from random import SystemRandom

from PyQt6 import QtCore as C
from mtg_ui.jobs import JobQueue
from .decks import DeckTranslationError
from .presentation import local_adapter


class OpponentRandomizer(C.QObject):
    changed = C.pyqtSignal()
    message = C.pyqtSignal(str)
    selected = C.pyqtSignal(int)

    def __init__(self, parent=None, *, adapter_factory=local_adapter):
        super().__init__(parent)
        self.jobs = JobQueue(self)
        self.jobs.status.connect(self._completed)
        self.jobs.progress.connect(self._progress)
        self.jobs.idle.connect(self.changed)
        self.factory = adapter_factory
        self._owner = None  # Worker-only; retained after uncertain cleanup.
        self.cleanup_pending = False
        self._cancelled = False

    @property
    def busy(self):
        return self.jobs.busy or self.cleanup_pending

    def _close_owner(self):
        if self._owner is None:
            return
        try:
            self._owner.close()
        except Exception as error:
            result = getattr(self._owner, "result", None)
            if (
                getattr(error, "code", None) != "ENGINE_RUNTIME_FAILED"
                or result is None
                or any(code is None for _, code in result.process_exit_codes)
            ):
                raise
        self._owner = None

    def start(self, documents, format, current=None, *, oracle_lookup=None):
        if self.busy or format not in {"freeform", "commander"}:
            return False
        self._cancelled = False

        def work(cancel, report):
            eligible = []
            outcome = {"state": "failed"}
            try:
                copies = tuple(deepcopy(document) for document in documents)
                if not cancel.is_set():
                    report({"phase": "starting"})
                    self._owner = self.factory()
                    self._owner.__enter__()
                    for index, document in enumerate(copies):
                        if cancel.is_set():
                            break
                        report(
                            {
                                "phase": "checking",
                                "current": index + 1,
                                "total": len(copies),
                            }
                        )
                        try:
                            valid = self._owner.validate_deck(
                                document, format, oracle_lookup=oracle_lookup
                            )
                        except DeckTranslationError:
                            continue  # This exact source cannot be prepared by the engine.
                        if valid is True:
                            eligible.append(index)
                    if not cancel.is_set():
                        choices = (
                            [index for index in eligible if index != current]
                            if len(eligible) > 1
                            else eligible
                        )
                        outcome = (
                            {
                                "state": "selected",
                                "index": SystemRandom().choice(choices),
                            }
                            if choices
                            else {"state": "empty"}
                        )
            except Exception:
                # No raw engine exception or private card data reaches queue logs/UI.
                outcome = {"state": "failed"}
            finally:
                report({"phase": "cleanup"})
                try:
                    self._close_owner()
                except Exception:
                    outcome = {"state": "cleanup"}
            if cancel.is_set() and outcome["state"] != "cleanup":
                outcome = {"state": "cancelled"}
            return outcome

        self.jobs.submit(work, quiet=True)
        self.changed.emit()
        return True

    def cancel(self):
        self._cancelled = True
        self.jobs.cancel_all()

    def retry_cleanup(self):
        if self.jobs.busy or not self.cleanup_pending:
            return

        def work(cancel, report):
            try:
                self._close_owner()
                return {"state": "cancelled"}
            except Exception:
                return {"state": "cleanup"}

        self.jobs.submit(work, quiet=True)
        self.changed.emit()

    @C.pyqtSlot(str, object)
    def _progress(self, job, value):
        phase = value.get("phase") if isinstance(value, dict) else None
        if phase == "checking":
            self.message.emit(
                f"Checking opponent decks with XMage: {value['current']} of {value['total']}"
            )
        elif phase == "starting":
            self.message.emit("Starting offline XMage to check opponent decks...")
        elif phase == "cleanup":
            self.message.emit("Closing opponent preparation runtime...")

    @C.pyqtSlot(str, str, object)
    def _completed(self, job, status, value):
        if status not in {"completed", "failed", "cancelled"}:
            return
        state = (
            value.get("state", "failed")
            if isinstance(value, dict)
            else "cancelled"
            if status == "cancelled"
            else "failed"
        )
        if status != "completed" and self.cleanup_pending:
            state = "cleanup"  # Cancelling a queued retry does not prove cleanup.
        if state == "selected" and self._cancelled:
            state = "cancelled"
        self.cleanup_pending = state == "cleanup"
        if state == "selected" and not self._cancelled:
            self.selected.emit(value["index"])
            self.message.emit(
                "Opponent deck selected after XMage validation. Review it before starting."
            )
        else:
            self.message.emit(
                {
                    "empty": "No saved decks passed XMage eligibility for this format. Your selection has been kept.",
                    "cleanup": "Runtime cleanup is unconfirmed. Retry preparation cleanup before starting or leaving Play.",
                    "cancelled": "Opponent preparation cancelled. Your selection has been kept.",
                }.get(
                    state,
                    "Could not verify opponent decks. Your selection has been kept; try again.",
                )
            )
        self.changed.emit()
