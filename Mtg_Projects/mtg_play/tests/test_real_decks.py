"""Boundary regressions for CI; live evidence remains in acceptance reports."""

from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mtg_core"))
from mtg_play.adapter import AdapterError
from mtg_play.decks import prepare_deck, DeckTranslationError
from mtg_play.diagnostics import diagnostic_category
from mtg_play.real_deck_fixtures import commander_decks
from mtg_play.real_deck_acceptance import validate_view


def test_commander_fixtures_are_singleton_hundred_card_documents_and_not_mutated():
    for document in commander_decks():
        before = deepcopy(document.to_dict())
        entries = document.deck.entries
        assert sum(e.quantity for e in entries) == 100
        assert document.deck.commander_entry_ids == ["commander"]
        assert len({e.name for e in entries}) == len(entries)
        assert all(
            e.quantity == 1
            for e in entries
            if e.name not in {"Forest", "Island", "Mountain", "Plains"}
        )

        def resolve(queries):
            return [
                dict(
                    key=q["key"],
                    name=q["name"],
                    set=q["set"] or "FIX",
                    number=q["number"] or str(i),
                )
                for i, q in enumerate(queries)
            ]

        prepared = prepare_deck(document, resolve, commander=True)
        assert sum(e["quantity"] for e in prepared.cards) == 99
        assert sum(e["quantity"] for e in prepared.sideboard) == 1
        assert prepared.bindings[("M10", "248")].printing_id == "fixture-forest-M10-248"
        assert document.to_dict() == before


def test_selected_printing_cannot_be_bound_to_engine_fallback():
    document = commander_decks()[0]

    def resolve(queries):
        return [
            dict(key=q["key"], name=q["name"], set="WRONG", number=str(i))
            for i, q in enumerate(queries)
        ]

    with pytest.raises(DeckTranslationError) as failure:
        prepare_deck(document, resolve, commander=True)
    assert [(i.entry_id, i.code) for i in failure.value.issues] == [
        ("forest", "PRINTING_NOT_RESOLVED")
    ]


@pytest.mark.parametrize(
    "code,category",
    [
        ("CARD_NOT_SUPPORTED", "card_missing_from_pinned_engine"),
        ("PRINTING_NOT_RESOLVED", "identity_or_printing_resolution"),
        ("UNSUPPORTED_SECTION", "unsupported_deck_configuration"),
        ("UNSUPPORTED_DECISION", "unsupported_game_decision"),
        ("PINNED_METADATA_INTERFACE_CHANGED", "adapter_translation_failure"),
        ("SCENARIO_TIMEOUT", "unexpected_engine_or_harness_behavior"),
    ],
)
def test_diagnostic_categories_preserve_distinctions(code, category):
    assert diagnostic_category(code) == category


@pytest.mark.parametrize(
    "change,code",
    [
        ({"zone": "hand", "owner_id": "two"}, "OPPONENT_HAND_EXPOSED"),
        ({"hidden": True, "characteristics": object()}, "HIDDEN_IDENTITY_EXPOSED"),
        ({"copy_source_id": "retired"}, "COPY_SOURCE_NOT_VISIBLE"),
    ],
)
def test_live_inspector_rejects_visibility_and_identity_regressions(change, code):
    values = dict(
        object_id="object",
        zone="battlefield",
        owner_id="one",
        hidden=False,
        characteristics=None,
        card_identity=None,
        copy_source_id=None,
    )
    values.update(change)
    view = NS(viewer_id="one", objects=(NS(**values),), decision=None)
    with pytest.raises(AdapterError, match=code):
        validate_view(view)


def test_live_inspector_does_not_allow_duplicate_token_references():
    obj = NS(object_id="token")
    with pytest.raises(AdapterError, match="DUPLICATE_OBJECT_REFERENCES"):
        validate_view(NS(objects=(obj, obj)))
