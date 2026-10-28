"""Browse Online UI tests with fake clients; CI never needs a remote library."""
import threading
import time
from types import SimpleNamespace
import uuid
import os

from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
import pytest

from mtg_core.decks import Deck, DeckEntry, DeckStore
from mtg_core.library import LibraryError
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
    assert len(workspace.connections.list()) == 0
    assert workspace.add_button.isEnabled()
    assert not workspace.search_button.isEnabled()
    assert workspace.empty_title.text() == 'Join a deck library'
    assert workspace.empty_button.text() == 'Join library'
    assert workspace.filters_container.isHidden()
    assert not workspace.preview_dialog.isVisible()
    assert not workspace.publishing.isVisible()
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
    assert len(workspace.connections.list()) == 0
    assert copies[0].exists()
    assert workspace.prepare_to_close()
    workspace.close()


def test_all_libraries_share_gallery_and_offline_failure_keeps_own_snapshot(app, tmp_path):
    workspace = LibraryWorkspace(object(), root=tmp_path, deck_root=tmp_path / 'decks')
    first = workspace.connections.add(SimpleNamespace(url='https://first.invalid'),
                                      {'server_id': str(uuid.uuid4()), 'name': 'First'})
    second = workspace.connections.add(SimpleNamespace(url='https://second.invalid'),
                                       {'server_id': str(uuid.uuid4()), 'name': 'Second'})
    first_row, second_row = record(), record()
    # Identical remote IDs must remain distinct across independent servers.
    second_row['deck_id'] = first_row['deck_id']
    second_row['deck']['name'] = 'Second deck'
    workspace.views[first['id']] = {'rows': [first_row], 'filters': {}, 'more': False}
    class Offline:
        token = 'session'
        def browse(self, *args, **kwargs):
            raise OSError('Library is offline')
    class Online:
        token = 'session'
        def browse(self, *args, **kwargs):
            return [second_row]
    workspace.clients[first['id']] = Offline()
    workspace.clients[second['id']] = Online()
    workspace.reload_connections()
    workspace.search()
    settle(app, workspace)
    assert workspace.results.count() == 2
    assert '1 unavailable' in workspace.connection_status.text()
    rows = [workspace.results.item(i).data(C.Qt.ItemDataRole.UserRole) for i in range(2)]
    assert len({workspace.row_key(row) for row in rows}) == 2
    assert {row['library']['name'] for row in rows} == {'First', 'Second'}
    assert next(row for row in rows if row['library']['id'] == first['id'])['cached']
    copies = []
    workspace.copyCreated.connect(copies.append)
    for index, row in enumerate(rows):
        workspace.results.setCurrentRow(index)
        assert workspace.selected_connection()['id'] == row['library']['id']
        workspace.copy_selected()
        settle(app, workspace)
        source = DeckStore().load(copies[-1]).deck.extras['library_source']
        assert source['server_id'] == row['library']['server_id']
        assert source['server_url'] == row['library']['url']
    workspace.remove(connection=first)
    settle(app, workspace)
    assert [row['id'] for row in workspace.connections.list()] == [second['id']]
    assert workspace.results.count() == 1
    assert all(path.exists() for path in copies)
    assert workspace.search_button.isEnabled()
    assert workspace.prepare_to_close()
    workspace.close()


def test_add_and_reconnect_are_explicit_and_do_not_persist_credentials(app, tmp_path):
    server_id = str(uuid.uuid4())
    calls = []
    class Client:
        def __init__(self, url, **options):
            self.url, self.token = url, None
            calls.append(options)
        def login(self, username, password, *, invitation=''):
            assert (username, password) == ('friend', 'a sufficiently long password')
            assert invitation == ('invite' if calls[-1]['server_id'] is None else '')
            self.token = 'memory-session'
            return {'server_id': server_id, 'name': 'Friends'}
        def disconnect(self):
            self.token = None
        def browse(self, filters, offset=0):
            return []
    def complete_form(dialog, *, creating=False):
        dialog.remember.setChecked(False)  # This case exercises sign-in without local persistence.
        dialog.mode.setCurrentIndex(1 if creating else 0)
        dialog.url.setText('https://friend.invalid')
        dialog.username.setText('friend')
        dialog.password.setText('a sufficiently long password')
        dialog.invitation.setText('invite' if creating else '')
        dialog.submit_button.click()
    workspace = LibraryWorkspace(object(), root=tmp_path, client_factory=Client)
    assert not calls
    complete_form(workspace.sign_in(new=True), creating=True)
    settle(app, workspace)
    assert len(workspace.connections.list()) == 1
    connection = workspace.connection()
    assert workspace.clients[connection['id']].token == 'memory-session'
    assert calls[0]['server_id'] is None
    complete_form(workspace.sign_in(new=False))
    settle(app, workspace)
    assert calls[1]['server_id'] == server_id
    assert b'a sufficiently long password' not in workspace.connections.path.read_bytes()
    assert b'memory-session' not in workspace.connections.path.read_bytes()
    assert workspace.prepare_to_close()
    workspace.close()


def test_publish_conflict_review_unpublish_and_republish_are_explicit(app, tmp_path):
    from copy import deepcopy
    workspace = LibraryWorkspace(object(), root=tmp_path)
    main_thread = threading.get_ident()
    class Client:
        url, token = 'https://friend.invalid', 'session'
        server_id, remote_id = str(uuid.uuid4()), str(uuid.uuid4())
        account_id = str(uuid.uuid4())
        revision = 0
        operations = []
        def publish_operation(self, operation):
            assert threading.get_ident() != main_thread
            self.operations.append(deepcopy(operation))
            if operation['expected_revision'] != self.revision:
                raise LibraryError(409, 'Revision changed. Review first.')
            if operation['kind'] == 'publish':
                self.revision += 1
            return {'deck_id': self.remote_id, 'revision': self.revision}
        def download(self, deck_id):
            result = record()
            result.update(deck_id=self.remote_id, revision=self.revision)
            result['deck']['name'] = 'A remote edit'
            return result
    client = Client()
    connection = workspace.connections.add(client, {'server_id': client.server_id, 'name': 'Friend library'})
    workspace.clients[connection['id']] = client
    workspace.reload_connections(connection['id'])
    snapshot = record()['deck']
    snapshot['entries'][0].update(print_status='Printed', owned=6, do_not_print=True)
    panel = workspace.publishing
    assert panel.prepare(snapshot, 'U')
    assert not client.operations  # Preparing a snapshot never uploads it.
    snapshot['name'] = 'Later local edit'
    panel.publish()
    settle(app, workspace)
    assert client.operations[0]['deck']['name'] == '<b>Shared deck</b>'
    assert 'owned' not in client.operations[0]['deck']['entries'][0]
    assert 'print_status' not in client.operations[0]['deck']['entries'][0]
    local_id = snapshot['deck_id']
    assert workspace.publications.get(client.server_id, local_id)['revision'] == 1
    client.revision = 2  # A newer owner publication from another client.
    panel.publish()
    settle(app, workspace)
    assert workspace.publications.get(client.server_id, local_id)['revision'] == 1
    assert 'Retry upload' == panel.publish_button.text()
    panel.review()
    settle(app, workspace)
    assert 'A remote edit' in workspace.details.toPlainText()
    assert workspace.publications.get(client.server_id, local_id)['revision'] == 1
    panel.accept_review()
    settle(app, workspace)
    assert workspace.publications.get(client.server_id, local_id)['revision'] == 2
    assert snapshot['name'] == 'Later local edit'
    panel.publish()
    settle(app, workspace)
    assert client.revision == 3
    assert client.operations[-1]['deck_id'] == client.remote_id
    panel.publish(unpublish=True)
    settle(app, workspace)
    assert workspace.publications.get(client.server_id, local_id)['published'] == 0
    panel.publish()
    settle(app, workspace)
    assert client.revision == 4
    assert client.operations[-1]['deck_id'] == client.remote_id
    assert workspace.prepare_to_close()
    workspace.close()


def test_editor_forwards_a_saved_snapshot_only_for_explicit_publish():
    from mtg_core.decks import DeckDocument
    from mtg_editor.gui import EditorWindow
    snapshots, saves = [], []
    document = DeckDocument(deck=Deck(name='Local deck', entries=[DeckEntry('one', 'Card')]))
    editor = SimpleNamespace(task=None, _has_active_deck=True, document=document,
                             save=lambda: saves.append(True) or True,
                             publish_deck_handler=lambda deck, color: snapshots.append((deck, color)))
    EditorWindow.publish_to_library(editor)
    assert saves == [True] and snapshots[0][0]['name'] == 'Local deck'
    document.deck.name = 'Changed later'
    assert snapshots[0][0]['name'] == 'Local deck'
    editor.save = lambda: False
    EditorWindow.publish_to_library(editor)
    assert len(snapshots) == 1
    editor._has_active_deck = False
    EditorWindow.publish_to_library(editor)
    assert len(snapshots) == 1


def test_follow_offline_restart_review_and_accept_are_separate(app, tmp_path):
    from copy import deepcopy
    workspace = LibraryWorkspace(object(), root=tmp_path, deck_root=tmp_path / 'decks')
    value = record()
    class Client:
        url, token = 'https://friend.invalid', 'session'
        server_id = str(uuid.uuid4())
        calls = 0
        def check(self):
            return {'server_id': self.server_id, 'name': 'Friends'}
        def download(self, deck_id):
            self.calls += 1
            return deepcopy(value)
    client = Client()
    connection = workspace.connections.add(client, {'server_id': client.server_id, 'name': 'Friends'})
    workspace.clients[connection['id']] = client
    workspace.reload_connections(connection['id'])
    workspace.views[connection['id']] = {'rows': [value], 'filters': {}, 'more': False}
    workspace.switch_library()
    workspace.results.setCurrentRow(0)
    workspace.follow_selected()
    settle(app, workspace)
    assert workspace.view_mode.currentIndex() == 1
    assert workspace.results.count() == 1
    assert 'Followed' in workspace.results.item(0).text()
    workspace.results.setCurrentRow(0)
    assert 'Read-only' in workspace.preview_dialog.hint.text()
    assert workspace.details.isReadOnly()
    assert client.calls == 1
    workspace.following.tick()  # Automatic checks require separate explicit opt-in.
    assert not workspace.jobs.busy and client.calls == 1
    value['revision'] = 2
    value['deck']['name'] = 'New owner revision'
    notices = []
    workspace.followUpdates.connect(lambda name, count: notices.append((name, count)))
    workspace.following.check()
    settle(app, workspace)
    assert notices == [('Friends', 1)]
    assert workspace.followed.get(client.server_id, value['deck_id'])['revision'] == 1
    workspace.following.review()
    settle(app, workspace)
    assert 'New owner revision' in workspace.details.toPlainText()
    assert workspace.followed.get(client.server_id, value['deck_id'])['revision'] == 1
    workspace.following.accept()
    settle(app, workspace)
    assert workspace.followed.get(client.server_id, value['deck_id'])['revision'] == 2
    # Removing the connection retains the cache and allows offline copying after restart.
    workspace.connections.remove(connection['id'])
    assert workspace.prepare_to_close()
    workspace.close()
    restarted = LibraryWorkspace(object(), root=tmp_path, deck_root=tmp_path / 'decks')
    assert len(restarted.connections.list()) == 0 and not restarted.clients
    restarted.view_mode.setCurrentIndex(1)
    restarted.results.setCurrentRow(0)
    assert 'New owner revision' in restarted.details.toPlainText()
    assert not restarted.following.check_button.isEnabled()
    copies = []
    restarted.copyCreated.connect(copies.append)
    restarted.copy_selected()
    settle(app, restarted)
    assert len(copies) == 1
    assert DeckStore().load(copies[0]).deck.name == 'New owner revision'
    assert restarted.prepare_to_close()
    restarted.close()


def test_gallery_reuses_project_tiles_and_only_opens_actions_with_a_deck(app, tmp_path):
    from mtg_editor.project_browser import ProjectTileDelegate
    workspace = LibraryWorkspace(object(), root=tmp_path)
    client = SimpleNamespace(url='https://friend.invalid', token='session')
    connection = workspace.connections.add(client, {'server_id': str(uuid.uuid4()), 'name': 'Friends'})
    workspace.clients[connection['id']] = client
    workspace.reload_connections(connection['id'])
    workspace.views[connection['id']] = {'rows': [record()], 'filters': {}, 'more': False}
    workspace.render_shared()
    assert workspace.results.viewMode() == W.QListView.ViewMode.IconMode
    assert isinstance(workspace.results.itemDelegate(), ProjectTileDelegate)
    assert not hasattr(workspace, 'selector')
    assert workspace.filters_container.isHidden()
    assert not workspace.preview_dialog.isVisible()
    assert workspace.preview_dialog.isAncestorOf(workspace.copy_button)
    assert workspace.preview_dialog.isAncestorOf(workspace.follow_button)
    row = workspace.results.item(0).data(C.Qt.ItemDataRole.UserRole)
    assert row['summary_lines'][0] == 'friend - Friends'
    assert row['color_identity'] == ['U']
    workspace.results.setCurrentRow(0)
    workspace.open_preview()
    assert workspace.preview_dialog.isVisible()
    assert workspace.preview_dialog.title.text() == '<b>Shared deck</b>'
    assert workspace.preview_dialog.title.textFormat() == C.Qt.TextFormat.PlainText
    assert workspace.preview_dialog.cards.topLevelItemCount() == 1
    assert workspace.preview_dialog.cards.topLevelItem(0).child(0).text(1) == 'Commander'
    workspace.preview_dialog.reject()
    workspace.filter_button.setChecked(True)
    assert not workspace.filters_container.isHidden()
    workspace.filter_button.setChecked(False)
    assert workspace.filters_container.isHidden()
    assert workspace.prepare_to_close()
    workspace.close()


def test_failed_sign_in_stays_in_form_and_can_retry_without_losing_address(app, tmp_path):
    calls = []
    class Client:
        def __init__(self, url, **options):
            self.url, self.token = url, None
        def login(self, username, password, *, invitation=''):
            calls.append((username, password, invitation))
            if len(calls) == 1:
                raise LibraryError(401, 'The username or password was rejected.')
            self.token = 'test-session'
            return {'server_id': str(uuid.uuid4()), 'name': 'Friends'}
        def browse(self, filters, offset=0):
            return []
    workspace = LibraryWorkspace(object(), root=tmp_path, client_factory=Client)
    dialog = workspace.sign_in(new=True)
    assert dialog.invitation.isHidden()
    dialog.remember.setChecked(False)  # The retry fixture provides no persistent account metadata.
    assert dialog.lan.isHidden()
    dialog.url.setText('https://friend.invalid')
    dialog.username.setText('friend')
    dialog.password.setText('a sufficiently long password')
    dialog.submit_button.click()
    settle(app, workspace)
    assert dialog.isVisible()
    assert dialog.error.text() == 'The username or password was rejected.'
    assert dialog.url.text() == 'https://friend.invalid'
    assert dialog.username.text() == 'friend'
    assert not dialog.password.text()
    assert 'rejected' not in workspace.connection_status.text()
    assert workspace.connections.list() == []
    dialog.password.setText('a corrected long password')
    dialog.submit_button.click()
    settle(app, workspace)
    assert workspace._signin_dialog is None
    assert len(workspace.connections.list()) == 1
    assert workspace.empty_title.text() == 'No decks shared yet'
    assert calls[-1][2] == ''
    assert workspace.prepare_to_close()
    workspace.close()


def test_sign_in_and_account_creation_have_separate_validation(app, tmp_path):
    workspace = LibraryWorkspace(object(), root=tmp_path)
    dialog = workspace.sign_in(new=True)
    dialog.mode.setCurrentIndex(1)
    assert not dialog.invitation.isHidden()
    dialog.url.setText('https://friend.invalid')
    dialog.username.setText('friend')
    dialog.password.setText('short')
    dialog.invitation.setText('invitation')
    dialog.submit_button.click()
    assert 'at least 12' in dialog.error.text()
    assert not workspace.jobs.busy
    dialog.mode.setCurrentIndex(0)
    assert dialog.invitation.isHidden()
    dialog.reject()
    assert workspace._signin_dialog is None
    assert workspace.prepare_to_close()
    workspace.close()


def test_color_controls_are_exclusive_with_colorless(app):
    from mtg_home.library_widgets import ColorChoices
    colors = ColorChoices()
    colors.buttons['U'].click()
    colors.buttons['G'].click()
    assert colors.text() == 'UG'
    colors.buttons['C'].click()
    assert colors.text() == 'C'
    colors.buttons['W'].click()
    assert colors.text() == 'W'
    colors.clear()
    assert colors.text() == ''


def test_publishing_is_a_dialog_with_connection_first_when_no_library_exists(app, tmp_path):
    workspace = LibraryWorkspace(object(), root=tmp_path)
    panel = workspace.publishing
    assert isinstance(panel, W.QDialog)
    assert panel.prepare(record()['deck'], 'U')
    assert panel.isVisible()
    assert panel.publish_button.isHidden()
    assert panel.colors.isHidden()
    assert panel.connect_button.text() == 'Join library'
    panel.connect_button.click()
    assert workspace._signin_dialog.parentWidget() is panel
    workspace._signin_dialog.reject()
    panel.reject()
    assert not workspace.jobs.busy
    assert workspace.prepare_to_close()
    workspace.close()


def test_library_visual_review_artifacts(app, tmp_path):
    """CI screenshots make the real Qt layout reviewable without a local run."""
    import os
    from pathlib import Path
    from mtg_ui.theme import application_stylesheet
    workspace = LibraryWorkspace(object(), root=tmp_path)
    workspace.setStyleSheet(application_stylesheet())
    workspace.resize(1180, 760)
    workspace.show()
    app.processEvents()
    output = os.environ.get('MANAFORGE_UI_SCREENSHOTS')
    def capture(name, widget=None):
        if output:
            path = Path(output)
            path.mkdir(parents=True, exist_ok=True)
            assert (widget or workspace).grab().save(str(path / (name + '.png')))
    capture('library-empty')
    client = SimpleNamespace(url='https://friend.invalid', token='session')
    connection = workspace.connections.add(client, {'server_id': str(uuid.uuid4()), 'name': 'Friends library'})
    workspace.clients[connection['id']] = client
    workspace.reload_connections(connection['id'])
    rows = []
    for index, name in enumerate(['Artifacts', 'Elves', 'Tokens', 'Spells', 'Dragons', 'Lands', 'Counters', 'Control']):
        value = record()
        value['deck']['name'] = name
        card_id = f'fixture-{index}'
        value['deck']['entries'][0]['card_id'] = card_id
        pixmap = G.QPixmap(110, 154)
        pixmap.fill(G.QColor(['#3e6268', '#546348', '#746353', '#4a5675'][index % 4]))
        workspace.thumbnails.cache[(card_id, None)] = pixmap
        rows.append(value)
    workspace.render(rows)
    app.processEvents()
    assert workspace.gallery_stack.currentWidget() is workspace.results
    capture('library-gallery')
    workspace.resize(640, 740)
    app.processEvents()
    capture('library-gallery-narrow')
    workspace.results.setCurrentRow(0)
    workspace.open_preview()
    app.processEvents()
    capture('library-deck-preview', workspace.preview_dialog)
    workspace.preview_dialog.reject()
    workspace.publishing.prepare(rows[0]['deck'], 'U')
    app.processEvents()
    capture('library-publish', workspace.publishing)
    workspace.publishing.reject()
    dialog = workspace.sign_in(new=True)
    app.processEvents()
    capture('library-sign-in', dialog)
    dialog.mode.setCurrentIndex(1)
    app.processEvents()
    capture('library-create-account', dialog)
    dialog.reject()
    assert workspace.prepare_to_close()
    workspace.close()


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows DPAPI')
def test_saved_sign_in_restores_without_password_and_sign_out_removes_it(app, tmp_path):
    from mtg_core.library.client import LibraryConnections
    from mtg_core.library.sessions import SavedSessions
    source = SimpleNamespace(url='https://friends.invalid', server_id=str(uuid.uuid4()),
                             token='fixture-secret-session-token-1234567890', account_id=str(uuid.uuid4()),
                             expires_at=time.time() + 86400)
    connection = LibraryConnections(tmp_path).add(source, {'server_id': source.server_id, 'name': 'Friends'})
    sessions = SavedSessions(tmp_path)
    sessions.save(connection, source, 'friend')
    calls = []
    class Client:
        offline = False
        def __init__(self, url, **options):
            self.url, self.server_id, self.token = url, options['server_id'], None
        def resume(self, saved):
            calls.append('resume')
            if self.offline:
                raise LibraryError(503, 'Library is offline')
            self.token, self.account_id = saved['token'], saved['account_id']
        def browse(self, filters, offset=0):
            return []
        def disconnect(self):
            calls.append('logout')
            self.token = None
    Client.offline = True
    workspace = LibraryWorkspace(object(), root=tmp_path, client_factory=Client)
    workspace.restore_saved_sessions()
    settle(app, workspace)
    assert sessions.has(connection['id'])
    assert workspace.login_button.text() == 'Reconnect'
    Client.offline = False
    workspace.reconnect()
    settle(app, workspace)
    assert workspace.clients[connection['id']].token == source.token
    assert workspace._signin_dialog is None
    assert sessions.has(connection['id'])
    workspace.disconnect()
    settle(app, workspace)
    assert not sessions.has(connection['id'])
    assert calls == ['resume', 'resume', 'logout']
    assert workspace.prepare_to_close()
    workspace.close()


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows DPAPI')
def test_remember_checkbox_saves_session_and_removing_connection_forgets_it(app, tmp_path):
    calls = []
    class Client:
        def __init__(self, url, **options):
            self.url, self.server_id, self.token = url, str(uuid.uuid4()), None
        def login(self, username, password, *, invitation='', remember=False):
            calls.append(remember)
            self.token = 'fixture-persistent-session-1234567890'
            self.account_id, self.expires_at = str(uuid.uuid4()), time.time() + 730 * 86400
            return {'server_id': self.server_id, 'name': 'Friends'}
        def browse(self, filters, offset=0):
            return []
        def disconnect(self):
            self.token = None
    workspace = LibraryWorkspace(object(), root=tmp_path, client_factory=Client)
    dialog = workspace.sign_in(new=True)
    dialog.url.setText('https://friends.invalid')
    dialog.username.setText('friend')
    dialog.password.setText('a sufficiently long password')
    assert dialog.remember.isChecked()
    dialog.submit_button.click()
    settle(app, workspace)
    connection = workspace.connection()
    assert calls == [True]
    saved = workspace.saved_sessions.load(connection)
    assert saved['username'] == 'friend'
    assert 'password' not in saved
    assert b'a sufficiently long password' not in workspace.connections.path.read_bytes()
    assert workspace.saved_sessions.has(connection['id'])
    workspace.remove()
    settle(app, workspace)
    assert not workspace.saved_sessions.has(connection['id'])
    assert workspace.prepare_to_close()
    workspace.close()


def test_combined_gallery_loads_healthy_library_before_slow_source(app, tmp_path):
    workspace = LibraryWorkspace(object(), root=tmp_path)
    release = threading.Event()
    class Client:
        token = 'session'
        def __init__(self, name, slow=False):
            self.url, self.slow = 'https://' + name + '.invalid', slow
        def browse(self, filters, offset=0):
            if self.slow:
                release.wait(5)
                raise OSError('Offline')
            return [record()]
    for name, slow in [('slow', True), ('healthy', False)]:
        client = Client(name, slow)
        connection = workspace.connections.add(client, {'server_id': str(uuid.uuid4()), 'name': name})
        workspace.clients[connection['id']] = client
    workspace.reload_connections()
    workspace.search()
    try:
        deadline = time.monotonic() + 3
        while workspace.results.count() == 0 and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        assert workspace.jobs.busy
        assert workspace.results.count() == 1
        row = workspace.results.item(0).data(C.Qt.ItemDataRole.UserRole)
        assert row['library']['name'] == 'healthy'
    finally:
        release.set()
        settle(app, workspace)
        workspace.close()


def test_combined_pagination_only_fetches_sources_with_more_pages(app, tmp_path):
    workspace = LibraryWorkspace(object(), root=tmp_path)
    calls = []
    class Client:
        token = 'session'
        def __init__(self, name, count):
            self.url, self.name, self.count = 'https://' + name + '.invalid', name, count
        def browse(self, filters, offset=0):
            calls.append((self.name, offset))
            return [record() for _ in range(self.count if offset == 0 else 1)]
    for name, count in [('large', 50), ('small', 1)]:
        client = Client(name, count)
        connection = workspace.connections.add(client, {'server_id': str(uuid.uuid4()), 'name': name})
        workspace.clients[connection['id']] = client
    workspace.reload_connections()
    workspace.search()
    settle(app, workspace)
    assert workspace.results.count() == 51
    workspace.search(more=True)
    settle(app, workspace)
    assert workspace.results.count() == 52
    assert sorted(calls) == [('large', 0), ('large', 50), ('small', 0)]
    assert workspace.more_button.isHidden()
    workspace.close()


def test_publishing_requires_one_destination_without_filtering_gallery(app, tmp_path):
    workspace = LibraryWorkspace(object(), root=tmp_path)
    clients = []
    class Client:
        token = 'session'
        def __init__(self, name):
            self.url = 'https://' + name + '.invalid'
            self.server_id, self.account_id = str(uuid.uuid4()), str(uuid.uuid4())
            self.operations = []
        def publish_operation(self, operation):
            self.operations.append(operation)
            return {'deck_id': str(uuid.uuid4()), 'revision': 1}
    for name in ['first', 'second']:
        client = Client(name)
        connection = workspace.connections.add(client, {'server_id': client.server_id, 'name': name})
        workspace.clients[connection['id']] = client
        workspace.views[connection['id']] = {'rows': [record()], 'filters': {}, 'more': False}
        clients.append((client, connection))
    workspace.reload_connections()
    panel = workspace.publishing
    assert panel.prepare(record()['deck'], 'U')
    assert panel.context() == (None, None, None)
    panel.publish()
    assert not any(client.operations for client, _ in clients)
    panel.destination.setCurrentIndex(panel.destination.findData(clients[1][1]['id']))
    assert workspace.results.count() == 2
    panel.publish()
    settle(app, workspace)
    assert not clients[0][0].operations
    assert len(clients[1][0].operations) == 1
    assert workspace.results.count() == 2
    workspace.close()


@pytest.mark.parametrize('source_kind', ['library', 'follow'])
def test_editable_copy_uses_clicked_source_name_and_emits_saved_path(app, tmp_path, monkeypatch, source_kind):
    from mtg_core.decks import DeckStore
    workspace = LibraryWorkspace(object(), root=tmp_path / 'settings', deck_root=tmp_path / 'decks')
    value = record()
    source = dict(id='clicked', server_id=str(uuid.uuid4()), name='Clicked library', server_name='Clicked library',
                  url='https://clicked.invalid', server_url='https://clicked.invalid',
                  message='', pending_revision=None, active=True)
    value[source_kind] = source
    item = W.QListWidgetItem('Shared deck')
    item.setData(C.Qt.ItemDataRole.UserRole, value)
    workspace.results.addItem(item)
    workspace.results.setCurrentItem(item)
    monkeypatch.setattr(workspace, 'submit', lambda label, work, complete: complete(work()))
    copied = []
    workspace.copyCreated.connect(copied.append)
    workspace.copy_selected()
    assert len(copied) == 1
    assert DeckStore().load(copied[0]).deck.name == value['deck']['name'] + ' [Clicked library]'
    workspace.close()
    app.processEvents()
