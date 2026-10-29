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
    colors: tuple[str, ...] | None = None
    cover: tuple[str | None, str | None] = (None, None)


def saved_decks(root, service=None):
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
            colors = None
            if service is not None and hasattr(service, "get_deck_legality_data"):
                entries = [
                    entry
                    for entry in document.deck.entries
                    if entry.section not in ("excluded", "considering")
                ]
                facts = service.get_deck_legality_data(entries)
                if entries and all(
                    entry.card_id in facts
                    and "color_identity" in facts[entry.card_id]["payload"]
                    for entry in entries
                ):
                    present = {
                        color
                        for entry in entries
                        for color in facts[entry.card_id]["payload"]["color_identity"]
                    }
                    colors = tuple(color for color in "WUBRG" if color in present)
            decks.append(
                SavedDeck(Path(row["path"]), document, commanders, colors, row["cover"])
            )
        except (OSError, ValueError, TypeError, AttributeError):
            errors.append(
                "A saved deck could not be read. Open it in Deck Editor to review it."
            )
    return tuple(decks), tuple(errors)
