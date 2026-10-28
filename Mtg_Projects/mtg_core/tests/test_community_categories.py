"""Offline/consent/transport regressions, executed by the existing CI suite."""
from copy import deepcopy
import json
import sqlite3
import uuid

import pytest

from mtg_core.categorization import (apply_categories, category_origin, classify,
                                     override_categories, refresh_automatic_categories)
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_core.library import LibraryError
from mtg_core.library.category_evidence import (CAPABILITY, CategoryEvidence, contribute,
                                               feed, manual_snapshot, refine)
from mtg_core.library.store import LibraryStore


ORACLE = str(uuid.UUID(int=1))
COMMANDER = str(uuid.UUID(int=2))


def document():
    doc = DeckDocument()
    doc.deck.format = 'Commander'
    doc.deck.entries = [DeckEntry('card', 'Example', oracle_id=ORACLE,
        extras={'facts': {'type_line': 'Creature', 'oracle_text': 'Draw two cards.'}})]
    return doc


def test_origins_roundtrip_and_only_deliberately_selected_primary_is_shared(tmp_path, monkeypatch):
    monkeypatch.setenv('PRINT_PROXY_PREP_DATA_DIR', str(tmp_path))
    doc = document()
    apply_categories(doc, {'card': classify({}, ['ramp', 'draw'])})
    assert category_origin(doc.deck.entries[0]) == 'automatic'
    override_categories(doc, {'card'}, {'auto:draw': False})
    assert manual_snapshot(doc)['assignments'] == []  # Removing a secondary role does not verify Ramp.
    from mtg_editor.organization import assign
    assign(doc, {'card'}, 'category', 'auto:draw')
    restored = DeckDocument.from_dict(doc.to_dict())
    assert category_origin(restored.deck.entries[0]) == 'manual'
    assert manual_snapshot(restored)['assignments'][0]['category'] == 'Draw'
    before = deepcopy(restored.deck.entries[0].to_dict())
    restored.editor_preferences['manual_themes'] = [{'roles': ['Tokens']}]
    refresh_automatic_categories(restored)
    apply_categories(restored, {'card': classify({}, ['ramp'])}, reconsider_manual=True)
    assert restored.deck.entries[0].to_dict() == before
    restored.deck.entries[0].extras['auto_categories'] = {'manual': True}
    assert category_origin(restored.deck.entries[0]) == 'unknown'
    assert manual_snapshot(restored)['assignments'] == []
    restored.deck.entries[0].extras.pop('auto_categories')
    apply_categories(restored, {'card': classify({}, ['ramp'])})
    assert restored.deck.entries[0].category_ids[0] == 'auto:draw'


def records(category='Draw', count=3):
    return [dict(author=f'author-{i}', deck=f'deck-{i}', category=category,
                 commanders=[COMMANDER], themes=['Tokens'], format='Commander', function='') for i in range(count)]


def ambiguous():
    return [dict(name='Ramp', score=100, layer='function', reason='mana'),
            dict(name='Draw', score=100, layer='function', reason='cards')]


def test_context_independence_thresholds_contradictions_and_bounded_function_priority():
    evidence = ambiguous()
    options = dict(commanders=[COMMANDER], format='Commander')
    assert refine(evidence, records(), **options)[0]['name'] == 'Draw'
    for sample in (records(count=1), records(count=2),
                   [{**r, 'author': 'one'} for r in records(count=20)],
                   [{**r, 'deck': 'copy'} for r in records(count=20)],
                   records() + records('Ramp'), records() + records('Ramp', 2)):
        assert refine(evidence, sample, **options)[0]['name'] == 'Ramp'
    assert refine(evidence, records(), format='Commander')[0]['name'] == 'Ramp'
    assert refine(evidence, records(), themes=['Tokens'], format='Commander')[0]['name'] == 'Draw'
    assert refine(evidence, records(), commanders=[COMMANDER], format='Modern')[0]['name'] == 'Ramp'
    strong = deepcopy(evidence)
    strong[0]['score'] = 150
    assert refine(strong, records(count=100), **options)[0]['name'] == 'Ramp'
    thematic = [evidence[0], dict(name='Tokens', layer='theme', score=10000, reason='theme')]
    assert refine(thematic, records('Tokens', 100), **options)[0]['name'] == 'Ramp'
    generic = [dict(name='Creatures', layer='type', score=10, reason='fallback')]
    assert refine(generic, records(), **options) == generic
    assert evidence == ambiguous()


class Client:
    server_id = str(uuid.UUID(int=3))
    token = 'session'

    def __init__(self):
        self.calls = 0
        self.fail = False
        self.capabilities = [CAPABILITY]

    def check(self):
        return {'capabilities': self.capabilities}

    def request(self, *args, **kwargs):
        self.calls += 1
        if self.fail:
            raise LibraryError(503, 'offline')
        return {'version': 'v1', 'records': [dict(author='author', deck='deck', commanders=[COMMANDER],
            format='Commander', themes=['Tokens'], assignments=[{'oracle': ORACLE, 'category': 'Draw'}])],
            'next': None}


def test_daily_refresh_atomic_failure_offline_and_disconnect(tmp_path):
    cache, client = CategoryEvidence(tmp_path / 'cache.sqlite3'), Client()
    assert cache.consent(client.server_id) is False
    cache.sync(client)
    assert client.calls == 1
    cache.sync(client)
    assert client.calls == 1
    before = cache.for_cards([ORACLE])
    assert before[ORACLE][0]['category'] == 'Draw'
    client.fail = True
    with pytest.raises(LibraryError):
        cache.sync(client, force=True)
    assert cache.for_cards([ORACLE]) == before
    cache.sync(client)  # Failed attempts are throttled too.
    assert client.calls == 2
    cache.consent(client.server_id, True)
    cache.revoke(client.server_id)
    assert cache.for_cards([ORACLE]) == {}
    assert not cache.consent(client.server_id)


def test_refresh_does_not_edit_decks_and_editor_uses_only_local_cache(tmp_path, monkeypatch):
    monkeypatch.setenv('PRINT_PROXY_PREP_DATA_DIR', str(tmp_path))
    doc = document()
    before = doc.to_dict()
    cache = CategoryEvidence(tmp_path / 'library-category-evidence.sqlite3')
    cache.sync(Client())
    assert doc.to_dict() == before
    # Transport is forbidden throughout categorization, including manual refresh.
    monkeypatch.setattr(Client, 'request', lambda *a, **k: pytest.fail('network during editing'))
    refresh_automatic_categories(doc)
    assert doc.deck.entries[0].category_ids[0] == 'auto:draw'
    with sqlite3.connect(cache.path) as db:
        db.execute('DROP TABLE evidence')
    refresh_automatic_categories(doc)  # Damaged optional cache is also harmless.


def test_server_owner_visibility_revisions_dedup_and_compact_payload(tmp_path, monkeypatch):
    monkeypatch.setattr('mtg_core.library.store.PASSWORD_ROUNDS', 1)
    store = LibraryStore(tmp_path / 'server')
    store.initialize('Friends', 'admin', 'a sufficiently long password')
    owner = store.login('admin', 'a sufficiently long password')
    store.register(store.invite(owner), 'friend', 'another sufficiently long password')
    friend = store.login('friend', 'another sufficiently long password')
    doc = document()
    published = store.publish(owner, doc.deck.to_dict(), [])
    snapshot = {'assignments': [{'oracle': ORACLE, 'category': 'Draw'}], 'themes': ['Tokens']}
    with pytest.raises(LibraryError):
        contribute(store, friend, published['deck_id'], 1, snapshot)
    contribute(store, owner, published['deck_id'], 1, snapshot)
    contribute(store, owner, published['deck_id'], 1, snapshot)
    page = feed(store, friend)
    assert len(page['records']) == 1
    assert 'Example' not in json.dumps(page)
    assert 'entries' not in json.dumps(page)
    assert feed(store, friend, version=page['version'])['unchanged'] is True
    with pytest.raises(LibraryError):
        contribute(store, owner, published['deck_id'], 0, snapshot)
    store.publish(owner, doc.deck.to_dict(), [], deck_id=published['deck_id'], expected_revision=1)
    assert feed(store, friend)['records'] == []  # Stale revision evidence cannot survive edits.
    contribute(store, owner, published['deck_id'], 2, snapshot)
    store.unpublish(owner, published['deck_id'], 2)
    assert feed(store, friend)['records'] == []
