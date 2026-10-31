"""Ephemeral, viewer-scoped launch assets from Core's existing offline cache."""

import hashlib
import json
from pathlib import Path

from .artwork_pixels import cached_rgba
from .visual_catalog import collect_visual_candidates


class ArtworkBundleError(ValueError):
    pass


def export_artwork_bundle(
    service,
    printing_ids,
    destination,
    *,
    session_id,
    viewer_id,
    max_edge=896,
    max_asset_bytes=256 * 1024 * 1024,
):
    """Caller supplies only viewer-permitted IDs and owns temporary-folder cleanup.

    No decks are read or persisted. No downloads, fallback printings or per-action
    calls are introduced. Publish a new directory; originals/preferences stay intact.
    """
    ids = tuple(printing_ids)
    if (
        not 1 <= len(ids) <= 256
        or any(
            not isinstance(item, str) or not item or len(item) > 1024 for item in ids
        )
        or len(set(ids)) != len(ids)
        or any(
            not isinstance(item, str) or not item.strip() or len(item) > 1024
            for item in (session_id, viewer_id)
        )
    ):
        raise ArtworkBundleError("CORE_ARTWORK_CONTEXT")
    if (
        type(max_edge) is not int
        or not 1 <= max_edge <= 1024
        or type(max_asset_bytes) is not int
        or not 1 <= max_asset_bytes <= 256 * 1024 * 1024
    ):
        raise ArtworkBundleError("CORE_ARTWORK_LIMITS")
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=False)
    entries, unavailable, written, total = [], [], set(), 0
    for printing in ids:
        payload = service.get_card(card_id=printing) or {}
        if payload.get("id") != printing or not payload.get("oracle_id"):
            unavailable.append(
                dict(printing_id=printing, code="ARTWORK_METADATA_UNAVAILABLE")
            )
            continue
        try:
            candidates = collect_visual_candidates(
                service, printing, 0, max_cached_candidates=1
            )
        except ValueError:
            unavailable.append(
                dict(printing_id=printing, code="ARTWORK_METADATA_UNAVAILABLE")
            )
            continue
        selected = candidates[0] if candidates else None
        if (
            not selected
            or selected.printing_id != printing
            or selected.oracle_id != payload["oracle_id"]
            or not selected.standard_compatible
            or payload.get("layout") != "normal"
            or payload.get("card_faces")
            or not payload.get("type_line")
        ):
            unavailable.append(
                dict(printing_id=printing, code="ARTWORK_FACE_UNSUPPORTED")
            )
            continue
        pixels = cached_rgba(selected.local_path, max_edge) if selected.cached else None
        if pixels is None:
            unavailable.append(dict(printing_id=printing, code="ARTWORK_MISSING"))
            continue
        width, height, raw = pixels
        digest = hashlib.sha256(raw).hexdigest()
        if digest not in written:
            if total + len(raw) > max_asset_bytes:
                raise ArtworkBundleError("CORE_ARTWORK_BUDGET")
            (root / (digest + ".rgba")).write_bytes(raw)
            written.add(digest)
            total += len(raw)
        entries.append(
            dict(
                oracle_id=selected.oracle_id,
                printing_id=printing,
                face_key=selected.face_key,
                layout="normal",
                face_count=1,
                standard_compatible=True,
                printed_type_line=payload["type_line"],
                file=digest + ".rgba",
                width=width,
                height=height,
                byte_length=len(raw),
                sha256=digest,
                pixel_format="RGBA8",
                row_origin="bottom_left",
            )
        )
    manifest = dict(
        artwork_bundle_version=1,
        source="manaforge_core_cache",
        session_id=session_id,
        viewer_id=viewer_id,
        entries=entries,
        unavailable=unavailable,
    )
    encoded = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    if len(encoded) > 1024 * 1024:
        raise ArtworkBundleError("CORE_ARTWORK_MANIFEST_LIMIT")
    temporary = root / "manifest.json.tmp"
    temporary.write_bytes(encoded)
    temporary.replace(root / "manifest.json")
    return manifest, hashlib.sha256(encoded).hexdigest()
