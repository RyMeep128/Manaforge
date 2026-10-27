"""Security and API regressions for CI; no external services or network required."""
from copy import deepcopy
import io
import json

import pytest

from mtg_core.decks import Deck, DeckCategory, DeckEntry
from mtg_core.library import LibraryError
from mtg_core.library.api import LibraryAPI
from mtg_core.library.payload import MAX_BODY, shared_deck
from mtg_core.library.store import LibraryStore, digest


PASSWORD = 'a sufficiently long test password'


@pytest.fixture
def library(tmp_path, monkeypatch):
    # Exercise the real hashing implementation without paying production KDF cost in every fixture.
    monkeypatch.setattr('mtg_core.library.store.PASSWORD_ROUNDS', 1000)
    store = LibraryStore(tmp_path / 'private')
    store.initialize('Friends', 'admin', PASSWORD)
    admin = store.login('admin', PASSWORD)
    user_id = store.register(store.invite(admin), 'friend', PASSWORD)
    friend = store.login('friend', PASSWORD)
    return store, admin, friend, user_id


@pytest.fixture
def deck():
    return Deck(name='Artifacts', description='A shared deck', tags=['theme'],
                entries=[DeckEntry(entry_id='commander', name='Example Commander', quantity=1,
                                   card_id='printing-id', oracle_id='oracle-id', set_code='abc',
                                   collector_number='12', category_ids=['ramp'], tags=['mana'])],
                categories=[DeckCategory('ramp', 'Ramp')],
                commander_entry_ids=['commander']).to_dict()


def request(app, path, method='GET', body=None, token='', query='', raw=None, **extra):
    data = raw if raw is not None else json.dumps(body or {}).encode()
    env = {'PATH_INFO': path, 'REQUEST_METHOD': method, 'QUERY_STRING': query,
           'CONTENT_TYPE': 'application/json', 'CONTENT_LENGTH': str(len(data)),
           'wsgi.input': io.BytesIO(data), 'REMOTE_ADDR': '127.0.0.1',
           'HTTP_AUTHORIZATION': 'Bearer ' + token, **extra}
    response = {}
    def start(status, headers):
        response['status'] = int(status.split()[0])
        response['headers'] = dict(headers)
    response['body'] = json.loads(b''.join(app(env, start)))
    return response


def test_projection_strips_all_private_fields_without_mutating_source(deck):
    deck.update(print_status='Printed', playtest_notes='private',
                print_settings={'private': True}, arbitrary={'token': 'secret'})
    deck['entries'][0].update(owned=7, do_not_print=True, print_status='Printed',
                              image_asset_id='../../private', image_url='http://private/',
                              art_override={'path': 'C:/private'}, arbitrary='secret')
    original = deepcopy(deck)
    result = shared_deck(deck)
    assert deck == original
    assert set(result) == {'deck_id', 'name', 'format', 'description', 'tags',
                           'commander_entry_ids', 'entries', 'categories'}
    entry = result['entries'][0]
    assert entry['card_id'] == 'printing-id'
    assert entry['collector_number'] == '12'
    assert entry['category_ids'] == ['ramp']
    for key in ('owned', 'do_not_print', 'print_status', 'image_asset_id', 'image_url', 'art_override', 'arbitrary'):
        assert key not in entry


@pytest.mark.parametrize('change', [
    lambda d: d.update(entries='invalid'),
    lambda d: d['entries'][0].update(quantity=-1),
    lambda d: d['entries'][0].update(quantity=True),
    lambda d: d['entries'][0].update(quantity=10001),
    lambda d: d.update(commander_entry_ids=['missing']),
    lambda d: d['entries'].append(deepcopy(d['entries'][0])),
    lambda d: d['entries'][0].update(category_ids=['missing']),
    lambda d: d.update(tags=[{}]),
    lambda d: d.update(description='x' * MAX_BODY),
])
def test_malicious_or_invalid_payloads_are_rejected(deck, change):
    change(deck)
    with pytest.raises(LibraryError):
        shared_deck(deck)


def test_revision_ownership_conflicts_history_and_restart(library, deck):
    store, admin, friend, _ = library
    published = store.publish(friend, deck, ['U'])
    deck_id = published['deck_id']
    assert deck_id != deck['deck_id']
    assert published['revision'] == 1
    invitation = store.invite(admin)
    store.register(invitation, 'other', PASSWORD)
    other = store.login('other', PASSWORD)
    with pytest.raises(LibraryError, match='owner'):
        store.publish(other, deck, [], deck_id=deck_id, expected_revision=1)
    deck['name'] = 'Updated'
    assert store.publish(friend, deck, ['U'], deck_id=deck_id, expected_revision=1)['revision'] == 2
    with pytest.raises(LibraryError, match='Revision changed'):
        store.publish(friend, deck, [], deck_id=deck_id, expected_revision=1)
    reopened = LibraryStore(store.directory)
    reopened.check_schema()
    assert reopened.browse(friend, deck_id=deck_id)[0]['deck']['name'] == 'Updated'
    assert reopened.browse(friend, deck_id=deck_id, revision=1)[0]['deck']['name'] == 'Artifacts'
    with pytest.raises(LibraryError, match='owner'):
        store.unpublish(other, deck_id, 2)
    store.unpublish(admin, deck_id, 2)
    with pytest.raises(LibraryError, match='unavailable'):
        store.browse(friend, deck_id=deck_id, revision=1)
    assert store.browse(friend) == []


def test_invitation_credentials_revocation_and_hash_storage(library, deck):
    store, admin, friend, user_id = library
    invitation = store.invite(admin)
    store.register(invitation, 'new-user', PASSWORD)
    with pytest.raises(LibraryError):
        store.register(invitation, 'another', PASSWORD)
    with pytest.raises(LibraryError):
        store.invite(friend)
    store.publish(friend, deck, [])
    with store.db() as db:
        assert db.execute('SELECT token FROM sessions WHERE token=?', (digest(friend),)).fetchone()
        assert not db.execute('SELECT token FROM sessions WHERE token=?', (friend,)).fetchone()
        assert all(row['password'] != PASSWORD for row in db.execute('SELECT password FROM users'))
    store.revoke(admin, user_id)
    with pytest.raises(LibraryError):
        store.browse(friend)
    with pytest.raises(LibraryError):
        store.login('friend', PASSWORD)
    assert store.browse(admin) == []
    store.logout(admin)
    with pytest.raises(LibraryError):
        store.users(admin)


def test_failed_registration_preserves_invitation_and_existing_database(library):
    store, admin, _, _ = library
    invitation = store.invite(admin)
    with pytest.raises(LibraryError):
        store.register(invitation, 'friend', PASSWORD)
    assert store.register(invitation, 'available', PASSWORD)
    with pytest.raises(FileExistsError):
        store.initialize('Replacement', 'newadmin', PASSWORD)
    assert store.info()['name'] == 'Friends'


def test_expired_sessions_invitations_and_rate_limits(library):
    store, admin, _, _ = library
    invitation = store.invite(admin)
    with store.db() as db:
        db.execute('UPDATE invitations SET expires=0')
        db.execute('UPDATE sessions SET expires=0')
    with pytest.raises(LibraryError):
        store.register(invitation, 'expired', PASSWORD)
    with pytest.raises(LibraryError):
        store.invite(admin)
    store.throttle('limited', limit=1)
    with pytest.raises(LibraryError) as error:
        store.throttle('limited', limit=1)
    assert error.value.status == 429


def test_api_publish_browse_filters_and_versions(library, deck):
    store, _, friend, _ = library
    app = LibraryAPI(store)
    assert request(app, '/api/v1/info')['body']['server_id'] == store.info()['server_id']
    assert request(app, '/api/v2/decks')['status'] == 426
    assert request(app, '/api/v1/decks')['status'] == 401
    response = request(app, '/api/v1/decks', 'POST', {'deck': deck, 'color_identity': ['U']}, friend)
    assert response['status'] == 200
    deck_id = response['body']['deck_id']
    for query, count in [('commander=Example&color=U&tag=theme&owner=friend', 1),
                         ('color=C', 0), ('query=missing', 0), ('owner=admin', 0), ('offset=1', 0)]:
        result = request(app, '/api/v1/decks', token=friend, query=query)
        assert result['status'] == 200
        assert len(result['body']['decks']) == count
    response = request(app, '/api/v1/decks/' + deck_id, 'PUT',
                       {'deck': deck, 'expected_revision': 1}, friend)
    assert response['body']['revision'] == 2
    assert request(app, f'/api/v1/decks/{deck_id}/revisions/1', token=friend)['status'] == 200
    assert request(app, '/api/v1/decks', token=friend, query='offset=-1')['status'] == 400
    assert request(app, '/api/v1/decks', token=friend, query='owner=a&owner=b')['status'] == 400
    assert request(app, f'/api/v1/decks/{deck_id}', 'DELETE', {'expected_revision': 2}, friend)['status'] == 200
    assert request(app, f'/api/v1/decks/{deck_id}', token=friend)['status'] == 404


def test_api_limits_and_authentication_errors_do_not_echo_secrets(library):
    store, _, friend, _ = library
    app = LibraryAPI(store)
    for raw in (b'{broken', b'[]', b'{"x": NaN}', b'\xff'):
        assert request(app, '/api/v1/decks', 'POST', token=friend, raw=raw)['status'] == 400
    assert request(app, '/api/v1/decks', 'POST', token=friend,
                   CONTENT_LENGTH=str(MAX_BODY + 1))['status'] == 413
    assert request(app, '/api/v1/decks', 'POST', token=friend,
                   CONTENT_TYPE='text/plain')['status'] == 415
    assert request(app, '/api/v1/decks', 'POST', token=friend, CONTENT_LENGTH='-1')['status'] == 413
    response = request(app, '/api/v1/login', 'POST', {'username': 'admin', 'password': 'wrong long password'})
    assert response['status'] == 401
    assert 'wrong long password' not in json.dumps(response)
    assert response['headers']['Cache-Control'] == 'no-store'


def test_server_identity_is_independent_per_library(tmp_path, library):
    store, _, friend, _ = library
    other = LibraryStore(tmp_path / 'other')
    other.initialize('Other library', 'otheradmin', PASSWORD)
    assert other.info()['server_id'] != store.info()['server_id']
    with pytest.raises(LibraryError):
        other.browse(friend)
