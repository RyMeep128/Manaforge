import json
import socket
import struct

from PyQt6.QtGui import QImage

from mtg_play.public_artwork import PublicArtworkServer


class Service:
    def __init__(self, path):
        self.path = str(path)
        self.card = dict(
            id="public-print",
            oracle_id="public-oracle",
            name="Goblin",
            layout="token",
            type_line="Token Creature — Goblin",
            power="1",
            toughness="1",
            colors=["R"],
            oracle_text="",
        )

    def get_card(self, *, card_id):
        return self.card if card_id == self.card["id"] else None

    def get_image_path(self, printing):
        return self.path

    def search_cards(self, query, filters):
        assert filters["allow_remote"] is False
        return [type("Row", (), {"payload": self.card})()]


def exchange(server, **fields):
    query = dict(
        session_id=server.session, viewer_id=server.viewer, key=server.key, **fields
    )
    with socket.create_connection(
        server.server.server_address, timeout=2
    ) as connection:
        payload = json.dumps(query).encode()
        connection.sendall(struct.pack(">I", len(payload)) + payload)
        with connection.makefile("rb") as stream:
            size = struct.unpack(">I", stream.read(4))[0]
            header = json.loads(stream.read(size))
            pixels = stream.read(header.get("byte_length", 0))
            return header, pixels


def test_public_token_artwork_is_lazy_pinned_and_session_scoped(tmp_path):
    path = tmp_path / "token.png"
    image = QImage(2, 2, QImage.Format.Format_RGBA8888)
    image.fill(0xFFFF0000)
    assert image.save(str(path))
    server = PublicArtworkServer(tmp_path, "session", "viewer", Service(path))
    try:
        manifest = json.loads((tmp_path / "artwork/manifest.json").read_bytes())
        assert manifest["entries"] == [] and manifest["unavailable"] == []
        assert len(server.pixels) == 0  # No opponent deck inventory or eager pixels.
        header, _ = exchange(
            server,
            action="resolve_token",
            name="Goblin",
            type="Creature  - Goblin",
            power="1",
            toughness="1",
            color="R",
        )
        assert header == dict(oracle_id="public-oracle", printing_id="public-print")
        wrong, _ = exchange(
            server,
            action="resolve_token",
            name="Goblin",
            type="Creature - Goblin",
            power="2",
            toughness="2",
            color="R",
        )
        assert wrong == dict(unavailable=True)
        header, pixels = exchange(
            server,
            action="artwork",
            oracle_id="public-oracle",
            printing_id="public-print",
        )
        assert (
            header["layout"] == "token" and header["byte_length"] == len(pixels) == 16
        )
        wrong, _ = exchange(
            server,
            action="artwork",
            oracle_id="different-oracle",
            printing_id="public-print",
        )
        assert wrong == dict(unavailable=True)
        query = json.dumps(
            dict(
                session_id="foreign",
                viewer_id=server.viewer,
                key=server.key,
                action="artwork",
            )
        ).encode()
        with socket.create_connection(
            server.server.server_address, timeout=2
        ) as connection:
            connection.sendall(struct.pack(">I", len(query)) + query)
            assert connection.recv(4) == b""
    finally:
        server.close()
    assert not server.thread.is_alive() and not server.pixels
