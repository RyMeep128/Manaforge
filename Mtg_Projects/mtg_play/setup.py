"""Read saved native Core documents without converting or writing deck data."""

from dataclasses import dataclass
from pathlib import Path
from mtg_core.decks import DeckDocument, DeckStore
from mtg_core.project_catalog import project_catalog


@dataclass(frozen=True)
class SavedDeck:
    path: Path
    document: DeckDocument
    commanders: tuple[str, ...]


def saved_decks(root):
    root = Path(root)
    rows, errors = project_catalog(root / "decks", root / "projects")
    decks = []
    for row in rows:
        # Print projects are not native DeckStore documents. Never silently
        # convert a project to a different deck as part of starting a game.
        if row["kind"] != "Deck":
            continue
        try:
            document = DeckStore().load(row["path"])
            commanders = tuple(
                entry.name or "Unnamed commander"
                for entry in document.deck.entries
                if entry.entry_id in document.deck.commander_entry_ids
                or entry.section == "commander"
            )
            decks.append(SavedDeck(Path(row["path"]), document, commanders))
        except (OSError, ValueError, TypeError, AttributeError):
            errors.append(
                "A saved deck could not be read. Open it in Deck Editor to review it."
            )
    return tuple(decks), tuple(errors)
