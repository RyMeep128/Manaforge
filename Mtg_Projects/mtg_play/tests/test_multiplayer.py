"""Seat ownership, private deck transfer, invitations and lobby start admission."""

from copy import deepcopy
import pytest
from generate_launch_fixtures import native_deck
from mtg_play.multiplayer import (
    MultiplayerLobby,
    relay_url,
    invite,
    parse_invite,
    export_remote_deck,
    import_remote_deck,
)


def test_offline_fills_other_seats_with_ai_and_stages_larger_counts():
    lobby = MultiplayerLobby(online=False)
    assert [s.kind for s in lobby.seats] == ["human", "ai"]
    with pytest.raises(ValueError):
        lobby.set_kind(1, "open")
    for count in (3, 4, 5, True):
        with pytest.raises(ValueError):
            MultiplayerLobby(players=count)


def test_online_seats_readiness_and_start_freeze():
    lobby = MultiplayerLobby()
    deck = native_deck(False)
    lobby.select(0, deck)
    lobby.ready(0, True)
    assert not lobby.can_start
    lobby.join()
    assert not lobby.seats[0].ready
    with pytest.raises(ValueError):
        lobby.set_kind(1, "ai")
    lobby.select(1, deck)
    lobby.ready(0, True)
    lobby.ready(1, True)
    assert lobby.can_start
    lobby.select(0, deck)
    assert not any(s.ready for s in lobby.seats)
    lobby.ready(0, True)
    lobby.ready(1, True)
    lobby.start()
    for action in (
        lambda: lobby.select(0, deck),
        lambda: lobby.leave(),
        lambda: lobby.ready(0, False),
    ):
        with pytest.raises(ValueError):
            action()


def test_ai_assignment_requires_deck_and_leaving_clears_human_seat():
    lobby = MultiplayerLobby()
    deck = native_deck(False)
    lobby.join()
    lobby.select(1, deck)
    lobby.ready(1, True)
    lobby.leave()
    assert lobby.seats[1].deck is None and lobby.seats[1].kind == "open"
    lobby.set_kind(1, "ai")
    lobby.select(0, deck)
    lobby.ready(0, True)
    assert not lobby.can_start
    lobby.select(1, deck)
    lobby.ready(0, True)
    assert lobby.can_start
    assert lobby.seats[1].ready
    assert "deck" not in lobby.public()["seats"][0]


def test_invitation_carries_custom_endpoint_and_rejects_insecure_urls():
    endpoint = "wss://example.test/custom"
    code = "ABCDEFGHJKLM"
    assert parse_invite(invite(endpoint, code), "") == (endpoint, code)
    assert parse_invite("abcd-efgh-jklm", endpoint) == (endpoint, code)
    for value in (
        "ws://example.test",
        "https://example.test",
        "wss://user:secret@example.test",
        "wss://example.test?token=secret",
    ):
        with pytest.raises(ValueError):
            relay_url(value)
    assert relay_url("ws://127.0.0.1:8787", development=True) == "ws://127.0.0.1:8787"


@pytest.mark.parametrize("commander", [False, True])
def test_remote_deck_transfer_strips_personal_assets_and_preserves_native_structure(
    commander,
):
    document = native_deck(commander)
    original = deepcopy(document.to_dict())
    format = "commander" if commander else "freeform"
    payload = export_remote_deck(document, format)
    assert document.to_dict() == original
    assert all(
        e["owned"] == 0 and e["image_asset_id"] is None
        for e in payload["deck"]["entries"]
    )
    restored = import_remote_deck(payload, format)
    assert export_remote_deck(restored, format) == payload
    invalid = deepcopy(payload)
    invalid["deck"]["entries"][0]["quantity"] = "12"
    with pytest.raises(ValueError):
        import_remote_deck(invalid, format)


def test_invalid_replacement_deck_cannot_leave_seat_ready():
    lobby = MultiplayerLobby()
    lobby.select(0, native_deck(False))
    lobby.ready(0, True)
    with pytest.raises(ValueError):
        lobby.select(0, object())
    assert lobby.seats[0].deck is None and not lobby.seats[0].ready


@pytest.mark.parametrize("code", ["GAMEPLAY_RESPONSE_UNPROVEN", "PRIVATE message"])
def test_host_observes_shared_failure_from_either_seat(tmp_path, code):
    from mtg_play.multiplayer_runtime import _raise_game_error
    from mtg_play.live_game import LiveGameError
    import json

    seat = tmp_path / "seat-0"
    seat.mkdir()
    (tmp_path / "game-error.json").write_text(json.dumps({"code": code}))
    expected = (
        code if code == "GAMEPLAY_RESPONSE_UNPROVEN" else "MULTIPLAYER_ENGINE_FAILED"
    )
    with pytest.raises(LiveGameError, match=expected):
        _raise_game_error(seat)


def test_tunnel_keeps_an_update_burst_ordered_while_socket_writer_is_paused(
    monkeypatch,
):
    import base64
    import threading
    from mtg_play.relay_client import LoopbackTunnel

    monkeypatch.setattr(LoopbackTunnel, "_run", lambda self: None)
    errors = []
    tunnel = LoopbackTunnel(lambda _: None, errors.append, target_port=1)
    entered, release = threading.Event(), threading.Event()
    progress = threading.Condition()
    sent = []

    class PausedSocket:
        def sendall(self, packet):
            with progress:
                sent.append(packet[4:])
                progress.notify_all()
            if len(sent) == 1:
                entered.set()
                if not release.wait(8):
                    raise OSError("Fixture socket was not released")

        def shutdown(self, _):
            release.set()

        def close(self):
            release.set()

    tunnel.socket = PausedSocket()
    payloads = [f"update-{i}".encode() for i in range(64)]

    def feed(raw):
        tunnel.feed({"data": base64.b64encode(raw).decode()})

    feed(payloads[0])
    writer = threading.Thread(target=tunnel._write, daemon=True)
    writer.start()
    try:
        assert entered.wait(3)
        for payload in payloads[1:]:
            feed(payload)
        assert errors == []
        assert not tunnel.cancel.is_set()
        release.set()
        with progress:
            assert progress.wait_for(lambda: len(sent) == len(payloads), timeout=5)
        assert sent == payloads
    finally:
        release.set()
        tunnel.close()
        writer.join(3)
        tunnel.thread.join(3)
    assert not writer.is_alive()
    assert tunnel.queued_bytes == 0


@pytest.mark.parametrize("byte_limit", [False, True])
def test_tunnel_queue_remains_bounded_and_preserves_the_first_failure(
    monkeypatch, byte_limit
):
    import base64
    from mtg_play.relay_client import LoopbackTunnel, MAX_FRAME, MAX_TUNNEL_FRAMES

    monkeypatch.setattr(LoopbackTunnel, "_run", lambda self: None)
    errors = []
    tunnel = LoopbackTunnel(lambda _: None, errors.append, target_port=1)
    try:
        raw = b"x" * (MAX_FRAME if byte_limit else 1)
        payload = {"data": base64.b64encode(raw).decode()}
        for _ in range(8 if byte_limit else MAX_TUNNEL_FRAMES):
            tunnel.feed(payload)
        assert errors == []
        tunnel.feed(payload)
        assert errors == ["TUNNEL_INPUT_OVERFLOW"]
        assert tunnel.failure_code == "TUNNEL_INPUT_OVERFLOW"
        assert tunnel.cancel.is_set()
        assert tunnel.inbound.empty() and tunnel.queued_bytes == 0
        tunnel.feed({"data": "invalid base64"})
        assert errors == ["TUNNEL_INPUT_OVERFLOW"]
    finally:
        tunnel.close()
        tunnel.thread.join(3)


def test_tunnel_preserves_action_and_receipt_order_with_unbuffered_local_sockets():
    import socket
    import struct
    from mtg_play.relay_client import LoopbackTunnel

    def exact(peer, count):
        result = bytearray()
        while len(result) < count:
            data = peer.recv(count - len(result))
            assert data, "Tunnel closed in a frame"
            result.extend(data)
        return bytes(result)

    def read(peer):
        return exact(peer, struct.unpack(">I", exact(peer, 4))[0])

    def frame(data):
        return struct.pack(">I", len(data)) + data

    errors = []
    tunnels = {}

    def route(side, payload):
        if payload.get("type") == "frame":
            tunnels[side].feed(payload)

    with socket.socket() as native_listener:
        native_listener.bind(("127.0.0.1", 0))
        native_listener.listen(1)
        native_listener.settimeout(3)
        tunnels["guest"] = LoopbackTunnel(
            lambda value: route("host", value), errors.append
        )
        tunnels["host"] = LoopbackTunnel(
            lambda value: route("guest", value),
            errors.append,
            target_port=native_listener.getsockname()[1],
        )
        try:
            with (
                native_listener.accept()[0] as native,
                socket.create_connection(
                    ("127.0.0.1", tunnels["guest"].port),
                    timeout=3,
                ) as unity,
            ):
                native.settimeout(3)
                unity.sendall(frame(b"action-one") + frame(b"action-two"))
                assert [read(native), read(native)] == [b"action-one", b"action-two"]
                for message in (b"submitted", b"confirmed", b"snapshot"):
                    native.sendall(frame(message))
                assert [read(unity) for _ in range(3)] == [
                    b"submitted",
                    b"confirmed",
                    b"snapshot",
                ]
                for tunnel in tunnels.values():
                    assert (
                        tunnel.socket.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY)
                        == 1
                    )
                assert errors == []
                for tunnel in tunnels.values():
                    tunnel.close()
        finally:
            for tunnel in tunnels.values():
                tunnel.close()
                tunnel.thread.join(3)
                assert not tunnel.thread.is_alive()
