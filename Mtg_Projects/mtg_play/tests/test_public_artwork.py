import json
import socket
import struct

import pytest

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

    def get_print(self, *, set_code, collector_number):
        return self.card if (set_code, collector_number) == ("tst", "1") else None

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


def test_revealed_printing_resolution_requires_matching_public_name(tmp_path):
    server = PublicArtworkServer(
        tmp_path, "session", "viewer", Service(tmp_path / "unused.png")
    )
    try:
        header, pixels = exchange(
            server, action="resolve_printing", name="Goblin", set="TST", number="1"
        )
        assert header == dict(oracle_id="public-oracle", printing_id="public-print")
        assert pixels == b""
        wrong, _ = exchange(
            server, action="resolve_printing", name="Forest", set="TST", number="1"
        )
        assert wrong == dict(unavailable=True)
    finally:
        server.close()


def test_prototype_cached_image_keeps_its_layout_and_mana_cost(tmp_path):
    path = tmp_path / "prototype.png"
    image = QImage(2, 2, QImage.Format.Format_RGBA8888)
    image.fill(0xFF224466)
    assert image.save(str(path))
    service = Service(path)
    service.card.update(
        layout="prototype",
        name="Frogmyr Enforcer",
        type_line="Artifact Creature — Frog Myr",
        mana_cost="{7}",
    )
    server = PublicArtworkServer(tmp_path, "session", "viewer", service)
    try:
        header, pixels = exchange(
            server,
            action="artwork",
            oracle_id="public-oracle",
            printing_id="public-print",
        )
        assert header["layout"] == "prototype"
        assert header["printed_mana_cost"] == "{7}"
        assert header["standard_compatible"] is False
        assert len(pixels) == 16
    finally:
        server.close()


class FaceService(Service):
    def __init__(self, front, back=None):
        super().__init__(front)
        self.back = str(back) if back else None
        self.variants = []
        self.face_downloads = []
        self.card.update(
            name="Front // Back",
            layout="transform",
            card_faces=[
                dict(
                    name="Front",
                    type_line="Creature",
                    mana_cost="{2}{G}",
                    oracle_text="Front rules",
                    image_uris={"normal": "front"},
                ),
                dict(
                    name="Back",
                    type_line="Creature",
                    mana_cost="",
                    oracle_text="Back rules",
                    image_uris={"normal": "back"},
                ),
            ],
        )

    def get_image_path(self, printing, variant="default"):
        self.variants.append(variant)
        return self.path if variant == "default" else self.back

    def ensure_face_image(self, printing, index, *, allow_remote):
        self.face_downloads.append(index)
        return self.back


def face_images(tmp_path):
    paths = [tmp_path / "front.png", tmp_path / "back.png"]
    for path, color in zip(paths, [0xFFFF0000, 0xFF0000FF]):
        image = QImage(2, 2, QImage.Format.Format_RGBA8888)
        image.fill(color)
        assert image.save(str(path))
    return paths


@pytest.mark.parametrize(
    "layout",
    [
        "saga",
        "class",
        "leveler",
        "mutate",
        "case",
        "meld",
        "planar",
        "scheme",
        "vanguard",
        "emblem",
        "future_layout",
    ],
)
def test_single_image_special_layouts_are_not_rejected(tmp_path, layout):
    front, _ = face_images(tmp_path)
    service = Service(front)
    service.card.update(layout=layout, mana_cost="{3}")
    server = PublicArtworkServer(tmp_path, "session", "viewer", service)
    try:
        header, pixels = exchange(
            server,
            action="artwork",
            oracle_id="public-oracle",
            printing_id="public-print",
            face_name="Goblin",
        )
        assert header["layout"] == layout and header["printed_mana_cost"] == "{3}"
        assert len(pixels) == 16
    finally:
        server.close()


@pytest.mark.parametrize(
    "layout", ["transform", "modal_dfc", "double_faced_token", "reversible_card"]
)
def test_face_switches_use_independent_pixels_and_cache_keys(tmp_path, layout):
    front, back = face_images(tmp_path)
    service = FaceService(front, back)
    service.card["layout"] = layout
    server = PublicArtworkServer(tmp_path, "session", "viewer", service)
    try:
        query = dict(
            action="artwork", oracle_id="public-oracle", printing_id="public-print"
        )
        front_header, front_pixels = exchange(
            server, **query, face_name="Front", transformed=False
        )
        back_header, back_pixels = exchange(
            server, **query, face_name="Back", transformed=True
        )
        assert (
            front_header["printed_name"] == "Front"
            and back_header["printed_name"] == "Back"
        )
        assert (
            front_pixels != back_pixels
            and front_header["face_key"] != back_header["face_key"]
        )
        again, pixels = exchange(server, **query, face_name="Front", transformed=False)
        assert (
            again == front_header and pixels == front_pixels and len(server.pixels) == 2
        )
    finally:
        server.close()


def test_missing_back_never_returns_front_pixels(tmp_path):
    front, _ = face_images(tmp_path)
    service = FaceService(front)
    server = PublicArtworkServer(tmp_path, "session", "viewer", service)
    try:
        header, pixels = exchange(
            server,
            action="artwork",
            oracle_id="public-oracle",
            printing_id="public-print",
            face_name="Back",
            transformed=True,
        )
        assert header == dict(unavailable=True) and pixels == b""
        assert service.variants == ["face-1"] and service.face_downloads == [1]
    finally:
        server.close()


@pytest.mark.parametrize("layout", ["adventure", "split", "aftermath"])
def test_shared_image_cards_select_metadata_without_requesting_a_back_image(
    tmp_path, layout
):
    front, _ = face_images(tmp_path)
    service = FaceService(front)
    service.card.update(layout=layout, image_uris={"normal": "combined"})
    server = PublicArtworkServer(tmp_path, "session", "viewer", service)
    try:
        header, pixels = exchange(
            server,
            action="artwork",
            oracle_id="public-oracle",
            printing_id="public-print",
            face_name="Back",
        )
        assert (
            header["printed_name"] == "Back"
            and header["printed_rules"] == "Back rules"
            and len(pixels) == 16
        )
        assert service.variants == ["default"] and not service.face_downloads
    finally:
        server.close()


def test_meld_result_requires_an_exact_catalog_relationship(tmp_path):
    front, back = face_images(tmp_path)

    class MeldService(Service):
        def get_card(self, *, card_id):
            if card_id == "meld-result":
                return dict(
                    id="meld-result",
                    oracle_id="meld-oracle",
                    name="Joined form",
                    layout="meld",
                    type_line="Creature",
                    oracle_text="Meld rules",
                )
            return super().get_card(card_id=card_id)

        def get_image_path(self, printing):
            return str(back) if printing == "meld-result" else self.path

    service = MeldService(front)
    service.card.update(
        layout="meld",
        all_parts=[dict(id="meld-result", name="Joined form", component="meld_result")],
    )
    server = PublicArtworkServer(tmp_path, "session", "viewer", service)
    try:
        header, pixels = exchange(
            server,
            action="artwork",
            oracle_id="public-oracle",
            printing_id="public-print",
            face_name="Joined form",
        )
        assert (
            header["printed_name"] == "Joined form"
            and "meld-result" in header["face_key"]
            and len(pixels) == 16
        )
        resolved, _ = exchange(
            server, action="resolve_printing", set="TST", number="1", name="Joined form"
        )
        assert resolved == dict(oracle_id="meld-oracle", printing_id="meld-result")
        missing, pixels = exchange(
            server,
            action="artwork",
            oracle_id="public-oracle",
            printing_id="public-print",
            face_name="Unrelated form",
        )
        assert missing == dict(unavailable=True) and pixels == b""
    finally:
        server.close()


def test_flip_back_rotates_the_shared_image_without_modifying_its_cache(tmp_path):
    path = tmp_path / "flip.png"
    image = QImage(2, 2, QImage.Format.Format_RGBA8888)
    image.fill(0xFFFF0000)
    image.setPixel(0, 0, 0xFF0000FF)
    assert image.save(str(path))
    original = path.read_bytes()
    service = FaceService(path)
    service.card.update(layout="flip", image_uris={"normal": "combined"})
    server = PublicArtworkServer(tmp_path, "session", "viewer", service)
    try:
        query = dict(
            action="artwork", oracle_id="public-oracle", printing_id="public-print"
        )
        _, front = exchange(server, **query, face_name="Front")
        header, back = exchange(server, **query, face_name="Back")
        assert header["printed_name"] == "Back"
        assert back == b"".join(
            reversed([front[i : i + 4] for i in range(0, len(front), 4)])
        )
        assert path.read_bytes() == original and not service.face_downloads
    finally:
        server.close()


def test_incomplete_dfc_metadata_cannot_guess_a_back_image(tmp_path):
    front, _ = face_images(tmp_path)
    service = FaceService(front)
    service.card["card_faces"] = []
    server = PublicArtworkServer(tmp_path, "session", "viewer", service)
    try:
        header, pixels = exchange(
            server,
            action="artwork",
            oracle_id="public-oracle",
            printing_id="public-print",
            face_name="Back",
            transformed=True,
        )
        assert header == dict(unavailable=True) and pixels == b""
        assert not service.variants
    finally:
        server.close()
