"""Controlled subprocess tests; these do not start XMage or require Java."""

import importlib.util
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest

spec = importlib.util.spec_from_file_location(
    "connection_proof", Path(__file__).resolve().parents[1] / "connection_proof.py"
)
proof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proof)


@pytest.fixture
def children():
    processes = []

    def start(code):
        process = subprocess.Popen(
            [sys.executable, "-u", "-c", code],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        processes.append(process)
        return process

    yield start
    for process in processes:
        proof.stop_process(process)


@pytest.mark.parametrize(
    "line",
    [
        "not json",
        "[]",
        "null",
        "{}",
        '{"protocol":true,"event":"status"}',
        '{"protocol":2,"event":"status"}',
        '{"protocol":1,"event":[]}',
        '{"protocol":1,"event":"unknown"}',
        '{"protocol":1,"event":"callback"}',
    ],
)
def test_rejects_malformed_protocol(line):
    with pytest.raises(proof.ProofError):
        proof.decode_event(line)


def test_real_callback_is_distinct_from_connection(children):
    child = children(
        'print(\'{"protocol":1,"event":"connection"}\');'
        'print(\'{"protocol":1,"event":"callback","method":"CHATMESSAGE","message_id":7}\');'
        "input()"
    )
    events = proof.BridgeEvents(child, io.StringIO())
    event = events.wait("callback", time.monotonic() + 5)
    assert event["message_id"] == 7
    assert events.callbacks == [event]
    proof.stop_process(child)
    events.thread.join(timeout=2)


def test_wait_times_out_without_callback(children):
    child = children('print(\'{"protocol":1,"event":"connection"}\');input()')
    events = proof.BridgeEvents(child, io.StringIO())
    with pytest.raises(proof.ProofError, match="Timed out"):
        events.wait("callback", time.monotonic() + 0.2)
    assert not events.callbacks
    proof.stop_process(child)
    events.thread.join(timeout=2)


def test_unexpected_exit(children):
    child = children("raise SystemExit(3)")
    events = proof.BridgeEvents(child, io.StringIO())
    with pytest.raises(proof.ProofError, match="exited unexpectedly"):
        events.wait("callback", time.monotonic() + 5)
    events.thread.join(timeout=2)


def test_malformed_subprocess_output(children):
    child = children("print('engine log accidentally on stdout')")
    events = proof.BridgeEvents(child, io.StringIO())
    with pytest.raises(proof.ProofError, match="Malformed bridge JSON"):
        events.wait("status", time.monotonic() + 5)
    events.thread.join(timeout=2)


def test_engine_error_propagates(children):
    child = children(
        'print(\'{"protocol":1,"event":"error","message":"version mismatch"}\')'
    )
    events = proof.BridgeEvents(child, io.StringIO())
    with pytest.raises(proof.ProofError, match="version mismatch"):
        events.wait("connected", time.monotonic() + 5)
    events.thread.join(timeout=2)


def test_request_ids_are_correlated(children):
    child = children(
        'print(\'{"protocol":1,"event":"status","request_id":"old"}\');'
        'print(\'{"protocol":1,"event":"status","request_id":"current"}\')'
    )
    events = proof.BridgeEvents(child, io.StringIO())
    assert (
        events.wait("status", time.monotonic() + 5, "current")["request_id"]
        == "current"
    )
    events.thread.join(timeout=2)


def test_normal_shutdown_reaps_only_owned_child(children):
    owned = children('import sys;sys.exit(0 if input() == "shutdown" else 2)')
    unrelated = children("input()")
    result = proof.stop_process(owned, "shutdown")
    assert result["exit_code"] == 0
    assert result["reaped"] and not result["forced"]
    assert unrelated.poll() is None
    assert proof.stop_process(owned)["exit_code"] == 0


def test_forced_cleanup_when_child_ignores_stdin(children, monkeypatch):
    child = children("import time;time.sleep(60)")
    monkeypatch.setattr(proof, "STOP_TIMEOUT", 0.2)
    result = proof.stop_process(child, "shutdown")
    assert result["reaped"] and result["forced"]


def test_missing_runtime_is_actionable(tmp_path):
    with pytest.raises(proof.ProofError, match="Missing Java tool"):
        proof.validate_installation(tmp_path, tmp_path)


def test_modified_artifact_is_rejected(tmp_path, monkeypatch):
    (tmp_path / "java/jre1.8.0_201/bin").mkdir(parents=True)
    (tmp_path / "java/jre1.8.0_201/bin/java.exe").touch()
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin/javac.exe").touch()
    (tmp_path / "engine.jar").write_bytes(b"different")
    (tmp_path / "artifacts.json").write_text(
        json.dumps(
            {
                "artifacts": {"engine.jar": "0" * 64},
            }
        )
    )
    monkeypatch.setattr(proof, "HERE", tmp_path)
    with pytest.raises(proof.ProofError, match="artifact/version mismatch"):
        proof.validate_installation(tmp_path, tmp_path)


def test_occupied_port_does_not_disturb_listener():
    listener = proof.reserve_port()
    port = listener.getsockname()[1]
    try:
        with pytest.raises(proof.ProofError, match="unavailable"):
            proof.reserve_port(port)
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass
    finally:
        listener.close()


def test_server_exit_and_timeout(children, tmp_path):
    log = tmp_path / "server.log"
    log.write_text("Still starting")
    child = children("raise SystemExit(4)")
    child.wait(timeout=5)
    with pytest.raises(proof.ProofError, match="server exited"):
        proof.wait_for_server(child, log, time.monotonic() + 1)
    live = children("input()")
    with pytest.raises(proof.ProofError, match="startup timed out"):
        proof.wait_for_server(live, log, time.monotonic() + 0.1)


def test_generated_config_preserves_original(tmp_path):
    original = tmp_path / "bundle/xmage/mage-server"
    for folder in ("lib", "plugins", "config"):
        (original / folder).mkdir(parents=True)
    config = b'<config><server serverAddress="0.0.0.0" authenticationActivated="true"/></config>'
    (original / "config/config.xml").write_bytes(config)
    (original / "server.msg.txt").write_text("hello")
    server = proof.prepare_workspace(tmp_path / "bundle", tmp_path / "run", 1234, 1235)
    settings = proof.ET.parse(server / "config/config.xml").getroot().find("server")
    assert settings.attrib == {
        "serverAddress": "127.0.0.1",
        "authenticationActivated": "false",
        "port": "1234",
        "secondaryBindPort": "1235",
    }
    assert (original / "config/config.xml").read_bytes() == config
