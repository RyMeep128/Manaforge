"""Recovery ownership, explicit resume and bounded cross-thread lifecycle requests."""

import pytest
from mtg_play.recovery import MatchRecovery, RecoveryMailbox
from mtg_play.recovery import HostRecovery, atomic_json
import threading


def test_disconnect_never_resumes_or_replaces_a_seat_automatically():
    state = MatchRecovery()
    state.disconnect()
    assert state.paused and state.claimable
    assert not state.connected and not state.can_resume
    with pytest.raises(ValueError, match="RECOVERY_NOT_READY"):
        state.resume()
    generation = state.claim()
    assert generation == 1 and state.paused and not state.claimable
    assert not state.can_resume
    state.ready = True
    assert state.paused
    state.resume()
    assert not state.paused


def test_ai_seat_can_be_claimed_but_connected_human_cannot():
    state = MatchRecovery()
    with pytest.raises(ValueError, match="SEAT_UNAVAILABLE"):
        state.claim()
    with pytest.raises(ValueError, match="SEAT_UNAVAILABLE"):
        state.add_ai()
    state.disconnect()
    state.add_ai()
    assert state.controller == "ai" and state.paused and not state.can_resume
    state.ready = True
    state.resume()
    assert state.claimable
    state.claim()
    assert state.controller == "human" and state.paused and not state.ready
    with pytest.raises(ValueError, match="SEAT_UNAVAILABLE"):
        state.claim()


@pytest.mark.parametrize("terminal", ["ended", "finished"])
def test_terminal_seats_cannot_be_claimed_or_resumed(terminal):
    state = MatchRecovery(paused=True, controller="ai", connected=False, ready=True)
    setattr(state, terminal, True)
    assert not state.claimable and not state.can_resume
    with pytest.raises(ValueError):
        state.claim()


def test_recovery_mailbox_is_bounded():
    mailbox = RecoveryMailbox()
    for _ in range(16):
        mailbox.send("claim")
    with pytest.raises(ValueError, match="RECOVERY_BUSY"):
        mailbox.send("claim")


def host_recovery(tmp_path):
    (tmp_path / "seat-0").mkdir()
    atomic_json(
        tmp_path / "recovery-gateway-status.json",
        {"game": "game", "guest_native_id": "guest", "connected": False},
    )
    packets, gateway = [], []
    mailbox = RecoveryMailbox()
    host = HostRecovery(
        tmp_path,
        None,
        tmp_path,
        None,
        threading.Event(),
        lambda value: None,
        mailbox,
        {"viewer_key_hex": "old"},
        packets.append,
    )
    host.native_command = lambda action: {"ready": True, "ended": False}
    host.gateway_command = lambda action, **extra: gateway.append((action, extra))
    host.initialized = True
    return host, mailbox, packets, gateway


def test_claim_waits_for_pause_rotates_credentials_and_keeps_host_paused(tmp_path):
    host, mailbox, packets, gateway = host_recovery(tmp_path)
    host.state.disconnect()
    mailbox.send({"action": "claim", "ticket": "claimant"})
    host.tick()
    assert len(packets) == 1 and packets[0]["claim_ticket"] == "claimant"
    assert packets[0]["viewer_key_hex"] != "old"
    assert [action for action, _ in gateway] == ["pause", "rotate", "human"]
    assert host.state.paused and not host.state.can_resume


def test_stale_claim_cannot_disconnect_or_pause_an_occupied_seat(tmp_path):
    host, mailbox, packets, gateway = host_recovery(tmp_path)
    atomic_json(
        tmp_path / "recovery-gateway-status.json",
        {"game": "game", "guest_native_id": "guest", "connected": True},
    )
    mailbox.send({"action": "claim", "ticket": "too-late"})
    host.tick()
    assert host.state.connected and not host.state.paused
    assert packets == [] and gateway == []
