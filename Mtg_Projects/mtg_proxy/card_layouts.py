"""Physical print rules for Scryfall card layouts."""
from __future__ import annotations

from dataclasses import dataclass


PAIRED_BACK_LAYOUTS = frozenset({
    "transform", "modal_dfc", "double_faced_token", "reversible_card",
    "art_series",
})
SINGLE_IMAGE_LAYOUTS = frozenset({
    "normal", "meld", "split", "aftermath", "adventure", "flip",
    "planar", "scheme", "token", "emblem", "leveler", "saga",
    "class", "case", "prototype", "mutate", "host", "augment",
})


@dataclass(frozen=True)
class CardLayoutPolicy:
    layout: str
    image_mode: str
    paired_back: bool
    footprint: str = "single-slot"
    oversized_compatible: bool = True
    recognized: bool = True


def policy_for_layout(layout: str | None) -> CardLayoutPolicy:
    normalized = str(layout or "custom").strip().casefold() or "custom"
    if normalized in PAIRED_BACK_LAYOUTS:
        return CardLayoutPolicy(normalized, "separate-faces", True)
    if normalized in SINGLE_IMAGE_LAYOUTS:
        return CardLayoutPolicy(normalized, "single-image", False)
    return CardLayoutPolicy(
        normalized, "single-image", False, recognized=False)


def has_printed_back(card_data: dict) -> bool:
    faces = card_data.get("card_faces") or []
    face_image_count = sum(bool((face.get("image_uris") or {})) for face in faces)
    if face_image_count < 2:
        return False
    layout = str(card_data.get("layout") or "").strip().casefold()
    # Older cached records may predate layout storage. Independently imaged
    # faces preserve their established front/back pairing behavior.
    return not layout or policy_for_layout(layout).paired_back
