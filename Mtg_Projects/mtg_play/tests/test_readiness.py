"""Local deck readiness uses Core checks; execution belongs to CI."""

from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mtg_core"))
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_play.decks import deck_document_issues, prepare_deck, DeckTranslationError
from mtg_play.readiness import local_readiness
from mtg_play.setup import SavedDeck, prepare_catalog


def commander_fixture():
    document = DeckDocument()
    document.deck.entries = [
        DeckEntry(
            "leader",
            "Leader",
            1,
            section="commander",
            card_id="leader-print",
            image_asset_id="selected-art",
        ),
        DeckEntry("land", "Forest", 99, card_id="forest-print"),
    ]
    document.deck.commander_entry_ids = ["leader"]
    records = {
        "leader-print": dict(
            payload=dict(
                name="Leader",
                type_line="Legendary Creature",
                oracle_text="",
                color_identity=["G"],
                legalities=dict(commander="legal"),
            ),
            cached_at=time.time() - 1,
        ),
        "forest-print": dict(
            payload=dict(
                name="Forest",
                type_line="Basic Land - Forest",
                oracle_text="",
                color_identity=["G"],
                legalities=dict(commander="legal"),
            ),
            cached_at=time.time() - 1,
        ),
    }
    return document, records


def test_commander_local_checks_preserve_deck_and_do_not_claim_engine_compatibility():
    document, records = commander_fixture()
    document.print_settings["preserve"] = True
    original = deepcopy(document.to_dict())
    check = local_readiness(document, "commander", records)
    assert check.state == "available" and check.can_start
    assert "Engine validation happens at start" in check.summary
    assert document.to_dict() == original
    assert local_readiness(document, "freeform", records).state == "blocked"


def test_missing_or_stale_metadata_is_review_not_a_legality_guarantee():
    document, records = commander_fixture()
    missing = local_readiness(document, "commander")
    assert missing.state == "review" and missing.can_start
    assert "undated" in missing.codes
    records["forest-print"]["cached_at"] = time.time() - 31 * 86400
    stale = local_readiness(document, "commander", records)
    assert stale.state == "review" and "stale" in stale.codes


def test_known_commander_problem_blocks_without_exposing_private_card_details():
    document, records = commander_fixture()
    records["forest-print"]["payload"].update(
        name="PRIVATE_CARD_NAME", legalities=dict(commander="banned")
    )
    check = local_readiness(document, "commander", records)
    assert check.state == "blocked" and not check.can_start
    assert "legality" in check.codes
    assert "PRIVATE_CARD_NAME" not in json.dumps(asdict(check))
    document.deck.entries[1].quantity = 98
    assert "size" in local_readiness(document, "commander", records).codes


@pytest.mark.parametrize("quantity", [True, -1, "60"])
def test_invalid_quantities_are_blocked_by_shared_adapter_checks(quantity):
    document = DeckDocument()
    document.deck.entries = [DeckEntry("entry", "Forest", quantity, card_id="selected")]
    check = local_readiness(document, "freeform")
    assert not check.can_start and "INVALID_QUANTITY" in check.codes
    row = prepare_catalog((SavedDeck(Path("deck"), document, ()),))[0]
    assert not row.readiness("freeform").can_start


def test_freeform_does_not_apply_unrelated_constructed_size_rules():
    document = DeckDocument()
    assert not local_readiness(document, "freeform").can_start
    document.deck.entries = [DeckEntry("entry", "Forest", 1, card_id="selected")]
    assert local_readiness(document, "freeform").can_start
    document.deck.entries.append(
        DeckEntry("duplicate", "Forest", 5, card_id="selected")
    )
    assert local_readiness(document, "freeform").can_start


def test_structure_check_does_not_fabricate_oracle_or_printing_resolution():
    document = DeckDocument()
    document.deck.entries = [
        DeckEntry("entry", "", 1, oracle_id="oracle", card_id="exact-print")
    ]
    assert deck_document_issues(document) == ()
    with pytest.raises(DeckTranslationError) as failure:
        prepare_deck(document, lambda queries: [])
    assert failure.value.issues[0].code == "ORACLE_ID_NOT_RESOLVED"
    assert document.deck.entries[0].card_id == "exact-print"


def test_catalog_does_not_repeat_failing_metadata_access_for_every_deck():
    document, _ = commander_fixture()
    calls = []

    def unavailable(entries):
        calls.append(len(entries))
        raise OSError("PRIVATE_DATABASE_PATH")

    rows = prepare_catalog(
        (SavedDeck(Path("one"), document, ()), SavedDeck(Path("two"), document, ())),
        NS(get_deck_legality_data=unavailable),
    )
    assert len(calls) == 1
    assert all(row.readiness("commander").state == "review" for row in rows)


def test_commander_art_uses_exact_selected_printing_and_asset_keys():
    document, records = commander_fixture()
    row = prepare_catalog(
        (SavedDeck(Path("deck"), document, ()),),
        NS(get_deck_legality_data=lambda entries: records),
    )[0]
    assert row.commander_art == (("Leader", ("leader-print", "selected-art")),)
    assert row.commanders == ("Leader",) and row.colors == ("G",)


def test_partial_local_metadata_does_not_hide_the_saved_deck_or_claim_a_pass():
    document, records = commander_fixture()
    records["forest-print"]["payload"]["color_identity"] = None
    rows = prepare_catalog(
        (SavedDeck(Path("deck"), document, ()),),
        NS(get_deck_legality_data=lambda entries: records),
    )
    assert len(rows) == 1 and rows[0].colors is None
    assert rows[0].readiness("commander").state == "review"
    records["forest-print"]["payload"] = None
    assert local_readiness(document, "commander", records).state == "review"


def test_partner_previews_keep_each_selected_printing_independent():
    document, records = commander_fixture()
    document.deck.entries[1].quantity = 98
    document.deck.entries.append(
        DeckEntry("other", "Other", 1, section="commander", card_id="other-print")
    )
    document.deck.commander_entry_ids.append("other")
    records["leader-print"]["payload"]["oracle_text"] = "Partner"
    records["other-print"] = deepcopy(records["leader-print"])
    records["other-print"]["payload"]["name"] = "Other"
    row = prepare_catalog(
        (SavedDeck(Path("pair"), document, ()),),
        NS(get_deck_legality_data=lambda entries: records),
    )[0]
    assert row.readiness("commander").can_start
    assert row.commander_art == (
        ("Leader", ("leader-print", "selected-art")),
        ("Other", ("other-print", None)),
    )


def test_unknown_play_sections_are_identified_without_ignoring_them():
    from mtg_core.decks import DeckDocument, DeckEntry
    from mtg_play.readiness import local_readiness

    document = DeckDocument()
    document.deck.entries = [
        DeckEntry("land", "Forest", 60),
        DeckEntry("special", "Special", section="planar"),
    ]
    check = local_readiness(document, "freeform")
    assert not check.can_start
    assert "planar" in " ".join(check.messages)
    assert "Special" not in " ".join(check.messages)
