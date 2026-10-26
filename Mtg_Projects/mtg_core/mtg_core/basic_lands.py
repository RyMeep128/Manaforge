"""Deterministic pip-weighted basic land planning; callers own transactions."""
from fractions import Fraction
from copy import deepcopy
import re
import uuid

from .card_pool import pool_context, in_card_pool

BASICS = {'W': 'Plains', 'U': 'Island', 'B': 'Swamp', 'R': 'Mountain', 'G': 'Forest', 'C': 'Wastes'}
MANAGED_COPIES = 'automatic_basic_land_copies'
AUTOMATION = 'automatic_basic_lands'


def is_land(entry):
    facts = entry.extras.get('facts') or {}
    front = (facts.get('card_faces') or [facts])[0]
    return ('Land' in (front.get('type_line') or '').split()
            or entry.name in BASICS.values() or entry.name in {'Snow-Covered ' + n for n in list(BASICS.values())[:5]})


def land_quantities(document):
    result = {}
    for entry in document.deck.entries:
        if entry.section in ('mainboard', 'commander') and is_land(entry):
            key = entry.name.casefold()
            result[key] = result.get(key, 0) + entry.quantity
    return result


def stop_on_land_removal(document, previous):
    current = land_quantities(document)
    if any(current.get(name, 0) < count for name, count in previous.items()):
        document.deck.extras[AUTOMATION] = False


def managed_copies(entry):
    return min(entry.quantity, max(0, int(entry.extras.get(MANAGED_COPIES, 0)))) if entry.section == 'mainboard' else 0


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


def allocate_basics(pips, slots, identity, existing=None):
    """Largest remainders after reserving explicitly added basics of each color."""
    existing = existing or {}
    colors = [c for c in 'WUBRG' if identity is None or c in identity]
    weights = {c: Fraction(pips.get(c, 0)) for c in colors}
    if not sum(weights.values()):
        if identity is None and any(existing.get(BASICS[c], 0) for c in colors):
            weights = {c: Fraction(existing.get(BASICS[c], 0)) for c in colors}
        else:
            weights = {c: Fraction(1) for c in colors} if identity else {'C': Fraction(1)}
    total = sum(weights.values())
    basic_slots = slots + sum(existing.values())
    deficits = {c: max(Fraction(), basic_slots*w/total - existing.get(BASICS[c], 0)) for c, w in weights.items()}
    remaining = sum(deficits.values())
    quotas = {c: slots*w/remaining if remaining else Fraction() for c, w in deficits.items()}
    counts = {c: int(q) for c, q in quotas.items()}
    order = sorted(weights, key=lambda c: (-(quotas[c]-counts[c]), 'WUBRGC'.index(c)))
    for color in order[:slots-sum(counts.values())]:
        counts[color] += 1
    return {BASICS[c]: n for c, n in counts.items()}


def reconcile_basic_lands(document, templates=None):
    """Fill unoccupied deck slots in the caller's edit, preserving manual copies.

    Artwork/catalog resolution is independent of this deterministic quantity
    operation. Name-only entries are valid deck entries while metadata loads.
    """
    if document.deck.extras.get(AUTOMATION, True) is False:
        return
    def wait():
        # Drop derived copies that no longer have a confirmed legal plan.
        for entry in document.deck.entries:
            entry.quantity -= managed_copies(entry)
            entry.extras.pop(MANAGED_COPIES, None)
        document.deck.entries = [e for e in document.deck.entries if e.quantity > 0]

    from .deck_insights import deck_insights
    from .decks import DeckEntry
    from .categorization import apply_categories, classify
    analysis = deepcopy(document)
    for entry in analysis.deck.entries:
        entry.quantity -= managed_copies(entry)
    analysis.deck.entries = [e for e in analysis.deck.entries if e.quantity > 0]
    active = [e for e in analysis.deck.entries if e.section in ('mainboard', 'commander')]
    commander = analysis.deck.format.casefold() == 'commander' or any(
        e.section == 'commander' or e.entry_id in analysis.deck.commander_entry_ids for e in active)
    if commander:
        analysis.deck.format = 'Commander'
    target = 100 if commander else 60
    slots = max(0, target - sum(e.quantity for e in active)) if active else 0
    _, identity, _ = pool_context(analysis)
    if slots and commander and identity is None:
        return wait()
    if slots and identity is None and not any((e.extras.get('facts') or {}).get('mana_cost') is not None
                                             or e.name in BASICS.values() for e in active):
        return wait()  # Wait for legacy-card hydration.
    existing = {}
    for entry in active:
        name = entry.name.removeprefix('Snow-Covered ')
        if name in BASICS.values() and is_land(entry):
            existing[name] = existing.get(name, 0) + entry.quantity
    pips = deck_insights(analysis)['pips']
    if slots and identity is None and not any(pips.get(c) for c in 'WUBRG') and not existing:
        return wait()
    # Automation always respects legality, even when browsing illegal cards.
    analysis.editor_preferences['include_illegal_cards'] = False
    allowed = {c for c, name in BASICS.items() if (templates or {}).get(name)
               and in_card_pool(templates[name], analysis)}
    wanted = allocate_basics(pips, slots, identity, existing)
    if slots and any(count and next(c for c, n in BASICS.items() if n == name) not in allowed
                     for name, count in wanted.items()):
        return wait()  # Keep automation enabled while catalog data loads.
    counts = wanted
    previous, managed_ids = {}, set()
    for entry in document.deck.entries:
        copies = managed_copies(entry)
        if copies:
            managed_ids.add(entry.entry_id)
            previous.setdefault(entry.name, entry)
            entry.quantity -= copies
        entry.extras.pop(MANAGED_COPIES, None)
    proposals = {}
    for name, count in counts.items():
        if not count:
            continue
        entry = previous.get(name) or next((e for e in document.deck.entries
            if e.section == 'mainboard' and e.name == name and is_land(e)), None)
        if entry is None:
            color = next(c for c, land in BASICS.items() if land == name)
            payload = (templates or {}).get(name) or dict(name=name, type_line='Basic Land' + (' — ' + name if color != 'C' else ''),
                mana_cost='', cmc=0, colors=[], color_identity=[] if color == 'C' else [color])
            entry = DeckEntry(str(uuid.uuid4()), name, quantity=0, card_id=payload.get('id'),
                oracle_id=payload.get('oracle_id'), set_code=payload.get('set'),
                collector_number=payload.get('collector_number'), pre_cropped=True,
                extras={'facts': deepcopy(payload)}, sort_order=max((e.sort_order for e in document.deck.entries), default=-1)+1)
            document.deck.entries.append(entry)
            proposals[entry.entry_id] = classify(payload)
        entry.quantity += count
        entry.extras[MANAGED_COPIES] = count
    document.deck.entries = [e for e in document.deck.entries if e.quantity > 0 or e.entry_id not in managed_ids]
    apply_categories(document, proposals)
