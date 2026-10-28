"""Shared samples never enter the personal collection or published datasets."""
from contextlib import closing
from types import SimpleNamespace
import time

import pytest

from mtg_core.decks import DeckDocument, DeckEntry
from mtg_core.library import LibraryError
from mtg_core.library.recommendations import LibraryRecommendations
from mtg_core.recommendation_sources import recommend


def publication(deck_id='deck', *, revision=1, commander='cmd', card='spell', tags=()):
    return dict(deck_id=deck_id, revision=revision, color_identity=['U'], deck=dict(
        commander_entry_ids=['commander'], tags=list(tags), entries=[
            dict(entry_id='commander', oracle_id=commander, quantity=1, section='commander'),
            dict(entry_id='card', oracle_id=card, quantity=1, section='mainboard')]))


class Client:
    def __init__(self, server='server', rows=None):
        self.server_id, self.account_id = server, 'account'
        self.expires_at = time.time() + 3600
        self.rows = rows if rows is not None else [publication()]
        self.error = None

    def check(self):
        if self.error:
            raise self.error

    def browse(self, *, offset=0):
        return self.rows[offset:offset + 50]


def test_incremental_revisions_deletions_multiple_libraries_and_copies(tmp_path):
    cache = LibraryRecommendations(tmp_path / 'shared.sqlite3')
    first, second = Client(), Client('other', [publication('copy')])
    cache.sync(first)
    cache.sync(second)
    row = cache.snapshot(['cmd'])['results'][0]
    assert row['shared_decks'] == 1
    assert row['score'] == pytest.approx(1 / 6)
    with closing(cache.connect()) as db:
        original = db.execute('SELECT rowid FROM members WHERE server=? ORDER BY oracle', ('server',)).fetchall()
    cache.sync(first)
    with closing(cache.connect()) as db:
        assert original == db.execute('SELECT rowid FROM members WHERE server=? ORDER BY oracle', ('server',)).fetchall()
    first.rows = [publication(revision=2, card='updated')]
    cache.sync(first)
    assert {r['oracle_id'] for r in cache.snapshot(['cmd'])['results']} == {'spell', 'updated'}
    second.rows = []
    cache.sync(second)
    assert [r['oracle_id'] for r in cache.snapshot(['cmd'])['results']] == ['updated']
    cache.revoke(first.server_id)
    assert cache.snapshot(['cmd'])['results'] == []


def test_offline_cache_expiry_access_rejection_and_account_switch(tmp_path):
    cache, client = LibraryRecommendations(tmp_path / 'shared.sqlite3'), Client()
    cache.sync(client)
    client.error = LibraryError(503, 'offline')
    with pytest.raises(LibraryError):
        cache.sync(client)
    assert cache.snapshot(['cmd'])['results']
    client.error = LibraryError(403, 'revoked')
    with pytest.raises(LibraryError):
        cache.sync(client)
    assert not cache.snapshot(['cmd'])['results']
    client.error = None
    cache.sync(client)
    client.account_id, client.error = 'different', LibraryError(503, 'offline')
    with pytest.raises(LibraryError):
        cache.sync(client)
    assert not cache.snapshot(['cmd'])['results']
    client.error, client.expires_at = None, time.time() - 1
    cache.sync(client)
    assert not cache.snapshot(['cmd'])['results']


def test_same_commander_then_theme_then_overlap_and_partner_cohorts(tmp_path):
    document = DeckDocument()
    document.deck.tags = ['spells']
    document.deck.entries = [DeckEntry('seed', 'Seed', oracle_id='seed')]
    cache = LibraryRecommendations(tmp_path / 'shared.sqlite3', document=document)
    cache.sync(Client(rows=[publication('exact'), publication('theme', commander='other', card='theme-card', tags=['spells']),
                            publication('unrelated', commander='third', card='unrelated')]))
    rows = cache.snapshot(['cmd'])['results']
    assert [r['oracle_id'] for r in rows] == ['spell', 'theme-card']
    assert cache.snapshot(['cmd', 'partner'])['results'][0]['oracle_id'] == 'theme-card'
    assert not cache.snapshot(['cmd'], exclude=['spell', 'theme-card'])['results']


def test_shared_evidence_is_bounded_and_can_supply_missing_candidates(tmp_path):
    cache = LibraryRecommendations(tmp_path / 'shared.sqlite3')
    cache.sync(Client())
    public = SimpleNamespace(source_id='edhrec', role='public', snapshot=lambda *a, **k:
                             dict(results=[dict(oracle_id='public', score=1)], sources=[]))
    rows = recommend([cache, public], ['cmd'])['results']
    assert [row['oracle_id'] for row in rows] == ['public', 'spell']
    assert rows[1]['score'] < 0.2
    assert rows[1]['source_evidence']['library']['shared_decks'] == 1
    assert recommend([cache], ['cmd'])['results']


def test_cancelled_listing_does_not_delete_cached_samples(tmp_path):
    cache, client = LibraryRecommendations(tmp_path / 'shared.sqlite3'), Client()
    cache.sync(client)
    from mtg_core.search.cancellation import SearchCancelled
    with pytest.raises(SearchCancelled):
        cache.sync(client, should_cancel=lambda: True)
    assert cache.snapshot(['cmd'])['results']
