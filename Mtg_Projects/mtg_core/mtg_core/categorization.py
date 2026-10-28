"""Deterministic deck roles from local tags, Oracle wording, and structured facts.

Scores are rule priorities, not probabilities. No AI or remote classification.
"""
from .decks import DeckCategory
from .role_analysis import RULE_VERSION, analyze_effects, deck_context
from .strategy_analysis import memberships
from .categorization_policy import evidence_layer, ordered_evidence

# Earlier functional roles win primary-category ties; all matches are retained.
ROLE_TAGS = (
    ('Graveyard Hate', ('graveyard-hate', 'gravehate', 'grave-hate')),
    ('Evasion', ('evasion', 'unblockable')),
    ('Goad', ('goad',)),
    ('Copy', ('copy',)),
    ('Extra Combat', ('extra-combat',)),
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
    ('Enchantment Matters', ('enchantment-matters', 'enchantment-synergy', 'enchantress', 'aura-synergy')),
    ('Equipment', ('equipment', 'equipment-synergy')),
    ('Keyword Soup', ('keyword-soup',)),
    ('Spellslinger', ('spellslinger', 'magecraft')),
    ('Graveyard', ('graveyard', 'self-mill', 'mill')),
    ('Sacrifice / Aristocrats', ('sacrifice-outlet', 'aristocrats', 'sacrifice-payoff')),
    ('Utility', ('utility', 'scry', 'surveil')),
)
TYPES = ('Land', 'Creature', 'Planeswalker', 'Battle', 'Artifact', 'Enchantment', 'Instant', 'Sorcery')
CATEGORY_ALIASES = {'land': 'lands', 'board wipe': 'board wipes', 'boardwipes': 'board wipes',
                    'gravehate': 'graveyard hate', 'grave hate': 'graveyard hate', 'graveyard-hate': 'graveyard hate',
                    'card draw': 'draw', 'life gain': 'lifegain', 'counterspell': 'counterspells',
                    'anthem effects': 'anthem', '+1/+1 counters': 'counters',
                    'token generation': 'tokens', 'blink / etb': 'blink', 'enchantress': 'enchantment matters',
                    'sacrifice': 'sacrifice / aristocrats', 'aristocrats': 'sacrifice / aristocrats'}


def category_key(name):
    key = ' '.join(name.casefold().split())
    return CATEGORY_ALIASES.get(key, key)


def select_categories(evidence, categories):
    """Prefer the strongest available functional category; retain all role evidence.

    Unrecognized custom names are never guessed. New roles remain available when
    no existing category matches. Stable auto IDs also survive category renames.
    """
    # Merely having a category is not an instruction to put more cards into it.
    # Current evidence chooses the job first; apply_categories reuses matching
    # custom names/IDs afterward. Explicit per-card manual assignments are kept.
    if evidence and evidence[0].get('layer') in {'designation', 'function', 'tag'}:
        return ordered_evidence(evidence)
    # Generated secondary categories must not become new preferences on the next
    # run. Custom categories and explicitly renamed auto categories express intent.
    preferred = [c for c in categories if not c.category_id.startswith('auto:') or
                 category_key(c.name) != category_key(c.category_id[5:].replace('-', ' '))]
    available = {category_key(c.name) for c in preferred}
    available.update(c.category_id[5:].replace('-', ' ') for c in preferred if c.category_id.startswith('auto:'))
    # Older saved suggestions and recommendation providers may omit scores.
    # Treat those roles as ordinary functional evidence without mutating them.
    # Explicit category choices may prefer a keyword role (80), while incidental
    # utility/self-recursion and type fallbacks remain below this threshold.
    candidates = [m for m in evidence if m.get('score', 100) >= 80 and category_key(m['name']) in available
                  and (evidence[0].get('layer') != 'function' or m.get('layer', 'function') == 'function')]
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
        matches.append({'name': 'Lands', 'score': 200, 'layer': 'designation', 'reason': 'Front face has type Land'})
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
                            'layer': evidence_layer(name, effect.get('score', score), has_effect=bool(effect)),
                            'reason': '; '.join(dict.fromkeys(reasons))})
    strategy = (context or {}).get('_strategy', {})
    existing = {m['name']: m for m in matches}
    for role in sorted(memberships(payload, strategy)):
        if role in existing:
            continue
        # Keep efficient functional engines ahead of supporting theme membership.
        matches.append({'name': role, 'score': 148 if role in strategy.get('commander_themes', []) else 115,
                        'layer': 'theme',
                        'reason': 'Supported deck strategy: ' + role})
    matches = ordered_evidence(matches)
    if not matches:
        kind = next((kind for kind in TYPES if kind in front_types), None)
        if kind:
            matches.append({'name': 'Sorceries' if kind == 'Sorcery' else kind + 's', 'score': 10, 'layer': 'type',
                            'reason': f'Type fallback: {kind}; no matching functional rule'})
    return matches


def is_manual(entry):
    record = entry.extras.get('auto_categories', {})
    return bool(record.get('manual') or (entry.category_ids and category_origin(entry) == 'unknown'))


def category_origin(entry):
    """Legacy protected assignments are unknown, never verified human evidence."""
    record = entry.extras.get('auto_categories', {})
    if record.get('origin') == 'manual' and record.get('manual') is True:
        return 'manual'
    if not record.get('manual') and (record.get('origin') == 'automatic' or
            {'version', 'managed_ids', 'evidence'} <= record.keys()):
        return 'automatic'
    return 'unknown'


def theme_priorities(document, evidence):
    """Manual themes break functional-role ties without replacing role evidence."""
    roles = {role.casefold() for theme in document.editor_preferences.get('manual_themes', [])
             for role in theme.get('roles', [])}
    if not roles or not evidence or evidence[0]['name'] in ('Lands', 'Commander'):
        return evidence
    result = []
    for match in evidence:
        item = dict(match)
        if (item['name'].casefold() in roles and item.get('score', 100) >= 100
                and 'Manual deck theme priority' not in item.get('reason', '')):
            item['score'] = item.get('score', 100) + 8
            item['reason'] = item.get('reason', '') + '; Manual deck theme priority (+8)'
        result.append(item)
    return ordered_evidence(result)


def selected_theme_keys(document):
    """Explicit strategy identities, including typal themes with no role labels."""
    return sorted({key for theme in document.editor_preferences.get('manual_themes', [])
                   for key in [*theme.get('roles', []),
                               'theme:' + theme['slug'] if theme.get('slug') else '',
                               'tribal:' + theme['subtype'].casefold() if theme.get('subtype') else ''] if key})


def selected_strategy(document):
    from .strategy_analysis import THEMES
    aliases = {'enchantress': 'Enchantment Matters', 'aristocrats': 'Sacrifice / Aristocrats',
               'plus-1-plus-1-counters': 'Counters'}
    names, tribes = set(), set()
    for theme in document.editor_preferences.get('manual_themes', []):
        slug = theme.get('slug', '')
        names.update(role for role in theme.get('roles', []) if role in THEMES)
        names.update(role for role in THEMES if role.casefold().replace(' ', '-') == slug)
        if slug in aliases:
            names.add(aliases[slug])
        if theme.get('subtype'):
            tribes.add(theme['subtype'].casefold())
    return {'themes': sorted(names), 'tribes': sorted(tribes)}


def apply_categories(document, proposals, reconsider_manual=False, *, community_records=None):
    """Apply entry-id -> evidence in the caller's transaction, protecting manual work."""
    available_categories = list(document.deck.categories)
    from .library.category_evidence import CategoryEvidence, refine
    from .paths import data_root
    import sqlite3
    cache = data_root() / 'library-category-evidence.sqlite3'
    community = community_records or {}
    if community_records is None and cache.is_file():
        try:
            community = CategoryEvidence(cache, initialize=False).for_cards([e.oracle_id for e in document.deck.entries
                if e.entry_id in proposals and e.oracle_id and not is_manual(e)])
        except (OSError, sqlite3.Error, ValueError, TypeError):
            pass  # Optional knowledge must never interrupt deck editing.
    commanders = [e.oracle_id for e in document.deck.entries if e.oracle_id and
                  (e.entry_id in document.deck.commander_entry_ids or e.section == 'commander')]
    themes = selected_theme_keys(document)
    explicit_strategy = selected_strategy(document)
    for entry in document.deck.entries:
        evidence = proposals.get(entry.entry_id)
        if not evidence or is_manual(entry):
            continue
        categories = document.deck.categories
        if entry.section == 'commander' or entry.entry_id in document.deck.commander_entry_ids:
            evidence = [{'name': 'Commander', 'score': 250, 'reason': 'Deck commander designation'}]
        explicit_roles = memberships(entry.extras.get('facts', {}), explicit_strategy)
        evidence = [dict(match, score=max(156, match.get('score', 100)))
                    if match['name'] in explicit_roles and match.get('layer') == 'theme' else match
                    for match in evidence]
        detected = {match['name'] for match in evidence}
        evidence = ordered_evidence([*evidence, *[
            {'name': role, 'score': 156, 'layer': 'theme', 'reason': 'Explicitly selected deck theme'}
            for role in sorted(explicit_roles - detected)]])
        evidence = refine(theme_priorities(document, evidence), community.get(entry.oracle_id, []),
                          commanders=commanders, themes=themes, format=document.deck.format)
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
        entry.extras['auto_categories'] = {'origin': 'automatic', 'version': RULE_VERSION, 'managed_ids': managed, 'evidence': evidence}
    used = {cid for entry in document.deck.entries for cid in entry.category_ids}
    foundational = {'auto:ramp', 'auto:draw', 'auto:removal', 'auto:protection'}
    document.deck.categories[:] = [c for c in document.deck.categories if c.category_id in used or c.category_id in foundational
        or not c.category_id.startswith('auto:')
        or category_key(c.name) != category_key(c.category_id[5:].replace('-', ' '))]



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
            previous_manual = entry.extras.get('auto_categories', {}).get('manual_ids', [])
            entry.category_ids = selected
            entry.extras['auto_categories'] = {
                **entry.extras.get('auto_categories', {}), 'manual': True, 'origin': 'manual',
                'manual_ids': [cid for cid in selected if cid in previous_manual or choices.get(cid) is True]}


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


def refresh_automatic_categories(document, *, community_records=None):
    """Reevaluate deck-dependent evidence from cached facts inside an edit transaction.

    Per-card Oracle analysis is memoized; only composition changes trigger this.
    Entries lacking local facts keep their current assignments until hydration.
    """
    entries = document.deck.entries
    active = [e for e in entries if e.quantity > 0 and e.section in ('mainboard', 'commander')]
    commanders = set(document.deck.commander_entry_ids)
    context = deck_context([e.extras.get('facts', {}) for e in active],
        [e.extras.get('facts', {}) for e in active if e.section == 'commander' or e.entry_id in commanders])
    def local_tags(entry):
        tags = set(entry.extras['facts'].get('oracle_tags') or ())
        # Older saved facts omit Oracle tags; retain their local tag evidence.
        for match in entry.extras.get('auto_categories', {}).get('evidence', []):
            reason = match.get('reason', '')
            if 'Local Oracle Tags: ' in reason:
                tags.update(reason.split('Local Oracle Tags: ', 1)[1].split(';', 1)[0].split(', '))
        return tags
    proposals = {e.entry_id: classify(e.extras['facts'], local_tags(e), context)
                 for e in entries if e.extras.get('facts') and not is_manual(e)}
    apply_categories(document, proposals, community_records=community_records)
