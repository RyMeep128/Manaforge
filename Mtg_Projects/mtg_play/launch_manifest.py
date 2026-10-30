"""One-time private launch projection; no engine startup or deck/file writes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
import uuid

from mtg_core.decks import DECK_SCHEMA_VERSION, Deck, DeckDocument, DeckEntry

from .contracts import ADAPTER_VERSION, GAME_PROTOCOL_VERSION, GameSetup, MatchSeat
from .decks import deck_document_issues

LAUNCH_MANIFEST_VERSION = 1
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_DECK_ENTRIES = 4096  # Transport allocation limit, not a Magic deck-size rule.
MAX_INTEGER = 2**63 - 1
ENTRY_FIELDS = (
    "entry_id",
    "name",
    "quantity",
    "section",
    "card_id",
    "oracle_id",
    "set_code",
    "collector_number",
    "owned",
    "image_asset_id",
    "backside_asset_id",
)


class LaunchManifestError(ValueError):
    """Stable codes only in exception text; never include deck/card content."""

    def __init__(self, code, *, seat_id=None, entry_id=None):
        self.code, self.seat_id, self.entry_id = code, seat_id, entry_id
        super().__init__(code)


def _text(value, *, optional=False):
    if optional and value is None:
        return
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise LaunchManifestError("INVALID_TEXT_FIELD")


def _project_deck(document, *, commander):
    if not isinstance(document, DeckDocument):
        raise LaunchManifestError("NATIVE_DECK_REQUIRED")
    if (
        type(document.schema_version) is not int
        or document.schema_version != DECK_SCHEMA_VERSION
    ):
        raise LaunchManifestError("INCOMPATIBLE_DECK_SCHEMA")
    deck = document.deck
    if not isinstance(deck, Deck) or not isinstance(deck.entries, (list, tuple)):
        raise LaunchManifestError("NATIVE_DECK_REQUIRED")
    for value in (deck.deck_id, deck.name, deck.format):
        _text(value)
    if not isinstance(deck.commander_entry_ids, (list, tuple)) or any(
        not isinstance(value, str) or not value for value in deck.commander_entry_ids
    ):
        raise LaunchManifestError("INVALID_COMMANDER_REFERENCES")
    if not isinstance(deck.extras, Mapping):
        raise LaunchManifestError("INVALID_DECK_METADATA")
    for entry in deck.entries:
        if not isinstance(entry, DeckEntry):
            raise LaunchManifestError("NATIVE_DECK_REQUIRED")
        _text(entry.entry_id)
    # Reuse the executable baseline's structural checks. Never resolve rules,
    # names, printings or companion restrictions as exporter policy.
    issues = deck_document_issues(document, commander=commander)
    if issues:
        raise LaunchManifestError(issues[0].code, entry_id=issues[0].entry_id)
    entries = []
    for entry in deck.entries:
        if (
            entry.section in ("considering", "excluded", "display_commander")
            or entry.quantity == 0
        ):
            continue
        _text(entry.entry_id)
        if not isinstance(entry.name, str) or len(entry.name) > 4096:
            raise LaunchManifestError("INVALID_TEXT_FIELD", entry_id=entry.entry_id)
        for field in (
            "card_id",
            "oracle_id",
            "set_code",
            "collector_number",
            "image_asset_id",
            "backside_asset_id",
        ):
            _text(getattr(entry, field), optional=True)
        for field in ("quantity", "owned"):
            value = getattr(entry, field)
            if type(value) is not int or not 0 <= value <= MAX_INTEGER:
                raise LaunchManifestError(
                    "INVALID_INTEGER_FIELD", entry_id=entry.entry_id
                )
        entries.append({field: getattr(entry, field) for field in ENTRY_FIELDS})
        if len(entries) > MAX_DECK_ENTRIES:
            raise LaunchManifestError("LAUNCH_DECK_TOO_LARGE")
    by_id = {entry["entry_id"]: entry for entry in entries}
    commanders = list(deck.commander_entry_ids)
    if any(not isinstance(value, str) for value in commanders) or len(
        set(commanders)
    ) != len(commanders):
        raise LaunchManifestError("INVALID_COMMANDER_REFERENCES")
    if any(value not in by_id for value in commanders):
        raise LaunchManifestError("INVALID_COMMANDER_REFERENCES")
    companion = deck.extras.get("companion_entry_id")
    _text(companion, optional=True)
    if companion is not None and (
        companion not in by_id or by_id[companion]["section"] != "sideboard"
    ):
        raise LaunchManifestError("INVALID_COMPANION_REFERENCE")
    # Native field names and native document schema; omitted editor/print fields
    # take their ordinary defaults if inspected with DeckDocument.from_dict.
    return {
        "schema_version": document.schema_version,
        "deck": {
            "deck_id": deck.deck_id,
            "name": deck.name,
            "format": deck.format,
            "entries": entries,
            "commander_entry_ids": commanders,
            "companion_entry_id": companion,
        },
    }


def export_launch_manifest(
    setup: GameSetup, documents, *, manaforge_version: str, deck_owners=None
) -> bytes:
    """Return immutable UTF-8 bytes for the trusted gateway owner only.

    documents maps seat IDs to existing DeckDocuments. Owners are optional deck
    provenance, never seat authorization or a required online account.
    """
    if (
        not isinstance(setup, GameSetup)
        or not isinstance(documents, Mapping)
        or (deck_owners is not None and not isinstance(deck_owners, Mapping))
    ):
        raise LaunchManifestError("INVALID_LAUNCH_INPUT")
    if not isinstance(setup.seats, (list, tuple)) or any(
        not isinstance(seat, MatchSeat) for seat in setup.seats
    ):
        raise LaunchManifestError("INVALID_LAUNCH_INPUT")
    if (
        type(setup.protocol_version) is not int
        or setup.protocol_version != GAME_PROTOCOL_VERSION
    ):
        raise LaunchManifestError("INCOMPATIBLE_GAME_PROTOCOL")
    if setup.format not in ("freeform", "commander"):
        raise LaunchManifestError("UNSUPPORTED_GAME_SETUP")
    _text(manaforge_version)
    seat_ids = []
    for seat in setup.seats:
        _text(seat.seat_id)
        _text(seat.name)
        if seat.controller not in ("local_human", "engine_ai"):
            raise LaunchManifestError("UNSUPPORTED_CONTROLLER")
        seat_ids.append(seat.seat_id)
    if len(seat_ids) < 2 or len(set(seat_ids)) != len(seat_ids):
        raise LaunchManifestError("INVALID_SEAT_IDENTITIES")
    if set(documents) != set(seat_ids):
        raise LaunchManifestError("DECK_SEAT_MISMATCH")
    owners = {} if deck_owners is None else dict(deck_owners)
    if set(owners) - set(seat_ids):
        raise LaunchManifestError("DECK_OWNER_SEAT_MISMATCH")
    seats = []
    for seat in setup.seats:
        owner = owners.get(seat.seat_id)
        _text(owner, optional=True)
        try:
            document = _project_deck(
                documents[seat.seat_id], commander=setup.format == "commander"
            )
        except LaunchManifestError as error:
            raise LaunchManifestError(
                error.code, seat_id=seat.seat_id, entry_id=error.entry_id
            ) from None
        seats.append(
            {
                "seat_id": seat.seat_id,
                "name": seat.name,
                "controller": seat.controller,
                "deck_owner_id": owner,
                "document": document,
            }
        )
    raw_pin = Path(__file__).with_name("artifacts.json").read_bytes()
    engine = json.loads(raw_pin)
    result = {
        "launch_manifest_version": LAUNCH_MANIFEST_VERSION,
        "protocol_version": GAME_PROTOCOL_VERSION,
        "manifest_id": uuid.uuid4().hex,
        "manaforge_version": manaforge_version,
        "engine": {
            "engine_version": engine["engine"],
            "adapter_version": ADAPTER_VERSION,
            "artifact_manifest_sha256": hashlib.sha256(raw_pin).hexdigest(),
        },
        "format": setup.format,
        "seats": seats,
    }
    try:
        payload = json.dumps(
            result, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise LaunchManifestError("INVALID_MANIFEST_ENCODING") from None
    if len(payload) > MAX_MANIFEST_BYTES:
        raise LaunchManifestError("LAUNCH_MANIFEST_TOO_LARGE")
    return payload
