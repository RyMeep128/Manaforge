from __future__ import annotations

import re


def normalize_card_name(value: str) -> str:
    normalized = re.sub(r"\s+", " ", (value or "").strip())
    normalized = normalized.replace(" / ", " // ")
    return normalized


def normalized_search_text(value: str) -> str:
    return normalize_card_name(value).casefold()


def choose_canonical_print_key(card_payload: dict) -> tuple:
    return (
        str(card_payload.get("released_at") or ""),
        str(card_payload.get("set") or ""),
        str(card_payload.get("collector_number") or ""),
        str(card_payload.get("id") or ""),
    )
