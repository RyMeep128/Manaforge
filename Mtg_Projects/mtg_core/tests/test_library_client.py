"""Client security, session isolation and local-copy regressions for CI."""
import io
import json
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
import uuid

import pytest

from mtg_core.decks import Deck, DeckDocument, DeckEntry, DeckStore
from mtg_core.library import LibraryError
from mtg_core.library.client import (
    LibraryClient, LibraryConnections, MAX_RESPONSE, _NoRedirects, copy_publication, server_url,
)


SERVER_ID = str(uuid.uuid4())
DECK_ID = str(uuid.uuid4())


class Response(io.BytesIO):
    def read1(self, size):
        return self.read(size)


class Opener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return Response(value if isinstance(value, bytes) else json.dumps({'api_version': 1, **value}).encode())


def publication():
    return {'deck_id': DECK_ID, 'revision': 2, 'owner': 'friend', 'color_identity': ['U'],
            'deck': Deck(name='Shared deck', description='Description', tags=['theme'],
                         commander_entry_ids=['cmdr'],
                         entries=[DeckEntry(entry_id='cmdr', name='Commander', card_id='printing',
                                            oracle_id='oracle', quantity=1, set_code='abc',
                                            collector_number='123')]).to_dict()}


@pytest.mark.parametrize('url', [
    'http://public.example', 'http://8.8.8.8', 'http://0.0.0.0', 'http://[::]',
    'http://224.0.0.1', 'http://127.0.0.1', 'ftp://private.example',
    'https://username:password@host', 'https://host/path', 'https://host?token=secret',
    'https://host#fragment', 'https://host:0', 'https://host:999999', 'https://host\n',
    'https://host\\path', 'http://host.local',
])
def test_insecure_or_ambiguous_urls_are_rejected_by_default(url):
    with pytest.raises(LibraryError):
        server_url(url)


def test_lan_http_requires_explicit_consent_and_literal_private_address():
    assert server_url('http://192.168.1.2:8771/', allow_lan=True) == 'http://192.168.1.2:8771'
    assert server_url('http://[::1]:8771', allow_lan=True) == 'http://[::1]:8771'
    assert server_url('https://EXAMPLE.invalid/') == 'https://example.invalid'
    for value in ('http://8.8.8.8', 'http://host.local', 'http://0.0.0.0'):
        with pytest.raises(LibraryError):
            server_url(value, allow_lan=True)


def test_identity_pin_prevents_sending_credentials_to_replaced_library():
    opener = Opener({'server_id': str(uuid.uuid4()), 'name': 'Unexpected'})
    client = LibraryClient('https://library.invalid', server_id=SERVER_ID, opener=opener)
    with pytest.raises(LibraryError, match='different library'):
        client.login('friend', 'password that must not be sent')
    assert len(opener.requests) == 1
    assert opener.requests[0].data is None
    assert not opener.requests[0].has_header('Authorization')


def test_credentials_and_bearer_tokens_are_isolated_between_libraries():
    info = {'server_id': SERVER_ID, 'name': 'Friends'}
    first = Opener(info, {'token': 'a' * 43}, {'decks': [publication()]}, {})
    client = LibraryClient('https://first.invalid', opener=first)
    assert client.login('friend', 'long enough password')['server_id'] == SERVER_ID
    assert client.browse({'owner': 'friend'})[0]['deck_id'] == DECK_ID
    assert first.requests[-1].get_header('Authorization') == 'Bearer ' + 'a' * 43
    assert not first.requests[1].has_header('Authorization')
    assert 'password' not in first.requests[1].full_url
    other = LibraryClient('https://second.invalid', opener=Opener())
    with pytest.raises(LibraryError, match='Sign in'):
        other.browse()
    client.disconnect()
    assert client.token is None


def test_untrusted_responses_errors_and_disconnect_failure():
    for response in (b'[]', b'{broken', b'{"api_version": 2}', b'{"api_version": true}',
                     b'x' * (MAX_RESPONSE + 1)):
        client = LibraryClient('https://library.invalid', opener=Opener(response))
        with pytest.raises(LibraryError):
            client.check()
    error = HTTPError('https://library.invalid', 401, 'sensitive server detail', {}, io.BytesIO())
    client = LibraryClient('https://library.invalid', opener=Opener(error))
    client.token = 'a' * 43
    with pytest.raises(LibraryError) as caught:
        client.browse()
    assert 'sensitive' not in str(caught.value)
    assert client.token is None
    client.opener = Opener(URLError('private connection details'))
    client.token = 'b' * 43
    with pytest.raises(LibraryError, match='Cannot reach'):
        client.disconnect()
    assert client.token is None


def test_redirects_never_forward_authentication():
    handler = _NoRedirects()
    assert handler.redirect_request(None, None, 302, '', {}, 'https://other.invalid') is None


def test_publication_requires_server_retry_capability_before_upload():
    opener = Opener({'server_id': SERVER_ID, 'name': 'Older server'})
    client = LibraryClient('https://library.invalid', server_id=SERVER_ID, opener=opener)
    client.token = 'a' * 43
    with pytest.raises(LibraryError, match='Upgrade'):
        client.publish_operation({'kind': 'publish', 'operation_id': str(uuid.uuid4()),
                                  'expected_revision': 0, 'deck': publication()['deck'], 'color_identity': []})
    assert len(opener.requests) == 1
    assert opener.requests[0].get_method() == 'GET'


def test_saved_connections_contain_no_secrets_and_removal_preserves_other_libraries(tmp_path):
    connections = LibraryConnections(tmp_path)
    client = SimpleNamespace(url='https://first.invalid', token='secret token', password='secret password')
    first = connections.add(client, {'server_id': SERVER_ID, 'name': 'First'})
    second = connections.add(SimpleNamespace(url='https://second.invalid'),
                             {'server_id': str(uuid.uuid4()), 'name': 'Second'})
    with pytest.raises(LibraryError):
        connections.add(client, {'server_id': SERVER_ID, 'name': 'Duplicate'})
    reopened = LibraryConnections(tmp_path)
    assert len(reopened.list()) == 2
    assert b'secret token' not in connections.path.read_bytes()
    assert b'secret password' not in connections.path.read_bytes()
    assert set(reopened.list()[0]) == {'id', 'url', 'name', 'server_id', 'allow_lan'}
    reopened.remove(first['id'])
    assert reopened.list()[0]['id'] == second['id']


def test_copy_uses_existing_deck_format_and_new_identity_without_private_data(tmp_path):
    value = publication()
    value['deck']['entries'][0].update(owned=5, do_not_print=True, print_status='Printed',
                                       image_asset_id='../../private', image_url='http://private.invalid')
    value['deck']['print_settings'] = {'private': True}
    first = copy_publication(value, server_id=SERVER_ID, server_address='https://library.invalid', deck_root=tmp_path)
    second = copy_publication(value, server_id=SERVER_ID, server_address='https://library.invalid', deck_root=tmp_path)
    document = DeckStore().load(first)
    assert isinstance(document, DeckDocument)
    assert document.deck.deck_id not in (DECK_ID, DeckStore().load(second).deck.deck_id)
    assert first.name == document.deck.deck_id + '.manaforge.json'
    assert document.deck.name == 'Shared deck'
    assert document.deck.commander_entry_ids == ['cmdr']
    entry = document.deck.entries[0]
    assert (entry.card_id, entry.oracle_id, entry.set_code, entry.collector_number) == ('printing', 'oracle', 'abc', '123')
    assert entry.owned == 0 and not entry.do_not_print
    assert entry.image_asset_id is None
    assert 'print_status' not in entry.extras
    assert document.print_settings == {}
    assert document.deck.extras['library_source']['kind'] == 'independent_copy'
    # Editing and reopening needs no server or sign-in.
    document.deck.name = 'My independent edit'
    DeckStore().save(first, document)
    assert DeckStore().load(first).deck.name == 'My independent edit'


def test_copy_write_failure_leaves_existing_decks_intact(tmp_path):
    existing = tmp_path / 'existing.manaforge.json'
    DeckStore().save(existing, DeckDocument())
    before = existing.read_bytes()
    class FailingStore:
        def save(self, path, document):
            raise OSError('Disk full')
    with pytest.raises(OSError):
        copy_publication(publication(), server_id=SERVER_ID, server_address='https://library.invalid',
                         deck_root=tmp_path, store=FailingStore())
    assert existing.read_bytes() == before


def test_untrusted_publication_paths_and_wrong_deck_are_rejected():
    value = publication()
    value['deck_id'] = '../../private'
    with pytest.raises(LibraryError):
        LibraryClient.publication(value)
    client = LibraryClient('https://library.invalid', opener=Opener({'publication': publication()}))
    client.token = 'a' * 43
    with pytest.raises(LibraryError, match='wrong deck'):
        client.download(str(uuid.uuid4()))


def test_client_and_server_contract_end_to_end_without_network(tmp_path, monkeypatch):
    from urllib.parse import urlsplit
    from mtg_core.library.api import LibraryAPI
    from mtg_core.library.store import LibraryStore
    monkeypatch.setattr('mtg_core.library.store.PASSWORD_ROUNDS', 1000)
    store = LibraryStore(tmp_path / 'hosted')
    password = 'a sufficiently long password'
    store.initialize('Friends', 'administrator', password)
    admin = store.login('administrator', password)
    published = store.publish(admin, publication()['deck'], ['U'])
    invitation = store.invite(admin)
    app = LibraryAPI(store)
    class WSGIOpener:
        def open(self, request, timeout):
            parsed = urlsplit(request.full_url)
            data = request.data or b''
            env = {'PATH_INFO': parsed.path, 'QUERY_STRING': parsed.query,
                   'REQUEST_METHOD': request.method, 'CONTENT_LENGTH': str(len(data)),
                   'CONTENT_TYPE': 'application/json', 'wsgi.input': io.BytesIO(data),
                   'HTTP_AUTHORIZATION': request.get_header('Authorization', ''),
                   'REMOTE_ADDR': '127.0.0.1'}
            status = []
            raw = b''.join(app(env, lambda code, headers: status.append(int(code.split()[0]))))
            if status[0] >= 400:
                raise HTTPError(request.full_url, status[0], 'error', {}, Response(raw))
            return Response(raw)
    client = LibraryClient('https://library.invalid', opener=WSGIOpener())
    assert client.login('friend', password, invitation=invitation)['name'] == 'Friends'
    rows = client.browse({'commander': 'Commander', 'color': 'U', 'owner': 'administrator'})
    assert len(rows) == 1
    assert rows[0]['deck_id'] == published['deck_id']
    downloaded = client.download(published['deck_id'])
    copied = copy_publication(downloaded, server_id=client.server_id, server_address=client.url,
                              deck_root=tmp_path / 'decks')
    from mtg_core.library.publishing import PublicationJournal
    journal = PublicationJournal(LibraryConnections(tmp_path / 'client'))
    local = DeckStore().load(copied).deck
    # Simulate a dropped response after the server commits a create.
    class InterruptedOpener(WSGIOpener):
        interrupt = True
        def open(self, request, timeout):
            response = super().open(request, timeout)
            if self.interrupt and request.method == 'POST' and urlsplit(request.full_url).path.endswith('/decks'):
                self.interrupt = False
                response.close()
                raise URLError('Response interrupted after upload')
            return response
    client.opener = InterruptedOpener()
    with pytest.raises(LibraryError):
        journal.send(client, client.server_id, local.deck_id, deck=local.to_dict(), color_identity=['U'])
    recovered = journal.send(client, client.server_id, local.deck_id, deck=local.to_dict(), color_identity=['U'])
    assert len(client.browse({'owner': 'friend'})) == 1
    assert recovered['revision'] == 1
    local.name = 'Explicitly updated'
    updated = journal.send(client, client.server_id, local.deck_id, deck=local.to_dict(), color_identity=['U'])
    assert updated['deck_id'] == recovered['deck_id'] and updated['revision'] == 2
    journal.send(client, client.server_id, local.deck_id, unpublish=True)
    assert client.browse({'owner': 'friend'}) == []
    client.disconnect()
    assert DeckStore().load(copied).deck.name == 'Shared deck'
