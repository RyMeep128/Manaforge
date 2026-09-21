from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping
import uuid


DECK_SCHEMA_VERSION = 1


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _quantity(value: Any, default: int = 1) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


@dataclass
class DeckCategory:
    category_id: str
    name: str
    sort_order: int = 0

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DeckCategory":
        return cls(
            category_id=str(value.get("category_id") or uuid.uuid4()),
            name=str(value.get("name") or "Uncategorized"),
            sort_order=int(value.get("sort_order", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "category_id": self.category_id,
            "name": self.name,
            "sort_order": self.sort_order,
        }


@dataclass
class DeckEntry:
    entry_id: str
    name: str
    quantity: int = 1
    section: str = "mainboard"
    sort_order: int = 0
    card_id: str | None = None
    oracle_id: str | None = None
    set_code: str | None = None
    collector_number: str | None = None
    image_asset_id: str | None = None
    category_ids: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    owned: int = 0
    do_not_print: bool = False
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DeckEntry":
        known = {
            "entry_id", "name", "quantity", "section", "sort_order", "card_id",
            "oracle_id", "set_code", "collector_number", "image_asset_id",
            "category_ids", "tags", "notes", "owned", "do_not_print",
        }
        return cls(
            entry_id=str(value.get("entry_id") or uuid.uuid4()),
            name=str(value.get("name") or ""),
            quantity=_quantity(value.get("quantity")),
            section=str(value.get("section") or "mainboard"),
            sort_order=int(value.get("sort_order", 0)),
            card_id=_text(value.get("card_id")),
            oracle_id=_text(value.get("oracle_id")),
            set_code=_text(value.get("set_code")),
            collector_number=_text(value.get("collector_number")),
            image_asset_id=_text(value.get("image_asset_id")),
            category_ids=[str(item) for item in value.get("category_ids", [])],
            tags=[str(item) for item in value.get("tags", [])],
            notes=str(value.get("notes") or ""),
            owned=_quantity(value.get("owned"), 0),
            do_not_print=bool(value.get("do_not_print", False)),
            extras={key: deepcopy(item) for key, item in value.items() if key not in known},
        )

    def to_dict(self) -> dict[str, Any]:
        result = deepcopy(self.extras)
        result.update({
            "entry_id": self.entry_id,
            "name": self.name,
            "quantity": self.quantity,
            "section": self.section,
            "sort_order": self.sort_order,
            "category_ids": list(self.category_ids),
            "tags": list(self.tags),
            "notes": self.notes,
            "owned": self.owned,
            "do_not_print": self.do_not_print,
        })
        for key in ("card_id", "oracle_id", "set_code", "collector_number", "image_asset_id"):
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        return result


@dataclass
class Deck:
    deck_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Untitled Deck"
    format: str = "Custom"
    description: str = ""
    entries: list[DeckEntry] = field(default_factory=list)
    categories: list[DeckCategory] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    commander_entry_ids: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "Deck":
        value = dict(value or {})
        known = {"deck_id", "name", "format", "description", "entries", "categories",
                 "tags", "commander_entry_ids"}
        return cls(
            deck_id=str(value.get("deck_id") or uuid.uuid4()),
            name=str(value.get("name") or "Untitled Deck"),
            format=str(value.get("format") or "Custom"),
            description=str(value.get("description") or ""),
            entries=[DeckEntry.from_dict(item) for item in value.get("entries", []) if isinstance(item, Mapping)],
            categories=[DeckCategory.from_dict(item) for item in value.get("categories", []) if isinstance(item, Mapping)],
            tags=[str(item) for item in value.get("tags", [])],
            commander_entry_ids=[str(item) for item in value.get("commander_entry_ids", [])],
            extras={key: deepcopy(item) for key, item in value.items() if key not in known},
        )

    def to_dict(self) -> dict[str, Any]:
        result = deepcopy(self.extras)
        result.update({
            "deck_id": self.deck_id,
            "name": self.name,
            "format": self.format,
            "description": self.description,
            "entries": [entry.to_dict() for entry in self.entries],
            "categories": [category.to_dict() for category in self.categories],
            "tags": list(self.tags),
            "commander_entry_ids": list(self.commander_entry_ids),
        })
        return result


@dataclass
class DeckDocument:
    deck: Deck = field(default_factory=Deck)
    print_settings: dict[str, Any] = field(default_factory=dict)
    editor_preferences: dict[str, Any] = field(default_factory=dict)
    schema_version: int = DECK_SCHEMA_VERSION
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "DeckDocument":
        value = dict(value or {})
        version = int(value.get("schema_version", DECK_SCHEMA_VERSION))
        if version > DECK_SCHEMA_VERSION:
            raise ValueError(f"Deck schema {version} is newer than supported schema {DECK_SCHEMA_VERSION}.")
        known = {"schema_version", "deck", "print_settings", "editor_preferences"}
        return cls(
            schema_version=version,
            deck=Deck.from_dict(value.get("deck")),
            print_settings=deepcopy(dict(value.get("print_settings") or {})),
            editor_preferences=deepcopy(dict(value.get("editor_preferences") or {})),
            extras={key: deepcopy(item) for key, item in value.items() if key not in known},
        )

    def to_dict(self) -> dict[str, Any]:
        result = deepcopy(self.extras)
        result.update({
            "schema_version": self.schema_version,
            "deck": self.deck.to_dict(),
            "print_settings": deepcopy(self.print_settings),
            "editor_preferences": deepcopy(self.editor_preferences),
        })
        return result

    @classmethod
    def from_legacy_proxy(cls, project: Mapping[str, Any], *, name: str = "Untitled Deck") -> "DeckDocument":
        project = deepcopy(dict(project))
        raw_entries = project.get("card_entries")
        if not isinstance(raw_entries, list) or not raw_entries:
            raw_entries = []
            metadata = project.get("card_metadata") if isinstance(project.get("card_metadata"), Mapping) else {}
            for index, (front_name, count) in enumerate(dict(project.get("cards") or {}).items()):
                raw_entries.append({
                    "entry_id": front_name,
                    "front_name": front_name,
                    "count": count,
                    "metadata": deepcopy(metadata.get(front_name, {})),
                    "backside_name": dict(project.get('backsides') or {}).get(front_name),
                    "backside_short_edge": bool(dict(project.get('backside_short_edge') or {}).get(front_name)),
                    "oversized": bool(dict(project.get('oversized') or {}).get(front_name)),
                })

        entries: list[DeckEntry] = []
        commanders: list[str] = []
        for index, raw in enumerate(raw_entries):
            if not isinstance(raw, Mapping):
                continue
            front_name = str(raw.get("front_name") or "")
            if not front_name or front_name.startswith("__"):
                continue
            metadata = raw.get("metadata") if isinstance(raw.get("metadata"), Mapping) else {}
            section = str(metadata.get("section") or "mainboard").casefold()
            entry_id = str(raw.get("entry_id") or front_name)
            entry = DeckEntry(
                entry_id=entry_id,
                name=str(metadata.get("name") or Path(front_name).stem),
                quantity=_quantity(raw.get("count")),
                section=section,
                sort_order=index,
                card_id=_text(raw.get("card_id")),
                oracle_id=_text(raw.get("oracle_id")),
                set_code=_text(metadata.get("set_code")),
                collector_number=_text(metadata.get("collector_number")),
                image_asset_id=_text(raw.get("image_asset_id")),
                do_not_print=bool(raw.get("do_not_print", False)),
                extras={"proxy_front_name": front_name,
                        "oversized": bool(raw.get('oversized', False)),
                        **{key: deepcopy(raw[key]) for key in ('backside_name', 'backside_asset_id', 'backside_short_edge') if raw.get(key) is not None},
                        **({'art_override': deepcopy(project['high_res_front_overrides'][front_name])}
                           if front_name in (project.get('high_res_front_overrides') or {}) else {})},
            )
            entries.append(entry)
            if section in {"commander", "commanders"}:
                commanders.append(entry_id)

        return cls(
            deck=Deck(name=name, entries=entries, commander_entry_ids=commanders),
            # The complete legacy payload is intentionally retained. The proxy owns
            # these fields and can evolve them without making Core understand them.
            print_settings={"proxy_project": project},
        )

    def apply_to_legacy_proxy(self) -> dict[str, Any]:
        project = deepcopy(dict(self.print_settings.get("proxy_project") or {}))
        original = {
            str(item.get("entry_id") or item.get("front_name") or ""): deepcopy(dict(item))
            for item in project.get("card_entries", [])
            if isinstance(item, Mapping)
        }
        card_entries = []
        for entry in sorted(self.deck.entries, key=lambda item: item.sort_order):
            raw = original.get(entry.entry_id, {})
            front_name = str(entry.extras.get("proxy_front_name") or raw.get("front_name") or entry.name)
            metadata = deepcopy(dict(raw.get("metadata") or {}))
            metadata.update({"name": entry.name, "section": entry.section})
            if entry.set_code is not None:
                metadata["set_code"] = entry.set_code
            if entry.collector_number is not None:
                metadata["collector_number"] = entry.collector_number
            raw.update({
                "entry_id": entry.entry_id,
                "front_name": front_name,
                "count": entry.quantity,
                "do_not_print": entry.do_not_print,
                "metadata": metadata,
            })
            for key in ("card_id", "oracle_id", "image_asset_id"):
                value = getattr(entry, key)
                if value is not None:
                    raw[key] = value
            card_entries.append(raw)
            for key in ('backside_name', 'backside_asset_id', 'backside_short_edge', 'oversized'):
                if key in entry.extras:
                    raw[key] = deepcopy(entry.extras[key])
        project["card_entries"] = card_entries
        project["cards"] = {item["front_name"]: item["count"] for item in card_entries}
        return project


class DeckHistory:
    """Snapshot history for model-level edits, independent of Qt widgets."""

    def __init__(self, document: DeckDocument, limit: int = 100):
        self.document = document
        self.limit = max(1, int(limit))
        self._undo: list[dict[str, Any]] = []
        self._redo: list[dict[str, Any]] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def execute(self, edit: Callable[[DeckDocument], None]) -> bool:
        before = self.document.to_dict()
        try:
            edit(self.document)
        except Exception:
            self._restore(before)
            raise
        if self.document.to_dict() == before:
            return False
        self._undo.append(before)
        self._undo = self._undo[-self.limit:]
        self._redo.clear()
        return True

    def _restore(self, value: Mapping[str, Any]) -> None:
        restored = DeckDocument.from_dict(value)
        self.document.deck = restored.deck
        self.document.print_settings = restored.print_settings
        self.document.editor_preferences = restored.editor_preferences
        self.document.schema_version = restored.schema_version
        self.document.extras = restored.extras

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.document.to_dict())
        self._restore(self._undo.pop())
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.document.to_dict())
        self._restore(self._redo.pop())
        return True


class DeckStore:
    """Atomic JSON persistence with bounded pre-save recovery snapshots."""

    def __init__(self, backup_limit: int = 5):
        self.backup_limit = max(1, int(backup_limit))

    def load(self, path: str | os.PathLike[str]) -> DeckDocument:
        with open(path, "r", encoding="utf-8") as handle:
            return DeckDocument.from_dict(json.load(handle))

    def save(self, path: str | os.PathLike[str], document: DeckDocument) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            backup_dir = destination.parent / ".recovery"
            backup_dir.mkdir(exist_ok=True)
            backup = backup_dir / f"{destination.stem}-{uuid.uuid4().hex}.json"
            backup.write_bytes(destination.read_bytes())
            backups = sorted(backup_dir.glob(f"{destination.stem}-*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
            for obsolete in backups[self.backup_limit:]:
                obsolete.unlink(missing_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{destination.stem}-", suffix=".tmp", dir=destination.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(document.to_dict(), handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
        return destination

    def recovery_paths(self, path: str | os.PathLike[str]) -> list[Path]:
        destination = Path(path)
        backup_dir = destination.parent / ".recovery"
        if not backup_dir.exists():
            return []
        return sorted(backup_dir.glob(f"{destination.stem}-*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
