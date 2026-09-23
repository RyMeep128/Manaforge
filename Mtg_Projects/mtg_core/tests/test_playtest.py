from collections import Counter
import random

import pytest

from mtg_core.decks import Deck, DeckDocument, DeckEntry
from mtg_core.playtest import HandSampler


def test_quantities_identity_and_no_deck_mutation():
    deck = Deck(entries=[DeckEntry('a', 'Same name', quantity=8, card_id='print1'),
                         DeckEntry('b', 'Same name', quantity=4, card_id='print2')])
    before = deck.to_dict()
    sample = HandSampler(deck, rng=random.Random(42))
    repeat = HandSampler(deck, rng=random.Random(42))
    assert sample.hand == repeat.hand
    assert len(sample.hand) == 7 and len(sample.library) == 5
    assert Counter(card.entry_id for card in sample.cards) == {'a': 8, 'b': 4}
    assert len(set(sample.hand + sample.library)) == 12
    sample.keep()
    while sample.draw() is not None:
        pass
    assert set(sample.hand) == set(sample.cards)
    sample.restart()
    assert len(sample.hand) == 7 and not sample.kept and sample.mulligans == 0
    assert deck.to_dict() == before


def test_inclusion_and_commander_identity():
    deck = Deck(entries=[DeckEntry('main', 'Main'), DeckEntry('owned', 'Owned', do_not_print=True),
        DeckEntry('cmd', 'Commander'), DeckEntry('side', 'Side', section='sideboard'),
        DeckEntry('maybe', 'Maybe', section='considering'), DeckEntry('excluded', 'Excluded', section='excluded')],
        commander_entry_ids=['cmd'])
    assert {c.entry_id for c in HandSampler(deck).cards} == {'main', 'owned'}
    sample = HandSampler(deck, sections=('mainboard', 'commander', 'sideboard', 'considering', 'excluded'),
                         include_do_not_print=False)
    assert {c.entry_id for c in sample.cards} == {'main', 'cmd', 'side', 'maybe', 'excluded'}


def test_mulligan_bottoming_conserves_copies_and_free_mulligan():
    sample = HandSampler(Deck(entries=[DeckEntry('a', 'Card', quantity=20)]),
                         free_mulligans=1, rng=random.Random(1))
    sample.mulligan()
    assert sample.bottom_count == 0 and len(sample.hand) == 7
    sample.mulligan()
    sample.mulligan()
    assert sample.bottom_count == 2
    before = list(sample.hand)
    for invalid in ([], [sample.hand[0]] * 2, sample.library[:2]):
        with pytest.raises(ValueError):
            sample.keep(invalid)
        assert sample.hand == before
    bottom = sample.hand[:2]
    sample.keep(bottom)
    assert len(sample.hand) == 5 and len(sample.library) == 15
    assert sample.library[:2] == list(reversed(bottom))
    drawn = [sample.draw() for _ in range(15)]
    assert drawn[-2:] == bottom
    assert len(set(sample.hand)) == 20
    with pytest.raises(ValueError):
        sample.mulligan()


def test_empty_and_small_decks_and_old_notes_format():
    empty = HandSampler(Deck())
    assert not empty.cards and not empty.can_mulligan
    with pytest.raises(ValueError):
        empty.draw()
    small = HandSampler(Deck(entries=[DeckEntry('a', 'Card', quantity=2)]))
    small.mulligan()
    small.mulligan()
    assert not small.can_mulligan and small.bottom_count == 2
    small.keep(small.hand)
    assert small.hand == [] and len(small.library) == 2
    old = DeckDocument.from_dict({'deck': {'name': 'Legacy'}})
    assert old.deck.playtest_notes == ''
    old.deck.playtest_notes = 'Keep more two-land hands.\nTry another draw spell.'
    assert DeckDocument.from_dict(old.to_dict()).deck.playtest_notes == old.deck.playtest_notes
