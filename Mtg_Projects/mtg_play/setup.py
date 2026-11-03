"""Read saved native Core documents without converting or writing deck data."""

from dataclasses import dataclass, replace
import sqlite3
from pathlib import Path
from mtg_core.decks import DeckDocument, DeckStore
from mtg_core.project_catalog import project_catalog
from mtg_core.commander import commander_entries
from .readiness import DeckReadiness, local_readiness


@dataclass(frozen=True)
class SavedDeck:
    path: Path | None
    document: DeckDocument
    commanders: tuple[str, ...]
    colors: tuple[str, ...] | None = None
    cover: tuple[str | None, str | None] = (None, None)
    source_id: str | None = None
    owner_id: str | None = None
    source_label: str = "Saved on this computer"
    checks: tuple[DeckReadiness, ...] = ()
    commander_art: tuple[tuple[str, tuple[str | None, str | None]], ...] = ()

    @property
    def key(self):
        return self.source_id or "file:" + str(self.path)

    def readiness(self, format):
        return next((check for check in self.checks if check.format == format), None)


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
                for entry in commander_entries(document)
            )
            colors = None
            decks.append(
                SavedDeck(Path(row["path"]), document, commanders, colors, row["cover"])
            )
        except (OSError, ValueError, TypeError, AttributeError):
            errors.append(
                "A saved deck could not be read. Open it in Deck Editor to review it."
            )
    # Read only accepted local snapshots. No sign-in, refresh, or remote request.
    if (root / "library-connections.sqlite3").is_file():
        try:
            from mtg_core.library.client import LibraryConnections
            from mtg_core.library.following import FollowedDecks

            for record in FollowedDecks(LibraryConnections(root)).list():
                document = record["document"]
                commanders = tuple(
                    entry.name or "Unnamed commander"
                    for entry in commander_entries(document)
                )
                candidates = commander_entries(document) or [
                    entry
                    for entry in document.deck.entries
                    if entry.section == "mainboard"
                    and type(entry.quantity) is int
                    and entry.quantity > 0
                ]
                cover = (
                    (candidates[0].card_id, candidates[0].image_asset_id)
                    if candidates
                    else (None, None)
                )
                source = "followed:" + record["server_id"] + ":" + record["deck_id"]
                owner = "library:" + record["server_id"] + ":owner:" + record["owner"]
                decks.append(
                    SavedDeck(
                        None,
                        document,
                        commanders,
                        colors=tuple(
                            color for color in "WUBRG" if color in record["colors"]
                        ),
                        cover=cover,
                        source_id=source,
                        owner_id=owner,
                        source_label="Shared cache: "
                        + record["server_name"]
                        + " - "
                        + record["owner"],
                    )
                )
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
            errors.append(
                "Some cached shared decks could not be read. Review Browse Online; saved decks remain available."
            )
    if service is not None:
        decks = prepare_catalog(decks, service)
    return tuple(decks), tuple(errors)


def prepare_catalog(decks, service=None, *, cancel=None, report=None):
    prepared = []
    metadata_available = True
    for index, row in enumerate(decks):
        if cancel is not None and cancel.is_set():
            from mtg_core.downloads import DownloadCancelled

            raise DownloadCancelled()
        if report is not None:
            report(
                dict(
                    operation="Preparing match lobby",
                    stage="local_deck_checks",
                    current=index,
                    total=len(decks),
                )
            )
        records = {}
        try:
            if (
                metadata_available
                and service is not None
                and hasattr(service, "get_deck_legality_data")
            ):
                records = (
                    service.get_deck_legality_data(row.document.deck.entries) or {}
                )
        except (OSError, sqlite3.Error, ValueError):
            metadata_available = (
                False  # Avoid retrying a failing database for every deck.
            )
        entries = commander_entries(row.document)
        colors = row.colors
        active = [
            entry
            for entry in row.document.deck.entries
            if entry.section not in ("excluded", "considering")
            and type(entry.quantity) is int
            and entry.quantity > 0
        ]
        if active and all(
            isinstance(
                ((records.get(entry.card_id) or {}).get("payload") or {}).get(
                    "color_identity"
                ),
                (list, tuple),
            )
            for entry in active
        ):
            present = {
                color
                for entry in active
                for color in records[entry.card_id]["payload"]["color_identity"]
            }
            colors = tuple(color for color in "WUBRG" if color in present)
        checks = tuple(
            local_readiness(row.document, format, records)
            for format in ("freeform", "commander")
        )
        prepared.append(
            replace(
                row,
                colors=colors,
                checks=checks,
                commanders=tuple(
                    entry.name or "Unnamed commander" for entry in entries
                ),
                commander_art=tuple(
                    (
                        entry.name or "Unnamed commander",
                        (entry.card_id, entry.image_asset_id),
                    )
                    for entry in entries
                ),
            )
        )
    if report is not None:
        report(
            dict(
                operation="Preparing match lobby",
                stage="local_deck_checks",
                current=len(decks),
                total=len(decks),
            )
        )
    return tuple(prepared)
