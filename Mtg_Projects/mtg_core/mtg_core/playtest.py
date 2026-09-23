"""Quantity-aware opening-hand sampling; no rules engine or Qt dependency."""
from dataclasses import dataclass
import random


@dataclass(frozen=True)
class SampleCard:
    entry_id: str
    copy_index: int


class HandSampler:
    def __init__(self, deck, *, sections=('mainboard',), include_do_not_print=True,
                 free_mulligans=0, rng=None):
        self.rng = rng if rng is not None else random.Random()
        self.free_mulligans = max(0, int(free_mulligans))
        commanders = set(deck.commander_entry_ids)
        self.cards = tuple(SampleCard(entry.entry_id, copy_index)
            for entry in deck.entries
            if ('commander' if entry.entry_id in commanders else entry.section) in sections
            and (include_do_not_print or not entry.do_not_print)
            for copy_index in range(max(0, entry.quantity)))
        self.restart()

    @property
    def bottom_count(self):
        return min(len(self.hand), max(0, self.mulligans - self.free_mulligans))

    @property
    def can_mulligan(self):
        return bool(self.cards) and not self.kept and self.mulligans < self.free_mulligans + min(7, len(self.cards))

    def _deal(self):
        self.library = list(self.cards)
        self.rng.shuffle(self.library)
        self.hand = [self.library.pop() for _ in range(min(7, len(self.library)))]
        self.kept = False

    def restart(self):
        self.mulligans = 0
        self._deal()

    def mulligan(self):
        if not self.can_mulligan:
            raise ValueError('Start a new sample to draw another opening hand.')
        self.mulligans += 1
        self._deal()

    def keep(self, bottom=()):
        bottom = list(bottom)
        if self.kept:
            raise ValueError('This hand is already kept.')
        if len(bottom) != self.bottom_count or len(set(bottom)) != len(bottom) or any(c not in self.hand for c in bottom):
            raise ValueError(f'Select exactly {self.bottom_count} cards to put on the bottom.')
        self.hand = [card for card in self.hand if card not in bottom]
        self.library[0:0] = list(reversed(bottom))
        self.kept = True

    def draw(self):
        if not self.kept:
            raise ValueError('Keep your opening hand before drawing.')
        if not self.library:
            return None
        card = self.library.pop()
        self.hand.append(card)
        return card
