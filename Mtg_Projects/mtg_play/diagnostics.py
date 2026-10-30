"""Bounded lifecycle diagnostics and sanitized compatibility categories."""

from collections import deque
from contextlib import contextmanager
import logging
import subprocess
import threading
import time


STAGE_LABELS = {
    "runtime_validation": "Checking the local Play runtime",
    "workspace_preparation": "Preparing the local game workspace",
    "bridge_compilation": "Preparing the game connection",
    "server_startup": "Starting the local rules engine",
    "client_connection": "Connecting to the local rules engine",
    "engine_handshake": "Checking the engine connection",
    "deck_resolution": "Resolving the selected decks",
    "player_connections": "Connecting local players",
    "table_creation": "Creating the match table",
    "deck_submission": "Submitting the selected decks",
    "match_start": "Starting the match",
    "opening_state": "Waiting for the opening game state",
    "runtime_shutdown": "Disconnecting from the local game",
    "process_cleanup": "Cleaning up the local game",
}


class LifecycleDiagnostics:
    """Numeric timings and allowlisted codes only; observers never own engine work.

    Callbacks run on the reporting worker. GUI consumers must marshal them through
    queued signals. History is bounded across repeated stages and cleanup retries.
    """

    def __init__(self, callback=None, *, clock=time.monotonic):
        self._callback, self._clock = callback, clock
        self._records = deque(maxlen=128)
        self._lock = threading.RLock()
        self._failure = None

    def set_callback(self, callback):
        with self._lock:
            self._callback = callback

    @property
    def records(self):
        with self._lock:
            return tuple(dict(row) for row in self._records)

    @property
    def failure(self):
        with self._lock:
            return None if self._failure is None else dict(self._failure)

    def _emit(self, row):
        with self._lock:
            self._records.append(dict(row))
            if row["state"] == "failed":
                self._failure = dict(row)
            callback = self._callback
        logging.getLogger(__name__).info(
            "Play lifecycle stage=%s state=%s elapsed_ms=%.1f code=%s",
            row["stage"],
            row["state"],
            row["elapsed_ms"],
            row["code"],
        )
        if callback is not None:
            try:
                callback(dict(row))
            except Exception:
                # A broken progress consumer must not interrupt or replay an action.
                logging.getLogger(__name__).warning("Play lifecycle observer failed")

    def begin(self, stage):
        if stage not in STAGE_LABELS:
            raise ValueError("Unknown Play lifecycle stage")
        started = self._clock()
        self._emit(dict(stage=stage, state="started", elapsed_ms=0.0, code=None))
        return stage, started

    def end(self, token, *, failure=None, cancelled=False):
        stage, started = token
        if stage not in STAGE_LABELS:
            raise ValueError("Unknown Play lifecycle stage")
        suffix = failure if failure in {"TIMEOUT", "UNCERTAIN", "FAILED"} else None
        self._emit(
            dict(
                stage=stage,
                state="failed" if suffix else "cancelled" if cancelled else "completed",
                elapsed_ms=round(max(0.0, self._clock() - started) * 1000, 1),
                code="PLAY_" + stage.upper() + "_" + suffix if suffix else None,
            )
        )

    @contextmanager
    def stage(self, stage):
        token = self.begin(stage)
        try:
            yield
        except BaseException as error:
            code = getattr(error, "code", None)
            failure = (
                "TIMEOUT"
                if isinstance(error, (TimeoutError, subprocess.TimeoutExpired))
                or isinstance(code, str)
                and code.endswith("_TIMEOUT")
                else "UNCERTAIN"
                if getattr(error, "code", None) == "COMMAND_OUTCOME_UNCERTAIN"
                else "FAILED"
            )
            self.end(token, failure=failure)
            raise
        else:
            self.end(token)


def diagnostic_category(code):
    if code == "AI_ACCEPTANCE_UNSUPPORTED_DECISION":
        return "acceptance_pilot_gap"
    if any(code.startswith("PLAY_" + stage.upper() + "_") for stage in STAGE_LABELS):
        return "game_lifecycle_failure"
    if code == "CARD_NOT_SUPPORTED":
        return "card_missing_from_pinned_engine"
    if code in {
        "PRINTING_NOT_RESOLVED",
        "ORACLE_ID_NOT_RESOLVED",
        "MISSING_CARD_NAME",
        "AMBIGUOUS_INSTANCE_PRINTING",
        "MISSING_RESOLUTION",
    }:
        return "identity_or_printing_resolution"
    if code in {
        "INVALID_QUANTITY",
        "DUPLICATE_ENTRY_ID",
        "UNSUPPORTED_SECTION",
        "COMMANDER_FORMAT_REQUIRED",
        "MISSING_COMMANDER_ENTRY",
        "EMPTY_MAINBOARD",
        "UNSUPPORTED_GAME_SETUP",
        "INVALID_SEATS",
        "INVALID_SEAT_IDENTITIES",
    }:
        return "unsupported_deck_configuration"
    if "DECISION_UNSUPPORTED" in code or code in {
        "UNSUPPORTED_DECISION",
        "UNSUPPORTED_PROMPT",
        "SCENARIO_TARGET_UNSUPPORTED",
    }:
        return "unsupported_game_decision"
    if code.startswith(("PINNED_METADATA_", "METADATA_")) or code in {
        "DUPLICATE_OBJECT_REFERENCES",
        "HIDDEN_IDENTITY_EXPOSED",
        "COPY_SOURCE_NOT_VISIBLE",
        "OPPONENT_HAND_EXPOSED",
        "OPPONENT_DECISION_EXPOSED",
    }:
        return "adapter_translation_failure"
    return "unexpected_engine_or_harness_behavior"
