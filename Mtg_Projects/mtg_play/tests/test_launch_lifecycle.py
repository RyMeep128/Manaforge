"""Ownership/state regressions plus tiny real children; no Unity or XMage."""

from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mtg_play import launch_lifecycle as module
from mtg_play import connection_proof
from mtg_play.launch_lifecycle import LaunchLifecycleError, LaunchOwner, LaunchState


class StubChild:
    def __init__(self):
        self.returncode = None

    def poll(self):
        return self.returncode


@pytest.fixture
def rig(monkeypatch):
    children, stops, commands = [], [], []

    def spawn(command, **kwargs):
        commands.append((command, kwargs))
        child = StubChild()
        children.append(child)
        return child

    def stop(child):
        stops.append(child)
        child.returncode = 0 if child.returncode is None else child.returncode
        return dict(exit_code=child.returncode, reaped=True, forced=False)

    monkeypatch.setattr(module.subprocess, "Popen", spawn)
    monkeypatch.setattr(module, "stop_process", stop)
    return children, stops, commands


def active(owner):
    owner.start_gateway(["fixture-gateway"])
    owner.gateway_ready()
    owner.start_client(["fixture-client"])
    owner.client_ready()


def test_ordered_startup_and_reverse_owned_cleanup(rig):
    children, stops, commands = rig
    owner = LaunchOwner()
    active(owner)
    assert owner.state == LaunchState.ACTIVE
    report = owner.close(runtime_cleanup=lambda: True)
    assert stops == list(reversed(children))
    assert [child.role for child in report.children] == ["client", "gateway"]
    assert report.confirmed and not report.forced and owner.state == LaunchState.CLOSED
    for command, options in commands:
        assert isinstance(command, tuple)
        assert options["shell"] is False and options["close_fds"] is True
        assert options["stdout"] == options["stderr"] == subprocess.DEVNULL
    assert owner.close() is report
    with pytest.raises(FrozenInstanceError):
        report.confirmed = False


@pytest.mark.parametrize("step", ["gateway_ready", "start_client", "client_ready"])
def test_out_of_order_readiness_or_client_launch_is_rejected(rig, step):
    owner = LaunchOwner()
    with pytest.raises(LaunchLifecycleError, match="^INVALID_LAUNCH_TRANSITION$"):
        getattr(owner, step)(["fixture-client"]) if step == "start_client" else getattr(
            owner, step
        )()
    assert not rig[0]


def test_root_exit_never_proves_engine_cleanup_or_allows_retry(rig):
    owner = LaunchOwner()
    active(owner)
    report = owner.close()
    assert all(child.reaped for child in report.children)
    assert not report.runtime_confirmed and not report.confirmed
    assert owner.state == LaunchState.CLEANUP_BLOCKED
    with pytest.raises(LaunchLifecycleError, match="^INVALID_LAUNCH_TRANSITION$"):
        owner.start_gateway(["fixture-retry"])
    assert owner.close(runtime_cleanup=lambda: True).confirmed


@pytest.mark.parametrize("evidence", [None, False, "yes", 1])
def test_cleanup_requires_explicit_boolean_proof(rig, evidence):
    owner = LaunchOwner()
    active(owner)
    assert not owner.close(runtime_cleanup=lambda: evidence).confirmed


def test_cleanup_callback_failure_does_not_expose_private_contents(rig, caplog):
    owner = LaunchOwner()
    active(owner)

    def broken():
        raise OSError("PRIVATE_TOKEN_OR_DECK")

    report = owner.close(runtime_cleanup=broken)
    assert not report.confirmed
    assert "PRIVATE" not in repr(report) + caplog.text


def test_cleanup_continues_after_one_child_failure_and_can_retry(rig, monkeypatch):
    children, stops, _ = rig
    owner = LaunchOwner()
    active(owner)
    good_stop = module.stop_process

    def first_failure(child):
        if child is children[1]:
            raise OSError("PRIVATE_PAYLOAD")
        return good_stop(child)

    monkeypatch.setattr(module, "stop_process", first_failure)
    report = owner.close(runtime_cleanup=lambda: True)
    assert stops == [children[0]]
    assert report.children[0].code == "CHILD_CLEANUP_UNCONFIRMED"
    assert report.children[0].forced is None
    assert not report.confirmed and "PRIVATE" not in repr(report)
    monkeypatch.setattr(module, "stop_process", good_stop)
    assert owner.close(runtime_cleanup=lambda: True).confirmed


def test_forced_cleanup_history_survives_retry(rig, monkeypatch):
    owner = LaunchOwner()
    active(owner)
    original = module.stop_process

    def force(child):
        return {**original(child), "forced": True}

    monkeypatch.setattr(module, "stop_process", force)
    assert owner.close().forced
    monkeypatch.setattr(module, "stop_process", original)
    report = owner.close(runtime_cleanup=lambda: True)
    assert report.confirmed and report.forced


def test_cancel_before_start_creates_no_child(rig):
    owner = LaunchOwner()
    owner.request_cancel()
    with pytest.raises(LaunchLifecycleError, match="^LAUNCH_CANCELLED$"):
        owner.start_gateway(["fixture"])
    assert not rig[0] and owner.report.confirmed


def test_cancel_during_spawn_still_registers_and_reaps_child(rig, monkeypatch):
    owner = LaunchOwner()
    original = module.subprocess.Popen

    def cancel_then_spawn(*args, **kwargs):
        owner.request_cancel()
        return original(*args, **kwargs)

    monkeypatch.setattr(module.subprocess, "Popen", cancel_then_spawn)
    with pytest.raises(LaunchLifecycleError, match="^LAUNCH_CANCELLED$"):
        owner.start_gateway(["fixture"])
    assert len(rig[0]) == 1 and len(rig[1]) == 1
    assert owner.state == LaunchState.CLEANUP_BLOCKED


def test_partial_start_failure_preserves_other_child_for_confirmed_cleanup(
    rig, monkeypatch
):
    owner = LaunchOwner()
    owner.start_gateway(["fixture"])
    owner.gateway_ready()

    def fail(*args, **kwargs):
        raise OSError("PRIVATE_EXECUTABLE_PATH")

    monkeypatch.setattr(module.subprocess, "Popen", fail)
    with pytest.raises(LaunchLifecycleError, match="^CHILD_START_FAILED$"):
        owner.start_client(["fixture-client"])
    assert len(rig[1]) == 1 and owner.state == LaunchState.CLEANUP_BLOCKED


def test_startup_deadline_closes_owned_child_without_synthesizing_readiness(rig):
    now = [10.0]
    owner = LaunchOwner(startup_timeout=5, clock=lambda: now[0])
    owner.start_gateway(["fixture"])
    now[0] = 15
    with pytest.raises(LaunchLifecycleError, match="^LAUNCH_STARTUP_TIMEOUT$"):
        owner.gateway_ready()
    assert len(rig[1]) == 1 and owner.state == LaunchState.CLEANUP_BLOCKED


def test_gateway_crash_prevents_client_spawn_and_is_not_a_game_result(rig):
    owner = LaunchOwner()
    owner.start_gateway(["fixture"])
    owner.gateway_ready()
    rig[0][0].returncode = 17
    with pytest.raises(LaunchLifecycleError, match="^OWNED_CHILD_EXITED$"):
        owner.start_client(["fixture-client"])
    assert len(rig[0]) == 1
    assert owner.report.children[0].exit_code == 17
    assert owner.state == LaunchState.CLEANUP_BLOCKED


@pytest.mark.parametrize("timeout", [0, -1, True, float("nan"), float("inf")])
def test_invalid_startup_budget_is_rejected(timeout):
    with pytest.raises(LaunchLifecycleError, match="^INVALID_STARTUP_TIMEOUT$"):
        LaunchOwner(startup_timeout=timeout)


@pytest.mark.parametrize(
    "command", ["shell command", [], [""], ["program", None], ["bad\x00command"]]
)
def test_invalid_command_never_spawns(rig, command):
    owner = LaunchOwner()
    with pytest.raises(LaunchLifecycleError, match="^INVALID_CHILD_COMMAND$"):
        owner.start_gateway(command)
    assert not rig[0] and owner.state == LaunchState.NEW


def test_context_exit_reports_unconfirmed_cleanup(rig):
    owner = LaunchOwner()
    with pytest.raises(LaunchLifecycleError, match="^LAUNCH_CLEANUP_UNCONFIRMED$"):
        with owner:
            active(owner)
    assert owner.state == LaunchState.CLEANUP_BLOCKED


def test_context_exit_preserves_original_failure_and_adds_safe_cleanup_note(rig):
    owner = LaunchOwner()
    failure = RuntimeError("synthetic failure")
    with pytest.raises(RuntimeError) as caught:
        with owner:
            active(owner)
            raise failure
    assert caught.value is failure
    assert "LAUNCH_CLEANUP_UNCONFIRMED" in failure.__notes__
    assert owner.state == LaunchState.CLEANUP_BLOCKED


def test_context_exit_accepts_explicit_runtime_proof(rig):
    with LaunchOwner(runtime_cleanup=lambda: True) as owner:
        active(owner)
    assert owner.report.confirmed and owner.state == LaunchState.CLOSED


def test_failed_poll_during_cleanup_cannot_prevent_other_children_stopping(
    rig, monkeypatch
):
    owner = LaunchOwner()
    active(owner)
    client = rig[0][1]
    original = module.stop_process

    def broken_poll():
        raise OSError("PRIVATE_PATH")

    client.poll = broken_poll

    def broken_stop(child):
        if child is client:
            raise OSError("PRIVATE_CONTENT")
        return original(child)

    monkeypatch.setattr(module, "stop_process", broken_stop)
    report = owner.close(runtime_cleanup=lambda: True)
    assert not report.confirmed
    assert report.children[0].exit_code is None and report.children[0].forced is None
    assert report.children[1].reaped and "PRIVATE" not in repr(report)


def test_owner_import_is_independent_of_qt_core_and_engine_installations():
    root = str(Path(__file__).resolve().parents[2])
    code = f"import sys; sys.path.insert(0, {root!r}); import mtg_play.launch_lifecycle; assert not any(name.startswith(('PyQt', 'mtg_core')) for name in sys.modules)"
    subprocess.run([sys.executable, "-I", "-c", code], check=True, timeout=10)


def reap_fixture(process):
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)
    if process.stdin:
        process.stdin.close()


def test_real_eof_cleanup_leaves_unrelated_process_running():
    owner = LaunchOwner()
    bystander = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        command = [sys.executable, "-c", "import sys; sys.stdin.buffer.read()"]
        owner.start_gateway(command)
        owner.gateway_ready()
        owner.start_client(command)
        owner.client_ready()
        report = owner.close(
            runtime_cleanup=lambda: True
        )  # These fixtures have no descendants.
        assert report.confirmed and not report.forced
        assert all(child.exit_code == 0 for child in report.children)
        assert bystander.poll() is None
    finally:
        for child in owner._children.values():
            reap_fixture(child)
        reap_fixture(bystander)


def test_real_forced_stop_is_reported_and_does_not_claim_descendant_cleanup(
    monkeypatch,
):
    monkeypatch.setattr(connection_proof, "STOP_TIMEOUT", 0.05)
    owner = LaunchOwner()
    try:
        owner.start_gateway([sys.executable, "-c", "import time; time.sleep(60)"])
        report = owner.close()
        assert report.forced and report.children[0].reaped
        assert not report.confirmed and owner.state == LaunchState.CLEANUP_BLOCKED
    finally:
        for child in owner._children.values():
            reap_fixture(child)
