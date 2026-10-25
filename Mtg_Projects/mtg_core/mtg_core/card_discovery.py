"""Explainable local functional similarity and cached commander usage."""
import json
import re
import sqlite3

from .card_pool import deck_query, in_card_pool
from .category_rules import clean_text, keyword_profile
from .role_analysis import analyze_effects
from .search.cancellation import check_cancelled

EFFECT_WORDS = frozenset(('draw', 'counter', 'destroy', 'exile', 'return', 'sacrifice',
                          'create', 'token', 'discard', 'mill', 'untap', 'copy', 'damage',
                          'search', 'equip', 'enchant', 'proliferate', 'scry', 'surveil'))


def signature(payload):
    roles = {k for k, v in analyze_effects(payload).items() if v['score'] >= 100}
    text = clean_text(' '.join(f.get('oracle_text') or '' for f in payload.get('card_faces') or [payload]))
    for name in [payload.get('name') or '', *[f.get('name') or '' for f in payload.get('card_faces') or []]]:
        if name:
            text = text.replace(name.casefold(), '~')
    words = set(re.findall(r'[a-z]+', text)) & EFFECT_WORDS
    possessed, granted = keyword_profile(payload)
    return roles, words, possessed | granted


def similar_cards(service, seed, document, *, should_cancel=None):
    source_roles, source_words, source_keywords = signature(seed)
    terms = ['o:' + json.dumps(word) for word in sorted(source_words | source_keywords)]
    if not terms and source_roles:
        text = ' '.join(f.get('oracle_text') or '' for f in seed.get('card_faces') or [seed])
        stop = {'this', 'that', 'your', 'with', 'from', 'each', 'target', 'whenever', 'when', 'card', 'cards'}
        fallback = sorted(set(re.findall(r'[a-z]{4,}', clean_text(text))) - stop)
        terms = ['o:' + json.dumps(word) for word in fallback[:8]]
    if not terms:
        return dict(results=[], status='No functional abilities are available for this card in the local catalog.')
    query = deck_query('(' + ' or '.join(terms) + ')', document)
    batch = service.search_cards(query, dict(scryfall_syntax=True, allow_remote=False,
                                            limit=2000, should_cancel=should_cancel))
    rows = []
    for result in batch:
        check_cancelled(should_cancel)
        payload = result.payload or {}
        if (result.oracle_id == seed.get('oracle_id') or payload.get('name') == seed.get('name')
                or not in_card_pool(payload, document)):
            continue
        roles, words, keywords = signature(payload)
        shared_roles, shared_words, shared_keywords = source_roles & roles, source_words & words, source_keywords & keywords
        if not (shared_roles or shared_keywords or len(shared_words) >= 2):
            continue
        overlap = lambda a, b: len(a & b) / max(1, len(a | b))
        value = 0.65*overlap(source_roles, roles) + 0.25*overlap(source_words, words) + 0.10*overlap(source_keywords, keywords)
        reasons = []
        if shared_roles:
            reasons.append('Shared functional roles: ' + ', '.join(sorted(shared_roles)))
        if shared_words:
            reasons.append('Comparable effects: ' + ', '.join(sorted(shared_words)))
        if shared_keywords:
            reasons.append('Shared keywords: ' + ', '.join(sorted(shared_keywords)))
        rows.append(dict(payload=payload, reason='\n'.join(reasons), score=value))
    rows.sort(key=lambda r: (-r['score'], r['payload'].get('name', '').casefold()))
    return dict(results=rows[:200], status=f'{min(200, len(rows))} functional matches from up to 2,000 local candidates. '
                'Similarity uses rules, effects and keywords; it is a heuristic, not a rules-equivalence guarantee.')


def popular_commanders(service, seed, document, sources, *, should_cancel=None):
    """Keep providers and cohorts separate; their samples must never be added."""
    from .commander import eligible
    from .public_deck_datasets import SOURCE_LABELS
    rows, notices = [], []
    for source in sources:
        check_cancelled(should_cancel)
        reader = getattr(source, 'commanders_using', None)
        if not callable(reader):
            continue
        try:
            usage = reader(seed.get('oracle_id'), should_cancel=should_cancel)
        except (OSError, ValueError, sqlite3.DatabaseError) as exc:
            check_cancelled(should_cancel)
            notices.append(f'{source.source_id}: {exc}')
            continue
        for cohort in sorted(usage, key=lambda c: (-c['count'], c['commanders']))[:100]:
            check_cancelled(should_cancel)
            payloads = [service.choose_preferred_print(oid) for oid in cohort['commanders']]
            if not all(p and in_card_pool(p, document) for p in payloads):
                continue
            names = ' + '.join(p['name'] for p in payloads)
            reason = (f"{SOURCE_LABELS.get(source.source_id, source.source_id)}: "
                      f"{cohort['count']:,} / {cohort['sample']:,} cached eligible decks "
                      f"({cohort['count']/cohort['sample']:.1%}) include this card.\nCohort: {names}")
            for payload in payloads:
                if eligible(payload) is True:
                    rows.append(dict(payload=payload, reason=reason, count=cohort['count']))
    rows.sort(key=lambda r: (-r['count'], r['payload']['name'].casefold(), r['reason']))
    return dict(results=rows[:200], status=('Cached inclusion statistics; coverage varies by provider. Partner cohorts remain labeled. '
                'Samples from different providers are not combined.' if rows else
                'No cached commander inclusion data matches this card and deck filters. Import recommendation data or include illegal cards to broaden the pool.')
                + (' Unavailable providers: ' + '; '.join(notices) if notices else ''))
