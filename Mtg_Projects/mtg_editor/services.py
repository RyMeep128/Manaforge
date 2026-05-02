from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from mtg_editor.models import DEFAULT_CATEGORY_ID, DEFAULT_SECTION, DeckCard, DeckProject


SECTION_LABELS = {
    "commander": "Commander",
    "main": "Main Deck",
    "sideboard": "Sideboard",
    "maybeboard": "Maybeboard",
    "excluded": "Excluded",
}


@dataclass(frozen=True)
class CardGroup:
    key: str
    label: str
    card_ids: list[str]


def sort_cards(project: DeckProject, sort_mode: str) -> list[DeckCard]:
    cards = list(project.cards)
    original_index = {card.card_id: index for index, card in enumerate(cards)}

    if sort_mode == "alphabetical_az":
        return sorted(cards, key=lambda card: card.name.casefold())
    if sort_mode == "alphabetical_za":
        return sorted(cards, key=lambda card: card.name.casefold(), reverse=True)
    if sort_mode == "quantity":
        return sorted(cards, key=lambda card: (-card.quantity, card.name.casefold()))
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
    raise ValueError(f"Unsupported group mode: {group_mode}")


def compute_deck_stats(project: DeckProject) -> dict[str, object]:
    section_counts: dict[str, dict[str, int]] = OrderedDict()
    category_counts: dict[str, dict[str, int]] = OrderedDict()
    tag_counts: dict[str, dict[str, int]] = OrderedDict()
    total_unique_cards = 0
    total_copies = 0

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

    return {
        "total_unique_cards": total_unique_cards,
        "total_copies": total_copies,
        "section_counts": dict(section_counts),
        "category_counts": dict(category_counts),
        "tag_counts": dict(tag_counts),
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


def _increment_count(target: dict[str, dict[str, int]], key: str, count: int) -> None:
    if key not in target:
        target[key] = {"unique": 0, "copies": 0}
    target[key]["unique"] += 1
    target[key]["copies"] += count
