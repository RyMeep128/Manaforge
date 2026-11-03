"""Lifecycle regression tests executed by CI, without a real runtime."""

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mtg_play.adapter import AdapterError, LocalGameAdapter
from mtg_play.diagnostics import LifecycleDiagnostics, diagnostic_category


def test_measured_timeout_keeps_operation_and_excludes_exception_contents(caplog):
    timestamps = iter((10.0, 12.5))
    tracker = LifecycleDiagnostics(clock=lambda: next(timestamps))
    secret = "PRIVATE_CARD_IDENTITY_AND_ENGINE_PAYLOAD"
    with pytest.raises(TimeoutError, match=secret):
        with tracker.stage("server_startup"):
            raise TimeoutError(secret)
    assert tracker.failure == dict(
        stage="server_startup",
        state="failed",
        elapsed_ms=2500.0,
        code="PLAY_SERVER_STARTUP_TIMEOUT",
    )
    assert secret not in json.dumps(tracker.records) + caplog.text
    assert diagnostic_category(tracker.failure["code"]) == "game_lifecycle_failure"


def test_uncertain_outcome_is_preserved_and_not_replayed():
    tracker = LifecycleDiagnostics()
    original = AdapterError("COMMAND_OUTCOME_UNCERTAIN")
    attempts = []
    with pytest.raises(AdapterError) as failure:
        with tracker.stage("table_creation"):
            attempts.append("request")
            raise original
    assert failure.value is original
    assert attempts == ["request"]
    assert tracker.failure["code"] == "PLAY_TABLE_CREATION_UNCERTAIN"


def test_progress_consumer_cannot_modify_history_or_interrupt_engine_work(caplog):
    def broken_observer(row):
        row["stage"] = "PRIVATE_CONTENT"
        raise RuntimeError("PRIVATE_CALLBACK_ERROR")

    tracker = LifecycleDiagnostics(broken_observer)
    with tracker.stage("deck_resolution"):
        pass
    assert [row["state"] for row in tracker.records] == ["started", "completed"]
    assert all(row["stage"] == "deck_resolution" for row in tracker.records)
    assert "PRIVATE" not in caplog.text + json.dumps(tracker.records)
    exported = tracker.records
    exported[0]["stage"] = "modified"
    assert tracker.records[0]["stage"] == "deck_resolution"


def test_history_is_bounded_and_unknown_stage_is_rejected():
    tracker = LifecycleDiagnostics()
    for _ in range(100):
        with tracker.stage("deck_submission"):
            pass
    assert len(tracker.records) == 128
    with pytest.raises(ValueError, match="Unknown Play lifecycle stage"):
        tracker.begin("PRIVATE_CARD_NAME")
    assert "PRIVATE" not in json.dumps(tracker.records)


@pytest.mark.parametrize("missing_cleanup", [False, True])
def test_failed_startup_preserves_stage_error_only_after_confirmed_cleanup(
    monkeypatch, missing_cleanup
):
    from mtg_play import adapter as module

    def failed_proof(bundle, jdk, *, runtime_consumer, diagnostics, cancel=None):
        try:
            with diagnostics.stage("bridge_compilation"):
                raise TimeoutError("private compilation payload")
        except TimeoutError:
            return dict(
                success=False,
                server=dict(started=missing_cleanup, exit_code=None),
                bridge=dict(started=False),
            )

    monkeypatch.setattr(module.transport, "run_proof", failed_proof)
    for _ in range(3):
        owner = LocalGameAdapter()
        expected = (
            "ENGINE_RUNTIME_FAILED"
            if missing_cleanup
            else "PLAY_BRIDGE_COMPILATION_TIMEOUT"
        )
        with pytest.raises(AdapterError, match="^" + expected + "$"):
            owner.__enter__()
        assert owner._done.is_set() and owner._release.is_set()
        owner._thread.join(timeout=1)
        assert not owner._thread.is_alive()
        expected_processes = (("server", None),) if missing_cleanup else ()
        assert owner.result.process_exit_codes == expected_processes


@pytest.mark.parametrize("report_unwritable", [False, True])
@pytest.mark.parametrize("cancellable", [False, True])
def test_bridge_compile_failure_reports_stage_and_reaps_only_started_processes(
    tmp_path, monkeypatch, report_unwritable, cancellable
):
    from types import SimpleNamespace as NS
    from mtg_play import connection_proof as proof

    tracker = LifecycleDiagnostics()
    monkeypatch.setattr(proof, "HERE", tmp_path)
    monkeypatch.setattr(
        proof,
        "validate_installation",
        lambda bundle, jdk: (
            tmp_path / "java.exe",
            tmp_path / "javac.exe",
            dict(engine="pinned-fixture"),
        ),
    )
    monkeypatch.setattr(
        proof,
        "reserve_port",
        lambda port=0: NS(getsockname=lambda: ("127.0.0.1", 1234), close=lambda: None),
    )
    monkeypatch.setattr(proof, "prepare_workspace", lambda *args: tmp_path / "server")
    monkeypatch.setattr(
        proof.subprocess, "run", lambda *args, **kwargs: NS(returncode=1)
    )

    def forbidden_child(command, **kwargs):
        if cancellable and command[0] == str(tmp_path / "javac.exe"):
            assert kwargs.get("creationflags") == getattr(
                proof.subprocess, "CREATE_NO_WINDOW", 0
            )
            return NS(poll=lambda: 1, returncode=1, pid=123, stdin=None, stdout=None)
        raise AssertionError("Compilation failure must not launch an engine")

    monkeypatch.setattr(proof.subprocess, "Popen", forbidden_child)
    if report_unwritable:
        original_write = Path.write_text

        def fail_result_write(path, *args, **kwargs):
            if path.name == "result.json":
                raise PermissionError("PRIVATE_STORAGE_ERROR")
            return original_write(path, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", fail_result_write)
    import threading

    report = proof.run_proof(
        tmp_path,
        tmp_path,
        diagnostics=tracker,
        cancel=threading.Event() if cancellable else None,
    )
    assert report["compiler"]["started"] is cancellable
    if cancellable:
        assert report["compiler"]["exit_code"] == 1 and report["compiler"]["reaped"]
    assert not report["success"]
    assert report["server"] == report["bridge"] == {"started": False}
    assert tracker.failure["code"] == "PLAY_BRIDGE_COMPILATION_FAILED"
    assert tracker.records[-1]["stage"] == "process_cleanup"
    assert tracker.records[-1]["state"] == "completed"
    if report_unwritable:
        assert report["diagnostics_write_failed"] is True
    else:
        assert json.loads((Path(report["workspace"]) / "result.json").read_text())[
            "lifecycle"
        ]


def test_cancelled_stage_is_not_recorded_as_an_engine_failure():
    from mtg_play.adapter import AdapterError

    tracker = LifecycleDiagnostics()
    with pytest.raises(AdapterError):
        with tracker.stage("bridge_compilation"):
            raise AdapterError("RUNTIME_CANCELLED")
    assert tracker.records[-1]["state"] == "cancelled"
    assert tracker.failure is None


@pytest.mark.parametrize("exit_code", [0, None])
def test_runtime_report_retains_started_compiler_even_when_exit_is_unknown(exit_code):
    owner = LocalGameAdapter.__new__(LocalGameAdapter)
    owner._runtime_result = dict(
        success=exit_code == 0,
        compiler=dict(started=True, exit_code=exit_code, forced=False),
        server=dict(started=False),
        bridge=dict(started=False),
    )
    assert owner.result.process_exit_codes == (("compiler", exit_code),)
    assert owner.result.success is (exit_code == 0)
