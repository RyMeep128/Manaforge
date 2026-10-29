"""Translate Core deck documents without changing them or persisting another deck model."""

from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable
from .contracts import CardIdentity

if TYPE_CHECKING:
    from mtg_core.decks import DeckDocument


@dataclass(frozen=True)
class DeckIssue:
    entry_id: str
    code: str

    @property
    def category(self):
        from .diagnostics import diagnostic_category
        return diagnostic_category(self.code)


class DeckTranslationError(ValueError):
    def __init__(self, issues: list[DeckIssue]):
        self.issues = tuple(issues)
        super().__init__(
            "Deck translation failed: "
            + ", ".join(f"{i.entry_id}: {i.code}" for i in issues)
        )


@dataclass(frozen=True)
class PreparedDeck:
    cards: tuple[dict, ...]
    sideboard: tuple[dict, ...]
    bindings: dict[tuple[str, str], CardIdentity]


def prepare_deck(
    document: DeckDocument,
    resolve: Callable,
    oracle_lookup: Callable | None = None,
    *,
    commander: bool = False,
) -> PreparedDeck:
    issues = []
    queries = []
    entries = []
    seen = set()
    commander_ids = set(document.deck.commander_entry_ids)
    for missing in commander_ids - {entry.entry_id for entry in document.deck.entries}:
        issues.append(DeckIssue(missing, "MISSING_COMMANDER_ENTRY"))
    for entry in document.deck.entries:
        if entry.section in ("considering", "excluded"):
            continue
        if type(entry.quantity) is not int or entry.quantity < 0:
            issues.append(DeckIssue(entry.entry_id, "INVALID_QUANTITY"))
            continue
        if entry.quantity == 0:
            continue
        if entry.entry_id in seen:
            issues.append(DeckIssue(entry.entry_id, "DUPLICATE_ENTRY_ID"))
            continue
        seen.add(entry.entry_id)
        if type(entry.quantity) is not int or entry.quantity < 0:
            issues.append(DeckIssue(entry.entry_id, "INVALID_QUANTITY"))
            continue
        if entry.section not in ("mainboard", "sideboard", "commander"):
            issues.append(DeckIssue(entry.entry_id, "UNSUPPORTED_SECTION"))
            continue
        if (
            entry.section == "commander" or entry.entry_id in commander_ids
        ) and not commander:
            issues.append(DeckIssue(entry.entry_id, "COMMANDER_FORMAT_REQUIRED"))
            continue
        name = entry.name
        if entry.oracle_id:
            canonical = (
                oracle_lookup(entry.oracle_id) if oracle_lookup is not None else None
            )
            if canonical is None:
                issues.append(DeckIssue(entry.entry_id, "ORACLE_ID_NOT_RESOLVED"))
                continue
            name = canonical.name
        if not name:
            issues.append(DeckIssue(entry.entry_id, "MISSING_CARD_NAME"))
            continue
        entries.append(entry)
        queries.append(
            dict(
                key=entry.entry_id,
                name=name,
                set=(entry.set_code or "").upper(),
                number=entry.collector_number or "",
            )
        )
    resolved = {row["key"]: row for row in resolve(queries)} if queries else {}
    cards, sideboard, bindings = [], [], {}
    for entry in entries:
        row = resolved.get(entry.entry_id)
        if row is None or row.get("error"):
            issues.append(
                DeckIssue(
                    entry.entry_id,
                    row.get("error", "CARD_NOT_SUPPORTED")
                    if row
                    else "MISSING_RESOLUTION",
                )
            )
            continue
        if ((entry.set_code and row["set"].upper() != entry.set_code.upper()) or
                (entry.collector_number and row["number"] != entry.collector_number)):
            issues.append(DeckIssue(entry.entry_id, "PRINTING_NOT_RESOLVED"))
            continue
        identity = CardIdentity(entry.oracle_id, entry.card_id, entry.entry_id)
        key = (row["set"], row["number"])
        previous = bindings.get(key)
        if previous is not None and (previous.oracle_id, previous.printing_id) != (
            identity.oracle_id,
            identity.printing_id,
        ):
            issues.append(DeckIssue(entry.entry_id, "AMBIGUOUS_INSTANCE_PRINTING"))
            continue
        bindings[key] = (
            CardIdentity(identity.oracle_id, identity.printing_id, None)
            if previous is not None and previous.deck_entry_id != identity.deck_entry_id
            else identity
        )
        destination = (
            sideboard
            if entry.section in ("sideboard", "commander")
            or entry.entry_id in commander_ids
            else cards
        )
        destination.append(
            dict(
                name=row["name"],
                set=row["set"],
                number=row["number"],
                quantity=entry.quantity,
            )
        )
    if issues:
        raise DeckTranslationError(issues)
    if not cards:
        raise DeckTranslationError([DeckIssue("", "EMPTY_MAINBOARD")])
    return PreparedDeck(tuple(cards), tuple(sideboard), bindings)
