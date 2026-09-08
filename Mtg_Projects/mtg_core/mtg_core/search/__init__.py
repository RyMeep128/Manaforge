from __future__ import annotations

import re


def normalize_card_name(value: str) -> str:
    normalized = re.sub(r"\s+", " ", (value or "").strip())
    normalized = normalized.replace(" / ", " // ")
    return normalized


def normalized_search_text(value: str) -> str:
    return normalize_card_name(value).casefold()


def card_rules_text(payload: dict) -> str:
    """Readable stored card text, including every face without truncation."""
    return '\n\n'.join('\n'.join(str(face[key]) for key in
        ('name', 'mana_cost', 'type_line', 'oracle_text', 'power', 'toughness', 'loyalty', 'flavor_text')
        if face.get(key) is not None) for face in (payload.get('card_faces') or [payload]))


def choose_canonical_print_key(card_payload: dict) -> tuple:
    return (
        str(card_payload.get("released_at") or ""),
        str(card_payload.get("set") or ""),
        str(card_payload.get("collector_number") or ""),
        str(card_payload.get("id") or ""),
    )
