"""Durable publication tracking never changes the user's local deck."""
from copy import deepcopy
import uuid

import pytest

from mtg_core.decks import Deck, DeckEntry
from mtg_core.library import LibraryError
from mtg_core.library.client import LibraryConnections
from mtg_core.library.publishing import PublicationJournal, suggested_colors


@pytest.fixture
def snapshot():
    return Deck(name='My deck', entries=[DeckEntry(entry_id='card', name='Card',
                owned=9, do_not_print=True, extras={'print_status': 'Printed',
                                                  'facts': {'color_identity': ['U']}})]).to_dict()


class Client:
    def __init__(self):
        self.server_id = str(uuid.uuid4())
        self.account_id = str(uuid.uuid4())
        self.remote_id = str(uuid.uuid4())
        self.operations = []
        self.fail_after_upload = False

    def publish_operation(self, operation):
        self.operations.append(deepcopy(operation))
        if self.fail_after_upload:
            self.fail_after_upload = False
            raise LibraryError(503, 'Response interrupted')
        return {'deck_id': operation['deck_id'] or self.remote_id,
                'revision': operation['expected_revision'] + (operation['kind'] == 'publish')}


def test_manual_evidence_requires_consent_and_retries_as_one_batch(tmp_path, snapshot):
    from mtg_core.library.category_evidence import CategoryEvidence, CAPABILITY
    journal, client = PublicationJournal(LibraryConnections(tmp_path)), Client()
    cache = CategoryEvidence(tmp_path / 'library-category-evidence.sqlite3')
    calls = []
    client.check = lambda: {'capabilities': [CAPABILITY]}
    def upload(method, path, body):
        calls.append((method, path, deepcopy(body)))
        if len(calls) == 1:
            raise LibraryError(503, 'Interrupted after publishing')
        return {}
    client.request = upload
    evidence = {'assignments': [{'oracle': str(uuid.UUID(int=1)), 'category': 'Draw'}], 'themes': ['Tokens']}
    local_id = snapshot['deck_id']
    journal.send(client, client.server_id, local_id, deck=snapshot, color_identity=[], community=evidence)
    assert calls == []
    cache.consent(client.server_id, True)
    with pytest.raises(LibraryError):
        journal.send(client, client.server_id, local_id, deck=snapshot, color_identity=[], community=evidence)
    pending = journal.get(client.server_id, local_id)['pending']
    assert len(pending['community']['assignments']) == 1
    journal.send(client, client.server_id, local_id, deck=snapshot, color_identity=[], community={'assignments': []})
    assert calls[0] == calls[1]
    assert journal.get(client.server_id, local_id)['pending'] is None
    cache.consent(client.server_id, False)
    journal.send(client, client.server_id, local_id, deck=snapshot, color_identity=[], community=evidence)
    assert len(calls) == 2


def test_pending_snapshot_survives_restart_and_ignores_later_edits(tmp_path, snapshot):
    client = Client()
    journal = PublicationJournal(LibraryConnections(tmp_path))
    local_id, original = snapshot['deck_id'], deepcopy(snapshot)
    client.fail_after_upload = True
    with pytest.raises(LibraryError):
        journal.send(client, client.server_id, local_id, deck=snapshot, color_identity=['U'])
    pending = journal.get(client.server_id, local_id)['pending']
    assert pending['deck']['name'] == 'My deck'
    assert 'owned' not in pending['deck']['entries'][0]
    assert 'print_status' not in pending['deck']['entries'][0]
    assert snapshot == original
    snapshot['name'] = 'Later local edit'
    reopened = PublicationJournal(LibraryConnections(tmp_path))
    result = reopened.send(client, client.server_id, local_id, deck=snapshot, color_identity=['R'])
    assert result['revision'] == 1
    assert client.operations[0] == client.operations[1]
    link = reopened.get(client.server_id, local_id)
    assert link['deck_id'] == client.remote_id and link['pending'] is None
    assert link['published'] == 1
    reopened.send(client, client.server_id, local_id, deck=snapshot, color_identity=['R'])
    assert client.operations[-1]['deck']['name'] == 'Later local edit'
    assert client.operations[-1]['expected_revision'] == 1
    assert client.operations[-1]['deck_id'] == client.remote_id


def test_library_links_remain_separate_and_survive_connection_removal(tmp_path, snapshot):
    connections = LibraryConnections(tmp_path)
    journal = PublicationJournal(connections)
    first, second = Client(), Client()
    first.url, second.url = 'https://first.invalid', 'https://second.invalid'
    connection = connections.add(first, {'server_id': first.server_id, 'name': 'First'})
    local_id = snapshot['deck_id']
    one = journal.send(first, first.server_id, local_id, deck=snapshot, color_identity=[])
    two = journal.send(second, second.server_id, local_id, deck=snapshot, color_identity=[])
    assert one['deck_id'] != two['deck_id']
    connections.remove(connection['id'])
    assert journal.get(first.server_id, local_id)['deck_id'] == one['deck_id']
    assert journal.get(second.server_id, local_id)['deck_id'] == two['deck_id']
    with pytest.raises(LibraryError, match='original library'):
        journal.send(first, second.server_id, local_id, deck=snapshot, color_identity=[])


def test_unpublish_and_republish_keep_same_remote_identity(tmp_path, snapshot):
    journal, client = PublicationJournal(LibraryConnections(tmp_path)), Client()
    local_id = snapshot['deck_id']
    published = journal.send(client, client.server_id, local_id, deck=snapshot, color_identity=[])
    removed = journal.send(client, client.server_id, local_id, unpublish=True)
    assert removed == published
    assert journal.get(client.server_id, local_id)['published'] == 0
    again = journal.send(client, client.server_id, local_id, deck=snapshot, color_identity=[])
    assert again['deck_id'] == published['deck_id'] and again['revision'] == 2


def test_conflict_review_explicitly_replaces_base_and_clears_pending_only(tmp_path, snapshot):
    journal, client = PublicationJournal(LibraryConnections(tmp_path)), Client()
    local_id = snapshot['deck_id']
    journal.send(client, client.server_id, local_id, deck=snapshot, color_identity=[])
    journal.begin(client.server_id, local_id, client.account_id, deck=snapshot, color_identity=[])
    publication = {'deck_id': client.remote_id, 'revision': 5, 'owner': 'friend',
                   'color_identity': [], 'deck': deepcopy(snapshot)}
    publication['deck']['name'] = 'A remote edit'
    before = deepcopy(snapshot)
    journal.accept_reviewed_revision(client.server_id, local_id, publication)
    assert snapshot == before
    assert journal.get(client.server_id, local_id)['pending'] is None
    journal.send(client, client.server_id, local_id, deck=snapshot, color_identity=[])
    assert client.operations[-1]['expected_revision'] == 5
    assert client.operations[-1]['deck']['name'] == 'My deck'
    publication['deck_id'] = str(uuid.uuid4())
    with pytest.raises(LibraryError, match='does not match'):
        journal.accept_reviewed_revision(client.server_id, local_id, publication)


def test_pending_operations_cannot_be_changed_into_other_actions(tmp_path, snapshot):
    journal = PublicationJournal(LibraryConnections(tmp_path))
    server_id, local_id = str(uuid.uuid4()), snapshot['deck_id']
    account_id = str(uuid.uuid4())
    with pytest.raises(LibraryError):
        journal.begin(server_id, local_id, account_id, unpublish=True)
    pending = journal.begin(server_id, local_id, account_id, deck=snapshot, color_identity=[])
    with pytest.raises(LibraryError):
        journal.begin(server_id, local_id, account_id, unpublish=True)
    assert journal.get(server_id, local_id)['pending'] == pending
    with pytest.raises(LibraryError, match='another account'):
        journal.begin(server_id, local_id, str(uuid.uuid4()), deck=snapshot, color_identity=[])


def test_suggested_colors_use_existing_local_card_facts(snapshot):
    assert suggested_colors(Deck.from_dict(snapshot)) == 'U'
    assert suggested_colors(Deck()) == 'C'


def test_local_master_coalesces_saves_and_updates_same_publication(tmp_path, snapshot):
    journal, client = PublicationJournal(LibraryConnections(tmp_path)), Client()
    local_id = snapshot['deck_id']
    original = journal.send(client, client.server_id, local_id, deck=snapshot, color_identity=['U'])
    assert journal.queue_master(local_id, deck=snapshot, color_identity=['U']) == 0
    snapshot['name'] = 'First edit'
    assert journal.queue_master(local_id, deck=snapshot, color_identity=['U']) == 1
    snapshot['name'] = 'Latest edit'
    journal.queue_master(local_id, deck=snapshot, color_identity=['U'])
    restarted = PublicationJournal(LibraryConnections(tmp_path))
    queued = restarted.queued_masters()
    assert len(queued) == 1
    assert queued[0]['snapshot']['deck']['name'] == 'Latest edit'
    assert 'owned' not in queued[0]['snapshot']['deck']['entries'][0]
    updated = restarted.send(client, client.server_id, local_id, **queued[0]['snapshot'])
    assert updated['deck_id'] == original['deck_id']
    assert updated['revision'] == original['revision'] + 1
    assert restarted.queued_masters() == []


def test_initial_offline_upload_keeps_latest_master_behind_safe_retry(tmp_path, snapshot):
    journal, client = PublicationJournal(LibraryConnections(tmp_path)), Client()
    local_id = snapshot['deck_id']
    client.fail_after_upload = True
    with pytest.raises(LibraryError):
        journal.send(client, client.server_id, local_id, deck=snapshot, color_identity=['U'])
    first = deepcopy(client.operations[0])
    snapshot['name'] = 'Newer local edit'
    journal.queue_master(local_id, deck=snapshot, color_identity=['U'])
    queued = journal.queued_masters()[0]
    journal.send(client, client.server_id, local_id, **queued['snapshot'])
    assert client.operations[1] == first
    queued = journal.queued_masters()[0]
    journal.send(client, client.server_id, local_id, **queued['snapshot'])
    assert client.operations[2]['deck']['name'] == 'Newer local edit'
    assert client.operations[2]['deck_id'] == client.remote_id
    assert not journal.queued_masters()


def test_pause_and_unpublish_stop_automatic_master_updates(tmp_path, snapshot):
    journal, client = PublicationJournal(LibraryConnections(tmp_path)), Client()
    local_id = snapshot['deck_id']
    journal.send(client, client.server_id, local_id, deck=snapshot, color_identity=['U'])
    journal.pause_master(client.server_id, local_id)
    snapshot['name'] = 'Local only while paused'
    journal.queue_master(local_id, deck=snapshot, color_identity=['U'])
    assert not journal.queued_masters()
    journal.send(client, client.server_id, local_id, deck=snapshot, color_identity=['U'])
    assert not journal.queued_masters()
    journal.send(client, client.server_id, local_id, unpublish=True)
    snapshot['name'] = 'Unpublished edits'
    assert journal.queue_master(local_id, deck=snapshot, color_identity=['U']) == 0
