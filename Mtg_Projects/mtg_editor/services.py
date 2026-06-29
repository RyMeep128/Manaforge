from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Mapping

from mtg_editor.models import DEFAULT_CATEGORY_ID, DEFAULT_SECTION, DeckCard, DeckProject


SECTION_LABELS = {
    "commander": "Commander",
    "main": "Main Deck",
    "sideboard": "Sideboard",
    "maybeboard": "Maybeboard",
    "excluded": "Excluded",
}

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

COLOR_LABELS = {
    "W": "White",
    "U": "Blue",
    "B": "Black",
    "R": "Red",
    "G": "Green",
}
COLOR_BUCKET_ORDER = [
    "white",
    "blue",
    "black",
    "red",
    "green",
    "multicolor",
    "colorless",
]
COLOR_BUCKET_LABELS = {
    "white": "White",
    "blue": "Blue",
    "black": "Black",
    "red": "Red",
    "green": "Green",
    "multicolor": "Multicolor",
    "colorless": "Colorless",
}
COLOR_SYMBOL_TO_BUCKET = {
    "W": "white",
    "U": "blue",
    "B": "black",
    "R": "red",
    "G": "green",
}
MANA_BUCKET_ORDER = ["0", "1", "2", "3", "4", "5", "6", "7_plus", "unknown"]
MANA_BUCKET_LABELS = {
    "7_plus": "7+",
    "unknown": "Unknown",
}


@dataclass(frozen=True)
class CardGroup:
    key: str
    label: str
    card_ids: list[str]


@dataclass(frozen=True)
class CardFilters:
    text: str | None = None
    category: str | None = None
    tag: str | None = None
    section: str | None = None
    card_type: str | None = None
    color: str | None = None
    catalog_status: str | None = None
    missing_image: bool | None = None


def sort_cards(project: DeckProject, sort_mode: str) -> list[DeckCard]:
    cards = list(project.cards)
    original_index = {card.card_id: index for index, card in enumerate(cards)}

    if sort_mode == "alphabetical_az":
        return sorted(cards, key=lambda card: card.name.casefold())
    if sort_mode == "alphabetical_za":
        return sorted(cards, key=lambda card: card.name.casefold(), reverse=True)
    if sort_mode == "quantity":
        return sorted(cards, key=lambda card: (-card.quantity, card.name.casefold()))
    if sort_mode == "mana_value":
        return sorted(cards, key=lambda card: (_mana_sort_key(card), card.name.casefold()))
    if sort_mode == "color":
        return sorted(cards, key=lambda card: (_color_sort_key(card), card.name.casefold()))
    if sort_mode == "import_order":
        return sorted(
            cards,
            key=lambda card: (
                card.sort_index if card.sort_index is not None else original_index[card.card_id],
                original_index[card.card_id],
            ),
        )
    raise ValueError(f"Unsupported sort mode: {sort_mode}")


def group_cards(project: DeckProject, group_mode: str) -> list[CardGroup]:
    sorted_cards = sort_cards(project, project.preferences.sort_mode)
    if group_mode == "none":
        return [
            CardGroup(
                key="all",
                label="All Cards",
                card_ids=[card.card_id for card in sorted_cards],
            )
        ]
    if group_mode == "category":
        return _group_by_category(project, sorted_cards)
    if group_mode == "section":
        return _group_by_section(sorted_cards)
    if group_mode == "import_section":
        return _group_by_import_section(sorted_cards)
    if group_mode == "card_type":
        return _group_by_card_type(sorted_cards)
    if group_mode == "mana_value":
        return _group_by_mana_value(sorted_cards)
    if group_mode == "color":
        return _group_by_color(sorted_cards)
    raise ValueError(f"Unsupported group mode: {group_mode}")


def filter_cards(
    project: DeckProject,
    filters: CardFilters | Mapping[str, Any] | None,
) -> list[DeckCard]:
    normalized_filters = _normalize_filters(filters)
    return [
        card
        for card in project.cards
        if _matches_filters(card, normalized_filters)
    ]


def compute_deck_stats(project: DeckProject) -> dict[str, object]:
    section_counts: dict[str, dict[str, int]] = OrderedDict()
    category_counts: dict[str, dict[str, int]] = OrderedDict()
    tag_counts: dict[str, dict[str, int]] = OrderedDict()
    type_counts: dict[str, dict[str, int]] = OrderedDict()
    color_counts: dict[str, dict[str, int]] = OrderedDict()
    mana_value_counts: dict[str, dict[str, int]] = OrderedDict()
    total_unique_cards = 0
    total_copies = 0
    unresolved_count = 0
    missing_image_count = 0

    for card in project.cards:
        count = max(card.quantity, 0)
        if count <= 0:
            continue

        section = card.section or DEFAULT_SECTION
        category_id = card.primary_category or DEFAULT_CATEGORY_ID
        _increment_count(section_counts, section, count)
        _increment_count(category_counts, category_id, count)
        for tag in card.tags:
            _increment_count(tag_counts, tag, count)

        if section != "excluded":
            total_unique_cards += 1
            total_copies += count
            _increment_count(type_counts, _primary_card_type(card), count)
            _increment_count(color_counts, _color_bucket(card)[1], count)
            _increment_count(mana_value_counts, _mana_bucket(card)[1], count)
            if card.catalog_status == "unresolved":
                unresolved_count += 1
            if not _has_image(card):
                missing_image_count += 1

    return {
        "total_unique_cards": total_unique_cards,
        "total_copies": total_copies,
        "section_counts": dict(section_counts),
        "category_counts": dict(category_counts),
        "tag_counts": dict(tag_counts),
        "type_counts": dict(type_counts),
        "color_counts": dict(color_counts),
        "mana_value_counts": dict(mana_value_counts),
        "unresolved_count": unresolved_count,
        "missing_image_count": missing_image_count,
    }


def _group_by_category(project: DeckProject, sorted_cards: list[DeckCard]) -> list[CardGroup]:
    category_names = {category.id: category.name for category in project.categories}
    buckets: OrderedDict[str, list[str]] = OrderedDict(
        (category.id, []) for category in project.categories
    )
    for card in sorted_cards:
        category_id = (
            card.primary_category
            if card.primary_category in category_names
            else DEFAULT_CATEGORY_ID
        )
        buckets.setdefault(category_id, []).append(card.card_id)
    return [
        CardGroup(
            key=category_id,
            label=category_names.get(category_id, category_id),
            card_ids=card_ids,
        )
        for category_id, card_ids in buckets.items()
        if card_ids
    ]


def _group_by_section(sorted_cards: list[DeckCard]) -> list[CardGroup]:
    buckets: OrderedDict[str, list[str]] = OrderedDict()
    for card in sorted_cards:
        section = card.section or DEFAULT_SECTION
        buckets.setdefault(section, []).append(card.card_id)
    return [
        CardGroup(
            key=section,
            label=SECTION_LABELS.get(section, section.title()),
            card_ids=card_ids,
        )
        for section, card_ids in buckets.items()
    ]


def _group_by_import_section(sorted_cards: list[DeckCard]) -> list[CardGroup]:
    buckets: OrderedDict[str, list[str]] = OrderedDict()
    for card in sorted_cards:
        import_section = card.import_section or "Unsectioned"
        buckets.setdefault(import_section, []).append(card.card_id)
    return [
        CardGroup(key=section, label=section, card_ids=card_ids)
        for section, card_ids in buckets.items()
    ]


def _group_by_card_type(sorted_cards: list[DeckCard]) -> list[CardGroup]:
    buckets: OrderedDict[str, list[str]] = OrderedDict(
        (card_type.lower(), []) for card_type in CARD_TYPE_PRIORITY
    )
    buckets["other"] = []
    labels = {card_type.lower(): card_type for card_type in CARD_TYPE_PRIORITY}
    labels["other"] = "Other"
    for card in sorted_cards:
        key = _primary_card_type(card).lower()
        buckets.setdefault(key, []).append(card.card_id)
    return [
        CardGroup(key=key, label=labels.get(key, key.title()), card_ids=card_ids)
        for key, card_ids in buckets.items()
        if card_ids
    ]


def _group_by_mana_value(sorted_cards: list[DeckCard]) -> list[CardGroup]:
    buckets: OrderedDict[str, list[str]] = OrderedDict((key, []) for key in MANA_BUCKET_ORDER)
    for card in sorted_cards:
        key, _label = _mana_bucket(card)
        buckets.setdefault(key, []).append(card.card_id)
    return [
        CardGroup(
            key=key,
            label=MANA_BUCKET_LABELS.get(key, key),
            card_ids=card_ids,
        )
        for key, card_ids in buckets.items()
        if card_ids
    ]


def _group_by_color(sorted_cards: list[DeckCard]) -> list[CardGroup]:
    buckets: OrderedDict[str, list[str]] = OrderedDict((key, []) for key in COLOR_BUCKET_ORDER)
    for card in sorted_cards:
        key, _label = _color_bucket(card)
        buckets.setdefault(key, []).append(card.card_id)
    return [
        CardGroup(
            key=key,
            label=COLOR_BUCKET_LABELS.get(key, key.title()),
            card_ids=card_ids,
        )
        for key, card_ids in buckets.items()
        if card_ids
    ]


def _increment_count(target: dict[str, dict[str, int]], key: str, count: int) -> None:
    if key not in target:
        target[key] = {"unique": 0, "copies": 0}
    target[key]["unique"] += 1
    target[key]["copies"] += count


def _normalize_filters(filters: CardFilters | Mapping[str, Any] | None) -> CardFilters:
    if filters is None:
        return CardFilters()
    if isinstance(filters, CardFilters):
        return filters
    return CardFilters(
        text=_optional_str(filters.get("text")),
        category=_optional_str(filters.get("category")),
        tag=_optional_str(filters.get("tag")),
        section=_optional_str(filters.get("section")),
        card_type=_optional_str(filters.get("card_type")),
        color=_optional_str(filters.get("color")),
        catalog_status=_optional_str(filters.get("catalog_status")),
        missing_image=filters.get("missing_image"),
    )


def _matches_filters(card: DeckCard, filters: CardFilters) -> bool:
    if filters.text and filters.text.casefold() not in _search_text(card):
        return False
    if filters.category and card.primary_category != filters.category:
        return False
    if filters.tag and filters.tag.casefold() not in {tag.casefold() for tag in card.tags}:
        return False
    if filters.section and (card.section or DEFAULT_SECTION) != _normalize_section(filters.section):
        return False
    if filters.card_type:
        requested = filters.card_type.casefold()
        card_types = {card_type.casefold() for card_type in _card_types(card)}
        if requested not in card_types and requested != _primary_card_type(card).casefold():
            return False
    if filters.color:
        requested_color = _normalize_color_filter(filters.color)
        if requested_color is not None and _color_bucket(card)[0] != requested_color:
            return False
    if filters.catalog_status and (card.catalog_status or "").casefold() != filters.catalog_status.casefold():
        return False
    if filters.missing_image is not None and (not _has_image(card)) != bool(filters.missing_image):
        return False
    return True


def _search_text(card: DeckCard) -> str:
    values = [
        card.name,
        card.type_line,
        card.set_code,
        card.set_name,
        card.collector_number,
        card.mana_cost,
    ]
    return " ".join(value for value in values if value).casefold()


def _card_types(card: DeckCard) -> list[str]:
    if card.card_types:
        return list(card.card_types)
    if not card.type_line:
        return []
    primary_line = card.type_line.split("—", 1)[0].split("-", 1)[0]
    words = {word.casefold() for word in primary_line.split()}
    return [
        card_type
        for card_type in CARD_TYPE_PRIORITY
        if card_type.casefold() in words
    ] or ["Other"]


def _primary_card_type(card: DeckCard) -> str:
    card_types = {card_type.casefold() for card_type in _card_types(card)}
    for card_type in CARD_TYPE_PRIORITY:
        if card_type.casefold() in card_types:
            return card_type
    return "Other"


def _mana_bucket(card: DeckCard) -> tuple[str, str]:
    value = card.mana_value
    if value is None:
        return "unknown", "Unknown"
    if value >= 7:
        return "7_plus", "7+"
    key = str(max(0, int(value)))
    return key, key


def _mana_sort_key(card: DeckCard) -> tuple[int, float]:
    if card.mana_value is None:
        return (1, 0)
    return (0, card.mana_value)


def _color_bucket(card: DeckCard) -> tuple[str, str]:
    colors = card.color_identity or card.colors
    normalized_colors = [
        color.upper()
        for color in colors
        if color.upper() in COLOR_SYMBOL_TO_BUCKET
    ]
    unique_colors = list(dict.fromkeys(normalized_colors))
    if len(unique_colors) == 0:
        return "colorless", "Colorless"
    if len(unique_colors) > 1:
        return "multicolor", "Multicolor"
    color = unique_colors[0]
    return COLOR_SYMBOL_TO_BUCKET[color], COLOR_LABELS[color]


def _color_sort_key(card: DeckCard) -> int:
    return COLOR_BUCKET_ORDER.index(_color_bucket(card)[0])


def _normalize_color_filter(value: str) -> str | None:
    normalized = str(value or "").strip().casefold()
    if not normalized:
        return None
    symbol = normalized.upper()
    if symbol in COLOR_SYMBOL_TO_BUCKET:
        return COLOR_SYMBOL_TO_BUCKET[symbol]
    for key, label in COLOR_BUCKET_LABELS.items():
        if normalized in {key, label.casefold()}:
            return key
    return normalized


def _has_image(card: DeckCard) -> bool:
    return any(
        [
            card.image_path,
            card.image_uri,
            card.image_asset_id,
            card.local_image_path,
            card.preview_uri,
            card.thumbnail_uri,
        ]
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _normalize_section(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "_".join(text.split()) or DEFAULT_SECTION
