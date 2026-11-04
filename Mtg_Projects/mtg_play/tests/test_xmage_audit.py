import json
import sqlite3

from mtg_play import xmage_audit as audit
from mtg_play import xmage_support as support
from test_xmage_backlog import backlog


def fixture_card(**changes):
    card = dict(
        type_line="Creature",
        layout="normal",
        games=["paper"],
        set_type="funny",
        legalities={"commander": "legal"},
    )
    card.update(changes)
    return card


def test_mixed_unfinity_and_nonstandard_classification():
    assert backlog.category(fixture_card()) == "paper_rules"
    assert (
        backlog.category(
            fixture_card(security_stamp="acorn", legalities={"commander": "not_legal"})
        )
        == "novelty"
    )
    assert backlog.category(fixture_card(border_color="silver")) == "novelty"
    assert (
        backlog.category(
            fixture_card(
                promo_types=["playtest"], legalities={"commander": "not_legal"}
            )
        )
        == "novelty"
    )
    assert backlog.category(fixture_card(layout="scheme")) == "nonstandard_rules"
    assert (
        backlog.category(fixture_card(layout="art_series")) == "non_game_or_unresolved"
    )
    assert (
        backlog.category(fixture_card(type_line="Emblem", layout="emblem"))
        == "token_dependency"
    )


def test_oracle_reprints_and_set_grouping(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE cards_oracle (oracle_id, name, layout)")
        db.execute(
            "CREATE TABLE prints (oracle_id,name,set_code,set_name,payload_json,card_id)"
        )
        db.execute("INSERT INTO cards_oracle VALUES ('id','Card','normal')")
        for i, code in enumerate(["unf", "unf", "abc"]):
            card = fixture_card(border_color="silver") if i == 0 else fixture_card()
            db.execute(
                "INSERT INTO prints VALUES (?,?,?,?,?,?)",
                ("id", "Card", code, code, json.dumps(card), str(i)),
            )
    cards = audit.load_cards(path, backlog.category)
    assert len(cards) == 1
    assert cards[0]["category"] == "paper_rules"
    report = audit.assemble(cards, [], {}, [])
    assert report["counts"]["missing_commander_legal"] == 1
    assert [(s["set_code"], s["total"]) for s in report["sets"]] == [
        ("abc", 1),
        ("unf", 1),
    ]
    assert report["cards"][0]["behavior_verified"] is False
    report["provenance"] = {"generated_at": "fixed"}
    report["warnings"] = []
    audit.write(tmp_path / "one", report)
    audit.write(tmp_path / "two", report)
    assert {p.name: p.read_bytes() for p in (tmp_path / "one").iterdir()} == {
        p.name: p.read_bytes() for p in (tmp_path / "two").iterdir()
    }


def test_identity_relationships_and_missing_classes():
    engine = [
        dict(
            name="Front",
            related_names=["Back"],
            class_name="FrontClass",
            class_available=True,
        ),
        dict(name="Fire // Ice", class_name="SplitClass", class_available=True),
        dict(name="Absent class", class_name="Missing", class_available=False),
    ]
    rows = support.compare(
        [
            dict(name=n)
            for n in ["Front // Back", "Fire // Ice", "Absent class", "Unknown // Back"]
        ],
        engine,
    )
    assert [r["status"] for r in rows] == [
        "available",
        "available",
        "missing_implementation",
        "missing_card",
    ]
    assert not rows[-1]["engine_classes"]


def test_commander_filter_and_upstream_priority():
    cards = [
        dict(
            oracle_id=n,
            name=n,
            layout="normal",
            sets={"unf": "Unfinity"},
            category="paper_rules",
            commander_legality=legality,
            keywords=["Flying"],
        )
        for n, legality in [
            ("Legal", "legal"),
            ("Banned", "banned"),
            ("Unknown", "unknown"),
        ]
    ]
    report = audit.assemble(cards, [], {"legal": [{"class_name": "Legal"}]}, [])
    assert report["counts"]["missing_commander_legal"] == 1
    assert [r["priority"] for r in report["cards"]] == [2, 4, 4]
    assert [r["upstream_implemented"] for r in report["cards"]] == [True, False, False]


def test_saved_deck_compatibility_and_immutability(tmp_path):
    decks = tmp_path / "decks"
    decks.mkdir()
    path = decks / "saved.manaforge.json"
    path.write_text(
        json.dumps(
            {
                "deck": {
                    "name": "Saved",
                    "format": "Commander",
                    "entries": [
                        {"name": "Known", "quantity": 3},
                        {"name": "Unknown", "quantity": 1},
                        {"name": "Ignored", "section": "display_commander"},
                    ],
                }
            }
        )
    )
    before = path.read_bytes()
    catalog = tmp_path / "catalog.sqlite3"
    with sqlite3.connect(catalog) as db:
        db.execute("CREATE TABLE cards_oracle (oracle_id,name,layout)")
    engine = [dict(name="Known", class_name="Known", class_available=True)]
    results, warnings, hashes = audit.deck_inventory(decks, catalog, engine)
    assert results[0]["supported"] == 1
    assert results[0]["unsupported"] == 1
    assert [r["name"] for r in results[0]["missing"]] == ["Unknown"]
    assert results[0]["rules_availability_compatible"] is False
    assert path.read_bytes() == before
    assert hashes[0]["sha256"] == support.sha256(path)
