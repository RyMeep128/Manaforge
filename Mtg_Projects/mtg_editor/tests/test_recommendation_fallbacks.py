from types import SimpleNamespace

import pytest

from mtg_core.decks import DeckDocument, DeckEntry
from mtg_core.sections import DeckSection
from mtg_editor.recommendation_fallbacks import fallback_rows
from mtg_editor.recommendation_pages import RecommendationPages


def candidate(oid, kind='Instant', *, colors=(), legal='legal', rank=1):
    return SimpleNamespace(oracle_id=oid, card_id=oid, name=oid, payload=dict(
        id=oid, name=oid, oracle_id=oid, type_line=kind, color_identity=list(colors),
        legalities={'commander': legal}, edhrec_rank=rank))


@pytest.mark.parametrize('kind', ['Instant', 'Sorcery', 'Creature', 'Artifact', 'Enchantment', 'Planeswalker', 'Land'])
def test_type_fallback_uses_identity_legality_popularity_and_deduplication(kind):
    document = DeckDocument()
    document.deck.format = 'commander'
    document.deck.entries = [DeckEntry('c', 'Commander', oracle_id='commander', section=DeckSection.COMMANDER,
                                      extras={'facts': {'color_identity': ['U', 'R']}}),
                             DeckEntry('owned', 'owned', oracle_id='owned')]
    document.deck.commander_entry_ids = ['c']
    calls = []

    def search(query, options):
        calls.append((query, options))
        if f't:{kind}' not in query:
            return []
        return [candidate('good', kind, colors=['U']), candidate('colorless', kind),
                candidate('good', kind), candidate('owned', kind),
                candidate('wrong-color', kind, colors=['G']), candidate('banned', kind, legal='banned'),
                candidate('unranked', kind, rank=None), candidate('source-card', kind)]

    rows = list(fallback_rows(SimpleNamespace(search_cards=search), document, seen={'source-card'}))
    assert [r['oracle_id'] for r in rows] == ['good', 'colorless']
    assert all(r['fallback'] for r in rows)
    assert all('id<=UR' in query and 'legal:commander' in query for query, _ in calls)
    assert all(options['allow_remote'] is False and options['popularity'] for _, options in calls)


def row(oid, kind, *, fallback=False, score=1):
    return dict(oracle_id=oid, score=score, fallback=fallback, roles=[],
                entry=DeckEntry(oid, oid, oracle_id=oid, extras={'facts': {'type_line': kind}}))


def test_fallback_only_after_category_filters_membership_and_dismissals():
    pages, document = RecommendationPages(), DeckDocument()
    pages.append([row('specific', 'Instant'), row('popular', 'Instant', fallback=True, score=99),
                  row('sorcery', 'Sorcery', fallback=True)])
    assert [r['oracle_id'] for r in pages.page(document, category='Instants')[0]] == ['specific']
    assert [r['oracle_id'] for r in pages.page(document, category='Sorceries')[0]] == ['sorcery']
    assert [r['oracle_id'] for r in pages.page(document, category='Instants', dismissed=['specific'])[0]] == ['popular']
    document.deck.entries = [DeckEntry('owned', 'specific', oracle_id='specific')]
    assert [r['oracle_id'] for r in pages.page(document, category='Instants')[0]] == ['popular']
    assert [r['oracle_id'] for r in pages.page(document, category='Instants', text='popular')[0]] == ['popular']
    assert pages.page(document, category='High Lift')[0] == []


def test_cached_shared_pages_are_hidden_immediately_on_revocation(tmp_path):
    import time
    path = tmp_path / 'cache'
    path.write_text('authorized')
    shared = row('shared', 'Instant')
    shared['source_evidence'] = {'library': dict(cache_file=str(path), cache_mtime=path.stat().st_mtime_ns,
                                               cache_deadline=time.time() + 60)}
    pages, document = RecommendationPages(), DeckDocument()
    pages.append([shared])
    assert pages.page(document, category='Instants')[0]
    path.unlink()
    assert not pages.page(document, category='Instants')[0]
