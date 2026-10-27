"""Offline follows, explicit synchronization and personal state isolation for CI."""
from copy import deepcopy
import json
import sqlite3
import threading
import uuid

import pytest

from mtg_core.decks import Deck, DeckDocument, DeckEntry, DeckStore
from mtg_core.downloads import DownloadCancelled
from mtg_core.library import LibraryError
from mtg_core.library.client import LibraryConnections, copy_publication
from mtg_core.library.following import FollowedDecks


@pytest.fixture
def setup(tmp_path):
    connections = LibraryConnections(tmp_path)
    follows = FollowedDecks(connections)
    server_id = str(uuid.uuid4())
    publication = {'deck_id': str(uuid.uuid4()), 'revision': 1, 'owner': 'friend', 'color_identity': ['U'],
        'deck': Deck(name='Shared', entries=[DeckEntry('one', 'Card', card_id='print-1', oracle_id='oracle-1')]).to_dict()}
    follows.add(publication, server_id=server_id, address='https://friend.invalid', name='Friends')
    return connections, follows, server_id, publication


class Client:
    def __init__(self, server_id, publication):
        self.server_id, self.value = server_id, publication
        self.error = None
        self.calls = 0
    def check(self):
        if self.error and self.error.status == 503:
            raise self.error
    def download(self, deck_id):
        self.calls += 1
        if self.error:
            raise self.error
        return self.value


def newer(publication, revision=2):
    result = deepcopy(publication)
    result['revision'] = revision
    result['deck']['name'] = f'New revision {revision}'
    result['deck']['entries'].append(DeckEntry('new', 'New card', card_id='new-print').to_dict())
    return result


def test_check_only_stages_and_accept_preserves_all_local_print_metadata(setup):
    connections, follows, server_id, publication = setup
    record = follows.get(server_id, publication['deck_id'])
    local_id = record['local_id']
    document = record['document']
    entry = document.deck.entries[0]
    entry.owned, entry.do_not_print = 3, True
    entry.oversized = True
    entry.extras.update(print_status='Printed', future_print_state={'pending_copies': 2})
    document.print_settings['local'] = True
    document.editor_preferences['local'] = 'value'
    with connections.db() as db:
        db.execute('UPDATE followed_decks SET document=?', (json.dumps(document.to_dict()),))
    client = Client(server_id, newer(publication))
    follows.check(client)
    assert follows.get(server_id, publication['deck_id'])['revision'] == 1
    reviewed = follows.review(server_id, publication['deck_id'])
    accepted = follows.accept(server_id, publication['deck_id'], reviewed['fingerprint'])
    assert accepted['revision'] == 2 and accepted['pending'] is None
    assert accepted['local_id'] == local_id == accepted['document'].deck.deck_id
    kept, added = accepted['document'].deck.entries
    assert kept.extras == entry.extras and kept.oversized is True
    assert kept.owned == 3 and kept.do_not_print is True
    assert added.extras == {} and not added.do_not_print and added.owned == 0
    assert accepted['document'].print_settings == {'local': True}
    assert accepted['document'].editor_preferences == {'local': 'value'}
    with connections.db() as db:
        previous = DeckDocument.from_dict(json.loads(db.execute('SELECT document FROM followed_history').fetchone()[0]))
        assert previous.deck.entries[0].extras['print_status'] == 'Printed'


@pytest.mark.parametrize('status', [401, 403, 404, 503])
def test_unavailable_source_keeps_offline_cache_and_pending_update(setup, status):
    connections, follows, server_id, publication = setup
    client = Client(server_id, newer(publication))
    follows.check(client)
    before = follows.get(server_id, publication['deck_id'])
    client.error = LibraryError(status, 'Source unavailable')
    follows.check(client)
    reopened = FollowedDecks(connections)
    after = reopened.get(server_id, publication['deck_id'])
    assert after['document'].to_dict() == before['document'].to_dict()
    assert after['pending'] == before['pending']
    assert after['state'] in ('offline', 'unavailable')
    assert 'Source unavailable' in after['message']


def test_changed_staged_revision_requires_another_review(setup):
    _, follows, server_id, publication = setup
    client = Client(server_id, newer(publication))
    follows.check(client)
    old_review = follows.review(server_id, publication['deck_id'])
    client.value = newer(publication, 3)
    follows.check(client)
    with pytest.raises(LibraryError, match='Review it again'):
        follows.accept(server_id, publication['deck_id'], old_review['fingerprint'])
    assert follows.get(server_id, publication['deck_id'])['revision'] == 1


def test_local_content_edits_are_never_silently_overwritten(setup):
    connections, follows, server_id, publication = setup
    client = Client(server_id, newer(publication))
    follows.check(client)
    record = follows.get(server_id, publication['deck_id'])
    record['document'].deck.entries[0].quantity = 99
    with connections.db() as db:
        db.execute('UPDATE followed_decks SET document=?', (json.dumps(record['document'].to_dict()),))
    with pytest.raises(LibraryError, match='local content changes'):
        follows.accept(server_id, publication['deck_id'], follows.review(server_id, publication['deck_id'])['fingerprint'])
    assert follows.get(server_id, publication['deck_id'])['document'].deck.entries[0].quantity == 99


def test_failed_transaction_preserves_accepted_copy_and_staged_update(setup):
    connections, follows, server_id, publication = setup
    follows.check(Client(server_id, newer(publication)))
    before = follows.get(server_id, publication['deck_id'])
    with connections.db() as db:
        db.execute("CREATE TRIGGER fail_accept BEFORE UPDATE OF document ON followed_decks BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
    with pytest.raises(sqlite3.Error):
        follows.accept(server_id, publication['deck_id'], follows.review(server_id, publication['deck_id'])['fingerprint'])
    after = follows.get(server_id, publication['deck_id'])
    assert after['revision'] == 1 and after['document'].to_dict() == before['document'].to_dict()
    assert after['pending'] == before['pending']
    with connections.db() as db:
        assert db.execute('SELECT COUNT(*) FROM followed_history').fetchone()[0] == 0


def test_source_rollback_and_changed_immutable_revision_keep_previous_data(setup):
    _, follows, server_id, publication = setup
    client = Client(server_id, newer(publication, 3))
    follows.check(client)
    staged = follows.get(server_id, publication['deck_id'])['pending']
    client.value = newer(publication, 2)
    follows.check(client)
    assert follows.get(server_id, publication['deck_id'])['state'] == 'source_changed'
    assert follows.get(server_id, publication['deck_id'])['pending'] == staged
    client.value = deepcopy(staged)
    client.value['deck']['description'] = 'Changed without a revision'
    follows.check(client)
    assert follows.get(server_id, publication['deck_id'])['pending'] == staged


def test_sources_are_namespaced_and_stopping_keeps_an_independent_offline_cache(setup, tmp_path):
    connections, follows, first, publication = setup
    second = str(uuid.uuid4())
    follows.add(publication, server_id=second, address='https://second.invalid', name='Other')
    assert len(follows.list()) == 2
    assert follows.get(first, publication['deck_id'])['local_id'] != follows.get(second, publication['deck_id'])['local_id']
    follows.stop(first, publication['deck_id'])
    client = Client(first, newer(publication))
    follows.check(client)
    assert client.calls == 0
    cached = follows.get(first, publication['deck_id'])
    copied = copy_publication(follows.publication(cached), server_id=first,
                             server_address=cached['server_url'], deck_root=tmp_path / 'decks')
    assert DeckStore().load(copied).deck.deck_id != cached['local_id']
    assert follows.get(second, publication['deck_id'])['active'] == 1
    follows.add(newer(publication), server_id=first, address='https://friend.invalid', name='Friends')
    assert follows.get(first, publication['deck_id'])['revision'] == 1  # Re-follow stages, never overwrites.
    assert follows.get(first, publication['deck_id'])['pending']['revision'] == 2


def test_history_is_bounded_and_automatic_checks_default_off(setup):
    connections, follows, server_id, publication = setup
    assert not follows.auto_check(server_id)
    follows.auto_check(server_id, True)
    assert FollowedDecks(connections).auto_check(server_id)
    for revision in range(2, 9):
        follows.check(Client(server_id, newer(publication, revision)))
        follows.accept(server_id, publication['deck_id'], follows.review(server_id, publication['deck_id'])['fingerprint'])
    with connections.db() as db:
        assert db.execute('SELECT COUNT(*) FROM followed_history').fetchone()[0] == 5
    event = threading.Event()
    event.set()
    with pytest.raises(DownloadCancelled):
        follows.check(Client(server_id, publication), cancel=event)
