"""Offline, launch-time visual metadata; never a per-action gameplay adapter.

Call on an asset worker with an explicitly viewer-permitted printing. Results are
internal host metadata, not a wire contract; paths must not be sent to Unity.
"""

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtGui import QImage


@dataclass(frozen=True)
class VisualAssetCandidate:
    oracle_id: str
    printing_id: str
    face_key: str
    face_index: int
    standard_compatible: bool
    cached: bool
    local_path: str | None


def _face(payload, index):
    faces = payload.get("card_faces")
    if faces:
        if not isinstance(faces, list) or not 0 <= index < len(faces):
            return None
        face = faces[index]
        return face if isinstance(face, dict) else None
    return payload if index == 0 else None


def _standard(payload):
    # Conservative initial profile: unknown or specialized metadata stays authentic.
    return (
        payload.get("layout") == "normal"
        and not any(
            kind in (payload.get("type_line") or "").split("\u2014", 1)[0].split()
            for kind in (
                "Planeswalker",
                "Battle",
                "Plane",
                "Phenomenon",
                "Scheme",
                "Vanguard",
                "Dungeon",
                "Emblem",
            )
        )
        and payload.get("frame") == "2015"
        and payload.get("border_color") in ("black", "white")
        and payload.get("full_art") is False
        and payload.get("textless") is False
        and payload.get("promo") is False
        and payload.get("frame_effects", []) == []
        and not payload.get("card_faces")
    )


def collect_visual_candidates(
    service, printing_id, face_index=0, *, concealed=False, max_cached_candidates=None
):
    """Return immutable selected-first metadata, decoding only exact local assets.

    No downloads, preference writes, fallback-to-front calls, or persisted cache.
    Optional preparation budgets inspect selected artwork first, then standard
    candidates. Unexamined paths remain cached=False (unverified), not missing.
    The default still verifies every candidate.
    Face names match conservatively within one Oracle identity; an unmatched or
    malformed face cannot be substituted. Re-run after cache changes. A caller
    must discard these results on viewer handoff; this is not authorization.
    """
    if concealed:
        return ()
    if max_cached_candidates is not None and (
        type(max_cached_candidates) is not int or not 1 <= max_cached_candidates <= 16
    ):
        raise ValueError("VISUAL_CANDIDATE_BUDGET")
    if not isinstance(printing_id, str) or not printing_id:
        raise ValueError("VISUAL_PRINTING_REQUIRED")
    if type(face_index) is not int or face_index < 0:
        raise ValueError("VISUAL_FACE_INVALID")
    selected = service.get_card(card_id=printing_id) or {}
    oracle = selected.get("oracle_id")
    face = _face(selected, face_index)
    name = face.get("name") if face else None
    if selected.get("id") != printing_id or not oracle or not name:
        raise ValueError("VISUAL_IDENTITY_UNAVAILABLE")
    selected_faces = selected.get("card_faces")
    if (
        isinstance(selected_faces, list)
        and sum(
            isinstance(item, dict) and item.get("name") == name
            for item in selected_faces
        )
        != 1
    ):
        raise ValueError("VISUAL_FACE_AMBIGUOUS")
    # Exact face name rather than ordinal prevents front/back substitution when
    # another printing uses a different layout or order. No gameplay text parsing.
    result = []
    payloads = [selected] + sorted(
        service.get_prints(oracle, allow_remote=False),
        key=lambda item: (
            (not _standard(item), str(item.get("id", "")))
            if max_cached_candidates is not None
            else str(item.get("id", ""))
        ),
    )
    seen = set()
    verified_cached = 0
    for payload in payloads:
        identity = payload.get("id")
        if not identity or identity in seen or payload.get("oracle_id") != oracle:
            continue
        seen.add(identity)
        faces = payload.get("card_faces")
        indices = range(len(faces)) if isinstance(faces, list) and faces else range(1)
        matches = [i for i in indices if (_face(payload, i) or {}).get("name") == name]
        if len(matches) != 1:
            continue
        index = matches[0]
        # Flip cards share a rotated image. Leave that treatment unsupported here
        # rather than mark the unrotated front usable as the back.
        path = None
        if (
            max_cached_candidates is None or verified_cached < max_cached_candidates
        ) and not (payload.get("layout") == "flip" and index != 0):
            variant = "default" if index == 0 else f"face-{index}"
            path = service.get_image_path(identity, variant=variant)
        usable = bool(path and Path(path).is_file() and not QImage(str(path)).isNull())
        if usable:
            verified_cached += 1
        result.append(
            VisualAssetCandidate(
                oracle,
                identity,
                name,
                index,
                _standard(payload),
                usable,
                str(path) if usable else None,
            )
        )
    return tuple(result)
