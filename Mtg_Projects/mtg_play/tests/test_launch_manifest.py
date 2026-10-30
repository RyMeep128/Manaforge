"""Private launch structure, native deck preservation and Java fixture boundary."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from generate_launch_fixtures import artifacts, native_deck
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_play.contracts import GameSetup, MatchSeat
from mtg_play import launch_manifest
from mtg_play.launch_manifest import LaunchManifestError, export_launch_manifest
from mtg_play.launch_schema import launch_schema

DIRECTORY = Path(__file__).resolve().parents[1] / "protocol"
SCHEMA = json.loads((DIRECTORY / "launch-manifest-v1.schema.json").read_text())
POSITIVE = json.loads((DIRECTORY / "fixtures/launch-positive-v1.json").read_text())
NEGATIVE = json.loads((DIRECTORY / "fixtures/launch-negative-v1.json").read_text())


def launch(document=None, *, setup=None, owners=None):
    setup = setup or GameSetup(
        (MatchSeat("one", "Human"), MatchSeat("two", "AI", "engine_ai"))
    )
    document = document or native_deck(setup.format == "commander")
    return export_launch_manifest(
        setup,
        {seat.seat_id: document for seat in setup.seats},
        manaforge_version="fixture-alpha.1",
        deck_owners=owners,
    )


def test_schema_and_fixture_generation_are_reproducible():
    Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA == launch_schema()
    for name, value in artifacts().items():
        assert json.loads((DIRECTORY / name).read_text()) == value


@pytest.mark.parametrize("case", POSITIVE["cases"], ids=lambda case: case["name"])
def test_positive_launch_corpus(case):
    Draft202012Validator(SCHEMA).validate(case["payload"])


@pytest.mark.parametrize("case", NEGATIVE["cases"], ids=lambda case: case["name"])
def test_negative_launch_corpus(case):
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(case["payload"])


def test_native_document_is_unchanged_and_private_metadata_is_omitted():
    document = native_deck()
    before = deepcopy(document.to_dict())
    payload = launch(document, owners={"two": "lender"})
    assert document.to_dict() == before
    assert b"DO_NOT_EXPORT" not in payload
    manifest = json.loads(payload)
    assert manifest["seats"][1]["deck_owner_id"] == "lender"
    assert manifest["seats"][1]["controller"] == "engine_ai"
    projected = manifest["seats"][0]["document"]
    restored = DeckDocument.from_dict(projected)
    entry = restored.deck.entries[0]
    assert (entry.card_id, entry.oracle_id, entry.quantity, entry.owned) == (
        "selected-print",
        "fixture-oracle",
        3,
        2,
    )
    assert (entry.image_asset_id, entry.backside_asset_id) == (
        "fixture-front",
        "fixture-back",
    )
    assert entry.name == "Fixture Front // Fixture Back"
    assert [entry.entry_id for entry in restored.deck.entries] == ["main"]


def test_companion_and_commander_native_fields_survive_without_rules_policy():
    document = native_deck(True)
    # Engine validation, not the exporter, decides whether this arrangement is legal.
    document.deck.entries[-1].quantity = 2
    setup = GameSetup((MatchSeat("one", "One"), MatchSeat("two", "Two")), "commander")
    projected = json.loads(launch(document, setup=setup))["seats"][0]["document"]
    restored = DeckDocument.from_dict(projected)
    assert restored.deck.commander_entry_ids == ["commander", "partner"]
    assert restored.deck.extras["companion_entry_id"] == "companion"
    assert restored.deck.entries[-1].quantity == 2
    assert restored.deck.entries[1].card_id == "commander-print"


def test_bytes_remain_immutable_after_source_edits():
    document = native_deck()
    payload = launch(document)
    document.deck.entries[0].quantity = 42
    assert isinstance(payload, bytes)
    assert (
        json.loads(payload)["seats"][0]["document"]["deck"]["entries"][0]["quantity"]
        == 3
    )


@pytest.mark.parametrize(
    "problem,code",
    [
        ("unknown-section", "UNSUPPORTED_SECTION"),
        ("duplicate-entry", "DUPLICATE_ENTRY_ID"),
        ("boolean-quantity", "INVALID_QUANTITY"),
        ("negative-quantity", "INVALID_QUANTITY"),
        ("boolean-owned", "INVALID_INTEGER_FIELD"),
        ("overflow-quantity", "INVALID_INTEGER_FIELD"),
        ("unknown-schema", "INCOMPATIBLE_DECK_SCHEMA"),
        ("missing-companion", "INVALID_COMPANION_REFERENCE"),
        ("missing-commander", "MISSING_COMMANDER_ENTRY"),
        ("duplicate-commander", "INVALID_COMMANDER_REFERENCES"),
    ],
)
def test_invalid_native_input_fails_with_safe_codes(problem, code):
    document = native_deck(True)
    if problem == "unknown-section":
        document.deck.entries[0].section = "companion"
    elif problem == "duplicate-entry":
        document.deck.entries.append(deepcopy(document.deck.entries[0]))
    elif problem == "boolean-quantity":
        document.deck.entries[0].quantity = True
    elif problem == "negative-quantity":
        document.deck.entries[0].quantity = -1
    elif problem == "boolean-owned":
        document.deck.entries[0].owned = True
    elif problem == "overflow-quantity":
        document.deck.entries[0].quantity = 2**63
    elif problem == "unknown-schema":
        document.schema_version = 2
    elif problem == "missing-companion":
        document.deck.extras["companion_entry_id"] = "missing"
    elif problem == "missing-commander":
        document.deck.commander_entry_ids = ["missing"]
    elif problem == "duplicate-commander":
        document.deck.commander_entry_ids = ["commander", "commander"]
    setup = GameSetup((MatchSeat("one", "One"), MatchSeat("two", "Two")), "commander")
    with pytest.raises(LaunchManifestError) as failure:
        launch(document, setup=setup)
    assert str(failure.value) == code
    assert failure.value.seat_id == "one"


def test_printing_is_never_quietly_replaced_or_resolved():
    document = native_deck()
    document.deck.entries[0].card_id = None
    document.deck.entries[0].name = "UNRESOLVED SYNTHETIC NAME"
    payload = json.loads(launch(document))
    entry = payload["seats"][0]["document"]["deck"]["entries"][0]
    assert entry["card_id"] is None and entry["name"] == "UNRESOLVED SYNTHETIC NAME"


def test_transport_size_limits_are_enforced(monkeypatch):
    monkeypatch.setattr(launch_manifest, "MAX_MANIFEST_BYTES", 1)
    with pytest.raises(LaunchManifestError, match="^LAUNCH_MANIFEST_TOO_LARGE$"):
        launch()
    monkeypatch.setattr(launch_manifest, "MAX_MANIFEST_BYTES", 1024 * 1024)
    monkeypatch.setattr(launch_manifest, "MAX_DECK_ENTRIES", 1)
    document = native_deck()
    document.deck.entries.append(DeckEntry("another", "Synthetic card"))
    with pytest.raises(LaunchManifestError, match="^LAUNCH_DECK_TOO_LARGE$"):
        launch(document)


def test_invalid_seat_and_owner_mapping_are_rejected():
    setup = GameSetup((MatchSeat("one", "One"), MatchSeat("one", "Duplicate")))
    with pytest.raises(LaunchManifestError, match="^INVALID_SEAT_IDENTITIES$"):
        launch(setup=setup)
    with pytest.raises(LaunchManifestError, match="^DECK_OWNER_SEAT_MISMATCH$"):
        launch(owners={"unassigned": "lender"})
    with pytest.raises(LaunchManifestError, match="^INCOMPATIBLE_GAME_PROTOCOL$"):
        launch(setup=replace(setup, protocol_version=True))
    with pytest.raises(LaunchManifestError, match="^DECK_SEAT_MISMATCH$"):
        export_launch_manifest(
            GameSetup((MatchSeat("one", "One"), MatchSeat("two", "Two"))),
            {"one": native_deck()},
            manaforge_version="fixture-alpha.1",
        )
