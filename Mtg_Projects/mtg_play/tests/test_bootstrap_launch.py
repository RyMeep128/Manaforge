"""Owned private delivery with tiny real children; no Unity, Qt or engine."""

import os
import subprocess
import sys
import threading
import time

import pytest

from mtg_play import connection_proof, launch_lifecycle as module
from mtg_play.launch_lifecycle import LaunchLifecycleError, LaunchOwner, LaunchState
from mtg_play.viewer_bootstrap import export_viewer_bootstrap


def payload():
    return export_viewer_bootstrap(
        port=43210,
        session_id="fixture-session",
        viewer_id="seat-one",
        engine_version="fixture-engine",
        artifact_manifest_sha256="a" * 64,
        viewer_key=bytes(range(32)),
    )


def child(code):
    return [sys.executable, "-I", "-c", code]


@pytest.fixture
def owner(monkeypatch):
    # These dummy roots create no descendants. Never use this proof for XMage.
    value = LaunchOwner(runtime_cleanup=lambda: True)
    monkeypatch.setattr(connection_proof, "STOP_TIMEOUT", 0.1)
    value.start_gateway(child("import sys; sys.stdin.buffer.read()"))
    value.gateway_ready()
    try:
        yield value
    finally:
        assert value.close().confirmed


def test_private_frame_is_complete_under_partial_writes_and_keeps_lifeline_open(
    owner, monkeypatch
):
    original = os.write
    monkeypatch.setattr(module.os, "write", lambda fd, data: original(fd, data[:3]))
    code = """
import json, sys
stream = sys.stdin.buffer
header = stream.read(4)
assert len(header) == 4
size = int.from_bytes(header, 'big')
assert 1 <= size <= 16384
value = json.loads(stream.read(size))
assert value['viewer_id'] == 'seat-one'
assert stream.read(1) == b''
"""
    owner.start_client(child(code), viewer_bootstrap=payload())
    assert owner.client_bootstrap_written
    assert owner.state == LaunchState.STARTING_CLIENT  # Writing is not readiness.
    assert owner._children["client"].poll() is None
    report = owner.close()
    assert report.confirmed and not report.forced
    assert all(item.exit_code == 0 for item in report.children)


@pytest.mark.parametrize("bad", [b"", b"x" * 16385, "private", 1])
def test_invalid_payload_creates_no_client(owner, bad):
    with pytest.raises(LaunchLifecycleError, match="^INVALID_CLIENT_BOOTSTRAP$"):
        owner.start_client(child("raise AssertionError()"), viewer_bootstrap=bad)
    assert owner.state == LaunchState.GATEWAY_READY
    assert "client" not in owner._children


@pytest.mark.parametrize("bad", [False, 0, -1, float("nan"), 61])
def test_invalid_write_budget_creates_no_client(owner, bad):
    with pytest.raises(LaunchLifecycleError, match="^INVALID_BOOTSTRAP_TIMEOUT$"):
        owner.start_client(
            child("raise AssertionError()"),
            viewer_bootstrap=payload(),
            bootstrap_timeout=bad,
        )
    assert "client" not in owner._children


def bounded_pipe(monkeypatch):
    if sys.platform.startswith("linux"):
        original = subprocess.Popen

        def spawn(*args, **kwargs):
            return original(*args, **kwargs, pipesize=4096)

        monkeypatch.setattr(module.subprocess, "Popen", spawn)


def test_stalled_real_pipe_times_out_and_reaps_owned_roots(owner, monkeypatch):
    bounded_pipe(monkeypatch)
    begin = time.monotonic()
    with pytest.raises(LaunchLifecycleError, match="^CLIENT_BOOTSTRAP_TIMEOUT$"):
        owner.start_client(
            child("import time; time.sleep(60)"),
            viewer_bootstrap=b"x" * 16384,
            bootstrap_timeout=0.08,
        )
    assert time.monotonic() - begin < 3
    assert not owner.client_bootstrap_written
    assert owner.state == LaunchState.CLOSED
    assert all(item.reaped for item in owner.report.children)


def test_cancel_during_stalled_write_is_nonblocking_and_reaps_owned_roots(
    owner, monkeypatch
):
    bounded_pipe(monkeypatch)
    timer = threading.Timer(0.15, owner.request_cancel)
    timer.start()
    try:
        with pytest.raises(LaunchLifecycleError, match="^LAUNCH_CANCELLED$"):
            owner.start_client(
                child("import time; time.sleep(60)"),
                viewer_bootstrap=b"x" * 16384,
                bootstrap_timeout=5,
            )
    finally:
        timer.cancel()
        timer.join()
    assert owner.state == LaunchState.CLOSED
    assert all(item.reaped for item in owner.report.children)


def test_nonblocking_setup_failure_is_sanitized_and_closes_owned_roots(
    owner, monkeypatch, caplog
):
    def fail(*args):
        raise OSError("PRIVATE_PATH_OR_CREDENTIAL")

    monkeypatch.setattr(module.os, "set_blocking", fail)
    with pytest.raises(LaunchLifecycleError, match="^CLIENT_BOOTSTRAP_WRITE_FAILED$"):
        owner.start_client(
            child("import sys; sys.stdin.buffer.read()"), viewer_bootstrap=payload()
        )
    assert owner.state == LaunchState.CLOSED
    assert "PRIVATE" not in repr(owner.report) + caplog.text
