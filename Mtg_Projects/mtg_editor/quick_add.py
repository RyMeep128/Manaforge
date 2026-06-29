from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from mtg_editor.card_ops import add_or_increment_card
from mtg_editor.catalog import (
    CatalogCardCandidate,
    resolve_deck_entry,
    search_catalog_cards,
)
from mtg_editor.models import DeckProject


QUICK_ADD_PATTERN = re.compile(
    r"^\s*(?:(?P<count>\d+)\s*x?\s+)?"
    r"(?P<name>.+?)"
    r"(?:\s+\((?P<set_code>[A-Za-z0-9]+)\)(?:\s+(?P<collector_number>\S+))?)?"
    r"\s*$",
    re.IGNORECASE,
)

EXACT_CATALOG_SOURCES = {"local_exact_name", "local_exact_print"}


@dataclass(frozen=True)
class QuickAddQuery:
    name: str
    quantity: int = 1
    set_code: str | None = None
    collector_number: str | None = None
    section: str = "main"


@dataclass(frozen=True)
class QuickAddResult:
    status: str
    card_id: str | None = None
    candidates: list[CatalogCardCandidate] = field(default_factory=list)
    query: QuickAddQuery | None = None
    message: str = ""


def parse_quick_add_input(
    text: str,
    quantity: int | None = None,
    section: str = "main",
) -> QuickAddQuery:
    match = QUICK_ADD_PATTERN.match(str(text or ""))
    if match is None:
        raise ValueError("quick add text is required")

    name = _normalize_card_name(match.group("name"))
    if not name:
        raise ValueError("quick add text is required")

    parsed_quantity = int(match.group("count") or 1)
    if quantity is not None:
        parsed_quantity = int(quantity)
    if parsed_quantity <= 0:
        raise ValueError("quantity must be greater than zero")

    return QuickAddQuery(
        name=name,
        quantity=parsed_quantity,
        set_code=_normalize_set_code(match.group("set_code")),
        collector_number=_clean_optional(match.group("collector_number")),
        section=_normalize_section(section),
    )


def quick_add_card(
    project: DeckProject,
    text: str,
    quantity: int | None = None,
    section: str = "main",
    *,
    card_service: Any | None = None,
    allow_remote: bool = False,
) -> QuickAddResult:
    try:
        query = parse_quick_add_input(text, quantity=quantity, section=section)
    except (TypeError, ValueError) as exc:
        return QuickAddResult(status="invalid", message=str(exc))

    candidate = _resolve_exact_candidate(
        query,
        card_service=card_service,
        allow_remote=allow_remote,
    )
    if candidate is not None:
        result = add_or_increment_card(
            project,
            name=query.name,
            quantity=query.quantity,
            section=query.section,
            set_code=query.set_code,
            collector_number=query.collector_number,
            candidate=candidate,
        )
        return QuickAddResult(
            status="added",
            card_id=result.card_id,
            query=query,
            message="Card added." if result.created else "Card quantity updated.",
        )

    candidates = search_printings(
        query.name,
        set_filter=query.set_code,
        card_service=card_service,
        allow_remote=allow_remote,
        limit=20,
    )
    if candidates:
        return QuickAddResult(
            status="needs_selection",
            candidates=candidates,
            query=query,
            message="Choose a printing to add.",
        )

    return QuickAddResult(
        status="not_found",
        query=query,
        message="No matching card was found.",
    )


def search_printings(
    query: str,
    set_filter: str | None = None,
    *,
    card_service: Any | None = None,
    allow_remote: bool = False,
    limit: int = 20,
) -> list[CatalogCardCandidate]:
    return search_catalog_cards(
        query,
        set_filter=set_filter,
        card_service=card_service,
        allow_remote=allow_remote,
        limit=limit,
    )


def add_catalog_candidate(
    project: DeckProject,
    candidate: CatalogCardCandidate,
    quantity: int = 1,
    section: str = "main",
    import_section: str | None = None,
) -> QuickAddResult:
    try:
        count = int(quantity)
    except (TypeError, ValueError):
        return QuickAddResult(status="invalid", message="quantity must be greater than zero")
    if count <= 0:
        return QuickAddResult(status="invalid", message="quantity must be greater than zero")

    result = add_or_increment_card(
        project,
        name=candidate.name,
        quantity=count,
        section=section,
        import_section=import_section,
        set_code=candidate.set_code,
        collector_number=candidate.collector_number,
        candidate=candidate,
    )
    return QuickAddResult(
        status="added",
        card_id=result.card_id,
        message="Card added." if result.created else "Card quantity updated.",
    )


def _resolve_exact_candidate(
    query: QuickAddQuery,
    *,
    card_service: Any | None,
    allow_remote: bool,
) -> CatalogCardCandidate | None:
    try:
        candidate = resolve_deck_entry(
            query,
            card_service=card_service,
            allow_remote=allow_remote,
        )
    except Exception as exc:
        if exc.__class__.__name__ == "RemoteLookupUnavailable":
            return None
        raise

    if candidate is None:
        return None
    if query.set_code and query.collector_number:
        return candidate
    if candidate.source in EXACT_CATALOG_SOURCES:
        return candidate
    return None


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
