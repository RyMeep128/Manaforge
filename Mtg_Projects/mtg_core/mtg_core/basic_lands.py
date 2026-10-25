"""Deterministic pip-weighted basic land planning; callers own transactions."""
from fractions import Fraction
import re

from .card_pool import pool_context

BASICS = {'W': 'Plains', 'U': 'Island', 'B': 'Swamp', 'R': 'Mountain', 'G': 'Forest', 'C': 'Wastes'}


def mana_pips(cost):
    """Hybrid counts once for each color; monocolor hybrid/phyrexian count one.

    Generic, snow, variable, life and energy symbols contribute no color.
    Explicit colorless requirements are reported separately as C.
    """
    result = {}
    for symbol in re.findall(r'\{([^}]+)\}', cost or ''):
        colors = set(symbol.upper().split('/')) & set('WUBRGC')
        for color in 'WUBRGC':
            if color not in colors:
                continue
            result[color] = result.get(color, 0) + 1
    return result


def available_slots(document):
    total = sum(e.quantity for e in document.deck.entries if e.section in ('mainboard', 'commander'))
    return max(0, 100-total) if document.deck.format.casefold() == 'commander' else 10000


def basic_distribution(document, slots):
    from .deck_insights import deck_insights
    if not isinstance(slots, int) or slots < 0 or slots > available_slots(document):
        raise ValueError('The requested lands exceed the available deck slots.')
    pips = deck_insights(document)['pips']
    _, identity, _ = pool_context(document)
    colors = [c for c in 'WUBRG' if identity is None or c in identity]
    weights = {c: Fraction(pips.get(c, 0)) for c in colors}
    if not sum(weights.values()):
        weights = {c: Fraction(1) for c in colors} if identity else {'C': Fraction(1)}
    total = sum(weights.values())
    quotas = {c: slots*w/total for c, w in weights.items()}
    counts = {c: int(q) for c, q in quotas.items()}
    order = sorted(weights, key=lambda c: (-(quotas[c]-counts[c]), 'WUBRGC'.index(c)))
    for color in order[:slots-sum(counts.values())]:
        counts[color] += 1
    return {BASICS[c]: n for c, n in counts.items()}, pips
