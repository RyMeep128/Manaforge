from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import Any


CARD_TYPE_PRIORITY = [
    "Creature",
    "Planeswalker",
    "Battle",
    "Artifact",
    "Enchantment",
    "Instant",
    "Sorcery",
    "Land",
]


@dataclass(frozen=True)
class CatalogCardCandidate:
    name: str
    catalog_card_id: str | None = None
    oracle_id: str | None = None
    set_code: str | None = None
    set_name: str | None = None
    collector_number: str | None = None
    image_uri: str | None = None
    preview_uri: str | None = None
    thumbnail_uri: str | None = None
    local_image_path: str | None = None
    image_asset_id: str | None = None
    type_line: str | None = None
    mana_cost: str | None = None
    mana_value: float | None = None
    colors: list[str] = field(default_factory=list)
    color_identity: list[str] = field(default_factory=list)
    card_types: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "local"


def search_catalog_cards(
    query: str,
    set_filter: str | None = None,
    *,
    card_service: Any | None = None,
    allow_remote: bool = False,
    limit: int = 60,
) -> list[CatalogCardCandidate]:
    service = card_service or _get_default_card_service()
    clean_query = str(query or "").strip()
    if not clean_query:
        return []

    results = service.search_cards(
        clean_query,
        {
            "set_filter": _clean_optional(set_filter) or "",
            "allow_remote": bool(allow_remote),
            "limit": max(1, int(limit)),
        },
    )
    source = "remote_allowed" if allow_remote else "local"
    return [_candidate_from_search_result(result, service, source=source) for result in results]


def resolve_deck_entry(
    entry: Any,
    *,
    card_service: Any | None = None,
    allow_remote: bool = False,
) -> CatalogCardCandidate | None:
    service = card_service or _get_default_card_service()
    set_code = _clean_optional(getattr(entry, "set_code", None))
    collector_number = _clean_optional(getattr(entry, "collector_number", None))
    name = str(getattr(entry, "name", "") or "").strip()

    if set_code and collector_number:
        payload = service.get_print(set_code=set_code, collector_number=collector_number)
        if payload is not None:
            return _candidate_from_payload(payload, service, source="local_exact_print")

    if name:
        payload = service.get_card(exact_name=name)
        if payload is not None and _payload_matches_set(payload, set_code):
            return _candidate_from_payload(payload, service, source="local_exact_name")

        local_results = search_catalog_cards(
            name,
            set_filter=set_code,
            card_service=service,
            allow_remote=False,
            limit=20,
        )
        if local_results:
            return local_results[0]

        if allow_remote:
            remote_results = search_catalog_cards(
                name,
                set_filter=set_code,
                card_service=service,
                allow_remote=True,
                limit=20,
            )
            if remote_results:
                return remote_results[0]

    return None


def _candidate_from_search_result(
    result: Any,
    service: Any,
    *,
    source: str,
) -> CatalogCardCandidate:
    card_id = _clean_optional(getattr(result, "card_id", None))
    local_image_path, image_asset_id = _local_image_refs(service, card_id)
    payload = deepcopy(getattr(result, "payload", {}) or {})
    image_uri, payload_thumbnail_uri, payload_preview_uri = _extract_image_uris(payload)
    metadata = _extract_gameplay_metadata(payload)
    preview_uri = _clean_optional(getattr(result, "preview_url", None)) or payload_preview_uri
    thumbnail_uri = _clean_optional(getattr(result, "thumbnail_url", None)) or payload_thumbnail_uri
    return CatalogCardCandidate(
        catalog_card_id=card_id,
        oracle_id=_clean_optional(getattr(result, "oracle_id", None)),
        name=str(getattr(result, "name", "") or "").strip(),
        set_code=_normalize_set_code(getattr(result, "set_code", None)),
        set_name=_clean_optional(getattr(result, "set_name", None)),
        collector_number=_clean_optional(getattr(result, "collector_number", None)),
        image_uri=image_uri,
        preview_uri=preview_uri,
        thumbnail_uri=thumbnail_uri,
        local_image_path=local_image_path,
        image_asset_id=image_asset_id,
        **metadata,
        payload=payload,
        source=source,
    )


def _candidate_from_payload(
    payload: dict[str, Any],
    service: Any,
    *,
    source: str,
) -> CatalogCardCandidate:
    payload_copy = deepcopy(payload)
    card_id = _clean_optional(payload_copy.get("id"))
    local_image_path, image_asset_id = _local_image_refs(service, card_id)
    image_uri, thumbnail_uri, preview_uri = _extract_image_uris(payload_copy)
    metadata = _extract_gameplay_metadata(payload_copy)
    return CatalogCardCandidate(
        catalog_card_id=card_id,
        oracle_id=_clean_optional(payload_copy.get("oracle_id")),
        name=str(payload_copy.get("name") or "").strip(),
        set_code=_normalize_set_code(payload_copy.get("set")),
        set_name=_clean_optional(payload_copy.get("set_name")),
        collector_number=_clean_optional(payload_copy.get("collector_number")),
        image_uri=image_uri,
        preview_uri=preview_uri,
        thumbnail_uri=thumbnail_uri,
        local_image_path=local_image_path,
        image_asset_id=image_asset_id,
        **metadata,
        payload=payload_copy,
        source=source,
    )


def _extract_image_uris(payload: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    image_uris = payload.get("image_uris")
    if isinstance(image_uris, dict):
        image_uri = _clean_optional(
            image_uris.get("png") or image_uris.get("large") or image_uris.get("normal")
        )
        thumbnail_uri = _clean_optional(
            image_uris.get("small") or image_uris.get("normal") or image_uris.get("large")
        )
        preview_uri = _clean_optional(
            image_uris.get("normal") or image_uris.get("large") or image_uris.get("png")
        )
        return image_uri, thumbnail_uri, preview_uri

    for face in payload.get("card_faces") or []:
        if not isinstance(face, dict):
            continue
        image_uris = face.get("image_uris")
        if isinstance(image_uris, dict):
            image_uri = _clean_optional(
                image_uris.get("png") or image_uris.get("large") or image_uris.get("normal")
            )
            thumbnail_uri = _clean_optional(
                image_uris.get("small") or image_uris.get("normal") or image_uris.get("large")
            )
            preview_uri = _clean_optional(
                image_uris.get("normal") or image_uris.get("large") or image_uris.get("png")
            )
            return image_uri, thumbnail_uri, preview_uri

    return None, None, None


def _local_image_refs(service: Any, card_id: str | None) -> tuple[str | None, str | None]:
    if not card_id:
        return None, None

    database = getattr(service, "database", None)
    get_image_record = getattr(database, "get_image_record", None)
    if get_image_record is None:
        return None, None

    record = get_image_record(card_id, "default")
    if record is None:
        return None, None
    return _clean_optional(getattr(record, "path", None)), _clean_optional(getattr(record, "asset_id", None))


def _extract_gameplay_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    colors = _color_list(payload.get("colors"))
    if not colors:
        colors = _colors_from_faces(payload, "colors")
    color_identity = _color_list(payload.get("color_identity"))
    if not color_identity:
        color_identity = _colors_from_faces(payload, "color_identity")
    type_line = _clean_optional(payload.get("type_line"))
    mana_cost = _clean_optional(payload.get("mana_cost"))
    if not mana_cost:
        mana_cost = _mana_cost_from_faces(payload)
    return {
        "type_line": type_line,
        "mana_cost": mana_cost,
        "mana_value": _optional_float(payload.get("cmc", payload.get("mana_value"))),
        "colors": colors,
        "color_identity": color_identity,
        "card_types": _card_types_from_type_line(type_line),
    }


def _colors_from_faces(payload: dict[str, Any], field_name: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for face in payload.get("card_faces") or []:
        if not isinstance(face, dict):
            continue
        for color in _color_list(face.get(field_name)):
            if color not in seen:
                result.append(color)
                seen.add(color)
    return result


def _mana_cost_from_faces(payload: dict[str, Any]) -> str | None:
    costs = [
        cost
        for face in payload.get("card_faces") or []
        if isinstance(face, dict)
        for cost in [_clean_optional(face.get("mana_cost"))]
        if cost
    ]
    return " // ".join(costs) if costs else None


def _card_types_from_type_line(type_line: str | None) -> list[str]:
    if not type_line:
        return []
    primary_line = type_line.split("—", 1)[0].split("-", 1)[0]
    found: list[str] = []
    words = {word.casefold() for word in primary_line.split()}
    for card_type in CARD_TYPE_PRIORITY:
        if card_type.casefold() in words:
            found.append(card_type)
    return found or ["Other"]


def _color_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        color = str(item or "").strip().upper()
        if color in {"W", "U", "B", "R", "G"} and color not in seen:
            result.append(color)
            seen.add(color)
    return result


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _payload_matches_set(payload: dict[str, Any], set_code: str | None) -> bool:
    if not set_code:
        return True
    return _normalize_set_code(payload.get("set")) == _normalize_set_code(set_code)


def _normalize_set_code(value: Any) -> str | None:
    text = _clean_optional(value)
    return None if text is None else text.lower()


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _get_default_card_service() -> Any:
    core_root = Path(__file__).resolve().parents[1] / "mtg_core"
    if core_root.exists() and str(core_root) not in sys.path:
        sys.path.insert(0, str(core_root))

    from mtg_core import get_default_card_service

    return get_default_card_service()
