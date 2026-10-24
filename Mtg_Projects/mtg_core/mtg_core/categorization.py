"""Deterministic deck roles from local tags, Oracle wording, and structured facts.

Scores are rule priorities, not probabilities. No AI or remote classification.
"""
from .decks import DeckCategory
from .role_analysis import analyze_effects, deck_context

RULE_VERSION = 5
# Earlier functional roles win primary-category ties; all matches are retained.
ROLE_TAGS = (
    ('Board Wipes', ('board-wipe', 'boardwipe', 'sweeper', 'mass-removal')),
    ('Counterspells', ('counterspell', 'counter', 'counter-ability')),
    ('Interaction', ('redirect', 'redirection', 'spell-redirection', 'change-target')),
    ('Stax', ('stax', 'tax', 'taxes', 'hatebear')),
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
    ('Blink', ('blink', 'flicker')),
    ('Anthem', ('anthem',)),
    ('Counters', ('counters', '+1/+1-counters', 'proliferate')),
    ('Equipment', ('equipment', 'equipment-synergy')),
    ('Spellslinger', ('spellslinger', 'magecraft')),
    ('Graveyard', ('graveyard', 'self-mill', 'mill', 'graveyard-hate')),
    ('Sacrifice / Aristocrats', ('sacrifice-outlet', 'aristocrats', 'sacrifice-payoff')),
    ('Utility', ('utility', 'scry', 'surveil')),
)
TYPES = ('Land', 'Creature', 'Planeswalker', 'Battle', 'Artifact', 'Enchantment', 'Instant', 'Sorcery')
CATEGORY_ALIASES = {'land': 'lands', 'board wipe': 'board wipes', 'boardwipes': 'board wipes',
                    'card draw': 'draw', 'life gain': 'lifegain', 'counterspell': 'counterspells',
                    'anthem effects': 'anthem', '+1/+1 counters': 'counters'}


def category_key(name):
    key = ' '.join(name.casefold().split())
    return CATEGORY_ALIASES.get(key, key)


def select_categories(evidence, categories):
    """Prefer the strongest available functional category; retain all role evidence.

    Unrecognized custom names are never guessed. New roles remain available when
    no existing category matches. Stable auto IDs also survive category renames.
    """
    # Generated secondary categories must not become new preferences on the next
    # run. Custom categories and explicitly renamed auto categories express intent.
    preferred = [c for c in categories if not c.category_id.startswith('auto:') or
                 category_key(c.name) != category_key(c.category_id[5:].replace('-', ' '))]
    available = {category_key(c.name) for c in preferred}
    available.update(c.category_id[5:].replace('-', ' ') for c in preferred if c.category_id.startswith('auto:'))
    # Older saved suggestions and recommendation providers may omit scores.
    # Treat those roles as ordinary functional evidence without mutating them.
    candidates = [m for m in evidence if m.get('score', 100) >= 100 and category_key(m['name']) in available]
    if not candidates or evidence[0]['name'] in ('Lands', 'Commander'):
        return evidence
    primary = candidates[0]
    return [primary, *[m for m in evidence if m is not primary]]


def classify(payload, tags=(), context=None):
    """Return ordered, serializable evidence. Missing data stays uncategorized."""
    tags = {str(tag).casefold() for tag in tags}
    faces = payload.get('card_faces') or []
    type_line = str((faces[0] if faces else payload).get('type_line') or '')
    front_types = type_line.split('—')[0].split('//')[0].split()
    matches = []
    effects = analyze_effects(payload)
    if 'Land' in front_types:
        matches.append({'name': 'Lands', 'score': 200, 'reason': 'Front face has type Land'})
    for name, aliases in ROLE_TAGS:
        found = sorted(tags.intersection(aliases))
        effect = effects.get(name, {})
        reasons = (['Local Oracle Tags: ' + ', '.join(found)] if found else []) + effect.get('reasons', [])
        if reasons:
            # Casting this card again describes how it is used, not its main job.
            # Keep genuine graveyard-recovery effects at normal priority.
            keyword_recursion = (name == 'Recursion' and effect.get('reasons')
                and all(reason.startswith('Keywords:') for reason in effect['reasons'])
                and not set(found).difference({'recursion'}))
            score = 40 if keyword_recursion else max(100 if found else 0, effect.get('score', 0))
            bonus = min(8, max(0, (context or {}).get(name, 0))) if score >= 100 else 0
            if bonus:
                reasons.append(f'Deck context: commander or repeated {name.lower()} synergy (+{bonus})')
            matches.append({'name': name, 'score': score + bonus,
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
    available_categories = list(document.deck.categories)
    for entry in document.deck.entries:
        evidence = proposals.get(entry.entry_id)
        if not evidence or (is_manual(entry) and not reconsider_manual):
            continue
        categories = document.deck.categories
        if entry.section == 'commander' or entry.entry_id in document.deck.commander_entry_ids:
            evidence = [{'name': 'Commander', 'score': 250, 'reason': 'Deck commander designation'}]
        evidence = select_categories(evidence, available_categories)
        previous = entry.extras.get('auto_categories', {}).get('managed_ids', [])
        managed = []
        for match in evidence:
            name = match['name']
            stable_id = 'auto:' + name.casefold().replace(' ', '-')
            category = next((c for c in categories if c.category_id == stable_id), None)
            if category is None:
                category = next((c for c in categories if category_key(c.name) == category_key(name)), None)
            if category is None:
                category = DeckCategory(stable_id, name, max((c.sort_order for c in categories), default=-1) + 1)
                categories.append(category)
            managed.append(category.category_id)
        entry.category_ids = managed + [c for c in entry.category_ids if c not in previous and c not in managed]
        entry.extras['auto_categories'] = {'version': RULE_VERSION, 'managed_ids': managed, 'evidence': evidence}


def override_categories(document, entry_ids, choices):
    """Set deck-local memberships; omitted categories keep their current state.

    Preserve the primary category when retained, otherwise promote the next
    remaining category. The caller owns the history/persistence transaction.
    """
    known = {category.category_id for category in document.deck.categories}
    if choices.keys() - known:
        raise ValueError('Unknown category')
    if any(type(value) is not bool for value in choices.values()):
        raise ValueError('Category choices must be true or false')
    entry_ids = set(entry_ids)
    for entry in document.deck.entries:
        if entry.entry_id not in entry_ids:
            continue
        selected = [cid for cid in entry.category_ids if choices.get(cid, True)]
        selected.extend(cid for cid, enabled in choices.items() if enabled and cid not in selected)
        if selected != entry.category_ids:
            entry.category_ids = selected
            entry.extras['auto_categories'] = {
                **entry.extras.get('auto_categories', {}), 'manual': True}


def analyze_entries(database, entries, *, context_entries=None, commander_entry_ids=()):
    """Batch local data access; callers run this off the UI thread."""
    entries = list(entries)
    context_entries = list(context_entries) if context_entries is not None else entries
    all_entries = {e.entry_id: e for e in [*context_entries, *entries]}.values()
    data = database.categorization_data([e.card_id for e in all_entries], [e.oracle_id for e in all_entries])

    def payload_for(entry):
        return {**(entry.extras.get('facts') or {}),
                **{key: value for key, value in (data['cards'].get(entry.card_id) or {}).items() if value is not None}}

    active = [e for e in context_entries if e.quantity > 0 and e.section in ('mainboard', 'commander')]
    commanders = set(commander_entry_ids)
    context = deck_context([payload_for(e) for e in active],
                           [payload_for(e) for e in active if e.section == 'commander' or e.entry_id in commanders])
    result = {}
    for entry in entries:
        payload = payload_for(entry)
        oracle_id = entry.oracle_id or payload.get('oracle_id')
        result[entry.entry_id] = ([{'name': 'Commander', 'score': 250, 'reason': 'Deck commander designation'}]
                                 if entry.section == 'commander' or entry.entry_id in commanders else
                                 classify(payload, data['tags'].get(oracle_id, []), context))
    return result
