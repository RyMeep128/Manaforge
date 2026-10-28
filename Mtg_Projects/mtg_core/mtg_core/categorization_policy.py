"""Shared primary-role policy, independent of deck themes and numeric weights.

Scores compare evidence within a layer. They must never let deck membership
override a card's job, or let an incidental keyword override an actual effect.
Legacy evidence without a layer retains its existing score-based behavior.
"""

THEMATIC_ROLES = frozenset({'Enchantment Matters', 'Equipment', 'Spellslinger', 'Keyword Soup'})
LAYERS = {'designation': 0, 'function': 1, 'tag': 2, 'theme': 3, 'incidental': 4, 'type': 5}


def evidence_layer(role, score, *, has_effect):
    if role in THEMATIC_ROLES:
        return 'theme'
    if score < 100:
        return 'incidental'
    return 'function' if has_effect else 'tag'


def evidence_key(item):
    return LAYERS.get(item.get('layer', 'function'), 1), -item.get('score', 100)


def ordered_evidence(evidence):
    return sorted(evidence, key=evidence_key)
