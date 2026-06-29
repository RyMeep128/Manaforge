from __future__ import annotations

import csv
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mtg_editor.catalog import CatalogCardCandidate, resolve_deck_entry
from mtg_editor.card_ops import add_or_increment_card
from mtg_editor.models import DeckCard, DeckProject


LINE_PATTERN = re.compile(
    r"^(?:(?P<prefix>SB|MB|CMDR|COMMANDER):\s*)?"
    r"(?P<count>\d+)\s+"
    r"(?P<name>.+?)"
    r"(?:\s+\((?P<set_code>[A-Za-z0-9]+)\)(?:\s+(?P<collector_number>\S+))?)?$",
    re.IGNORECASE,
)

SECTION_MAP = {
    "deck": ("main", "Deck"),
    "main": ("main", "Main"),
    "maindeck": ("main", "Main Deck"),
    "mainboard": ("main", "Mainboard"),
    "sideboard": ("sideboard", "Sideboard"),
    "maybeboard": ("maybeboard", "Maybeboard"),
    "commander": ("commander", "Commander"),
    "companion": ("companion", "Companion"),
    "companions": ("companion", "Companions"),
    "excluded": ("excluded", "Excluded"),
}

PREFIX_MAP = {
    "MB": ("main", "Mainboard"),
    "SB": ("sideboard", "Sideboard"),
    "CMDR": ("commander", "Commander"),
    "COMMANDER": ("commander", "Commander"),
}

SECTION_EXPORT_ORDER = ["commander", "main", "sideboard", "maybeboard", "companion", "excluded"]
SECTION_EXPORT_LABELS = {
    "commander": "Commander",
    "main": "Mainboard",
    "sideboard": "Sideboard",
    "maybeboard": "Maybeboard",
    "companion": "Companion",
    "excluded": "Excluded",
}


@dataclass(frozen=True)
class DecklistEntry:
    count: int
    name: str
    set_code: str | None = None
    collector_number: str | None = None
    section: str = "main"
    import_section: str | None = None


@dataclass
class DecklistImportResult:
    project: DeckProject
    entries: list[DecklistEntry]
    added_card_ids: list[str]
    updated_card_ids: list[str]
    unresolved_entries: list[DecklistEntry]
    unmatched_lines: list[str]


def parse_decklist(deck_text: str) -> tuple[list[DecklistEntry], list[str]]:
    if _looks_like_csv(deck_text):
        return _parse_csv_decklist(deck_text)
    return _parse_text_decklist(deck_text)


def import_decklist(
    project: DeckProject,
    text: str,
    *,
    card_service: Any | None = None,
    allow_remote: bool = False,
) -> DecklistImportResult:
    entries, unmatched_lines = parse_decklist(text)
    added_card_ids: list[str] = []
    updated_card_ids: list[str] = []
    unresolved_entries: list[DecklistEntry] = []

    for entry in entries:
        candidate = _resolve_entry(entry, card_service=card_service, allow_remote=allow_remote)
        result = add_or_increment_card(
            project,
            name=entry.name,
            quantity=entry.count,
            section=entry.section,
            import_section=entry.import_section,
            set_code=entry.set_code,
            collector_number=entry.collector_number,
            candidate=candidate,
        )
        if result.created:
            added_card_ids.append(result.card_id)
        else:
            updated_card_ids.append(result.card_id)
        if candidate is None:
            unresolved_entries.append(entry)

    return DecklistImportResult(
        project=project,
        entries=entries,
        added_card_ids=added_card_ids,
        updated_card_ids=updated_card_ids,
        unresolved_entries=unresolved_entries,
        unmatched_lines=unmatched_lines,
    )


def export_decklist(
    project: DeckProject,
    *,
    include_set_info: bool = False,
    include_sections: bool = True,
    include_excluded: bool = False,
) -> str:
    cards = [
        card
        for card in _cards_in_import_order(project)
        if card.quantity > 0 and (include_excluded or card.section != "excluded")
    ]
    if not include_sections:
        return "\n".join(_format_card_line(card, include_set_info=include_set_info) for card in cards)

    lines: list[str] = []
    for section, section_cards in _cards_grouped_by_section(cards).items():
        if lines:
            lines.append("")
        lines.append(f"{SECTION_EXPORT_LABELS.get(section, section.title())}:")
        lines.extend(
            _format_card_line(card, include_set_info=include_set_info)
            for card in section_cards
        )
    return "\n".join(lines)


def read_decklist_file(path: str | Path) -> str:
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def import_decklist_file(
    project: DeckProject,
    path: str | Path,
    *,
    card_service: Any | None = None,
    allow_remote: bool = False,
) -> DecklistImportResult:
    return import_decklist(
        project,
        read_decklist_file(path),
        card_service=card_service,
        allow_remote=allow_remote,
    )


def write_decklist_file(
    path: str | Path,
    project: DeckProject,
    *,
    include_set_info: bool = False,
    include_sections: bool = True,
    include_excluded: bool = False,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        export_decklist(
            project,
            include_set_info=include_set_info,
            include_sections=include_sections,
            include_excluded=include_excluded,
        ),
        encoding="utf-8",
        newline="\n",
    )


def _parse_text_decklist(deck_text: str) -> tuple[list[DecklistEntry], list[str]]:
    aggregated: OrderedDict[tuple[str, str | None, str | None, str], DecklistEntry] = OrderedDict()
    unmatched_lines: list[str] = []
    current_section = "main"
    current_import_section = "Mainboard"

    for raw_line in str(deck_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        section = _section_from_label(line)
        if section is not None:
            current_section, current_import_section = section
            continue

        match = LINE_PATTERN.match(line)
        if match is None:
            unmatched_lines.append(line)
            continue

        prefix = match.group("prefix")
        entry_section, import_section = (
            PREFIX_MAP[prefix.upper()]
            if prefix
            else (current_section, current_import_section)
        )
        entry = DecklistEntry(
            count=int(match.group("count")),
            name=_normalize_card_name(match.group("name")),
            set_code=_normalize_set_code(match.group("set_code")),
            collector_number=_clean_optional(match.group("collector_number")),
            section=entry_section,
            import_section=import_section,
        )
        _aggregate_entry(aggregated, entry)

    return list(aggregated.values()), unmatched_lines


def _parse_csv_decklist(deck_text: str) -> tuple[list[DecklistEntry], list[str]]:
    aggregated: OrderedDict[tuple[str, str | None, str | None, str], DecklistEntry] = OrderedDict()
    unmatched_lines: list[str] = []
    reader = csv.DictReader(str(deck_text or "").splitlines())
    fieldnames = {_normalize_csv_field_name(field_name) for field_name in (reader.fieldnames or [])}
    if not {"count", "name"}.issubset(fieldnames):
        return _parse_text_decklist(deck_text)

    for row_number, row in enumerate(reader, start=2):
        normalized_row = {
            _normalize_csv_field_name(key): (value or "").strip()
            for key, value in row.items()
            if key is not None
        }
        count_raw = normalized_row.get("count", "")
        name_raw = normalized_row.get("name", "")
        if not count_raw.isdigit() or not name_raw:
            unmatched_lines.append(f"CSV row {row_number}")
            continue

        section = _section_from_label(normalized_row.get("section", "")) or ("main", "Mainboard")
        entry = DecklistEntry(
            count=int(count_raw),
            name=_normalize_card_name(name_raw),
            set_code=_normalize_set_code(normalized_row.get("set_code")),
            collector_number=_clean_optional(normalized_row.get("collector_number")),
            section=section[0],
            import_section=section[1],
        )
        _aggregate_entry(aggregated, entry)

    return list(aggregated.values()), unmatched_lines


def _aggregate_entry(
    aggregated: OrderedDict[tuple[str, str | None, str | None, str], DecklistEntry],
    entry: DecklistEntry,
) -> None:
    key = _entry_key(entry)
    if key not in aggregated:
        aggregated[key] = entry
        return

    previous = aggregated[key]
    aggregated[key] = DecklistEntry(
        count=previous.count + entry.count,
        name=previous.name,
        set_code=previous.set_code,
        collector_number=previous.collector_number,
        section=previous.section,
        import_section=previous.import_section,
    )


def _resolve_entry(
    entry: DecklistEntry,
    *,
    card_service: Any | None,
    allow_remote: bool,
) -> CatalogCardCandidate | None:
    try:
        return resolve_deck_entry(entry, card_service=card_service, allow_remote=allow_remote)
    except Exception as exc:
        if exc.__class__.__name__ == "RemoteLookupUnavailable":
            return None
        raise

def _cards_in_import_order(project: DeckProject) -> list[DeckCard]:
    original_index = {card.card_id: index for index, card in enumerate(project.cards)}
    return sorted(
        project.cards,
        key=lambda card: (
            card.sort_index if card.sort_index is not None else original_index[card.card_id],
            original_index[card.card_id],
        ),
    )


def _cards_grouped_by_section(cards: list[DeckCard]) -> OrderedDict[str, list[DeckCard]]:
    sections = {card.section for card in cards}
    ordered_sections = [
        section for section in SECTION_EXPORT_ORDER if section in sections
    ] + sorted(sections.difference(SECTION_EXPORT_ORDER))
    grouped: OrderedDict[str, list[DeckCard]] = OrderedDict((section, []) for section in ordered_sections)
    for card in cards:
        grouped[card.section].append(card)
    return grouped


def _format_card_line(card: DeckCard, *, include_set_info: bool) -> str:
    line = f"{card.quantity} {card.name}"
    if include_set_info and card.set_code:
        line += f" ({card.set_code.upper()})"
        if card.collector_number:
            line += f" {card.collector_number}"
    return line


def _entry_key(entry: DecklistEntry) -> tuple[str, str | None, str | None, str]:
    return (
        _normalize_card_name(entry.name).casefold(),
        _normalize_set_code(entry.set_code),
        _clean_optional(entry.collector_number),
        _normalize_section(entry.section),
    )


def _section_from_label(value: str) -> tuple[str, str] | None:
    key = re.sub(r"[\s_-]+", "", str(value or "").strip().rstrip(":").lower())
    return SECTION_MAP.get(key)


def _looks_like_csv(deck_text: str) -> bool:
    first_line = next((line for line in str(deck_text or "").splitlines() if line.strip()), "")
    if "," not in first_line:
        return False
    headers = {_normalize_csv_field_name(part) for part in first_line.split(",")}
    return {"count", "name"}.issubset(headers)


def _normalize_csv_field_name(value: str) -> str:
    return re.sub(r"[\s-]+", "_", str(value or "").strip().lower())


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
