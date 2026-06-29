from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from mtg_editor.catalog import CatalogCardCandidate
from mtg_editor.models import DeckCard, DeckProject


@dataclass(frozen=True)
class CardAddResult:
    card_id: str
    created: bool


def add_or_increment_card(
    project: DeckProject,
    *,
    name: str,
    quantity: int = 1,
    section: str = "main",
    import_section: str | None = None,
    set_code: str | None = None,
    collector_number: str | None = None,
    candidate: CatalogCardCandidate | None = None,
) -> CardAddResult:
    clean_name = _normalize_card_name(candidate.name if candidate is not None and candidate.name else name)
    if not clean_name:
        raise ValueError("card name is required")

    count = max(0, int(quantity))
    normalized_section = _normalize_section(section)
    effective_set_code = _normalize_set_code(
        candidate.set_code if candidate is not None and candidate.set_code else set_code
    )
    effective_collector_number = _clean_optional(
        candidate.collector_number
        if candidate is not None and candidate.collector_number
        else collector_number
    )

    existing = find_matching_card(
        project,
        name=clean_name,
        set_code=effective_set_code,
        collector_number=effective_collector_number,
        section=normalized_section,
    )
    if existing is not None:
        project.set_quantity(existing.card_id, existing.quantity + count)
        if candidate is not None:
            apply_candidate(existing, candidate)
        elif not existing.catalog_status:
            existing.catalog_status = "unresolved"
        return CardAddResult(card_id=existing.card_id, created=False)

    metadata = metadata_for_card(
        section=normalized_section,
        import_section=import_section,
        set_code=effective_set_code,
        collector_number=effective_collector_number,
        candidate=candidate,
    )
    card_id = project.add_card(clean_name, quantity=count, **metadata)
    return CardAddResult(card_id=card_id, created=True)


def find_matching_card(
    project: DeckProject,
    *,
    name: str,
    set_code: str | None = None,
    collector_number: str | None = None,
    section: str = "main",
) -> DeckCard | None:
    target_key = _card_key(
        name=name,
        set_code=set_code,
        collector_number=collector_number,
        section=section,
    )
    for card in project.cards:
        if (
            _card_key(
                name=card.name,
                set_code=card.set_code,
                collector_number=card.collector_number,
                section=card.section,
            )
            == target_key
        ):
            return card
    return None


def metadata_for_card(
    *,
    section: str,
    import_section: str | None = None,
    set_code: str | None = None,
    collector_number: str | None = None,
    candidate: CatalogCardCandidate | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "section": _normalize_section(section),
        "import_section": _clean_optional(import_section),
        "set_code": _normalize_set_code(set_code),
        "collector_number": _clean_optional(collector_number),
        "catalog_status": "unresolved",
    }
    if candidate is not None:
        metadata.update(
            {
                "set_code": _normalize_set_code(candidate.set_code) or metadata["set_code"],
                "collector_number": _clean_optional(candidate.collector_number)
                or metadata["collector_number"],
                "image_uri": candidate.image_uri,
                "image_asset_id": candidate.image_asset_id,
                "catalog_card_id": candidate.catalog_card_id,
                "oracle_id": candidate.oracle_id,
                "set_name": candidate.set_name,
                "preview_uri": candidate.preview_uri,
                "thumbnail_uri": candidate.thumbnail_uri,
                "local_image_path": candidate.local_image_path,
                "catalog_status": "resolved",
                "type_line": candidate.type_line,
                "mana_cost": candidate.mana_cost,
                "mana_value": candidate.mana_value,
                "colors": list(candidate.colors),
                "color_identity": list(candidate.color_identity),
                "card_types": list(candidate.card_types),
            }
        )
    return metadata


def apply_candidate(card: DeckCard, candidate: CatalogCardCandidate) -> None:
    card.set_code = card.set_code or _normalize_set_code(candidate.set_code)
    card.collector_number = card.collector_number or _clean_optional(candidate.collector_number)
    card.image_uri = card.image_uri or candidate.image_uri
    card.image_asset_id = card.image_asset_id or candidate.image_asset_id
    card.catalog_card_id = card.catalog_card_id or candidate.catalog_card_id
    card.oracle_id = card.oracle_id or candidate.oracle_id
    card.set_name = card.set_name or candidate.set_name
    card.preview_uri = card.preview_uri or candidate.preview_uri
    card.thumbnail_uri = card.thumbnail_uri or candidate.thumbnail_uri
    card.local_image_path = card.local_image_path or candidate.local_image_path
    card.catalog_status = "resolved"
    card.type_line = card.type_line or candidate.type_line
    card.mana_cost = card.mana_cost or candidate.mana_cost
    if card.mana_value is None:
        card.mana_value = candidate.mana_value
    if not card.colors:
        card.colors = list(candidate.colors)
    if not card.color_identity:
        card.color_identity = list(candidate.color_identity)
    if not card.card_types:
        card.card_types = list(candidate.card_types)


def _card_key(
    *,
    name: str,
    set_code: str | None,
    collector_number: str | None,
    section: str,
) -> tuple[str, str | None, str | None, str]:
    return (
        _normalize_card_name(name).casefold(),
        _normalize_set_code(set_code),
        _clean_optional(collector_number),
        _normalize_section(section),
    )


def _normalize_card_name(name: str) -> str:
    normalized = re.sub(r"\s+", " ", str(name or "").strip())
    return normalized.replace(" / ", " // ")


def _normalize_section(value: str | None) -> str:
    text = re.sub(r"\s+", "_", str(value or "").strip().lower())
    return text or "main"


def _normalize_set_code(value: Any) -> str | None:
    text = _clean_optional(value)
    return None if text is None else text.lower()


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None
