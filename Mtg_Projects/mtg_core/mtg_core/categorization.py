"""Deterministic deck roles from local tags, Oracle wording, and structured facts.

Scores are rule priorities, not probabilities. No AI or remote classification.
"""
from .decks import DeckCategory
from .category_rules import text_roles

RULE_VERSION = 4
# Earlier functional roles win primary-category ties; all matches are retained.
ROLE_TAGS = (
    ('Board Wipes', ('board-wipe', 'boardwipe', 'sweeper', 'mass-removal')),
    ('Counterspells', ('counterspell', 'counter', 'counter-ability')),
    ('Interaction', ('redirect', 'redirection', 'spell-redirection', 'change-target')),
    ('Ramp', ('ramp',)),
    ('Removal', ('removal',)),
    ('Tutors', ('tutor',)),
    ('Protection', ('protection',)),
    ('Recursion', ('recursion', 'reanimation')),
    ('Win Conditions', ('win-condition', 'wincon', 'finisher')),
    ('Draw', ('card-draw', 'draw')),
    ('Card Advantage', ('card-advantage', 'impulse-draw', 'impulsive-draw')),
    ('Tokens', ('token-generator', 'token-generation', 'token-creation')),
    ('Lifegain', ('lifegain', 'life-gain')),
    ('Graveyard', ('graveyard', 'self-mill', 'mill', 'graveyard-hate')),
    ('Sacrifice / Aristocrats', ('sacrifice-outlet', 'aristocrats', 'sacrifice-payoff')),
    ('Utility', ('utility', 'scry', 'surveil')),
)
TYPES = ('Land', 'Creature', 'Planeswalker', 'Battle', 'Artifact', 'Enchantment', 'Instant', 'Sorcery')


def classify(payload, tags=()):
    """Return ordered, serializable evidence. Missing data stays uncategorized."""
    tags = {str(tag).casefold() for tag in tags}
    faces = payload.get('card_faces') or []
    type_line = str((faces[0] if faces else payload).get('type_line') or '')
    front_types = type_line.split('—')[0].split('//')[0].split()
    matches = []
    text_evidence = text_roles(payload)
    if 'Land' in front_types:
        matches.append({'name': 'Lands', 'score': 200, 'reason': 'Front face has type Land'})
    for name, aliases in ROLE_TAGS:
        found = sorted(tags.intersection(aliases))
        reasons = (['Local Oracle Tags: ' + ', '.join(found)] if found else []) + text_evidence.get(name, [])
        if reasons:
            # Casting this card again describes how it is used, not its main job.
            # Keep genuine graveyard-recovery effects at normal priority.
            keyword_recursion = (name == 'Recursion' and text_evidence.get(name)
                and all(reason.startswith('Keywords:') for reason in text_evidence[name])
                and not set(found).difference({'recursion'}))
            matches.append({'name': name, 'score': 40 if keyword_recursion else 100,
                            'reason': '; '.join(dict.fromkeys(reasons))})
    matches.sort(key=lambda match: -match['score'])
    if not matches:
        kind = next((kind for kind in TYPES if kind in front_types), None)
        if kind:
            matches.append({'name': 'Sorceries' if kind == 'Sorcery' else kind + 's', 'score': 10,
                            'reason': f'Type fallback: {kind}; no matching functional rule'})
    return matches


def is_manual(entry):
    record = entry.extras.get('auto_categories', {})
    return bool(record.get('manual') or (entry.category_ids and not record))


def apply_categories(document, proposals, reconsider_manual=False):
    """Apply entry-id -> evidence in the caller's transaction, protecting manual work."""
    for entry in document.deck.entries:
        evidence = proposals.get(entry.entry_id)
        if not evidence or (is_manual(entry) and not reconsider_manual):
            continue
        categories = document.deck.categories
        previous = entry.extras.get('auto_categories', {}).get('managed_ids', [])
        managed = []
        for match in evidence:
            name = match['name']
            stable_id = 'auto:' + name.casefold().replace(' ', '-')
            category = next((c for c in categories if c.category_id == stable_id), None)
            if category is None:
                category = next((c for c in categories if c.name.casefold() == name.casefold()), None)
            if category is None:
                category = DeckCategory(stable_id, name, max((c.sort_order for c in categories), default=-1) + 1)
                categories.append(category)
            managed.append(category.category_id)
        entry.category_ids = managed + [c for c in entry.category_ids if c not in previous and c not in managed]
        entry.extras['auto_categories'] = {'version': RULE_VERSION, 'managed_ids': managed, 'evidence': evidence}


def analyze_entries(database, entries):
    """Batch local data access; callers run this off the UI thread."""
    entries = list(entries)
    data = database.categorization_data([e.card_id for e in entries], [e.oracle_id for e in entries])
    result = {}
    for entry in entries:
        payload = data['cards'].get(entry.card_id, entry.extras.get('facts', {}))
        oracle_id = entry.oracle_id or payload.get('oracle_id')
        result[entry.entry_id] = classify(payload, data['tags'].get(oracle_id, []))
    return result
