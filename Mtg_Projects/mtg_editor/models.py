from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping
import re
import uuid


SCHEMA_VERSION = 1
DEFAULT_CATEGORY_ID = "uncategorized"
DEFAULT_CATEGORY_NAME = "Uncategorized"
DEFAULT_SECTION = "main"
DEFAULT_DECK_NAME = "Untitled Deck"
DEFAULT_FORMAT = "Custom"
DEFAULT_VIEW_MODE = "grid"
DEFAULT_GROUP_MODE = "none"
DEFAULT_SORT_MODE = "alphabetical_az"


def _plain_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _plain_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item).strip()
        key = text.casefold()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _non_negative_int(value: Any, default: int = 0) -> int:
    return max(0, _int_or_default(value, default))


def _slugify(value: str, fallback: str = "category") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = slug.strip("-")
    return slug or fallback


def _normalize_section(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", "_", text)
    return text or DEFAULT_SECTION


def _new_card_id() -> str:
    return f"card-{uuid.uuid4().hex}"


@dataclass
class DeckMetadata:
    deck_name: str = DEFAULT_DECK_NAME
    format: str = DEFAULT_FORMAT
    description: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str | None = None
    modified_at: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "DeckMetadata":
        raw = _plain_dict(data)
        deck_name = str(raw.get("deck_name") or DEFAULT_DECK_NAME).strip()
        deck_format = str(raw.get("format") or DEFAULT_FORMAT).strip()
        return cls(
            deck_name=deck_name or DEFAULT_DECK_NAME,
            format=deck_format or DEFAULT_FORMAT,
            description=str(raw.get("description") or ""),
            tags=_string_list(raw.get("tags")),
            created_at=_optional_str(raw.get("created_at")),
            modified_at=_optional_str(raw.get("modified_at")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "deck_name": self.deck_name,
            "format": self.format,
            "description": self.description,
            "tags": list(self.tags),
            "created_at": self.created_at,
            "modified_at": self.modified_at,
        }


@dataclass
class DeckEditorPreferences:
    view_mode: str = DEFAULT_VIEW_MODE
    group_mode: str = DEFAULT_GROUP_MODE
    sort_mode: str = DEFAULT_SORT_MODE
    active_filters: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "DeckEditorPreferences":
        raw = _plain_dict(data)
        return cls(
            view_mode=str(raw.get("view_mode") or DEFAULT_VIEW_MODE),
            group_mode=str(raw.get("group_mode") or DEFAULT_GROUP_MODE),
            sort_mode=str(raw.get("sort_mode") or DEFAULT_SORT_MODE),
            active_filters=_plain_dict(raw.get("active_filters")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "view_mode": self.view_mode,
            "group_mode": self.group_mode,
            "sort_mode": self.sort_mode,
            "active_filters": deepcopy(self.active_filters),
        }


@dataclass
class Category:
    id: str
    name: str

    @classmethod
    def default(cls) -> "Category":
        return cls(id=DEFAULT_CATEGORY_ID, name=DEFAULT_CATEGORY_NAME)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "Category":
        raw = _plain_dict(data)
        category_id = str(raw.get("id") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not category_id or not name:
            raise ValueError("category id and name are required")
        return cls(id=category_id, name=name)

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name}


@dataclass
class DeckCard:
    card_id: str
    name: str
    quantity: int = 1
    section: str = DEFAULT_SECTION
    primary_category: str = DEFAULT_CATEGORY_ID
    tags: list[str] = field(default_factory=list)
    set_code: str | None = None
    collector_number: str | None = None
    import_section: str | None = None
    sort_index: int | None = None
    image_path: str | None = None
    image_uri: str | None = None
    image_asset_id: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "DeckCard":
        raw = _plain_dict(data)
        card_id = str(raw.get("card_id") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not card_id or not name:
            raise ValueError("card_id and name are required")
        raw_sort_index = raw.get("sort_index")
        return cls(
            card_id=card_id,
            name=name,
            quantity=_non_negative_int(raw.get("quantity"), 1),
            section=_normalize_section(raw.get("section", DEFAULT_SECTION)),
            primary_category=str(raw.get("primary_category") or DEFAULT_CATEGORY_ID),
            tags=_string_list(raw.get("tags")),
            set_code=_optional_str(raw.get("set_code")),
            collector_number=_optional_str(raw.get("collector_number")),
            import_section=_optional_str(raw.get("import_section")),
            sort_index=None if raw_sort_index is None else _int_or_default(raw_sort_index, 0),
            image_path=_optional_str(raw.get("image_path")),
            image_uri=_optional_str(raw.get("image_uri")),
            image_asset_id=_optional_str(raw.get("image_asset_id")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "name": self.name,
            "quantity": self.quantity,
            "section": self.section,
            "primary_category": self.primary_category,
            "tags": list(self.tags),
            "set_code": self.set_code,
            "collector_number": self.collector_number,
            "import_section": self.import_section,
            "sort_index": self.sort_index,
            "image_path": self.image_path,
            "image_uri": self.image_uri,
            "image_asset_id": self.image_asset_id,
        }


@dataclass
class DeckProject:
    metadata: DeckMetadata = field(default_factory=DeckMetadata)
    preferences: DeckEditorPreferences = field(default_factory=DeckEditorPreferences)
    categories: list[Category] = field(default_factory=lambda: [Category.default()])
    cards: list[DeckCard] = field(default_factory=list)
    notes: str = ""
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def new(
        cls,
        deck_name: str = DEFAULT_DECK_NAME,
        format: str = DEFAULT_FORMAT,
    ) -> "DeckProject":
        metadata = DeckMetadata(
            deck_name=str(deck_name).strip() or DEFAULT_DECK_NAME,
            format=str(format).strip() or DEFAULT_FORMAT,
        )
        return cls(metadata=metadata)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "DeckProject":
        raw = _plain_dict(data)
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"unsupported deck project schema_version: {raw.get('schema_version')!r}")

        categories = _parse_categories(raw.get("categories"))
        category_ids = {category.id for category in categories}
        cards = _parse_cards(raw.get("cards"), category_ids)
        return cls(
            metadata=DeckMetadata.from_dict(raw.get("metadata")),
            preferences=DeckEditorPreferences.from_dict(raw.get("preferences")),
            categories=categories,
            cards=cards,
            notes=str(raw.get("notes") or ""),
            schema_version=SCHEMA_VERSION,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "metadata": self.metadata.to_dict(),
            "preferences": self.preferences.to_dict(),
            "categories": [category.to_dict() for category in self.categories],
            "cards": [card.to_dict() for card in self.cards],
            "notes": self.notes,
        }

    def add_card(self, name: str, quantity: int = 1, **metadata: Any) -> str:
        clean_name = str(name).strip()
        if not clean_name:
            raise ValueError("card name is required")
        card_id = str(metadata.pop("card_id", "") or _new_card_id()).strip()
        if self.get_card(card_id) is not None:
            raise ValueError(f"duplicate card_id: {card_id}")
        primary_category = str(metadata.pop("primary_category", DEFAULT_CATEGORY_ID) or DEFAULT_CATEGORY_ID)
        if primary_category not in self._category_ids():
            raise KeyError(primary_category)
        raw_sort_index = metadata.pop("sort_index", None)
        card = DeckCard(
            card_id=card_id,
            name=clean_name,
            quantity=_non_negative_int(quantity, 1),
            section=_normalize_section(metadata.pop("section", DEFAULT_SECTION)),
            primary_category=primary_category,
            tags=_string_list(metadata.pop("tags", [])),
            set_code=_optional_str(metadata.pop("set_code", None)),
            collector_number=_optional_str(metadata.pop("collector_number", None)),
            import_section=_optional_str(metadata.pop("import_section", None)),
            sort_index=(
                len(self.cards)
                if raw_sort_index is None
                else _int_or_default(raw_sort_index, len(self.cards))
            ),
            image_path=_optional_str(metadata.pop("image_path", None)),
            image_uri=_optional_str(metadata.pop("image_uri", None)),
            image_asset_id=_optional_str(metadata.pop("image_asset_id", None)),
        )
        self.cards.append(card)
        return card.card_id

    def remove_card(self, card_id: str) -> None:
        self._get_card(card_id)
        self.cards = [card for card in self.cards if card.card_id != card_id]

    def set_quantity(self, card_id: str, quantity: int) -> None:
        self._get_card(card_id).quantity = _non_negative_int(quantity)

    def create_category(self, name: str) -> str:
        clean_name = str(name).strip()
        if not clean_name:
            raise ValueError("category name is required")
        base_id = _slugify(clean_name)
        existing = self._category_ids()
        category_id = base_id
        suffix = 2
        while category_id in existing:
            category_id = f"{base_id}-{suffix}"
            suffix += 1
        self.categories.append(Category(id=category_id, name=clean_name))
        return category_id

    def rename_category(self, category_id: str, name: str) -> None:
        category = self._get_category(category_id)
        clean_name = str(name).strip()
        if not clean_name:
            raise ValueError("category name is required")
        category.name = clean_name

    def delete_category(self, category_id: str) -> None:
        if category_id == DEFAULT_CATEGORY_ID:
            raise ValueError("the default category cannot be deleted")
        self._get_category(category_id)
        self.categories = [
            category for category in self.categories if category.id != category_id
        ]
        for card in self.cards:
            if card.primary_category == category_id:
                card.primary_category = DEFAULT_CATEGORY_ID

    def reorder_category(self, category_id: str, index: int) -> None:
        category = self._get_category(category_id)
        categories = [
            existing for existing in self.categories if existing.id != category_id
        ]
        clamped_index = max(0, min(int(index), len(categories)))
        categories.insert(clamped_index, category)
        self.categories = categories

    def assign_category(self, card_id: str, category_id: str) -> None:
        if category_id not in self._category_ids():
            raise KeyError(category_id)
        self._get_card(card_id).primary_category = category_id

    def add_tag(self, card_id: str, tag: str) -> None:
        clean_tag = str(tag).strip()
        if not clean_tag:
            return
        card = self._get_card(card_id)
        if clean_tag.casefold() not in {existing.casefold() for existing in card.tags}:
            card.tags.append(clean_tag)

    def remove_tag(self, card_id: str, tag: str) -> None:
        tag_key = str(tag).strip().casefold()
        card = self._get_card(card_id)
        card.tags = [
            existing for existing in card.tags if existing.casefold() != tag_key
        ]

    def set_section(self, card_id: str, section: str) -> None:
        self._get_card(card_id).section = _normalize_section(section)

    def set_import_section(self, card_id: str, import_section: str | None) -> None:
        self._get_card(card_id).import_section = _optional_str(import_section)

    def get_card(self, card_id: str) -> DeckCard | None:
        for card in self.cards:
            if card.card_id == card_id:
                return card
        return None

    def _category_ids(self) -> set[str]:
        return {category.id for category in self.categories}

    def _get_category(self, category_id: str) -> Category:
        for category in self.categories:
            if category.id == category_id:
                return category
        raise KeyError(category_id)

    def _get_card(self, card_id: str) -> DeckCard:
        card = self.get_card(card_id)
        if card is None:
            raise KeyError(card_id)
        return card


def _parse_categories(value: Any) -> list[Category]:
    categories: list[Category] = []
    seen: set[str] = set()
    for raw_category in _plain_list(value):
        category = Category.from_dict(raw_category)
        if category.id in seen:
            raise ValueError(f"duplicate category id: {category.id}")
        categories.append(category)
        seen.add(category.id)
    if DEFAULT_CATEGORY_ID not in seen:
        categories.insert(0, Category.default())
    return categories or [Category.default()]


def _parse_cards(value: Any, category_ids: set[str]) -> list[DeckCard]:
    cards: list[DeckCard] = []
    seen: set[str] = set()
    for index, raw_card in enumerate(_plain_list(value)):
        card = DeckCard.from_dict(raw_card)
        if card.card_id in seen:
            raise ValueError(f"duplicate card id: {card.card_id}")
        if card.primary_category not in category_ids:
            card.primary_category = DEFAULT_CATEGORY_ID
        if card.sort_index is None:
            card.sort_index = index
        cards.append(card)
        seen.add(card.card_id)
    return cards
