"""Regression coverage for UI-independent deck commands; executed by CI."""
from copy import deepcopy

from mtg_core.decks import DeckDocument, DeckEntry
from mtg_core.deck_mutations import (
    add_card, apply_quantity, change_candidate_quantity, change_quantities, remove_entries,
)
from mtg_core.sections import DeckSection


def document_with(*entries):
    document = DeckDocument()
    document.deck.entries = list(entries)
    return document


def test_zero_quantity_cleans_references_and_preserves_other_entries():
    document = document_with(DeckEntry('a', 'Commander'), DeckEntry('b', 'Other', quantity=3))
    document.deck.commander_entry_ids = ['a', 'b']
    document.deck.extras['companion_entry_id'] = 'a'
    apply_quantity(document, 'a', -2)
    assert [e.entry_id for e in document.deck.entries] == ['b']
    assert document.deck.entries[0].quantity == 3
    assert document.deck.commander_entry_ids == ['b']
    assert 'companion_entry_id' not in document.deck.extras


def test_multi_selection_changes_each_target_once():
    document = document_with(DeckEntry('a', 'A', quantity=2), DeckEntry('b', 'B'), DeckEntry('c', 'C'))
    change_quantities(document, ['a', 'a', 'b', 'missing'], -1)
    assert [(e.entry_id, e.quantity) for e in document.deck.entries] == [('a', 1), ('c', 1)]


def test_discovery_minus_prefers_mainboard_then_exact_printing():
    commander = DeckEntry('cmd', 'Example', section=DeckSection.COMMANDER, card_id='new', oracle_id='same')
    alternative = DeckEntry('old', 'Example', quantity=2, card_id='old', oracle_id='same')
    exact = DeckEntry('exact', 'Example', quantity=2, card_id='new', oracle_id='same')
    candidate = deepcopy(exact)
    document = document_with(commander, alternative, exact)
    change_candidate_quantity(document, candidate, -1)
    assert [e.quantity for e in document.deck.entries] == [1, 2, 1]
    assert candidate.quantity == 2
    change_candidate_quantity(document, candidate, -1)
    change_candidate_quantity(document, candidate, -1)
    assert alternative.quantity == 1
    assert commander.quantity == 1


def test_add_copies_candidate_and_merges_only_mainboard_printing():
    candidate = DeckEntry('result', 'Example', quantity=7, card_id='printing', oracle_id='oracle')
    document = document_with(DeckEntry('cmd', 'Example', section=DeckSection.COMMANDER, card_id='printing'))
    before = deepcopy(candidate.to_dict())
    add_card(document, candidate)
    added = document.deck.entries[-1]
    assert added.entry_id != candidate.entry_id
    assert added.quantity == 1
    assert added is not candidate
    add_card(document, candidate)
    assert len(document.deck.entries) == 2
    assert added.quantity == 2
    assert document.deck.entries[0].quantity == 1
    assert candidate.to_dict() == before


def test_discovery_name_fallback_and_missing_targets():
    document = document_with(DeckEntry('a', 'Forest', quantity=2))
    candidate = DeckEntry('result', 'FOREST')
    change_candidate_quantity(document, candidate, 1)
    assert document.deck.entries[0].quantity == 3
    change_candidate_quantity(document, candidate, -1)
    assert document.deck.entries[0].quantity == 2
    before = document.to_dict()
    change_candidate_quantity(document, DeckEntry('missing', 'Other'), -1)
    change_candidate_quantity(document, candidate, 0)
    apply_quantity(document, 'missing', 0)
    remove_entries(document, {'missing'})
    assert document.to_dict() == before


def test_removal_preserves_unrelated_companion():
    document = document_with(DeckEntry('a', 'A'), DeckEntry('b', 'B'))
    document.deck.extras['companion_entry_id'] = 'b'
    remove_entries(document, {'a'})
    assert document.deck.extras['companion_entry_id'] == 'b'
