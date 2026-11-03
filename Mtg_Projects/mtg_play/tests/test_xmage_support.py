import json
import sqlite3

import pytest

from mtg_play.xmage_support import (
    catalog_requests,
    compare,
    configured_catalog,
    deck_requests,
    write_reports,
)


def card(name="Nelly", code="MKC", number="4", implementation=True):
    return dict(
        name=name,
        set_code=code,
        collector_number=number,
        class_name="mage.cards.n.Nelly",
        class_available=implementation,
    )


@pytest.mark.parametrize(
    "card_request,catalog,expected",
    [
        (
            {"name": "Nelly", "set_code": "mkc", "collector_number": "4"},
            [card()],
            "available",
        ),
        ({"name": "Nelly"}, [card()], "available"),
        (
            {"name": "Nelly", "set_code": "MKC", "collector_number": "52"},
            [card()],
            "available",
        ),
        ({"name": "Feather"}, [card()], "missing_card"),
        ({"name": "Nelly"}, [card(implementation=False)], "missing_implementation"),
        (
            {"name": "Wrong card", "set_code": "MKC", "collector_number": "4"},
            [card()],
            "missing_card",
        ),
        (
            {"name": "Nelly", "set_code": "MKC", "collector_number": "4"},
            [card(implementation=False), card(number="52")],
            "available",
        ),
        ({"name": "Nelly", "skip_reason": "Display copy"}, [], "skipped"),
        ({"name": ""}, [card()], "invalid_metadata"),
        ({"name": "Front // Back"}, [card(name="Front")], "missing_card"),
    ],
)
def test_classification_keeps_name_printing_and_implementation_distinct(
    card_request, catalog, expected
):
    before = json.dumps(card_request, sort_keys=True)
    result = compare([card_request], catalog)[0]
    assert result["status"] == expected
    assert json.dumps(card_request, sort_keys=True) == before


def test_display_and_zero_quantity_are_reported_as_skipped():
    document = {
        "deck": {
            "name": "Blame Game",
            "entries": [
                {
                    "name": "Nelly",
                    "section": "commander",
                    "quantity": 1,
                    "set_code": "MKC",
                    "collector_number": "4",
                },
                {
                    "name": "Nelly",
                    "section": "display_commander",
                    "quantity": 1,
                    "set_code": "MKC",
                    "collector_number": "52",
                },
                {"name": "Unselected", "section": "mainboard", "quantity": 0},
            ],
        }
    }
    assert [
        row["status"] for row in compare(deck_requests(document, "deck.json"), [card()])
    ] == ["available", "skipped", "skipped"]


def test_reports_preserve_json_values_and_partition_csvs(tmp_path):
    requests = [
        {"name": "Nelly"},
        {"name": "Feather"},
        {"name": "Nelly", "set_code": "MKC", "collector_number": "52"},
        {"name": "=untrusted name"},
    ]
    counts = write_reports(
        tmp_path, compare(requests, [card()]), {"catalog_printings": 1}
    )
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert counts == {"available": 2, "missing_card": 2}
    assert report["results"][3]["name"] == "=untrusted name"
    assert "'=untrusted name" in (tmp_path / "missing.csv").read_text(
        encoding="utf-8-sig"
    )
    assert not (tmp_path / "printing_issues.csv").exists()


def test_local_core_catalog_is_read_only_and_unique_name_mode_is_explicit(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE cards_oracle (name TEXT)")
        db.executemany(
            "INSERT INTO cards_oracle VALUES (?)",
            [("Nelly",), ("Nelly",), ("Feather",)],
        )
    before = path.read_bytes()
    assert [row["name"] for row in catalog_requests(path)] == ["Feather", "Nelly"]
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match="does not exist"):
        catalog_requests(tmp_path / "missing.sqlite3")
    assert not (tmp_path / "missing.sqlite3").exists()


def test_configured_catalog_reads_existing_state_without_creating_default_state(
    tmp_path,
):
    assert configured_catalog(tmp_path) == tmp_path / "mtg_core/card_data.sqlite3"
    assert not (tmp_path / "mtg_core").exists()
    state = tmp_path / "mtg_core/installation.sqlite3"
    state.parent.mkdir()
    with sqlite3.connect(state) as db:
        db.execute("CREATE TABLE settings (key TEXT, value TEXT)")
        db.execute(
            "INSERT INTO settings VALUES (?,?)",
            ("catalog_path", json.dumps(str(tmp_path / "installed.sqlite3"))),
        )
    before = state.read_bytes()
    assert configured_catalog(tmp_path) == tmp_path / "installed.sqlite3"
    assert state.read_bytes() == before


def test_recorded_faces_resolve_without_guessing_and_names_ignore_case():
    engine = card(name="Front")
    engine["related_names"] = ["Back"]
    assert compare([{"name": "front // back"}], [engine])[0]["status"] == "available"
    assert (
        compare([{"name": "Front // Unrelated"}], [engine])[0]["status"]
        == "missing_card"
    )
    assert compare([{"name": "FRONT"}], [engine])[0]["status"] == "available"


def test_canonical_identity_lookup_is_read_only_and_token_is_not_missing_code(tmp_path):
    from mtg_play.rules_identity import canonical_cards, canonicalize_requests

    path = tmp_path / "core.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE cards_oracle (oracle_id TEXT, name TEXT, layout TEXT)")
        db.executemany(
            "INSERT INTO cards_oracle VALUES (?,?,?)",
            [("spell", "Jeska's Will", "normal"), ("token", "Treasure", "token")],
        )
    before = path.read_bytes()
    requests = [
        dict(name="Jeskas Will", oracle_id="spell"),
        dict(name="Treasure", oracle_id="token"),
    ]
    original = json.dumps(requests)
    normalized = canonicalize_requests(
        requests, canonical_cards(["spell", "token", "unknown"], path)
    )
    assert normalized[0]["source_name"] == "Jeskas Will"
    assert normalized[0]["name"] == "Jeska's Will"
    assert (
        compare(normalized, [card(name="Jeska's Will")])[1]["status"]
        == "token_dependency"
    )
    assert json.dumps(requests) == original
    assert path.read_bytes() == before
    assert canonical_cards(["unknown"], tmp_path / "missing.sqlite3") == {}
    assert not (tmp_path / "missing.sqlite3").exists()


def test_lossy_name_similarity_is_only_a_review_hint_not_rules_support():
    row = compare(
        [dict(name="Kh\u00e2rn the Betrayer")], [card(name="Kharn the Betrayer")]
    )[0]
    assert row["status"] == "identity_mismatch"
    assert row["engine_classes"] == []
    assert row["engine_name_candidates"] == ["Kharn the Betrayer"]
    assert (
        compare([dict(name="Unrelated card")], [card(name="Kharn the Betrayer")])[0][
            "status"
        ]
        == "missing_card"
    )
