"""Windows-protected saved sessions: no plaintext passwords/tokens on disk."""
from copy import deepcopy
import os
import time
from types import SimpleNamespace
import uuid

import pytest

from mtg_core.library import LibraryError
from mtg_core.library.sessions import SavedSessions


def record():
    connection = {'id': str(uuid.uuid4()), 'server_id': str(uuid.uuid4()), 'url': 'https://friends.invalid'}
    client = SimpleNamespace(url=connection['url'], server_id=connection['server_id'],
                             account_id=str(uuid.uuid4()), token='test-secret-session-token-with-43-characters',
                             expires_at=time.time() + 86400)
    return connection, client


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows DPAPI')
def test_windows_round_trip_is_encrypted_and_does_not_accept_another_origin(tmp_path):
    sessions = SavedSessions(tmp_path)
    connection, client = record()
    sessions.save(connection, client, 'friend')
    blob = sessions._path(connection['id']).read_bytes()
    assert client.token.encode() not in blob
    assert b'friend' not in blob
    reopened = SavedSessions(tmp_path)
    value = reopened.load(connection)
    assert value['token'] == client.token
    assert value['account_id'] == client.account_id
    assert value['username'] == 'friend'
    assert 'password' not in value
    changed = {**connection, 'url': 'https://other.invalid'}
    with pytest.raises(LibraryError):
        reopened.load(changed)
    changed = {**connection, 'server_id': str(uuid.uuid4())}
    with pytest.raises(LibraryError):
        reopened.load(changed)


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows DPAPI')
def test_expiry_and_removal_are_isolated_per_library(tmp_path, monkeypatch):
    sessions = SavedSessions(tmp_path)
    first, client = record()
    second, other = record()
    sessions.save(first, client, 'first')
    sessions.save(second, other, 'second')
    sessions.forget(first['id'])
    assert not sessions.has(first['id']) and sessions.has(second['id'])
    assert sessions.load(second)['token'] == other.token
    monkeypatch.setattr('mtg_core.library.sessions.time.time', lambda: other.expires_at + 1)
    assert sessions.load(second) is None
    assert not sessions.has(second['id'])


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows DPAPI')
def test_corrupt_ciphertext_is_not_treated_as_a_session(tmp_path):
    sessions = SavedSessions(tmp_path)
    connection, client = record()
    sessions.save(connection, client, 'friend')
    sessions._path(connection['id']).write_bytes(b'not an encrypted session')
    with pytest.raises(LibraryError):
        sessions.load(connection)
    with pytest.raises(LibraryError):
        sessions._path('../../credentials')


def test_unavailable_secure_storage_has_no_plaintext_fallback(tmp_path):
    sessions = SavedSessions(tmp_path)
    sessions.available = False
    connection, client = record()
    before = deepcopy(vars(client))
    with pytest.raises(LibraryError):
        sessions.save(connection, client, 'friend')
    assert vars(client) == before
    assert not sessions.root.exists()
