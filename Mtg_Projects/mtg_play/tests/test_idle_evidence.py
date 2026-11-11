"""Failure evidence must survive without publishing raw runtime diagnostics."""

import importlib.util
import json
from pathlib import Path
import sys

import pytest
from mtg_play.diagnostics import LifecycleDiagnostics

spec = importlib.util.spec_from_file_location(
    "idle_evidence",
    Path(__file__).resolve().parents[3] / "tools/check_play_idle_connection.py",
)
idle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(idle)


def test_failed_compile_report_does_not_copy_runtime_details():
    diagnostics = LifecycleDiagnostics()
    token = diagnostics.begin("bridge_compilation")
    diagnostics.end(token, failure="FAILED")
    result = idle.sanitized_report(
        {"success": False, "error": "private-token", "workspace": "private-path"},
        diagnostics,
        "runtime_setup",
        None,
    )
    assert result["failed_stage"] == "bridge_compilation"
    assert result["reason_code"] == "BRIDGE_COMPILATION_FAILED"
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("raises", [False, True])
def test_cli_writes_failure_report_before_raising(tmp_path, monkeypatch, raises):
    output = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "idle",
            "--xmage-root",
            str(tmp_path),
            "--jdk-path",
            str(tmp_path),
            "--output",
            str(output),
        ],
    )

    def proof(*args, **kwargs):
        diagnostics = kwargs["diagnostics"]
        token = diagnostics.begin("runtime_validation")
        diagnostics.end(token, failure="FAILED")
        if raises:
            raise RuntimeError("private-token")
        return {"success": False, "error": "private-token", "workspace": "private-path"}

    monkeypatch.setattr(idle.transport, "run_proof", proof)
    monkeypatch.setattr(idle.subprocess, "check_output", lambda *a, **k: "a" * 40)
    with pytest.raises(AssertionError, match="IDLE_PROOF_FAILED"):
        idle.main()
    report = json.loads(output.read_text())
    assert report["success"] is False
    assert report["failed_stage"] == "runtime_validation"
    assert report["commit"] == "a" * 40
    assert "private" not in output.read_text()
