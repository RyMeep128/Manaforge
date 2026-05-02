from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping
import re


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
    text = str(value)
    return text if text else None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def _slugify(value: str, fallback: str = "category") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = slug.strip("-")
    return slug or fallback


def _normalize_section(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", "_", text)
    return text or DEFAULT_SECTION


def _project_card_names(project_dict: Mapping[str, Any]) -> list[str]:
    card_entries = project_dict.get("card_entries")
    if isinstance(card_entries, list) and card_entries:
        names: list[str] = []
        seen: set[str] = set()
        for raw_entry in card_entries:
            if not isinstance(raw_entry, Mapping):
                continue
            name = str(raw_entry.get("front_name") or "")
            if not name or name.startswith("__") or name in seen:
                continue
            names.append(name)
            seen.add(name)
        return names

    cards = project_dict.get("cards")
    if isinstance(cards, Mapping):
        return [
            str(name)
            for name in cards.keys()
            if str(name) and not str(name).startswith("__")
        ]
    return []


@dataclass
class DeckMetadata:
    deck_name: str = DEFAULT_DECK_NAME
    format: str = DEFAULT_FORMAT
    description: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str | None = None
    modified_at: str | None = None

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any] | None,
        *,
        display_name: str | None = None,
    ) -> "DeckMetadata":
        raw = _plain_dict(data)
        deck_name = str(raw.get("deck_name") or display_name or DEFAULT_DECK_NAME).strip()
        return cls(
            deck_name=deck_name or DEFAULT_DECK_NAME,
            format=str(raw.get("format") or DEFAULT_FORMAT).strip() or DEFAULT_FORMAT,
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
    def from_dict(cls, data: Mapping[str, Any] | None) -> "Category | None":
        raw = _plain_dict(data)
        category_id = str(raw.get("id") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not category_id or not name:
            return None
        return cls(id=category_id, name=name)

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name}


@dataclass
class CardOrganization:
    primary_category: str = DEFAULT_CATEGORY_ID
    tags: list[str] = field(default_factory=list)
    section: str = DEFAULT_SECTION
    import_section: str | None = None
    sort_index: int | None = None

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any] | None,
        *,
        sort_index: int | None = None,
    ) -> "CardOrganization":
        raw = _plain_dict(data)
        raw_sort_index = raw.get("sort_index", sort_index)
        try:
            resolved_sort_index = None if raw_sort_index is None else int(raw_sort_index)
        except (TypeError, ValueError):
            resolved_sort_index = sort_index
        return cls(
            primary_category=str(raw.get("primary_category") or DEFAULT_CATEGORY_ID),
            tags=_string_list(raw.get("tags")),
            section=_normalize_section(raw.get("section", DEFAULT_SECTION)),
            import_section=_optional_str(raw.get("import_section")),
            sort_index=resolved_sort_index,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_category": self.primary_category,
            "tags": list(self.tags),
            "section": self.section,
            "import_section": self.import_section,
            "sort_index": self.sort_index,
        }


@dataclass
class DeckEditorState:
    metadata: DeckMetadata = field(default_factory=DeckMetadata)
    preferences: DeckEditorPreferences = field(default_factory=DeckEditorPreferences)
    categories: list[Category] = field(default_factory=lambda: [Category.default()])
    cards: dict[str, CardOrganization] = field(default_factory=dict)
    notes: str = ""

    @classmethod
    def from_project_dict(
        cls,
        project_dict: Mapping[str, Any] | None,
        display_name: str | None = None,
    ) -> "DeckEditorState":
        project = _plain_dict(project_dict)
        overlay = _plain_dict(project.get("deck_editor"))
        categories = _parse_categories(overlay.get("categories"))
        category_ids = {category.id for category in categories}
        raw_cards = _plain_dict(overlay.get("cards"))
        cards: dict[str, CardOrganization] = {}
        for sort_index, front_name in enumerate(_project_card_names(project)):
            organization = CardOrganization.from_dict(
                raw_cards.get(front_name),
                sort_index=sort_index,
            )
            if organization.primary_category not in category_ids:
                organization.primary_category = DEFAULT_CATEGORY_ID
            cards[front_name] = organization

        return cls(
            metadata=DeckMetadata.from_dict(
                overlay.get("metadata"),
                display_name=display_name,
            ),
            preferences=DeckEditorPreferences.from_dict(overlay.get("preferences")),
            categories=categories,
            cards=cards,
            notes=str(overlay.get("notes") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "preferences": self.preferences.to_dict(),
            "categories": [category.to_dict() for category in self.categories],
            "cards": {
                front_name: organization.to_dict()
                for front_name, organization in self.cards.items()
            },
            "notes": self.notes,
        }

    def merge_into_project_dict(self, project_dict: Mapping[str, Any]) -> dict[str, Any]:
        merged = deepcopy(dict(project_dict))
        merged["deck_editor"] = self.to_dict()
        return merged

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
        for organization in self.cards.values():
            if organization.primary_category == category_id:
                organization.primary_category = DEFAULT_CATEGORY_ID

    def reorder_category(self, category_id: str, index: int) -> None:
        category = self._get_category(category_id)
        categories = [
            existing for existing in self.categories if existing.id != category_id
        ]
        clamped_index = max(0, min(int(index), len(categories)))
        categories.insert(clamped_index, category)
        self.categories = categories

    def assign_category(self, front_name: str, category_id: str) -> None:
        if category_id not in self._category_ids():
            raise KeyError(category_id)
        self._ensure_card(front_name).primary_category = category_id

    def add_tag(self, front_name: str, tag: str) -> None:
        clean_tag = str(tag).strip()
        if not clean_tag:
            return
        organization = self._ensure_card(front_name)
        if clean_tag.casefold() not in {existing.casefold() for existing in organization.tags}:
            organization.tags.append(clean_tag)

    def remove_tag(self, front_name: str, tag: str) -> None:
        tag_key = str(tag).strip().casefold()
        organization = self._ensure_card(front_name)
        organization.tags = [
            existing for existing in organization.tags if existing.casefold() != tag_key
        ]

    def set_section(self, front_name: str, section: str) -> None:
        self._ensure_card(front_name).section = _normalize_section(section)

    def set_import_section(self, front_name: str, import_section: str | None) -> None:
        self._ensure_card(front_name).import_section = _optional_str(import_section)

    def _category_ids(self) -> set[str]:
        return {category.id for category in self.categories}

    def _get_category(self, category_id: str) -> Category:
        for category in self.categories:
            if category.id == category_id:
                return category
        raise KeyError(category_id)

    def _ensure_card(self, front_name: str) -> CardOrganization:
        clean_name = str(front_name).strip()
        if not clean_name:
            raise ValueError("front_name is required")
        if clean_name not in self.cards:
            self.cards[clean_name] = CardOrganization(sort_index=len(self.cards))
        return self.cards[clean_name]


def _parse_categories(value: Any) -> list[Category]:
    categories: list[Category] = []
    seen: set[str] = set()
    for raw_category in _plain_list(value):
        category = Category.from_dict(raw_category)
        if category is None or category.id in seen:
            continue
        categories.append(category)
        seen.add(category.id)
    if DEFAULT_CATEGORY_ID not in seen:
        categories.insert(0, Category.default())
    if not categories:
        categories = [Category.default()]
    return categories
