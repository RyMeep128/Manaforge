"""Private inherited-pipe delivery checks using tiny owned children, no engine/UI."""

import os
import subprocess
import sys
import threading
import pytest
from mtg_play import connection_proof, launch_lifecycle as module
from mtg_play.gateway_bootstrap import (
    GatewayBootstrapError,
    MAX_GATEWAY_BOOTSTRAP_BYTES,
    frame_gateway_manifest,
)
from mtg_play.launch_lifecycle import LaunchOwner, LaunchLifecycleError, LaunchState


def child(code):
    return [sys.executable, "-I", "-c", code]


@pytest.fixture
def owner(monkeypatch):
    result = LaunchOwner(
        runtime_cleanup=lambda: True
    )  # These test roots have no engine descendants.
    monkeypatch.setattr(connection_proof, "STOP_TIMEOUT", 0.15)
    yield result
    assert result.close().confirmed


def test_gateway_frame_has_a_separate_bound_and_caller_owned_clearing():
    payload = b"x" * MAX_GATEWAY_BOOTSTRAP_BYTES
    frame = frame_gateway_manifest(payload)
    assert isinstance(frame, bytearray) and int.from_bytes(frame[:4], "big") == len(
        payload
    )
    assert frame[4:] == payload
    frame[:] = bytes(len(frame))
    assert payload[:1] == b"x"


@pytest.mark.parametrize(
    "bad",
    [
        b"",
        b"x" * (MAX_GATEWAY_BOOTSTRAP_BYTES + 1),
        "private",
        1,
        bytearray(b"private"),
    ],
    ids=["empty", "oversize", "text", "integer", "mutable"],
)
def test_invalid_gateway_payload_spawns_nothing(owner, bad):
    with pytest.raises(GatewayBootstrapError):
        frame_gateway_manifest(bad)
    with pytest.raises(LaunchLifecycleError, match="^INVALID_GATEWAY_BOOTSTRAP$"):
        owner.start_gateway(child("raise AssertionError()"), launch_manifest=bad)
    assert owner.state == LaunchState.NEW and owner._children == {}


@pytest.mark.parametrize("budget", [False, 0, -1, float("nan"), 61])
def test_invalid_gateway_budget_spawns_nothing(owner, budget):
    with pytest.raises(LaunchLifecycleError, match="^INVALID_BOOTSTRAP_TIMEOUT$"):
        owner.start_gateway(
            child("raise AssertionError()"),
            launch_manifest=b"{}",
            bootstrap_timeout=budget,
        )
    assert owner._children == {}


def test_partial_writes_are_complete_private_cleared_and_not_readiness(
    owner, monkeypatch
):
    original = os.write
    monkeypatch.setattr(module.os, "write", lambda fd, data: original(fd, data[:3]))
    frames = []
    write = owner._write_gateway_bootstrap

    def observe(process, frame, timeout):
        frames.append(frame)
        return write(process, frame, timeout)

    monkeypatch.setattr(owner, "_write_gateway_bootstrap", observe)
    code = "import sys,json; s=sys.stdin.buffer; n=int.from_bytes(s.read(4),'big'); assert n>16384; value=json.loads(s.read(n)); assert s.read(1)==b''"
    command = child(code)
    payload = b'{"document":"PRIVATE_LAUNCH_CANARY' + b"x" * 25000 + b'"}'
    owner.start_gateway(command, launch_manifest=payload)
    assert owner.gateway_manifest_written and not owner.client_bootstrap_written
    assert (
        owner.state == LaunchState.STARTING_GATEWAY
        and "PRIVATE_LAUNCH_CANARY" not in repr(command)
    )
    assert len(frames) == 1 and frames[0] == bytearray(len(frames[0]))
    with pytest.raises(LaunchLifecycleError, match="INVALID_LAUNCH_TRANSITION"):
        owner.start_client(child("raise AssertionError()"))
    report = owner.close()
    assert report.confirmed and not report.forced and report.children[0].exit_code == 0


def bound_pipe(monkeypatch):
    if sys.platform.startswith("linux"):
        spawn = subprocess.Popen
        monkeypatch.setattr(
            module.subprocess,
            "Popen",
            lambda *args, **kwargs: spawn(*args, **kwargs, pipesize=4096),
        )


def test_stalled_gateway_write_times_out_and_reaps_only_owned_child(owner, monkeypatch):
    bound_pipe(monkeypatch)
    with pytest.raises(LaunchLifecycleError, match="^GATEWAY_BOOTSTRAP_TIMEOUT$"):
        owner.start_gateway(
            child("import time; time.sleep(60)"),
            launch_manifest=b"x" * MAX_GATEWAY_BOOTSTRAP_BYTES,
            bootstrap_timeout=0.08,
        )
    assert not owner.gateway_manifest_written and owner.report.confirmed
    assert [x.role for x in owner.report.children] == ["gateway"] and all(
        x.reaped for x in owner.report.children
    )


def test_cancel_stalled_gateway_write_reaps_and_does_not_claim_delivery(
    owner, monkeypatch
):
    bound_pipe(monkeypatch)
    timer = threading.Timer(0.12, owner.request_cancel)
    timer.start()
    try:
        with pytest.raises(LaunchLifecycleError, match="^LAUNCH_CANCELLED$"):
            owner.start_gateway(
                child("import time; time.sleep(60)"),
                launch_manifest=b"x" * MAX_GATEWAY_BOOTSTRAP_BYTES,
            )
    finally:
        timer.cancel()
        timer.join()
    assert not owner.gateway_manifest_written and owner.report.confirmed


def test_gateway_write_failures_do_not_leak_input_or_native_errors(
    owner, monkeypatch, caplog
):
    def fail(*args):
        raise OSError("PRIVATE_LAUNCH_CANARY")

    monkeypatch.setattr(module.os, "set_blocking", fail)
    with pytest.raises(LaunchLifecycleError, match="^GATEWAY_BOOTSTRAP_WRITE_FAILED$"):
        owner.start_gateway(
            child("import sys; sys.stdin.buffer.read()"),
            launch_manifest=b"PRIVATE_LAUNCH_CANARY",
        )
    assert (
        owner.report.confirmed
        and "PRIVATE_LAUNCH_CANARY" not in repr(owner.report) + caplog.text
    )


def test_legacy_gateway_without_manifest_retains_its_existing_pipe_contract(owner):
    owner.start_gateway(child("import sys; sys.stdin.buffer.read()"))
    assert (
        not owner.gateway_manifest_written
        and owner.state == LaunchState.STARTING_GATEWAY
    )
    owner.gateway_ready()
    assert owner.close().confirmed


# Validation receipt is separate from runtime readiness and client admission.
def receipt_child(mode):
    code = """
import sys, hashlib, time, os
inp = sys.stdin.buffer
size = int.from_bytes(inp.read(4), 'big')
payload = inp.read(size)
text = b'MANAFORGE_MANIFEST_VALIDATED_V1:' + hashlib.sha256(payload).hexdigest().encode('ascii')
frame = len(text).to_bytes(4, 'big') + text
MODE
inp.read()
"""
    actions = {
        "valid": "sys.stdout.buffer.write(frame); sys.stdout.buffer.flush(); os.close(1)",
        "wrong": "sys.stdout.buffer.write(frame[:-1] + b'x'); sys.stdout.buffer.flush(); os.close(1)",
        "truncated": "sys.stdout.buffer.write(frame[:-1]); sys.stdout.buffer.flush(); os.close(1)",
        "extra": "sys.stdout.buffer.write((len(text)+1).to_bytes(4, 'big') + text + b'x'); sys.stdout.buffer.flush(); os.close(1)",
        "silent": "pass",
        "no_eof": "sys.stdout.buffer.write(frame); sys.stdout.buffer.flush()",
        "partial": "[ (sys.stdout.buffer.write(bytes([b])), sys.stdout.buffer.flush(), time.sleep(.001)) for b in frame ]; os.close(1)",
    }
    return child(code.replace("MODE", actions[mode]))


@pytest.mark.parametrize("mode", ["valid", "partial", "no_eof"])
def test_exact_receipt_keeps_client_blocked_until_independent_readiness(owner, mode):
    owner.start_gateway(
        receipt_child(mode),
        launch_manifest=b"public-fixture",
        expect_manifest_validation=True,
    )
    assert not owner.gateway_manifest_validated
    owner.wait_gateway_manifest_validation(timeout=5)
    assert owner.gateway_manifest_validated
    assert owner.state == LaunchState.STARTING_GATEWAY
    with pytest.raises(LaunchLifecycleError, match="^INVALID_LAUNCH_TRANSITION$"):
        owner.start_client(child("raise AssertionError()"))
    with pytest.raises(
        LaunchLifecycleError, match="^INVALID_MANIFEST_VALIDATION_REQUEST$"
    ):
        owner.wait_gateway_manifest_validation()
    assert owner.close().confirmed


@pytest.mark.parametrize("mode", ["wrong", "truncated", "extra", "silent"])
def test_receipt_failure_closes_owned_child_without_claiming_validation(owner, mode):
    owner.start_gateway(
        receipt_child(mode),
        launch_manifest=b"public-fixture",
        expect_manifest_validation=True,
    )
    expected = (
        "GATEWAY_VALIDATION_TIMEOUT"
        if mode == "silent"
        else "GATEWAY_VALIDATION_INVALID"
    )
    with pytest.raises(LaunchLifecycleError, match="^" + expected + "$"):
        owner.wait_gateway_manifest_validation(timeout=1 if mode == "silent" else 5)
    assert not owner.gateway_manifest_validated
    assert owner.report.confirmed and owner.state == LaunchState.CLOSED


def test_validation_wait_cancellation_reaps_owned_child(owner):
    owner.start_gateway(
        receipt_child("silent"),
        launch_manifest=b"public-fixture",
        expect_manifest_validation=True,
    )
    timer = threading.Timer(0.05, owner.request_cancel)
    timer.start()
    try:
        with pytest.raises(LaunchLifecycleError, match="^LAUNCH_CANCELLED$"):
            owner.wait_gateway_manifest_validation()
    finally:
        timer.join()
    assert owner.report.confirmed and not owner.gateway_manifest_validated


@pytest.mark.parametrize("timeout", [False, 0, -1, float("nan"), 61])
def test_invalid_validation_timeout_does_not_consume_pipe(owner, timeout):
    with pytest.raises(
        LaunchLifecycleError, match="^INVALID_MANIFEST_VALIDATION_TIMEOUT$"
    ):
        owner.wait_gateway_manifest_validation(timeout=timeout)
    assert owner.state == LaunchState.NEW


def test_validation_capture_requires_manifest_and_explicit_boolean(owner):
    for options in [
        dict(expect_manifest_validation=True),
        dict(expect_manifest_validation=1, launch_manifest=b"{}"),
    ]:
        with pytest.raises(
            LaunchLifecycleError, match="^INVALID_MANIFEST_VALIDATION_REQUEST$"
        ):
            owner.start_gateway(child("raise AssertionError()"), **options)
    assert owner.state == LaunchState.NEW and not owner._children
