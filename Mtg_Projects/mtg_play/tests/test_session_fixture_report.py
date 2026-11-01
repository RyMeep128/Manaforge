"""Packaged synthetic session evidence contracts; no engine or user data."""

import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location(
    "session_fixture_tool",
    Path(__file__).resolve().parents[3] / "tools/check_play_unity_session.py",
)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def report(code="SESSION_FIXTURE_READY", decisions=False):
    value = dict(
        probe_version=1,
        fixture_only=True,
        code=code,
        snapshot_count=2,
        event_count=1,
        viewer_cleared=code == "SESSION_FIXTURE_OWNER_EOF",
    )
    if decisions:
        completed = code != "SESSION_FIXTURE_READY"
        value.update(
            ack_count=2 if completed else 0,
            result_count=1 if completed else 0,
            decision_panel_cleared=completed,
        )
    return value


@pytest.mark.parametrize(
    "code",
    [
        "SESSION_FIXTURE_READY",
        "SESSION_FIXTURE_OWNER_EOF",
        "SESSION_FIXTURE_DECISION_COMPLETE",
    ],
)
def test_explicit_decision_evidence_has_submitted_confirmed_result_and_cleared_panel(
    code,
):
    tool.validate(report(code, True), code, True)


def test_existing_read_only_report_contract_is_unchanged():
    tool.validate(report(), "SESSION_FIXTURE_READY")
    with pytest.raises(RuntimeError):
        tool.validate(report(decisions=True), "SESSION_FIXTURE_READY")


@pytest.mark.parametrize(
    "field,value",
    [
        ("ack_count", 1),
        ("ack_count", True),
        ("result_count", 0),
        ("result_count", True),
        ("decision_panel_cleared", False),
    ],
)
def test_incomplete_decision_evidence_is_rejected(field, value):
    item = report("SESSION_FIXTURE_DECISION_COMPLETE", True)
    item[field] = value
    with pytest.raises(RuntimeError):
        tool.validate(item, "SESSION_FIXTURE_DECISION_COMPLETE", True)


def test_a_fixture_write_acknowledgement_is_not_a_completed_scenario():
    item = report("SESSION_FIXTURE_DECISION_COMPLETE", True)
    item.update(ack_count=1, result_count=0, decision_panel_cleared=False)
    with pytest.raises(RuntimeError):
        tool.validate(item, "SESSION_FIXTURE_DECISION_COMPLETE", True)
