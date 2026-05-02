from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Mapping

from mtg_editor.models import DEFAULT_CATEGORY_ID, DEFAULT_SECTION, DeckEditorState


SECTION_LABELS = {
    "commander": "Commander",
    "main": "Main Deck",
    "sideboard": "Sideboard",
    "maybeboard": "Maybeboard",
    "excluded": "Excluded",
}


@dataclass(frozen=True)
class ProjectCard:
    front_name: str
    count: int
    metadata: dict[str, Any]
    import_order: int


@dataclass(frozen=True)
class CardGroup:
    key: str
    label: str
    card_names: list[str]


def sort_card_names(
    state: DeckEditorState,
    project_dict: Mapping[str, Any],
    sort_mode: str,
) -> list[str]:
    cards = _project_cards(project_dict)
    card_by_name = {card.front_name: card for card in cards}
    names = [card.front_name for card in cards]

    if sort_mode == "alphabetical_az":
        return sorted(names, key=lambda name: _card_display_name(card_by_name[name]))
    if sort_mode == "alphabetical_za":
        return sorted(
            names,
            key=lambda name: _card_display_name(card_by_name[name]),
            reverse=True,
        )
    if sort_mode == "quantity":
        return sorted(
            names,
            key=lambda name: (
                -card_by_name[name].count,
                _card_display_name(card_by_name[name]),
            ),
        )
    if sort_mode == "import_order":
        return sorted(
            names,
            key=lambda name: (
                _organization_sort_index(state, name, card_by_name[name].import_order),
                card_by_name[name].import_order,
            ),
        )
    raise ValueError(f"Unsupported sort mode: {sort_mode}")


def group_cards(
    state: DeckEditorState,
    project_dict: Mapping[str, Any],
    group_mode: str,
) -> list[CardGroup]:
    sorted_names = sort_card_names(state, project_dict, state.preferences.sort_mode)
    if group_mode == "none":
        return [CardGroup(key="all", label="All Cards", card_names=sorted_names)]
    if group_mode == "category":
        return _group_by_category(state, sorted_names)
    if group_mode == "section":
        return _group_by_section(state, sorted_names)
    if group_mode == "import_section":
        return _group_by_import_section(state, sorted_names)
    raise ValueError(f"Unsupported group mode: {group_mode}")


def compute_deck_stats(
    state: DeckEditorState,
    project_dict: Mapping[str, Any],
) -> dict[str, Any]:
    cards = _project_cards(project_dict)
    section_counts: dict[str, dict[str, int]] = OrderedDict()
    category_counts: dict[str, dict[str, int]] = OrderedDict()
    tag_counts: dict[str, dict[str, int]] = OrderedDict()
    total_unique_cards = 0
    total_copies = 0

    for card in cards:
        organization = state.cards.get(card.front_name)
        section = organization.section if organization is not None else DEFAULT_SECTION
        category_id = (
            organization.primary_category
            if organization is not None
            else DEFAULT_CATEGORY_ID
        )
        tags = organization.tags if organization is not None else []
        count = max(card.count, 0)
        if count <= 0:
            continue

        _increment_count(section_counts, section, count)
        _increment_count(category_counts, category_id, count)
        for tag in tags:
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


def _group_by_category(state: DeckEditorState, sorted_names: list[str]) -> list[CardGroup]:
    category_names = {category.id: category.name for category in state.categories}
    buckets: OrderedDict[str, list[str]] = OrderedDict(
        (category.id, []) for category in state.categories
    )
    for name in sorted_names:
        organization = state.cards.get(name)
        category_id = (
            organization.primary_category
            if organization is not None
            and organization.primary_category in category_names
            else DEFAULT_CATEGORY_ID
        )
        buckets.setdefault(category_id, []).append(name)
    return [
        CardGroup(key=category_id, label=category_names.get(category_id, category_id), card_names=cards)
        for category_id, cards in buckets.items()
        if cards
    ]


def _group_by_section(state: DeckEditorState, sorted_names: list[str]) -> list[CardGroup]:
    buckets: OrderedDict[str, list[str]] = OrderedDict()
    for name in sorted_names:
        organization = state.cards.get(name)
        section = organization.section if organization is not None else DEFAULT_SECTION
        buckets.setdefault(section, []).append(name)
    return [
        CardGroup(key=section, label=SECTION_LABELS.get(section, section.title()), card_names=cards)
        for section, cards in buckets.items()
    ]


def _group_by_import_section(state: DeckEditorState, sorted_names: list[str]) -> list[CardGroup]:
    buckets: OrderedDict[str, list[str]] = OrderedDict()
    for name in sorted_names:
        organization = state.cards.get(name)
        import_section = (
            organization.import_section
            if organization is not None and organization.import_section
            else "Unsectioned"
        )
        buckets.setdefault(import_section, []).append(name)
    return [
        CardGroup(key=section, label=section, card_names=cards)
        for section, cards in buckets.items()
    ]


def _project_cards(project_dict: Mapping[str, Any]) -> list[ProjectCard]:
    card_entries = project_dict.get("card_entries")
    metadata_by_name = _legacy_metadata(project_dict)
    if isinstance(card_entries, list) and card_entries:
        cards: list[ProjectCard] = []
        seen: set[str] = set()
        for index, raw_entry in enumerate(card_entries):
            if not isinstance(raw_entry, Mapping):
                continue
            front_name = str(raw_entry.get("front_name") or "")
            if not front_name or front_name.startswith("__") or front_name in seen:
                continue
            seen.add(front_name)
            cards.append(
                ProjectCard(
                    front_name=front_name,
                    count=_int_or_zero(raw_entry.get("count")),
                    metadata={
                        **metadata_by_name.get(front_name, {}),
                        **_entry_metadata(raw_entry),
                    },
                    import_order=index,
                )
            )
        return cards

    cards_raw = project_dict.get("cards")
    if not isinstance(cards_raw, Mapping):
        return []
    result: list[ProjectCard] = []
    for index, (front_name_raw, count_raw) in enumerate(cards_raw.items()):
        front_name = str(front_name_raw)
        if not front_name or front_name.startswith("__"):
            continue
        result.append(
            ProjectCard(
                front_name=front_name,
                count=_int_or_zero(count_raw),
                metadata=metadata_by_name.get(front_name, {}),
                import_order=index,
            )
        )
    return result


def _legacy_metadata(project_dict: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw_metadata = project_dict.get("card_metadata")
    if not isinstance(raw_metadata, Mapping):
        return {}
    return {
        str(front_name): dict(metadata)
        for front_name, metadata in raw_metadata.items()
        if isinstance(metadata, Mapping)
    }


def _entry_metadata(raw_entry: Mapping[str, Any]) -> dict[str, Any]:
    raw_metadata = raw_entry.get("metadata")
    return dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {}


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _card_display_name(card: ProjectCard) -> str:
    return str(card.metadata.get("name") or card.front_name).casefold()


def _organization_sort_index(
    state: DeckEditorState,
    front_name: str,
    default: int,
) -> int:
    organization = state.cards.get(front_name)
    if organization is None or organization.sort_index is None:
        return default
    return organization.sort_index


def _increment_count(target: dict[str, dict[str, int]], key: str, count: int) -> None:
    if key not in target:
        target[key] = {"unique": 0, "copies": 0}
    target[key]["unique"] += 1
    target[key]["copies"] += count
