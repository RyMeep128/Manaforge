"""Browse Online UI tests with fake clients; CI never needs a remote library."""
import threading
import time
from types import SimpleNamespace
import uuid

from PyQt6 import QtWidgets as W
import pytest

from mtg_core.decks import Deck, DeckEntry, DeckStore
from mtg_home.library_workspace import LibraryWorkspace


@pytest.fixture
def app():
    return W.QApplication.instance() or W.QApplication([])


def settle(app, workspace):
    deadline = time.monotonic() + 5
    while workspace.jobs.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    assert not workspace.jobs.busy


def record():
    return {'deck_id': str(uuid.uuid4()), 'revision': 1, 'owner': 'friend', 'color_identity': ['U'],
            'deck': Deck(name='<b>Shared deck</b>', description='Deck description', tags=['theme'],
                         commander_entry_ids=['cmdr'],
                         entries=[DeckEntry(entry_id='cmdr', name='Commander')]).to_dict()}


def test_opening_browse_online_never_connects(app, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail('Opening Browse Online must not connect to a server')
    workspace = LibraryWorkspace(object(), root=tmp_path, client_factory=forbidden)
    assert workspace.selector.count() == 0
    assert workspace.add_button.isEnabled()
    assert not workspace.search_button.isEnabled()
    assert 'No libraries configured' in workspace.connection_status.text()
    assert workspace.prepare_to_close()
    workspace.close()


def test_browse_is_background_copy_is_editable_and_connection_removal_keeps_copies(app, tmp_path):
    workspace = LibraryWorkspace(object(), root=tmp_path, deck_root=tmp_path / 'decks')
    main_thread = threading.get_ident()
    calls = []
    value = record()
    class Client:
        url = 'https://friend.invalid'
        token = 'session'
        def browse(self, filters, offset=0):
            calls.append((threading.get_ident(), filters, offset))
            return [value]
        def disconnect(self):
            self.token = None
    client = Client()
    connection = workspace.connections.add(client, {'server_id': str(uuid.uuid4()), 'name': 'Friend library'})
    workspace.clients[connection['id']] = client
    workspace.reload_connections(connection['id'])
    workspace.filters['commander'].setText('Commander')
    workspace.search()
    settle(app, workspace)
    assert calls[0][0] != main_thread
    assert calls[0][1] == {'commander': 'Commander'}
    assert workspace.results.count() == 1
    workspace.results.setCurrentRow(0)
    assert '<b>Shared deck</b>' in workspace.details.toPlainText()
    assert 'Owner: friend' in workspace.details.toPlainText()
    assert 'Commander' in workspace.details.toPlainText()
    assert workspace.copy_button.isEnabled()
    copies = []
    workspace.copyCreated.connect(copies.append)
    workspace.copy_selected()
    settle(app, workspace)
    assert len(copies) == 1
    document = DeckStore().load(copies[0])
    assert document.deck.deck_id != value['deck_id']
    workspace.remove()
    settle(app, workspace)
    assert workspace.selector.count() == 0
    assert copies[0].exists()
    assert workspace.prepare_to_close()
    workspace.close()


def test_connection_switches_and_failed_search_preserve_separate_snapshots(app, tmp_path):
    workspace = LibraryWorkspace(object(), root=tmp_path)
    first = workspace.connections.add(SimpleNamespace(url='https://first.invalid'),
                                      {'server_id': str(uuid.uuid4()), 'name': 'First'})
    second = workspace.connections.add(SimpleNamespace(url='https://second.invalid'),
                                       {'server_id': str(uuid.uuid4()), 'name': 'Second'})
    first_row, second_row = record(), record()
    second_row['deck']['name'] = 'Second deck'
    workspace.views[first['id']] = {'rows': [first_row], 'filters': {'owner': 'first'}, 'more': False}
    workspace.views[second['id']] = {'rows': [second_row], 'filters': {'owner': 'second'}, 'more': False}
    class Offline:
        token = 'session'
        def browse(self, *args, **kwargs):
            raise OSError('Library is offline')
    workspace.clients[first['id']] = Offline()
    workspace.reload_connections(first['id'])
    workspace.search()
    settle(app, workspace)
    assert workspace.results.count() == 1
    assert 'offline' in workspace.connection_status.text()
    workspace.selector.setCurrentIndex(1)
    assert 'Second deck' in workspace.results.item(0).text()
    assert workspace.filters['owner'].text() == 'second'
    assert not workspace.search_button.isEnabled()
    assert workspace.prepare_to_close()
    workspace.close()


def test_add_and_reconnect_are_explicit_and_do_not_persist_credentials(app, tmp_path, monkeypatch):
    from mtg_home.library_workspace import SignInDialog
    server_id = str(uuid.uuid4())
    calls = []
    class Client:
        def __init__(self, url, **options):
            self.url, self.token = url, None
            calls.append(options)
        def login(self, username, password, *, invitation=''):
            assert (username, password, invitation) == ('friend', 'a sufficiently long password', 'invite')
            self.token = 'memory-session'
            return {'server_id': server_id, 'name': 'Friends'}
        def disconnect(self):
            self.token = None
    def accept(dialog):
        dialog.url.setText('https://friend.invalid')
        dialog.username.setText('friend')
        dialog.password.setText('a sufficiently long password')
        dialog.invitation.setText('invite')
        return W.QDialog.DialogCode.Accepted
    monkeypatch.setattr(SignInDialog, 'exec', accept)
    workspace = LibraryWorkspace(object(), root=tmp_path, client_factory=Client)
    assert not calls
    workspace.sign_in(new=True)
    settle(app, workspace)
    assert workspace.selector.count() == 1
    connection = workspace.connection()
    assert workspace.clients[connection['id']].token == 'memory-session'
    assert calls[0]['server_id'] is None
    workspace.sign_in(new=False)
    settle(app, workspace)
    assert calls[1]['server_id'] == server_id
    assert b'a sufficiently long password' not in workspace.connections.path.read_bytes()
    assert b'memory-session' not in workspace.connections.path.read_bytes()
    assert workspace.prepare_to_close()
    workspace.close()
