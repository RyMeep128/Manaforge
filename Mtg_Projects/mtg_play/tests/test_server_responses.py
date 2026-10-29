"""CI regressions for response-file sharing locks, without launching XMage."""

import io
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mtg_core"))
from mtg_play.adapter import AdapterError, LocalGameAdapter
from mtg_play.adapter_acceptance import checked_poll, commander_acceptance
from mtg_play.contracts import GameEvent


@pytest.fixture
def response_control(tmp_path, monkeypatch):
    adapter = LocalGameAdapter()
    server = SimpleNamespace(stdin=io.StringIO(), poll=lambda: None)
    adapter._runtime = (None, None, None, None, server, tmp_path)
    response = tmp_path / "manaforge-responses" / "request.json"
    response.parent.mkdir()
    response.write_text('{"status": "ok"}', encoding="utf-8")
    monkeypatch.setattr("mtg_play.adapter.uuid.uuid4", lambda: "request")
    monkeypatch.setattr("mtg_play.adapter.time.sleep", lambda seconds: None)
    return adapter, server, response


@pytest.mark.parametrize("locked_operation", ["read", "unlink"])
def test_sharing_lock_retries_same_response_without_resending(
    response_control, monkeypatch, locked_operation
):
    adapter, server, response = response_control
    original_read, original_unlink = Path.read_text, Path.unlink
    counts = dict(read=0, unlink=0)

    def read(path, *args, **kwargs):
        counts["read"] += 1
        if locked_operation == "read" and counts["read"] == 1:
            raise PermissionError("simulated Windows sharing lock")
        return original_read(path, *args, **kwargs)

    def unlink(path, *args, **kwargs):
        counts["unlink"] += 1
        if locked_operation == "unlink" and counts["unlink"] == 1:
            raise PermissionError("simulated Windows sharing lock")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(Path, "unlink", unlink)
    assert adapter._server_request(command="metadata") == {"status": "ok"}
    assert len(server.stdin.getvalue().splitlines()) == 1
    assert not response.exists()
    if locked_operation == "unlink":
        assert counts["read"] == 1


@pytest.mark.parametrize("operation", ["read_text", "unlink"])
def test_permanent_lock_fails_with_bounded_sanitized_error(
    response_control, monkeypatch, operation
):
    adapter, server, response = response_control
    clock = iter((0, 0, 31))
    monkeypatch.setattr("mtg_play.adapter.time.monotonic", lambda: next(clock))

    def locked(*args, **kwargs):
        raise PermissionError("private filesystem detail")

    monkeypatch.setattr(Path, operation, locked)
    with pytest.raises(AdapterError, match="^SERVER_RESPONSE_ACCESS_TIMEOUT$"):
        adapter._server_request(command="metadata")
    assert len(server.stdin.getvalue().splitlines()) == 1
    assert response.exists()


def test_invalid_atomic_response_is_not_retried(response_control):
    adapter, server, response = response_control
    response.write_text("invalid JSON", encoding="utf-8")
    with pytest.raises(AdapterError, match="^SERVER_RESPONSE_INVALID$"):
        adapter._server_request(command="metadata")
    assert len(server.stdin.getvalue().splitlines()) == 1


def test_acceptance_keeps_multiplayer_failure_cause():
    session = SimpleNamespace(
        poll=lambda player: (
            GameEvent("session_failed", player, 0, "ENGINE_METADATA_TIMEOUT"),
        )
    )
    with pytest.raises(AdapterError, match="^ENGINE_METADATA_TIMEOUT$"):
        checked_poll(session, "one")


@pytest.mark.parametrize("reject", [False, True])
def test_commander_concessions_wait_for_terminal_confirmation(monkeypatch, reject):
    finished = set()
    pending = {}
    sent = []
    objects = [SimpleNamespace(zone="hand") for _ in range(7)] + [
        SimpleNamespace(
            zone="command",
            characteristics=SimpleNamespace(name="Isamaru, Hound of Konda"),
        )
        for _ in range(3)
    ]

    def poll(player):
        if player in pending:
            pending[player] -= 1
            if not pending[player]:
                del pending[player]
                finished.add(player)
                if len(finished) == 2:
                    finished.add("0")
        return ()

    def snapshot(player):
        terminal = player in finished
        return SimpleNamespace(
            status="finished" if terminal else "active",
            objects=objects,
            decision=None,
            result="did_not_win" if terminal else None,
        )

    def concede(player):
        assert not pending, "concession sent before previous elimination completed"
        sent.append(player)
        pending[player] = 3
        return SimpleNamespace(
            outcome="rejected" if reject else "submitted", code="SESSION_NOT_ACTIVE"
        )

    session = SimpleNamespace(poll=poll, snapshot=snapshot, concede=concede)
    adapter = SimpleNamespace(create_game=lambda *args: session)
    monkeypatch.setattr("mtg_play.adapter_acceptance.time.sleep", lambda seconds: None)
    if reject:
        with pytest.raises(AdapterError, match="^SESSION_NOT_ACTIVE$"):
            commander_acceptance(adapter, 3)
    else:
        report = commander_acceptance(adapter, 3)
        assert sent == ["1", "2"]
        assert set(report["finished"]) == {"0", "1", "2"}
