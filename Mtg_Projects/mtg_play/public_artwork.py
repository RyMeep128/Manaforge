"""Session-owned public catalog artwork, fetched lazily without exposing deck lists."""

from collections import OrderedDict
import hashlib
import hmac
import json
import re
from pathlib import Path
import secrets
import socketserver
import struct
import threading

from .artwork_pixels import cached_rgba
from .visual_catalog import _standard


class PublicArtworkServer:
    def __init__(self, root, session, viewer, service=None):
        if service is None:
            from mtg_core.services import CardService

            service = CardService()
        self.service = service
        self.session, self.viewer = session, viewer
        self.key = secrets.token_hex(32)
        self.lock = threading.Lock()
        self.pixels = OrderedDict()
        self.pixel_bytes = 0
        self.tokens = {}
        owner = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.connection.settimeout(30)
                try:
                    prefix = self.rfile.read(4)
                    if len(prefix) != 4:
                        return
                    length = struct.unpack(">I", prefix)[0]
                    if not 1 <= length <= 16384:
                        return
                    request = json.loads(self.rfile.read(length))
                    if not isinstance(request, dict) or not hmac.compare_digest(
                        str(request.get("key", "")), owner.key
                    ):
                        return
                    if (
                        request.get("session_id") != session
                        or request.get("viewer_id") != viewer
                    ):
                        return
                    with owner.lock:
                        header, pixels = owner.respond(request)
                    encoded = json.dumps(header, ensure_ascii=True).encode()
                    self.wfile.write(struct.pack(">I", len(encoded)) + encoded + pixels)
                except (OSError, ValueError, KeyError, TypeError):
                    return

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            block_on_close = False

        self.server = Server(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        directory = Path(root) / "artwork"
        directory.mkdir(exist_ok=False)
        manifest = dict(
            artwork_bundle_version=3,
            source="manaforge_core_cache",
            session_id=session,
            viewer_id=viewer,
            entries=[],
            unavailable=[],
            resolver=dict(
                host="127.0.0.1", port=self.server.server_address[1], key=self.key
            ),
        )
        encoded = (json.dumps(manifest, ensure_ascii=True) + "\n").encode()
        (directory / "manifest.json").write_bytes(encoded)
        self.directory = str(directory.resolve())
        self.pin = hashlib.sha256(encoded).hexdigest()

    def respond(self, request):
        if request.get("action") == "resolve_printing":
            card = self.service.get_print(
                set_code=str(request.get("set", "")).lower(),
                collector_number=str(request.get("number", "")),
            )
            if card:
                requested = request.get("name")
                names = {card.get("name")} | {face.get("name") for face in card.get("card_faces") or [] if isinstance(face, dict)}
                if requested not in names:
                    card = self._meld_result(card, requested) if isinstance(requested, str) and requested else None
                if card and card.get("id") and card.get("oracle_id"):
                    return dict(oracle_id=card["oracle_id"], printing_id=card["id"]), b""
            return dict(unavailable=True), b""
        if request.get("action") == "resolve_token":
            card = self.resolve_token(request)
            return (
                dict(oracle_id=card["oracle_id"], printing_id=card["id"])
                if card
                else dict(unavailable=True)
            ), b""
        if request.get("action") != "artwork":
            return dict(unavailable=True), b""
        printing, oracle = request.get("printing_id"), request.get("oracle_id")
        if (
            not isinstance(printing, str)
            or not isinstance(oracle, str)
            or max(len(printing), len(oracle)) > 1024
        ):
            return dict(unavailable=True), b""
        face_name = request.get("face_name")
        transformed = request.get("transformed")
        if (face_name is not None and (not isinstance(face_name, str) or len(face_name) > 1024)
                or transformed is not None and type(transformed) is not bool):
            return dict(unavailable=True), b""
        card = self.service.get_card(card_id=printing) or {}
        if card.get("id") != printing or card.get("oracle_id") != oracle:
            return dict(unavailable=True), b""
        layout = card.get("layout")
        if not isinstance(layout, str) or not layout or len(layout) > 128:
            return dict(unavailable=True), b""
        # A meld result is an explicit catalog relationship of the admitted
        # printing, never a same-name search or an arbitrary replacement image.
        image_card = self._meld_result(card, face_name) if layout == "meld" and face_name != card.get("name") else card
        if not image_card:
            return dict(unavailable=True), b""
        faces = image_card.get("card_faces") or []
        if not isinstance(faces, list) or len(faces) > 8 or any(not isinstance(face, dict) for face in faces):
            return dict(unavailable=True), b""
        if layout in ("transform", "modal_dfc", "double_faced_token", "reversible_card") and len(faces) != 2:
            return dict(unavailable=True), b""
        matches = [index for index, face in enumerate(faces) if face.get("name") == face_name]
        if len(matches) > 1:
            return dict(unavailable=True), b""
        index = matches[0] if matches else 0
        if transformed is True and layout in ("transform", "modal_dfc", "double_faced_token", "reversible_card"):
            index = 1
        face = faces[index] if faces else image_card
        # Split, Adventure and flip cards use one printed image; true DFCs
        # require an independently cached/downloaded face and never fall back.
        separate = bool(faces) and not bool(image_card.get("image_uris")) and layout != "flip"
        if separate and not face.get("image_uris"):
            return dict(unavailable=True), b""
        if not (face.get("type_line") or image_card.get("type_line")):
            return dict(unavailable=True), b""
        variant = "default" if not separate or index == 0 else f"face-{index}"
        image_printing = image_card["id"]
        cache_key = (printing, image_printing, index, bool(separate))
        if cache_key in self.pixels:
            header, pixels = self.pixels.pop(cache_key)
            self.pixels[cache_key] = (header, pixels)
            return (header, pixels) if header["oracle_id"] == oracle else (dict(unavailable=True), b"")
        path = self.service.get_image_path(image_printing) if variant == "default" else self.service.get_image_path(image_printing, variant=variant)
        if not path:
            if separate and index:
                path = self.service.ensure_face_image(image_printing, index, allow_remote=True)
            else:
                path = self.service.ensure_image(image_printing, allow_remote=True)
        converted = cached_rgba(path, 896, rotation=180 if layout == "flip" and index else 0) if path else None
        if not converted:
            return dict(unavailable=True), b""
        width, height, pixels = converted
        header = dict(
            oracle_id=oracle,
            printing_id=printing,
            face_key=oracle + ":" + ("front" if index == 0 and image_printing == printing else "face-" + str(index) + ":" + image_printing),
            standard_compatible=_standard(card) and image_printing == printing,
            layout=card["layout"],
            printed_type_line=face.get("type_line") or image_card.get("type_line") or "",
            printed_name=face.get("name"),
            printed_rules=face.get("oracle_text"),
            printed_mana_cost=face.get("mana_cost"),
            width=width,
            height=height,
            byte_length=len(pixels),
            sha256=hashlib.sha256(pixels).hexdigest(),
        )
        while self.pixels and (
            self.pixel_bytes + len(pixels) > 64 * 1024 * 1024 or len(self.pixels) >= 256
        ):
            _, (_, evicted) = self.pixels.popitem(last=False)
            self.pixel_bytes -= len(evicted)
        self.pixels[cache_key] = (header, pixels)
        self.pixel_bytes += len(pixels)
        return header, pixels

    def _meld_result(self, card, name):
        if not name or name == card.get("name"):
            return card
        candidates = [part for part in card.get("all_parts") or []
                      if isinstance(part, dict) and part.get("component") == "meld_result" and part.get("name") == name]
        if len(candidates) != 1:
            return None
        result = self.service.get_card(card_id=candidates[0].get("id")) or {}
        if not result and hasattr(self.service, "fetch_missing_card"):
            result = self.service.fetch_missing_card(card_id=candidates[0]["id"]) or {}
        return result if (result.get("id") == candidates[0].get("id") and result.get("name") == name
                          and result.get("layout") == "meld" and result.get("oracle_id")) else None

    def resolve_token(self, request):
        name = str(request.get("name") or "").removesuffix(" Token")
        power, toughness = (
            str(request.get("power") or ""),
            str(request.get("toughness") or ""),
        )
        color = str(request.get("color") or "").upper()
        colors = sorted(
            code
            for word, code in (
                ("WHITE", "W"),
                ("BLUE", "U"),
                ("BLACK", "B"),
                ("RED", "R"),
                ("GREEN", "G"),
            )
            if word in color
        )
        # XMage also supplies the original color identity as compact WUBRG.
        compact = re.sub(r"[{} ,/]", "", color)
        if compact and all(c in "WUBRG" for c in compact):
            colors = sorted(set(compact))
        type_line = str(request.get("type") or "").replace("—", "-")
        subtypes = (
            sorted(type_line.split("-", 1)[-1].split()) if "-" in type_line else []
        )
        signature = (name, power, toughness, tuple(colors), tuple(subtypes))
        if signature in self.tokens:
            return self.tokens[signature]
        if not name or len(name) > 256 or len(self.tokens) >= 256:
            return None
        rows = self.service.search_cards(
            name + " token", {"allow_remote": False, "limit": 2000}
        )
        matches = []
        for row in rows:
            card = row.payload
            printed_type = (card.get("type_line") or "").replace("—", "-")
            printed_subtypes = (
                sorted(printed_type.split("-", 1)[-1].split())
                if "-" in printed_type
                else []
            )
            if (
                card.get("layout") == "token"
                and not card.get("card_faces")
                and card.get("name") == name
                and card.get("power", "") == power
                and card.get("toughness", "") == toughness
                and sorted(card.get("colors") or []) == colors
                and printed_subtypes == subtypes
                and card.get("oracle_id")
            ):
                matches.append(card)
        matches.sort(
            key=lambda c: (
                bool(c.get("oracle_text")),
                not bool(self.service.get_image_path(c["id"])),
                c["id"],
            )
        )
        self.tokens[signature] = matches[0] if matches else None
        return self.tokens[signature]

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        with self.lock:
            self.pixels.clear()
            self.pixel_bytes = 0
            self.tokens.clear()
