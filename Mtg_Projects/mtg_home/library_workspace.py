"""Opt-in library browsing with the shared job queue and local deck persistence."""
from pathlib import Path
import sqlite3

from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_core.downloads import DownloadCancelled
from mtg_core.library import LibraryError
from mtg_core.library.client import LibraryClient, LibraryConnections, copy_publication
from mtg_core.library.publishing import PublicationJournal
from mtg_core.library.following import FollowedDecks
from mtg_core.paths import data_root
from mtg_editor.card_views import Thumbnails
from mtg_ui.jobs import JobQueue


class _LocalArtwork:
    """Reuse thumbnails without initiating card-provider network requests."""
    def __init__(self, service):
        self.service = service

    def get_image_path(self, card_id):
        return self.service.get_image_path(card_id)


class SignInDialog(W.QDialog):
    def __init__(self, parent=None, connection=None):
        super().__init__(parent)
        self.setWindowTitle('Sign in to library' if connection else 'Add a library')
        form = W.QFormLayout(self)
        notice = W.QLabel('Use your own library or a friend’s URL. Passwords are never saved.\n'
                          'Sessions stay in memory until disconnect, expiry, or application exit.')
        notice.setWordWrap(True)
        form.addRow(notice)
        self.url = W.QLineEdit(connection['url'] if connection else '')
        self.url.setPlaceholderText('https://your-library-hostname')
        self.url.setReadOnly(bool(connection))
        form.addRow('Library server URL', self.url)
        self.lan = W.QCheckBox('Allow unencrypted HTTP to a private LAN IP')
        self.lan.setChecked(bool(connection and connection['allow_lan']))
        self.lan.setEnabled(not connection)
        form.addRow(self.lan)
        self.username = W.QLineEdit()
        form.addRow('Username', self.username)
        self.password = W.QLineEdit()
        self.password.setEchoMode(W.QLineEdit.EchoMode.Password)
        form.addRow('Password', self.password)
        self.invitation = W.QLineEdit()
        self.invitation.setEchoMode(W.QLineEdit.EchoMode.Password)
        self.invitation.setPlaceholderText('Only for creating a new account')
        form.addRow('Invitation (optional)', self.invitation)
        buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Ok | W.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class LibraryWorkspace(W.QMainWindow):
    copyCreated = C.pyqtSignal(object)
    followUpdates = C.pyqtSignal(str, int)

    def __init__(self, service, parent=None, *, jobs=None, root=None, deck_root=None, client_factory=LibraryClient):
        super().__init__(parent)
        self.setWindowTitle('Browse Online')
        self.connections = LibraryConnections(root or data_root())
        self.publications = PublicationJournal(self.connections)
        self.followed = FollowedDecks(self.connections)
        self.deck_root = Path(deck_root or data_root() / 'decks')
        self.client_factory = client_factory
        self.clients, self.views, self.states = {}, {}, {}
        self.message = ''
        self._job = None
        self._completion = None
        self._operation_connection = None
        self.jobs = jobs or JobQueue(self)
        self.jobs.status.connect(self.job_status)
        self.jobs.idle.connect(self.update_controls)
        self.thumbnails = Thumbnails(_LocalArtwork(service), self)
        self.thumbnails.updated.connect(self.refresh_icons)
        body = W.QWidget()
        layout = W.QVBoxLayout(body)
        title = W.QLabel('Browse Online')
        title.setProperty('role', 'title')
        layout.addWidget(title)
        layout.addWidget(W.QLabel('Join a library to browse shared decks. Copies in My Decks remain editable offline.'))
        connections = W.QHBoxLayout()
        self.selector = W.QComboBox()
        self.selector.setAccessibleName('Saved library connections')
        self.selector.currentIndexChanged.connect(self.switch_library)
        connections.addWidget(self.selector, 1)
        self.add_button = W.QPushButton('Add library…')
        self.add_button.clicked.connect(lambda: self.sign_in(new=True))
        self.login_button = W.QPushButton('Sign in / Reconnect…')
        self.login_button.clicked.connect(lambda: self.sign_in(new=False))
        self.disconnect_button = W.QPushButton('Disconnect')
        self.disconnect_button.clicked.connect(self.disconnect)
        self.remove_button = W.QPushButton('Remove')
        self.remove_button.clicked.connect(self.remove)
        for button in (self.add_button, self.login_button, self.disconnect_button, self.remove_button):
            connections.addWidget(button)
        layout.addLayout(connections)
        self.connection_status = W.QLabel()
        self.connection_status.setTextFormat(C.Qt.TextFormat.PlainText)
        self.connection_status.setWordWrap(True)
        layout.addWidget(self.connection_status)
        from .library_publishing import PublishingPanel
        self.publishing = PublishingPanel(self)
        layout.addWidget(self.publishing)
        self.view_mode = W.QComboBox()
        self.view_mode.setAccessibleName('Library view')
        self.view_mode.addItems(['Browse shared decks', 'Followed decks (offline)'])
        self.view_mode.currentIndexChanged.connect(self.switch_library)
        layout.addWidget(self.view_mode)
        self.filters_container = W.QWidget()
        filters = W.QFormLayout(self.filters_container)
        self.filters = {}
        for key, label in [('query', 'Name / description'), ('commander', 'Commander'),
                           ('owner', 'Owner'), ('tag', 'Tag / theme'), ('color', 'Color identity (WU, C, etc.)')]:
            field = W.QLineEdit()
            field.setMaxLength(256)
            field.returnPressed.connect(self.search)
            filters.addRow(label, field)
            self.filters[key] = field
        layout.addWidget(self.filters_container)
        actions = W.QHBoxLayout()
        self.search_button = W.QPushButton('Search / Refresh')
        self.search_button.clicked.connect(self.search)
        self.more_button = W.QPushButton('Load more')
        self.more_button.clicked.connect(lambda: self.search(more=True))
        self.copy_button = W.QPushButton('Copy to My Decks')
        self.copy_button.clicked.connect(self.copy_selected)
        self.follow_button = W.QPushButton('Follow Deck')
        self.follow_button.clicked.connect(self.follow_selected)
        for button in (self.search_button, self.more_button, self.follow_button, self.copy_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        split = W.QSplitter()
        self.results = W.QListWidget()
        self.results.setAccessibleName('Shared decks')
        self.results.setIconSize(C.QSize(90, 126))
        self.results.currentItemChanged.connect(self.preview)
        split.addWidget(self.results)
        self.details = W.QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName('Shared deck preview')
        split.addWidget(self.details)
        layout.addWidget(split, 1)
        from .library_following import FollowingPanel
        self.following = FollowingPanel(self)
        layout.addWidget(self.following)
        self.progress = W.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.setCentralWidget(body)
        self.reload_connections()

    def connection(self):
        return self.selector.currentData()

    def reload_connections(self, selected=None):
        selected = selected or (self.connection() or {}).get('id')
        self.selector.blockSignals(True)
        self.selector.clear()
        for row in self.connections.list():
            self.selector.addItem(row['name'] + ' — ' + row['url'], row)
        for index in range(self.selector.count()):
            if self.selector.itemData(index)['id'] == selected:
                self.selector.setCurrentIndex(index)
        self.selector.blockSignals(False)
        self.switch_library()

    def switch_library(self):
        self.results.clear()
        self.details.clear()
        if self.view_mode.currentIndex() == 1:
            self.refresh_follows()
            return
        connection = self.connection()
        view = self.views.get(connection['id']) if connection else None
        for key, field in self.filters.items():
            field.setText(view['filters'].get(key, '') if view else '')
        if view:
            self.render(view['rows'])
        self.update_controls()

    def update_controls(self):
        busy = bool(self._job) or self.jobs.busy
        connection = self.connection()
        client = self.clients.get(connection['id']) if connection else None
        connected = bool(client and client.token)
        follows = self.view_mode.currentIndex() == 1
        self.selector.setEnabled(not busy)
        self.add_button.setEnabled(not busy)
        self.login_button.setEnabled(bool(connection) and not busy)
        self.remove_button.setEnabled(bool(connection) and not busy)
        self.disconnect_button.setEnabled(connected and not busy)
        self.search_button.setEnabled(connected and not busy and not follows)
        self.search_button.setVisible(not follows)
        self.more_button.setVisible(not follows)
        self.filters_container.setVisible(not follows)
        self.follow_button.setVisible(not follows)
        self.follow_button.setEnabled(connected and not busy and self.results.currentItem() is not None and not follows)
        self.following.setVisible(follows)
        self.following.refresh()
        view = self.views.get(connection['id'], {}) if connection else {}
        self.more_button.setEnabled(connected and view.get('more', False) and not busy)
        self.copy_button.setEnabled(self.results.currentItem() is not None and not busy)
        for field in self.filters.values():
            field.setEnabled(not busy)
        self.publishing.refresh()
        self.progress.setVisible(bool(self._job))
        if not connection:
            self.connection_status.setText('No libraries configured. Add your own server or a friend’s library. ' + self.message)
        elif not self._job:
            state = self.states.get(connection['id'], '')
            base = 'Signed in.' if connected else 'Disconnected. Sign in to search online.'
            self.connection_status.setText(base + (' ' + state if state else ''))

    def submit(self, operation, work, complete, *, with_context=False):
        if self._job or self.jobs.busy:
            return
        connection = self.connection()
        self._operation_connection = connection['id'] if connection else None
        self._completion = complete
        def run(cancel, report):
            if cancel.is_set():
                raise DownloadCancelled()
            report({'operation': operation})
            return work(cancel, report) if with_context else work()
        self._job = self.jobs.submit(run)
        self.update_controls()
        self.connection_status.setText(operation + '…')

    @C.pyqtSlot(str, str, object)
    def job_status(self, job_id, state, value):
        if job_id != self._job or state not in ('completed', 'failed', 'cancelled'):
            return
        complete = self._completion
        self._job, self._completion = None, None
        key = self._operation_connection
        if state == 'completed':
            try:
                complete(value)
            except Exception:
                message = 'The operation finished, but its result could not be displayed. Retry or reopen Browse Online.'
                self.message = message
                if key:
                    self.states[key] = message
        elif key:
            self.states[key] = ('Request failed: ' + str(value) + ' Existing results are an earlier snapshot.'
                                if state == 'failed' else 'Operation cancelled. Existing results are unchanged.')
        else:
            self.message = str(value) if state == 'failed' else 'Operation cancelled.'
        # JobQueue still owns the worker until idle; only then re-enable actions.
        self.update_controls()

    def sign_in(self, *, new):
        connection = None if new else self.connection()
        if not new and not connection:
            return
        dialog = SignInDialog(self, connection)
        if dialog.exec() != W.QDialog.DialogCode.Accepted:
            dialog.password.clear()
            dialog.invitation.clear()
            return
        url, username, password, invitation = (dialog.url.text().strip(), dialog.username.text().strip(),
                                               dialog.password.text(), dialog.invitation.text().strip())
        allow_lan = dialog.lan.isChecked()
        dialog.password.clear()
        dialog.invitation.clear()
        # Construct and validate in worker as SSL setup may read certificate files.
        old_client = self.clients.get(connection['id']) if connection else None
        def work():
            client = self.client_factory(url, allow_lan=allow_lan,
                                         server_id=connection['server_id'] if connection else None)
            info = client.login(username, password, invitation=invitation)
            try:
                record = connection or self.connections.add(client, info)
            except Exception:
                try:
                    client.disconnect()
                except Exception:
                    pass
                raise
            if old_client:
                try:
                    old_client.disconnect()
                except Exception:
                    pass
            return client, record
        def complete(value):
            client, record = value
            self.clients[record['id']] = client
            self.states[record['id']] = 'Signed in. Select Search / Refresh to browse.'
            self.reload_connections(record['id'])
        self.submit('Signing in to library', work, complete)

    def disconnect(self):
        connection = self.connection()
        client = self.clients.get(connection['id']) if connection else None
        if not client:
            return
        def work():
            try:
                client.disconnect()
                return 'Session ended on the server.'
            except Exception:
                return 'Local session cleared. Server unavailable; its session will expire automatically.'
        def complete(message):
            self.states[connection['id']] = message
        self.submit('Disconnecting', work, complete)

    def remove(self):
        connection = self.connection()
        if not connection:
            return
        client = self.clients.get(connection['id'])
        def work():
            if client:
                try:
                    client.disconnect()
                except Exception:
                    pass
            self.connections.remove(connection['id'])
        def complete(_):
            for mapping in (self.clients, self.views, self.states):
                mapping.pop(connection['id'], None)
            self.reload_connections()
        self.submit('Removing library connection', work, complete)

    def search(self, *, more=False):
        if self.view_mode.currentIndex() == 1:
            return
        connection = self.connection()
        client = self.clients.get(connection['id']) if connection else None
        if not client or not client.token:
            return
        previous = self.views.get(connection['id'], {})
        filters = {key: field.text().strip() for key, field in self.filters.items() if field.text().strip()}
        # Loading another page always continues the previous query, regardless of draft edits.
        if more:
            filters = previous.get('filters', {})
        offset = previous.get('offset', 0) + 50 if more else 0
        def complete(rows):
            combined = {row['deck_id']: row for row in (previous.get('rows', []) if more else [])}
            combined.update({row['deck_id']: row for row in rows})
            self.views[connection['id']] = {'rows': list(combined.values()), 'filters': filters,
                                            'offset': offset, 'more': len(rows) == 50}
            self.states[connection['id']] = f'{len(combined)} shared decks in this search snapshot.'
            self.switch_library()
        self.submit('Searching library', lambda: client.browse(filters, offset=offset), complete)

    def render(self, rows):
        self.results.clear()
        for row in rows:
            deck = row['deck']
            commanders = [entry['name'] for entry in deck['entries'] if entry['entry_id'] in deck['commander_entry_ids']]
            label = (deck['name'] + '\n' + row['owner'] + ' · ' + (''.join(row['color_identity']) or 'C')
                     + '\n' + ', '.join(commanders) + '\n' + ', '.join(deck['tags']))
            if row.get('follow'):
                follow = row['follow']
                label += f"\nFollowed · {follow['server_name']} · cached revision {row['revision']}"
                if not follow['active']:
                    label += ' · stopped'
                if follow['pending_revision']:
                    label += f" · update {follow['pending_revision']} available"
                label += '\n' + follow['state']
            item = W.QListWidgetItem(label)
            item.setData(C.Qt.ItemDataRole.UserRole, row)
            item.setSizeHint(C.QSize(280, 180 if row.get('follow') else 140))
            self.results.addItem(item)
        self.refresh_icons()
        self.update_controls()

    def refresh_icons(self):
        for index in range(self.results.count()):
            item = self.results.item(index)
            deck = item.data(C.Qt.ItemDataRole.UserRole)['deck']
            cover = next((entry for entry in deck['entries'] if entry['entry_id'] in deck['commander_entry_ids']),
                         next(iter(deck['entries']), None))
            if cover and cover.get('card_id'):
                pixmap = self.thumbnails.get(cover['card_id'])
                if pixmap is not None and not pixmap.isNull():
                    item.setIcon(G.QIcon(pixmap))

    def preview(self, current=None, previous=None):
        if current is None:
            self.details.clear()
            self.update_controls()
            return
        row = current.data(C.Qt.ItemDataRole.UserRole)
        prefix = ''
        if row.get('follow'):
            follow = row['follow']
            prefix = 'FOLLOWED DECK — READ-ONLY OFFLINE CACHE\n' + follow['server_name'] + '\n' + follow['message'] + '\n\n'
        self.details.setPlainText(prefix + self.publication_text(row))
        self.update_controls()

    @staticmethod
    def publication_text(row):
        deck = row['deck']
        categories = {item['category_id']: item['name'] for item in deck['categories']}
        lines = [deck['name'], f"Owner: {row['owner']} · Revision: {row['revision']}",
                 'Colors: ' + (''.join(row['color_identity']) or 'C'),
                 'Tags: ' + ', '.join(deck['tags']), deck['description'], '',
                 'Shared preview — Copy to My Decks creates an independent, editable deck.', '']
        for entry in deck['entries']:
            commander = ' [Commander]' if entry['entry_id'] in deck['commander_entry_ids'] else ''
            printing = ' '.join(filter(None, (entry.get('set_code'), entry.get('collector_number'))))
            lines.append(f"{entry['quantity']} × {entry['name']}{commander} ({printing}) — {entry['section']}")
            labels = [categories[key] for key in entry['category_ids']]
            lines.append('  Categories: ' + ', '.join(labels) + ' · Tags: ' + ', '.join(entry['tags']))
            if entry.get('card_id'):
                lines.append('  Printing ID: ' + entry['card_id'])
            if entry['notes']:
                lines.append('  ' + entry['notes'])
        return '\n'.join(lines)

    def copy_selected(self):
        connection, item = self.connection(), self.results.currentItem()
        if item is None:
            return
        publication = item.data(C.Qt.ItemDataRole.UserRole)
        source = publication.get('follow') or connection
        if not source:
            return
        def complete(path):
            message = 'Independent copy saved in My Decks. Open it from Deck Editor → Projects.'
            self.message = message
            if connection:
                self.states[connection['id']] = message
            self.copyCreated.emit(path)
        self.submit('Copying deck to My Decks', lambda: copy_publication(publication,
                    server_id=source['server_id'], server_address=source.get('server_url') or source['url'],
                    deck_root=self.deck_root), complete)

    def follow_selected(self):
        connection, item = self.connection(), self.results.currentItem()
        client = self.clients.get(connection['id']) if connection else None
        if not item or not client or not client.token or self.view_mode.currentIndex() != 0:
            return
        deck_id = item.data(C.Qt.ItemDataRole.UserRole)['deck_id']
        def work():
            client.check()
            return self.followed.add(client.download(deck_id), server_id=connection['server_id'],
                                     address=connection['url'], name=connection['name'])
        def complete(_):
            self.states[connection['id']] = 'Deck followed. Accepted cache is available read-only offline.'
            self.view_mode.setCurrentIndex(1)
            self.refresh_follows()
        self.submit('Following shared deck', work, complete)

    def refresh_follows(self):
        try:
            records = self.followed.list()
        except (sqlite3.Error, OSError, ValueError, TypeError, LibraryError):
            self.following.status.setText('Followed deck cache could not be read. Check local storage or restore a backup; no cache was replaced.')
            return
        count = sum(bool(record['pending']) for record in records)
        self.view_mode.setItemText(1, f'Followed decks (offline · {count} updates)')
        if self.view_mode.currentIndex() != 1:
            self.update_controls()
            return
        selected = self.results.currentItem()
        selected = selected.data(C.Qt.ItemDataRole.UserRole).get('follow') if selected else None
        rows = []
        for record in records:
            try:
                publication = self.followed.publication(record)
            except (ValueError, TypeError, LibraryError):
                self.following.status.setText('A cached deck contains invalid data. Its stored copy was kept for repair; other follows remain available.')
                continue
            publication['follow'] = {key: record[key] for key in
                ('server_id', 'deck_id', 'server_url', 'server_name', 'active', 'state', 'message')}
            publication['follow']['pending_revision'] = record['pending']['revision'] if record['pending'] else None
            rows.append(publication)
        self.render(rows)
        if selected:
            for index, row in enumerate(rows):
                if (row['follow']['server_id'], row['deck_id']) == (selected['server_id'], selected['deck_id']):
                    self.results.setCurrentRow(index)

    def prepare_to_close(self):
        if self._job:
            self.jobs.cancel(self._job)
            return False
        # Clear memory credentials at exit, without making a network request during shutdown.
        for client in self.clients.values():
            client.token = None
        self.following.timer.stop()
        self.thumbnails.stopping = True
        self.thumbnails.pending.clear()
        self.thumbnails.next_timer.stop()
        return self.thumbnails.worker is None
