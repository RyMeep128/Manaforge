"""Generate private launch fixtures from synthetic native DeckDocuments only."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mtg_core"))

from mtg_core.decks import Deck, DeckDocument, DeckEntry
from mtg_play.contracts import GameSetup, MatchSeat
from mtg_play.launch_manifest import export_launch_manifest
from mtg_play.launch_schema import launch_schema

DIRECTORY = Path(__file__).resolve().parents[1] / "protocol"


def native_deck(commander=False):
    entries = [
        DeckEntry(
            "main",
            "Fixture Front // Fixture Back",
            3,
            card_id="selected-print",
            oracle_id="fixture-oracle",
            set_code="SYN",
            collector_number="1",
            owned=2,
            image_asset_id="fixture-front",
            backside_asset_id="fixture-back",
            notes="DO_NOT_EXPORT",
        ),
        DeckEntry("maybe", "DO_NOT_EXPORT", section="considering"),
        DeckEntry("excluded", "DO_NOT_EXPORT", section="excluded"),
    ]
    if commander:
        entries += [
            DeckEntry(
                "commander",
                "Fixture Commander",
                section="commander",
                card_id="commander-print",
            ),
            DeckEntry(
                "partner",
                "Fixture Partner or Background",
                section="commander",
                card_id="partner-print",
            ),
            DeckEntry(
                "companion",
                "Fixture Companion",
                section="sideboard",
                card_id="companion-print",
            ),
        ]
    return DeckDocument(
        deck=Deck(
            deck_id="fixture-deck",
            name="Synthetic native deck",
            format="Commander" if commander else "Custom",
            entries=entries,
            commander_entry_ids=["commander", "partner"] if commander else [],
            extras={
                "companion_entry_id": "companion" if commander else None,
                "private": "DO_NOT_EXPORT",
            },
            description="DO_NOT_EXPORT",
            playtest_notes="DO_NOT_EXPORT",
        ),
        print_settings={"private_path": "DO_NOT_EXPORT"},
        editor_preferences={"private": "DO_NOT_EXPORT"},
    )


def artifacts():
    cases = []
    for count, commander in ((2, False), (2, True), (5, True)):
        seats = tuple(
            MatchSeat(
                f"seat-{i}",
                f"Fixture {i}",
                "engine_ai" if count == 2 and i == 1 else "local_human",
            )
            for i in range(count)
        )
        setup = GameSetup(seats, "commander" if commander else "freeform")
        with patch(
            "mtg_play.launch_manifest.uuid.uuid4", return_value=uuid.UUID(int=1)
        ):
            value = json.loads(
                export_launch_manifest(
                    setup,
                    {seat.seat_id: native_deck(commander) for seat in seats},
                    manaforge_version="fixture-alpha.1",
                    deck_owners={"seat-1": "fixture-lender"},
                )
            )
        cases.append(
            dict(
                name=f"launch-{count}-{'commander' if commander else 'freeform'}",
                record="LaunchManifest",
                payload=value,
            )
        )
    negative = []
    for name in (
        "wrong-version",
        "missing-deck",
        "unknown-field",
        "boolean-quantity",
        "unsupported-section",
        "negative-owned",
        "missing-printing-field",
        "unsupported-controller",
        "one-seat",
    ):
        value = deepcopy(cases[0]["payload"])
        entry = value["seats"][0]["document"]["deck"]["entries"][0]
        if name == "wrong-version":
            value["launch_manifest_version"] = 2
        elif name == "missing-deck":
            del value["seats"][0]["document"]
        elif name == "unknown-field":
            value["local_file_path"] = "synthetic"
        elif name == "boolean-quantity":
            entry["quantity"] = True
        elif name == "unsupported-section":
            entry["section"] = "custom"
        elif name == "negative-owned":
            entry["owned"] = -1
        elif name == "missing-printing-field":
            del entry["card_id"]
        elif name == "unsupported-controller":
            value["seats"][1]["controller"] = "unrecognized"
        elif name == "one-seat":
            value["seats"] = value["seats"][:1]
        negative.append(dict(name=name, record="LaunchManifest", payload=value))
    return {
        "launch-manifest-v1.schema.json": launch_schema(),
        "fixtures/launch-positive-v1.json": {
            "fixture_format": 1,
            "provenance": "Synthetic native DeckDocuments; no engine or user data",
            "cases": cases,
        },
        "fixtures/launch-negative-v1.json": {"fixture_format": 1, "cases": negative},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, value in artifacts().items():
        path = DIRECTORY / name
        expected = json.dumps(value, indent=2) + "\n"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != expected:
                parser.exit(1, f"Launch artifact drift: {name}\n")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")
    print(
        "Launch schema and fixtures match source."
        if args.check
        else "Generated launch schema and fixtures."
    )


if __name__ == "__main__":
    main()
