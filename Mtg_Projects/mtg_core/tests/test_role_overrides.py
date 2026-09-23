import pytest

from mtg_core.categorization import apply_categories, classify, is_manual, override_categories
from mtg_core.deck_insights import deck_insights
from mtg_core.decks import DeckCategory, DeckDocument, DeckEntry, DeckHistory


def categorized_deck():
    document = DeckDocument()
    document.deck.entries = [DeckEntry('a', 'Card', quantity=3, tags=['Favorite']),
                             DeckEntry('b', 'Other')]
    apply_categories(document, {'a': classify({}, ['ramp', 'draw']),
                                'b': classify({}, ['draw'])})
    return document


def test_secondary_override_roundtrip_history_and_reanalysis():
    document = categorized_deck()
    before = document.to_dict()
    history = DeckHistory(document)
    history.execute(lambda d: override_categories(d, {'a'}, {'auto:draw': False}))
    assert document.deck.entries[0].category_ids == ['auto:ramp']
    assert deck_insights(document)['roles']['Draw'] == 1
    assert deck_insights(document)['roles']['Ramp'] == 3
    assert document.deck.entries[0].tags == ['Favorite']
    assert is_manual(document.deck.entries[0])
    edited = document.to_dict()
    assert history.undo() and document.to_dict() == before
    assert history.redo() and document.to_dict() == edited
    loaded = DeckDocument.from_dict(edited)
    proposals = {'a': classify({}, ['ramp', 'draw'])}
    apply_categories(loaded, proposals)
    assert loaded.to_dict() == edited
    apply_categories(loaded, proposals, reconsider_manual=True)
    assert loaded.deck.entries[0].category_ids == ['auto:ramp', 'auto:draw']


def test_bulk_changes_preserve_unmentioned_categories_and_unselected_entries():
    document = categorized_deck()
    document.deck.categories.append(DeckCategory('custom', 'My role'))
    other = document.deck.entries[1].to_dict()
    override_categories(document, {'a'}, {'auto:ramp': False, 'custom': True})
    assert document.deck.entries[0].category_ids == ['auto:draw', 'custom']
    assert document.deck.entries[1].to_dict() == other
    override_categories(document, {'a', 'b'}, {'auto:draw': False})
    assert [e.category_ids for e in document.deck.entries] == [['custom'], []]
    apply_categories(document, {'b': classify({}, ['draw'])})
    assert document.deck.entries[1].category_ids == []


def test_noop_and_invalid_choices_do_not_mutate():
    document = categorized_deck()
    before = document.to_dict()
    override_categories(document, {'a'}, {'auto:ramp': True})
    assert document.to_dict() == before
    for choices in ({'missing': True}, {'auto:ramp': None}):
        with pytest.raises(ValueError):
            override_categories(document, {'a'}, choices)
        assert document.to_dict() == before
