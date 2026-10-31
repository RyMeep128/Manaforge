"""One-time offline renderer fixtures from existing Core artwork, never live game data."""

import hashlib
import json
from pathlib import Path
import struct

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage

from .visual_catalog import collect_visual_candidates

MAX_CARDS = 32
MAX_ASSETS = 48
MAX_CANDIDATES = 2048
MAX_ASSET_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024


class VisualFixtureError(ValueError):
    pass


def export_visual_fixture(
    service,
    printings,
    destination,
    *,
    max_edge=896,
    assets_per_card=3,
    max_asset_bytes=MAX_ASSET_BYTES,
):
    """Prepare a NEW local fixture directory; preserve source artwork/preferences.

    printings is an ordered sequence of (public printing ID, face index). This
    API is not for session snapshots or private hands. Decode on an asset worker
    or in this separate preparation process, never Unity's rendering thread.
    """
    printings = tuple(printings)
    if not 1 <= len(printings) <= MAX_CARDS or not 1 <= assets_per_card <= 3:
        raise VisualFixtureError("VISUAL_FIXTURE_LIMIT")
    if type(max_edge) is not int or not 1 <= max_edge <= 1024:
        raise VisualFixtureError("VISUAL_FIXTURE_DIMENSIONS")
    if type(max_asset_bytes) is not int or not 1 <= max_asset_bytes <= MAX_ASSET_BYTES:
        raise VisualFixtureError("VISUAL_FIXTURE_BUDGET")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    assets, cards, total_bytes = {}, [], 0
    for printing, face_index in printings:
        candidates = collect_visual_candidates(
            service, printing, face_index, max_cached_candidates=assets_per_card
        )
        if len(candidates) > MAX_CANDIDATES:
            raise VisualFixtureError("VISUAL_FIXTURE_CANDIDATES")
        payload = service.get_card(card_id=printing)
        face = (payload.get("card_faces") or [payload])[face_index]
        # Bound the export budget, not the printing-resolution policy. Always keep
        # the selected authentic image first when available; Unity resolves from
        # the exported candidate metadata using its existing VisualPrintingPolicy.
        cached = sorted(
            (c for c in candidates if c.cached),
            key=lambda c: (
                c.printing_id != printing,
                not c.standard_compatible,
                c.printing_id,
            ),
        )[:assets_per_card]
        exported = {}
        for candidate in cached:
            image = QImage(candidate.local_path)
            if image.isNull():
                continue  # Cache may have changed since the collector verified it.
            if max(image.width(), image.height()) > max_edge:
                image = image.scaled(
                    max_edge,
                    max_edge,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            # Unity raw RGBA starts at bottom-left. Decode/flip here, not in Unity.
            image = image.convertToFormat(QImage.Format.Format_RGBA8888).mirrored(
                False, True
            )
            width, height = image.width(), image.height()
            raw = image.constBits().asstring(width * height * 4)
            asset_id = hashlib.sha256(
                struct.pack(">II", width, height) + raw
            ).hexdigest()
            if asset_id not in assets:
                if len(assets) >= MAX_ASSETS:
                    raise VisualFixtureError("VISUAL_FIXTURE_ASSET_LIMIT")
                if total_bytes + len(raw) > max_asset_bytes:
                    raise VisualFixtureError("VISUAL_FIXTURE_BUDGET")
                filename = asset_id + ".rgba"
                (destination / filename).write_bytes(raw)
                assets[asset_id] = dict(
                    asset_id=asset_id,
                    file=filename,
                    width=width,
                    height=height,
                    byte_length=len(raw),
                    sha256=hashlib.sha256(raw).hexdigest(),
                    pixel_format="RGBA8",
                    row_origin="bottom_left",
                )
                total_bytes += len(raw)
            exported[candidate.printing_id] = asset_id
        cards.append(
            dict(
                oracle_id=candidates[0].oracle_id,
                selected_printing_id=printing,
                selected_face=candidates[0].face_key,
                values_source="printed_reference_mock",
                layout=payload.get("layout") or "unknown",
                room_doors=[
                    {key: door.get(key) for key in ("name", "mana_cost", "oracle_text")}
                    for door in (payload.get("card_faces") or [])[:2]
                ]
                if "Room" in (face.get("type_line") or "").split()
                else [],
                mock_values={
                    name: face.get(name)
                    for name in (
                        "name",
                        "mana_cost",
                        "type_line",
                        "oracle_text",
                        "power",
                        "toughness",
                        "loyalty",
                        "defense",
                    )
                },
                candidates=[
                    dict(
                        oracle_id=c.oracle_id,
                        printing_id=c.printing_id,
                        face_key=c.face_key,
                        face_index=c.face_index,
                        standard_compatible=c.standard_compatible,
                        cached=c.printing_id in exported,
                        asset_id=exported.get(c.printing_id),
                    )
                    for c in candidates
                ],
            )
        )
    if not assets:
        raise VisualFixtureError("VISUAL_FIXTURE_NO_ARTWORK")
    manifest = dict(
        fixture_version=3,
        fixture_only=True,
        description="Offline public-card renderer fixture; no engine or authoritative current characteristics",
        assets=list(assets.values()),
        cards=cards,
    )
    encoded = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise VisualFixtureError("VISUAL_FIXTURE_MANIFEST_LIMIT")
    # Publication is last. Partial bundles have no manifest and must not be loaded.
    temporary = destination / "manifest.json.tmp"
    temporary.write_bytes(encoded)
    temporary.replace(destination / "manifest.json")
    return manifest
