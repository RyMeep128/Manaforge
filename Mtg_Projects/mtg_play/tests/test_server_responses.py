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
@pytest.mark.parametrize("requires_pass", [False, True])
@pytest.mark.parametrize("seats", [2, 3, 4, 5])
def test_commander_keeps_all_hands_before_conceding_and_waits_for_game_over(
    monkeypatch, reject, seats, requires_pass
):
    players = {str(index) for index in range(seats)}
    finished = set()
    eliminated = set()
    kept = set()
    pending = {}
    sent = []
    polls = 0
    priority_seen = False
    passed = set()
    objects = [SimpleNamespace(zone="hand") for _ in range(7)] + [
        SimpleNamespace(
            zone="command",
            characteristics=SimpleNamespace(name="Isamaru, Hound of Konda"),
        )
        for _ in range(seats)
    ]

    def poll(player):
        nonlocal polls
        polls += 1
        assert polls < 100, "acceptance stalled waiting for a terminal callback"
        if player in pending and (not requires_pass or player in passed):
            pending[player] -= 1
            if not pending[player]:
                del pending[player]
                eliminated.add(player)
        # Individual concessions do not finish the multiplayer game. Only emit
        # final statuses/results once all opponents' commands were processed.
        if len(sent) == seats - 1 and not pending:
            finished.update(players)
        return ()

    def snapshot(player):
        nonlocal priority_seen
        terminal = player in finished
        decision = None
        if sent:
            decision = SimpleNamespace(family="target", prompt="Discard a card")
            if requires_pass and player == "0" and pending:
                decision = SimpleNamespace(family="selection", decision_id="priority")
        elif kept == players and polls >= seats * 3:
            priority_seen = True
            decision = SimpleNamespace(family="selection")
        elif player not in kept and polls >= 4:
            decision = SimpleNamespace(
                family="boolean",
                prompt="Mulligan?",
                decision_id=player,
                options=[SimpleNamespace(label="No", option_id="keep")],
            )
        return SimpleNamespace(
            status="finished" if terminal else "active",
            objects=objects,
            players=[
                SimpleNamespace(
                    player_id=seat,
                    eliminated=seat in eliminated,
                    left_game=seat in eliminated,
                )
                for seat in players
            ],
            actions=[SimpleNamespace(kind="pass", action_id="pass")],
            decision=decision,
            result=("won" if player == "0" else "did_not_win") if terminal else None,
        )

    def concede(player):
        assert kept == players, "conceded before every hand was kept"
        assert priority_seen, "conceded before the engine processed keep responses"
        assert not pending, "overlapping concessions can lose an engine signal"
        sent.append(player)
        pending[player] = 3
        return SimpleNamespace(
            outcome="rejected" if reject else "submitted", code="SESSION_NOT_ACTIVE"
        )

    def choose(player, decision, option):
        assert not sent, "gameplay command sent during concession cleanup"
        assert decision == player and option == "keep"
        kept.add(player)
        return SimpleNamespace(outcome="submitted")

    def perform(player, decision, action):
        assert player == "0" and decision == "priority" and action == "pass"
        passed.update(pending)
        return SimpleNamespace(outcome="submitted")

    session = SimpleNamespace(
        poll=poll, snapshot=snapshot, concede=concede, choose=choose, perform=perform
    )
    adapter = SimpleNamespace(create_game=lambda *args: session)
    monkeypatch.setattr("mtg_play.adapter_acceptance.time.sleep", lambda seconds: None)
    if reject:
        with pytest.raises(AdapterError, match="^SESSION_NOT_ACTIVE$"):
            commander_acceptance(adapter, seats)
    else:
        report = commander_acceptance(adapter, seats)
        assert sent == [str(index) for index in range(1, seats)]
        assert set(report["kept_hands"]) == players
        assert set(report["finished"]) == players
        assert report["results"]["0"] == "won"
