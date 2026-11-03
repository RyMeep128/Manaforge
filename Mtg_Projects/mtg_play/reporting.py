"""Allowlisted Play feedback data; never serialize views, decks or raw logs."""

from math import isfinite
import re
from .diagnostics import STAGE_LABELS

STAGE_CODES = {
    "PLAY_" + stage.upper() + "_" + suffix
    for stage in STAGE_LABELS
    for suffix in ("FAILED", "TIMEOUT", "UNCERTAIN")
}
OPERATIONS = {"start", "refresh", "command", "concede", "stop"}


class PlayReport:
    def __init__(self, cause_codes):
        self.cause_codes = frozenset(cause_codes)
        self.compatibility = {}
        self.lifecycle = []
        self.failure = None
        self.format = None

    def accept(self, payload):
        if not isinstance(payload, dict):
            return
        compatibility = payload.get("compatibility")
        if isinstance(compatibility, dict):
            for field in ("manaforge_version", "adapter_version", "engine_version"):
                value = compatibility.get(field)
                if (
                    isinstance(value, str)
                    and re.fullmatch(
                        r"[0-9]+(?:\.[0-9]+){1,3}(?:[-.][A-Za-z0-9]+)*", value
                    )
                    and len(value) <= 48
                ):
                    self.compatibility[field] = value
            protocol = compatibility.get("protocol_version")
            if type(protocol) is int and 0 < protocol < 100:
                self.compatibility["protocol_version"] = protocol
            digest = compatibility.get("artifact_manifest_sha256")
            if isinstance(digest, str) and re.fullmatch(r"[0-9a-fA-F]{64}", digest):
                self.compatibility["artifact_manifest_sha256"] = digest
        rows = payload.get("lifecycle")
        if isinstance(rows, (list, tuple)):
            accepted = []
            for row in rows[-128:]:
                if not isinstance(row, dict):
                    continue
                stage, state, elapsed, code = (
                    row.get(key) for key in ("stage", "state", "elapsed_ms", "code")
                )
                if (
                    not isinstance(stage, str)
                    or stage not in STAGE_LABELS
                    or not isinstance(state, str)
                    or state not in {"started", "completed", "failed", "cancelled"}
                ):
                    continue
                if (
                    type(elapsed) not in (int, float)
                    or not isfinite(elapsed)
                    or elapsed < 0
                ):
                    continue
                expected = {
                    None,
                    *(
                        "PLAY_" + stage.upper() + "_" + suffix
                        for suffix in ("FAILED", "TIMEOUT", "UNCERTAIN")
                    ),
                }
                if not isinstance(code, (str, type(None))) or code not in expected:
                    continue
                accepted.append(
                    dict(stage=stage, state=state, elapsed_ms=elapsed, code=code)
                )
            self.lifecycle = accepted
        failure = payload.get("failure")
        if isinstance(failure, dict):
            operation, code, cause = (
                failure.get(key) for key in ("operation", "code", "cause")
            )
            if isinstance(operation, str) and operation in OPERATIONS:
                self.failure = dict(
                    operation=operation,
                    code=code
                    if isinstance(code, str)
                    and (
                        code in STAGE_CODES
                        or code in {"COMMAND_OUTCOME_UNCERTAIN", "UNSUPPORTED_DECISION"}
                        or code in self.cause_codes
                    )
                    else "UNCLASSIFIED_SETUP_ERROR",
                    cause=cause
                    if isinstance(cause, str) and cause in self.cause_codes
                    else "UNCLASSIFIED_SETUP_ERROR",
                )

    def snapshot(self, *, active, closing, busy):
        return dict(
            schema=1,
            mode="offline_ai",
            format=self.format
            if isinstance(self.format, str) and self.format in {"freeform", "commander"}
            else None,
            compatibility=dict(self.compatibility),
            lifecycle=[dict(row) for row in self.lifecycle],
            failure=dict(self.failure) if self.failure else None,
            session=dict(
                active=bool(active), closing=bool(closing), worker_busy=bool(busy)
            ),
        )
