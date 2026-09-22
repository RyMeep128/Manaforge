"""Quantity-weighted deck composition; never modifies cards or inferred roles."""
from collections import Counter
import math
import re

from .categorization import ROLE_TAGS, TYPES


def deck_insights(document, records=None, sections=('mainboard', 'commander')):
    records = records or {}
    categories = {c.category_id: c.name for c in document.deck.categories}
    curve, types, colors, pips = Counter(), Counter(), Counter(), Counter()
    roles = Counter({name: 0 for name, _ in ROLE_TAGS})
    roles.update({c.name: 0 for c in document.deck.categories})
    unknown = Counter()
    total = lands = known_mv = 0
    mana_sum = 0.0
    for entry in document.deck.entries:
        if entry.section not in sections or entry.quantity <= 0:
            continue
        qty = entry.quantity
        total += qty
        facts = dict(entry.extras.get('facts') or {})
        facts.update(records.get(entry.card_id) or {})
        faces = facts.get('card_faces') or []
        # A DFC's deck composition uses its front; split/adventure cards use the
        # combined top-level characteristics supplied by the card catalog.
        front = faces[0] if faces and not facts.get('mana_cost') and facts.get('layout') in (
            'transform', 'modal_dfc', 'reversible_card', 'double_faced_token') else facts
        line = front.get('type_line') or facts.get('type_line') or ''
        card_types = {word for half in line.split('//') for word in half.split('—')[0].split()}
        land = 'Land' in card_types
        lands += qty if land else 0
        if not line:
            unknown['type'] += qty
        for kind in TYPES:
            if kind in card_types:
                types[kind] += qty
        if not land and line:
            mv = facts.get('cmc')
            if isinstance(mv, (int, float)) and not isinstance(mv, bool) and math.isfinite(mv) and mv >= 0:
                curve[mv] += qty
                known_mv += qty
                mana_sum += mv * qty
            else:
                unknown['mana value'] += qty
        card_colors = front.get('colors', facts.get('colors'))
        if card_colors is None:
            unknown['color'] += qty
        elif not card_colors:
            colors['Colorless'] += qty
        else:
            for color in set(card_colors):
                colors[color] += qty
        cost = front.get('mana_cost')
        if cost is None:
            if not land:
                unknown['mana cost'] += qty
        else:
            for symbol in re.findall(r'\{([^}]+)\}', cost):
                for color in set(symbol.split('/')) & set('WUBRGC'):
                    pips[color] += qty
        # Categories and tags are authoritative deck-local choices. Do not
        # reclassify or resurrect roles a user has removed.
        names = [categories[c] for c in entry.category_ids if c in categories] + entry.tags
        canonical = {name.casefold(): name for name in roles}
        assigned = {canonical.setdefault(name.casefold(), name) for name in names}
        for name in assigned:
            roles[name] += qty
    return dict(total=total, lands=lands, nonlands=total-lands-unknown['type'],
                average_mana_value=mana_sum/known_mv if known_mv else None,
                known_mana_value=known_mv, curve=dict(sorted(curve.items())),
                types=dict(types), colors=dict(colors), pips=dict(pips),
                roles=dict(sorted(roles.items(), key=lambda item: item[0].casefold())),
                unknown={key: value for key, value in unknown.items() if value})
