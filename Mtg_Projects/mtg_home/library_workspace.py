"""Opt-in library browsing with the shared job queue and local deck persistence."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import sqlite3
from time import monotonic

from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_core.downloads import DownloadCancelled
from mtg_core.library import LibraryError
from mtg_core.library.client import LibraryClient, LibraryConnections, copy_publication
from mtg_core.library.publishing import PublicationJournal
from mtg_core.library.following import FollowedDecks
from mtg_core.library.sessions import SavedSessions
from mtg_core.paths import data_root
from mtg_editor.card_views import Thumbnails
from mtg_editor.card_drop import CardSearchEdit
from mtg_editor.project_browser import ProjectList, ProjectTileDelegate
from .library_widgets import COLOR_NAMES, ColorChoices, DeckPreviewDialog, SignInDialog, plain_label
from mtg_ui.jobs import JobQueue


class _LocalArtwork:
    """Reuse thumbnails without initiating card-provider network requests."""
    def __init__(self, service):
        self.service = service

    def get_image_path(self, card_id):
        return self.service.get_image_path(card_id)


class LibraryWorkspace(W.QMainWindow):
    copyCreated = C.pyqtSignal(object)
    masterSyncStatus = C.pyqtSignal(str)
    followUpdates = C.pyqtSignal(str, int)
    editorRequested = C.pyqtSignal()

    def __init__(self, service, parent=None, *, jobs=None, root=None, deck_root=None, client_factory=LibraryClient):
        super().__init__(parent)
        self.setWindowTitle('Browse Online')
        self.connections = LibraryConnections(root or data_root())
        self.saved_sessions = SavedSessions(self.connections.path.parent)
        self._saved_restore_attempted = False
        self.publications = PublicationJournal(self.connections)
        self.master_retry = {}
        self.master_timer = C.QTimer(self)
        self.master_timer.setInterval(30000)
        self.master_timer.timeout.connect(self.sync_local_master)
        self.master_timer.start()
        self.followed = FollowedDecks(self.connections)
        from mtg_core.library.recommendations import LibraryRecommendations
        self.recommendations = LibraryRecommendations(self.connections.path.parent / 'library-recommendations.sqlite3')
        from mtg_core.library.category_evidence import CategoryEvidence
        self.category_evidence = CategoryEvidence(self.connections.path.parent / 'library-category-evidence.sqlite3')
        self.deck_root = Path(deck_root or data_root() / 'decks')
        self.client_factory = client_factory
        self.clients, self.views, self.states = {}, {}, {}
        self.connection_errors = {}
        self.message = ''
        self._job = None
        self._completion = None
        self._operation_connection = None
        self._error_handler = None
        self._signin_dialog = None
        self._load_after_signin = None
        self.jobs = jobs or JobQueue(self)
        self.jobs.status.connect(self.job_status)
        self.jobs.progress.connect(self.library_progress)
        self.jobs.idle.connect(self.queue_idle)
        self.thumbnails = Thumbnails(_LocalArtwork(service), self)
        self.thumbnails.updated.connect(self.refresh_icons)
        body = W.QWidget()
        layout = W.QVBoxLayout(body)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(10)
        header = W.QHBoxLayout()
        title = plain_label('Browse Online', 'title')
        header.addWidget(title)
        header.addStretch()
        header.addWidget(plain_label('All libraries', 'muted'))
        self.add_button = W.QPushButton('Join library')
        self.add_button.setProperty('buttonRole', 'primary')
        self.add_button.clicked.connect(lambda: self.sign_in(new=True))
        self.login_button = W.QPushButton('Sign in')
        self.login_button.setProperty('buttonRole', 'primary')
        self.login_button.clicked.connect(self.reconnect)
        header.addWidget(self.add_button)
        header.addWidget(self.login_button)
        self.library_button = W.QToolButton()
        self.library_button.setText('Libraries')
        self.library_button.setAccessibleName('Manage libraries')
        self.library_button.setPopupMode(W.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.library_menu = W.QMenu(self.library_button)
        self.library_button.setMenu(self.library_menu)
        self.login_menu = W.QMenu(self.login_button)
        header.addWidget(self.library_button)
        layout.addLayout(header)
        self.connection_status = plain_label('', 'muted')
        layout.addWidget(self.connection_status)
        from .library_publishing import PublishingPanel
        self.publishing = PublishingPanel(self)
        tabs_row = W.QHBoxLayout()
        self.view_mode = W.QTabBar()
        self.view_mode.setAccessibleName('Library view')
        self.view_mode.addTab('Shared decks')
        self.view_mode.addTab('Following')
        self.view_mode.setExpanding(False)
        self.view_mode.currentChanged.connect(self.switch_library)
        tabs_row.addWidget(self.view_mode)
        tabs_row.addStretch()
        layout.addLayout(tabs_row)
        search = W.QHBoxLayout()
        self.filters = {'query': CardSearchEdit()}
        self.filters['query'].setPlaceholderText('Search decks…')
        self.filters['query'].setAccessibleName('Search shared or followed decks')
        self.filters['query'].returnPressed.connect(self.search_current)
        self.filters['query'].textEdited.connect(self.query_edited)
        search.addWidget(self.filters['query'], 1)
        self.filter_button = W.QPushButton('Filters')
        self.filter_button.setCheckable(True)
        self.filter_button.toggled.connect(self.toggle_filters)
        search.addWidget(self.filter_button)
        self.search_button = W.QPushButton('Refresh')
        self.search_button.clicked.connect(self.search)
        search.addWidget(self.search_button)
        self.sort = W.QComboBox()
        self.sort.setAccessibleName('Sort shared decks')
        self.sort.addItems(['Library order', 'Name: A–Z', 'Cards: most first'])
        self.sort.currentIndexChanged.connect(self.sort_gallery)
        search.addWidget(self.sort)
        layout.addLayout(search)
        self.filters_container = W.QFrame()
        self.filters_container.setProperty('role', 'panel')
        filters = W.QGridLayout(self.filters_container)
        for column, (key, label) in enumerate([('commander', 'Commander'), ('owner', 'Owner'), ('tag', 'Tag or theme')]):
            self.filters[key] = W.QLineEdit()
            self.filters[key].setPlaceholderText(label)
            self.filters[key].setAccessibleName(label + ' filter')
            self.filters[key].setMaxLength(256)
            self.filters[key].returnPressed.connect(self.search)
            filters.addWidget(self.filters[key], 0, column)
        self.filters['color'] = ColorChoices()
        filters.addWidget(self.filters['color'], 1, 0, 1, 3)
        filter_actions = W.QHBoxLayout()
        self.clear_filters_button = W.QPushButton('Reset filters')
        self.clear_filters_button.clicked.connect(self.clear_filters)
        filter_actions.addWidget(self.clear_filters_button)
        filter_actions.addStretch()
        apply_filters = W.QPushButton('Apply filters')
        apply_filters.setProperty('buttonRole', 'primary')
        apply_filters.clicked.connect(self.search)
        filter_actions.addWidget(apply_filters)
        filters.addLayout(filter_actions, 2, 0, 1, 3)
        self.filters_container.hide()
        layout.addWidget(self.filters_container)
        self.gallery_stack = W.QStackedWidget()
        self.results = ProjectList()
        self.results.setAccessibleName('Shared decks')
        self.results.setViewMode(W.QListView.ViewMode.IconMode)
        self.results.setResizeMode(W.QListView.ResizeMode.Adjust)
        self.results.setMovement(W.QListView.Movement.Static)
        self.results.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results.setSelectionMode(W.QAbstractItemView.SelectionMode.SingleSelection)
        self.results.setSpacing(8)
        self.results.setGridSize(C.QSize(228, 290))
        self.results.setMouseTracking(True)
        self.results.setItemDelegate(ProjectTileDelegate(self))
        self.results.currentItemChanged.connect(self.preview)
        self.results.itemClicked.connect(self.open_preview)
        self.results.itemActivated.connect(self.open_preview)
        self.results.verticalScrollBar().valueChanged.connect(self.refresh_icons)
        self.gallery_stack.addWidget(self.results)
        empty = W.QWidget()
        empty_layout = W.QVBoxLayout(empty)
        empty_layout.addStretch()
        self.empty_title = plain_label('', 'title')
        self.empty_title.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
        self.empty_text = plain_label('', 'subtitle')
        self.empty_text.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_title)
        empty_layout.addWidget(self.empty_text)
        self.empty_button = W.QPushButton('Join library')
        self.empty_button.setProperty('buttonRole', 'primary')
        self.empty_button.clicked.connect(self.empty_action)
        empty_layout.addWidget(self.empty_button, 0, C.Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addStretch()
        self.gallery_stack.addWidget(empty)
        layout.addWidget(self.gallery_stack, 1)
        bottom = W.QHBoxLayout()
        self.result_count = plain_label('', 'muted')
        bottom.addWidget(self.result_count)
        bottom.addStretch()
        self.more_button = W.QPushButton('Load more')
        self.more_button.clicked.connect(lambda: self.search(more=True))
        bottom.addWidget(self.more_button)
        layout.addLayout(bottom)
        self.preview_dialog = DeckPreviewDialog(self)
        self.details = self.preview_dialog.notes
        self.copy_button = W.QPushButton('Make editable copy')
        self.copy_button.setProperty('buttonRole', 'primary')
        self.copy_button.clicked.connect(self.copy_selected)
        self.follow_button = W.QPushButton('Follow deck')
        self.follow_button.clicked.connect(self.follow_selected)
        self.preview_dialog.footer.addWidget(self.follow_button)
        self.preview_dialog.footer.addWidget(self.copy_button)
        from .library_following import FollowingPanel
        self.following = FollowingPanel(self)
        self.preview_dialog.footer.addWidget(self.following.review_button)
        self.preview_dialog.footer.addWidget(self.following.accept_button)
        self.preview_dialog.more_menu.addAction(self.following.stop_button)
        self.preview_dialog.footer.addWidget(self.publishing.accept_button)
        layout.insertWidget(4, self.following)
        self.progress = W.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumHeight(4)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.search_timer = C.QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(450)
        self.search_timer.timeout.connect(self.search)
        shortcut = G.QShortcut(G.QKeySequence('Ctrl+F'), self)
        shortcut.setContext(C.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.filters['query'].setFocus)
        self.setCentralWidget(body)
        self.reload_connections()
        C.QTimer.singleShot(0, self.restore_saved_sessions)

    def connection(self, connection_id=None):
        records = self.connections.list()
        if connection_id:
            return next((row for row in records if row['id'] == connection_id), None)
        return records[0] if len(records) == 1 else None

    def connected_libraries(self):
        return [row for row in self.connections.list() if getattr(self.clients.get(row['id']), 'token', None)]

    def selected_connection(self):
        item = self.results.currentItem()
        row = item.data(C.Qt.ItemDataRole.UserRole) if item else {}
        if row.get('library'):
            return self.connection(row['library']['id'])
        follow = row.get('follow')
        if follow:
            return next((record for record in self.connections.list() if record['server_id'] == follow['server_id']), None)
        return self.connection()

    @staticmethod
    def row_key(row):
        source = row.get('follow') or row.get('library') or {}
        return source.get('server_id'), row['deck_id']

    def reload_connections(self, selected=None):
        self.switch_library()

    def rebuild_library_menu(self):
        self.library_menu.clear()
        self.library_menu.addAction('Join another library...', lambda: self.sign_in(new=True))
        for record in self.connections.list():
            client = self.clients.get(record['id'])
            signed_in = bool(client and client.token)
            state = 'Unavailable' if record['id'] in self.connection_errors else ('Connected' if signed_in else 'Sign in needed')
            menu = self.library_menu.addMenu(record['name'] + ' - ' + state)
            menu.setToolTipsVisible(True)
            contribution = menu.addAction('Share manual categories when publishing decks')
            contribution.setCheckable(True)
            contribution.setChecked(self.category_evidence.consent(record['server_id']))
            contribution.setToolTip('Opt in for this library. Shares deliberate category choices only for decks you publish. Private local decks stay private.')
            contribution.toggled.connect(lambda checked, row=record: self.category_evidence.consent(row['server_id'], checked))
            if record['id'] in self.connection_errors:
                message = self.connection_errors[record['id']]
                action = menu.addAction(message.splitlines()[0][:120])
                action.setEnabled(False)
                action.setToolTip(message)
                menu.addSeparator()
            if signed_in:
                menu.addAction('Refresh community categories', lambda checked=False, row=record: self.refresh_category_evidence(row))
                menu.addAction('Sign in as another user...', lambda checked=False, row=record: self.sign_in(new=False, connection=row))
                menu.addAction('Sign out', lambda checked=False, row=record: self.disconnect(connection=row))
            else:
                label = 'Reconnect' if self.saved_sessions.has(record['id']) else 'Sign in...'
                menu.addAction(label, lambda checked=False, row=record: self.reconnect(connection=row))
            menu.addAction('Remove connection...', lambda checked=False, row=record: self.confirm_remove(connection=row))
        if self.connections.list():
            self.library_menu.addSeparator()
            self.library_menu.addAction(self.following.automatic)

    def switch_library(self):
        if self.view_mode.currentIndex() == 1:
            self.refresh_follows()
        else:
            self.render_shared()

    def search_filters(self):
        return {key: field.text().strip() for key, field in self.filters.items() if field.text().strip()}

    def render_shared(self):
        filters = self.search_filters()
        combined = {}
        records = self.connections.list()
        # Prefer the authenticated connection if the same library has two saved origins.
        records.sort(key=lambda row: bool(getattr(self.clients.get(row['id']), 'token', None)))
        for record in records:
            view = self.views.get(record['id'])
            if not view or view.get('filters', {}) != filters:
                continue
            for value in view['rows']:
                row = dict(value)
                row['library'] = record
                row['cached'] = record['id'] in self.connection_errors or not getattr(self.clients.get(record['id']), 'token', None)
                combined[(record['server_id'], row['deck_id'])] = row
        self.render(list(combined.values()))

    def update_controls(self):
        busy = bool(self._job) or self.jobs.busy
        records, connected = self.connections.list(), self.connected_libraries()
        disconnected = [row for row in records if not getattr(self.clients.get(row['id']), 'token', None)]
        follows = self.view_mode.currentIndex() == 1
        self.library_button.setVisible(bool(records))
        self.library_button.setEnabled(not busy)
        self.rebuild_library_menu()
        self.add_button.setVisible(not records and follows)
        self.add_button.setEnabled(not busy)
        self.login_button.setVisible(bool(disconnected))
        label = 'Reconnect' if disconnected and all(self.saved_sessions.has(row['id']) for row in disconnected) else 'Sign in'
        self.login_button.setText(label + (f' ({len(disconnected)})' if len(disconnected) > 1 else ''))
        self.login_button.setEnabled(not busy)
        self.search_button.setVisible(bool(records) and not follows)
        self.search_button.setEnabled(bool(connected) and not busy)
        self.filters['query'].setVisible(bool(records) or follows)
        self.filter_button.setVisible(bool(records) and not follows)
        self.filter_button.setEnabled(bool(connected) and not busy)
        self.filters_container.setVisible(not follows and self.filter_button.isChecked() and bool(records))
        active_filters = sum(bool(field.text()) for key, field in self.filters.items() if key != 'query')
        self.filter_button.setText(f'Filters ({active_filters})' if active_filters else 'Filters')
        self.sort.setVisible(bool(records) or follows)
        self.sort.setEnabled(not busy and bool(self.results.count()))
        self.following.setVisible(follows)
        self.following.refresh()
        filters = self.search_filters()
        more = any(self.views.get(row['id'], {}).get('more') and self.views[row['id']].get('filters', {}) == filters for row in connected)
        self.more_button.setVisible(not follows and more)
        self.more_button.setEnabled(not busy and more)
        for field in self.filters.values():
            field.setEnabled(not busy and (follows or bool(connected)))
        self.publishing.refresh()
        self.update_preview_actions()
        self.progress.setVisible(bool(self._job))
        if not self._job:
            summary = (f'{len(records)} ' + ('library' if len(records) == 1 else 'libraries')
                       + f' - {len(connected)} signed in') if records else ''
            errors = sum(row['id'] in self.connection_errors for row in records)
            if errors:
                summary += f' - {errors} unavailable'
            self.connection_status.setText(self.message or summary)
            self.connection_status.setVisible(bool(self.message or summary))
        self.update_empty_state()

    def update_preview_actions(self):
        busy = bool(self._job) or self.jobs.busy
        row = self.preview_dialog.row or {}
        normal = self.preview_dialog.scope == 'browse'
        follow = row.get('follow')
        connection = self.selected_connection()
        client = self.clients.get(connection['id']) if connection else None
        selected = self.results.currentItem() is not None
        self.copy_button.setVisible(normal)
        self.copy_button.setEnabled(selected and not busy)
        self.follow_button.setVisible(normal and not follow)
        self.follow_button.setEnabled(selected and bool(client and client.token) and not busy)
        self.following.review_button.setVisible(normal and bool(follow and follow['pending_revision']))
        self.following.accept_button.setVisible(self.preview_dialog.scope == 'follow_review')
        self.publishing.accept_button.setVisible(self.preview_dialog.scope == 'publication_review')
        self.preview_dialog.more_button.setVisible(normal and bool(follow))
        self.preview_dialog.close_button.setEnabled(not busy)

    def update_empty_state(self):
        visible = sum(not self.results.item(index).isHidden() for index in range(self.results.count()))
        self.result_count.setText(f'{visible} deck' + ('' if visible == 1 else 's'))
        self.gallery_stack.setCurrentIndex(0 if visible else 1)
        if visible:
            return
        records, connected = self.connections.list(), self.connected_libraries()
        follows = self.view_mode.currentIndex() == 1
        loaded = any(row['id'] in self.views for row in records)
        if self._job:
            title, text, action = 'Loading…', 'Your decks will appear here.', None
        elif follows:
            title, text, action = ('No matching decks', 'Try a different search.', 'Clear search') if self.results.count() else (
                'No followed decks yet', 'Follow a shared deck to keep a read-only copy available offline.', 'Browse shared decks')
        elif not records:
            title, text, action = 'Join a deck library', 'Connect to your own library or one shared by a friend.', 'Join library'
        elif not connected:
            title, text, action = 'Sign in to your libraries', 'Your local decks are always available in the Deck Editor.', 'Sign in'
        elif not loaded:
            title, text, action = 'Browse shared decks', 'See what your friends have shared across your libraries.', 'Load decks'
        elif any(field.text() for field in self.filters.values()):
            title, text, action = 'No decks found', 'Try another search or reset the filters.', 'Reset search'
        else:
            title, text, action = 'No decks shared yet', 'Publish a deck from the Deck Editor to get started.', 'Open Deck Editor'
        self.empty_title.setText(title)
        self.empty_text.setText(text)
        self.empty_button.setVisible(action is not None)
        if action:
            self.empty_button.setText(action)
        self.empty_button.setEnabled(not self._job and not self.jobs.busy)

    def empty_action(self):
        action = self.empty_button.text()
        if action == 'Join library':
            self.sign_in(new=True)
        elif action == 'Sign in':
            self.reconnect()
        elif action == 'Browse shared decks':
            self.view_mode.setCurrentIndex(0)
        elif action == 'Open Deck Editor':
            self.editorRequested.emit()
        elif action in ('Clear search', 'Reset search'):
            for field in self.filters.values():
                field.clear()
            self.search_current()
        else:
            self.search()

    def queue_idle(self):
        if not self._saved_restore_attempted:
            self.restore_saved_sessions()
            if self._job:
                return
        self.update_controls()
        key, self._load_after_signin = self._load_after_signin, None
        if key and self.view_mode.currentIndex() == 0:
            self.search()

    def reconnect(self, *, connection=None):
        if connection is None:
            records = [row for row in self.connections.list() if not getattr(self.clients.get(row['id']), 'token', None)]
            if len(records) > 1:
                self.login_menu.clear()
                for record in records:
                    self.login_menu.addAction(record['name'], lambda checked=False, row=record: self.reconnect(connection=row))
                self.login_menu.popup(self.login_button.mapToGlobal(C.QPoint(0, self.login_button.height())))
                return
            connection = records[0] if records else self.connection()
        if connection and self.saved_sessions.has(connection['id']):
            self.restore_saved_sessions(records=[connection])
        else:
            self.sign_in(new=False, connection=connection)

    def restore_saved_sessions(self, *, records=None):
        if self._job or self.jobs.busy or self._signin_dialog is not None:
            return
        if records is None:
            if self._saved_restore_attempted:
                return
            self._saved_restore_attempted = True
            records = self.connections.list()
        records = [row for row in records if self.saved_sessions.has(row['id'])
                   and not getattr(self.clients.get(row['id']), 'token', None)]
        if not records:
            return
        def work(cancel, report):
            result = []
            for record in records:
                if cancel.is_set():
                    raise DownloadCancelled()
                report({'operation': 'Restoring library sign-in'})
                try:
                    saved = self.saved_sessions.load(record)
                    if saved is None:
                        result.append((record, None, 'Saved sign-in expired. Sign in again.'))
                        continue
                    client = self.client_factory(record['url'], allow_lan=bool(record['allow_lan']), server_id=record['server_id'])
                    client.resume(saved)
                    try:
                        self.category_evidence.sync(client, should_cancel=cancel.is_set)
                    except (LibraryError, sqlite3.Error, OSError):
                        pass
                    result.append((record, client, ''))
                except LibraryError as error:
                    if error.status in (401, 403, 404, 409):
                        self.recommendations.revoke(record['server_id'])
                        self.category_evidence.revoke(record['server_id'])
                    if error.status in (401, 409):
                        self.saved_sessions.forget(record['id'])
                    result.append((record, None, str(error)))
            return result
        def complete(results):
            for record, client, message in results:
                self.states[record['id']] = message
                if client is not None:
                    self.clients[record['id']] = client
                    self.connection_errors.pop(record['id'], None)
                elif message:
                    self.connection_errors[record['id']] = message
            if self.connected_libraries() and not self.publishing.isVisible():
                self._load_after_signin = True
            self.switch_library()
        self.submit('Restoring saved sign-in', work, complete, with_context=True)

    def toggle_filters(self, checked):
        self.filters_container.setVisible(checked and self.view_mode.currentIndex() == 0)

    def clear_filters(self):
        for key, field in self.filters.items():
            if key != 'query':
                field.clear()
        self.search()

    def query_edited(self):
        if self.view_mode.currentIndex() == 1:
            self.filter_followed_rows()
        elif self.search_button.isEnabled():
            self.search_timer.start()

    def search_current(self):
        if self.view_mode.currentIndex() == 1:
            self.filter_followed_rows()
        else:
            self.search()

    def filter_followed_rows(self):
        query = self.filters['query'].text().strip().casefold()
        for index in range(self.results.count()):
            item = self.results.item(index)
            row = item.data(C.Qt.ItemDataRole.UserRole)
            deck = row['deck']
            words = [deck['name'], deck['description'], row['owner'], *deck['tags'],
                     *(entry['name'] for entry in deck['entries']), row.get('follow', {}).get('server_name', '')]
            item.setHidden(query not in ' '.join(words).casefold())
        self.update_empty_state()

    def sort_gallery(self):
        rows = [self.results.item(index).data(C.Qt.ItemDataRole.UserRole) for index in range(self.results.count())]
        self.render(rows)

    def confirm_remove(self, *, connection=None):
        if W.QMessageBox.question(self, 'Remove library connection',
                'Remove this saved connection? Your local decks and followed copies will stay on this computer.') == W.QMessageBox.StandardButton.Yes:
            self.remove(connection=connection)

    def closeEvent(self, event):
        self.master_timer.stop()
        super().closeEvent(event)

    def sync_local_master(self):
        self.master_timer.setInterval(30000)
        if self._job or self.jobs.busy:
            return
        try:
            pending = self.publications.queued_masters()
            connections = self.connections.list()
        except (OSError, sqlite3.Error):
            self.masterSyncStatus.emit('Saved locally. Library sync storage is unavailable; queued updates will retry.')
            return
        for queued in pending:
            key = queued['server_id'], queued['local_id']
            if self.master_retry.get(key, 0) > monotonic():
                continue
            connection = next((row for row in connections if row['server_id'] == queued['server_id']), None)
            client = self.clients.get(connection['id']) if connection else None
            if not client or not client.token or getattr(client, 'account_id', None) != queued['account_id']:
                continue
            snapshot = queued['snapshot']
            def work(client=client, queued=queued, snapshot=snapshot):
                try:
                    return dict(result=self.publications.send(client, queued['server_id'], queued['local_id'], **snapshot))
                except LibraryError as error:
                    return dict(error=str(error), status=error.status)
            def complete(value, queued=queued, connection=connection, snapshot=snapshot):
                if 'error' in value:
                    if 400 <= value['status'] < 500:
                        self.publications.pause_master(queued['server_id'], queued['local_id'])
                        message = 'Library sync paused. Review and publish this deck to resume: ' + value['error']
                    else:
                        self.master_retry[(queued['server_id'], queued['local_id'])] = monotonic() + 60
                        message = 'Saved locally. Library update queued for retry: ' + value['error']
                else:
                    self.master_retry.pop((queued['server_id'], queued['local_id']), None)
                    self._load_after_signin = True
                    message = snapshot['deck']['name'] + ' updated in ' + connection['name'] + '.'
                self.states[connection['id']] = message
                self.connection_status.setText(message)
                self.masterSyncStatus.emit(message)
            def failed(message, queued=queued):
                self.master_retry[(queued['server_id'], queued['local_id'])] = monotonic() + 60
                self.masterSyncStatus.emit('Saved locally. Library update queued for retry: ' + message)
            self.submit('Updating library from local master', work, complete, on_error=failed)
            return

    def submit(self, operation, work, complete, *, with_context=False, on_error=None):
        if self._job or self.jobs.busy:
            return
        connection = self.connection()
        self._operation_connection = connection['id'] if connection else None
        self._completion = complete
        self._error_handler = on_error
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
        complete, on_error = self._completion, self._error_handler
        self._error_handler = None
        self._job, self._completion = None, None
        key = self._operation_connection
        if state == 'completed':
            try:
                complete(value)
            except Exception:
                message = 'The operation finished, but its result could not be displayed. Retry or reopen Browse Online.'
                if on_error:
                    on_error(message)
                else:
                    self.message = message
                    if key:
                        self.states[key] = message
        elif on_error:
            on_error(str(value) if state == 'failed' else 'Connection cancelled.')
        elif key:
            self.states[key] = ('Request failed: ' + str(value) + ' Existing results are an earlier snapshot.'
                                if state == 'failed' else 'Operation cancelled. Existing results are unchanged.')
            client = self.clients.get(key)
            if state == 'failed' and client is not None and not client.token:
                try:
                    self.saved_sessions.forget(key)
                except LibraryError:
                    pass
        else:
            self.message = str(value) if state == 'failed' else 'Operation cancelled.'
        if state == 'failed' and not on_error:
            if self.preview_dialog.isVisible():
                self.preview_dialog.hint.setText(str(value))
                self.preview_dialog.hint.show()
            elif self.publishing.isVisible():
                self.publishing.show_error(str(value))
        # JobQueue still owns the worker until idle; only then re-enable actions.
        self.update_controls()

    def sign_in(self, *, new, connection=None):
        if self._job or self.jobs.busy:
            return
        if self._signin_dialog is not None and self._signin_dialog.isVisible():
            self._signin_dialog.raise_()
            return
        connection = None if new else (connection or self.connection())
        if not new and not connection:
            return
        parent = self.publishing if self.publishing.isVisible() else self
        dialog = SignInDialog(parent, connection)
        dialog.remember_supported = self.saved_sessions.available
        dialog.remember.setEnabled(self.saved_sessions.available)
        dialog.remember.setChecked(self.saved_sessions.available)
        if connection and self.saved_sessions.has(connection['id']):
            dialog.remember.setChecked(True)
            try:
                saved = self.saved_sessions.load(connection)
                if saved:
                    dialog.username.setText(saved.get('username', ''))
            except LibraryError:
                pass
        self._signin_dialog = dialog
        def submit():
            if self._job or self.jobs.busy:
                return
            url, username, password = dialog.url.text().strip(), dialog.username.text().strip(), dialog.password.text()
            invitation = dialog.invitation.text().strip() if dialog.mode.currentIndex() == 1 else ''
            allow_lan = dialog.lan.isChecked()
            remember = dialog.remember.isChecked() and self.saved_sessions.available
            old_client = self.clients.get(connection['id']) if connection else None
            dialog.set_busy(True)
            def work():
                client = self.client_factory(url, allow_lan=allow_lan,
                                             server_id=connection['server_id'] if connection else None)
                options = {'invitation': invitation}
                if remember:
                    options['remember'] = True
                info = client.login(username, password, **options)
                try:
                    record = connection or self.connections.add(client, info)
                except Exception:
                    try:
                        client.disconnect()
                    except Exception:
                        pass
                    raise
                warning = ''
                if old_client and getattr(old_client, 'account_id', None) != getattr(client, 'account_id', None):
                    self.category_evidence.revoke(record['server_id'])
                try:
                    self.category_evidence.sync(client)
                except (LibraryError, sqlite3.Error, OSError):
                    pass
                try:
                    if remember:
                        self.saved_sessions.save(record, client, username)
                    else:
                        self.saved_sessions.forget(record['id'])
                except LibraryError:
                    warning = 'Signed in for this session, but Windows could not save the sign-in. Check local storage permissions.'
                    try:
                        self.saved_sessions.forget(record['id'])
                    except LibraryError:
                        pass
                if old_client:
                    try:
                        old_client.disconnect()
                    except Exception:
                        pass
                return client, record, warning
            def complete(value):
                client, record, warning = value
                self.clients[record['id']] = client
                self.message = ''
                self.states[record['id']] = warning
                self.connection_errors.pop(record['id'], None)
                if warning:
                    self.statusBar().showMessage(warning, 15000)
                if self.publishing.isVisible():
                    self.publishing.use_connection(record['id'])
                self.reload_connections()
                if callable(getattr(client, 'browse', None)) and not self.publishing.isVisible():
                    self._load_after_signin = True
                dialog.password.clear()
                dialog.invitation.clear()
                dialog.set_busy(False)
                dialog.accept()
            self.submit('Signing in', work, complete, on_error=dialog.set_error)
        dialog.submitted.connect(submit)
        def finished(_):
            if self._signin_dialog is dialog:
                self._signin_dialog = None
            dialog.deleteLater()
            if not self._saved_restore_attempted:
                C.QTimer.singleShot(0, self.restore_saved_sessions)
        dialog.finished.connect(finished)
        dialog.open()
        (dialog.username if connection else dialog.url).setFocus()
        return dialog

    def forget_saved_sign_in(self, connection, client):
        saved = None
        if client is None and self.saved_sessions.has(connection['id']):
            try:
                saved = self.saved_sessions.load(connection)
            except LibraryError:
                pass
        self.saved_sessions.forget(connection['id'])
        try:
            if client is None and saved:
                client = self.client_factory(connection['url'], allow_lan=bool(connection['allow_lan']), server_id=connection['server_id'])
                client.resume(saved)
            if client:
                client.disconnect()
            return True
        except Exception:
            return False

    def disconnect(self, *, connection=None):
        connection = connection or self.connection()
        client = self.clients.get(connection['id']) if connection else None
        if not connection:
            return
        def work():
            self.recommendations.revoke(connection['server_id'])
            self.category_evidence.revoke(connection['server_id'])
            if self.forget_saved_sign_in(connection, client):
                return 'Signed out. Saved sign-in removed.'
            return 'Saved sign-in removed. Server unavailable; its session will expire automatically.'
        def complete(message):
            self.states[connection['id']] = message
            self.connection_errors.pop(connection['id'], None)
            self.message = message
            self.switch_library()
        self.submit('Disconnecting', work, complete)

    def remove(self, *, connection=None):
        connection = connection or self.connection()
        if not connection:
            return
        client = self.clients.get(connection['id'])
        def work():
            self.recommendations.revoke(connection['server_id'])
            self.category_evidence.revoke(connection['server_id'])
            self.forget_saved_sign_in(connection, client)
            self.publications.unlink_server(connection['server_id'])
            self.connections.remove(connection['id'])
        def complete(_):
            for mapping in (self.clients, self.views, self.states, self.connection_errors):
                mapping.pop(connection['id'], None)
            self.reload_connections()
        self.submit('Removing library connection', work, complete)

    def refresh_category_evidence(self, connection):
        client = self.clients.get(connection['id'])
        if client and client.token and not self._job and not self.jobs.busy:
            self.submit('Refreshing community categories',
                        lambda: self.category_evidence.sync(client, force=True),
                        lambda _: None)

    def search(self, *, more=False):
        if self.view_mode.currentIndex() == 1 or self._job or self.jobs.busy:
            return
        records = self.connected_libraries()
        filters = self.search_filters()
        if more:
            records = [row for row in records if self.views.get(row['id'], {}).get('more')
                       and self.views[row['id']].get('filters', {}) == filters]
        if not records:
            return
        self.search_timer.stop()
        previous = {row['id']: self.views.get(row['id'], {}) for row in records}
        def fetch(record, cancel):
            if cancel.is_set():
                raise DownloadCancelled()
            offset = previous[record['id']].get('offset', 0) + 50 if more else 0
            try:
                if not more:
                    try:
                        self.category_evidence.sync(self.clients[record['id']], should_cancel=cancel.is_set)
                    except (LibraryError, sqlite3.Error, OSError):
                        pass  # Evidence refresh is independent of browsing and editing.
                    try:
                        self.recommendations.sync(self.clients[record['id']], should_cancel=cancel.is_set)
                    except (sqlite3.Error, OSError):
                        pass  # Recommendation storage must not prevent library browsing.
                rows = self.clients[record['id']].browse(filters, offset=offset)
                return record, rows, offset, None
            except (LibraryError, OSError) as error:
                if isinstance(error, LibraryError) and error.status in (401, 403, 404, 409):
                    self.recommendations.revoke(record['server_id'])
                    self.category_evidence.revoke(record['server_id'])
                return record, None, offset, str(error)
        def work(cancel, report):
            outcomes = []
            with ThreadPoolExecutor(max_workers=min(4, len(records))) as pool:
                pending = [pool.submit(fetch, record, cancel) for record in records]
                for future in as_completed(pending):
                    if cancel.is_set():
                        for queued in pending:
                            queued.cancel()
                        raise DownloadCancelled()
                    outcome = future.result()
                    outcomes.append(outcome)
                    report({'operation': 'Loaded ' + outcome[0]['name'], 'phase': outcome[0]['id'],
                            'library_outcome': outcome, 'library_filters': filters, 'library_more': more})
            return outcomes
        def complete(outcomes):
            self.message = ''
            for outcome in outcomes:
                self.apply_library_outcome(outcome, filters, more)
            self.render_shared()
        self.submit('Loading all libraries', work, complete, with_context=True)

    def apply_library_outcome(self, outcome, filters, more):
        record, rows, offset, error = outcome
        key = record['id']
        if error is not None:
            self.connection_errors[key] = error
            self.states[key] = error
            client = self.clients.get(key)
            if client is not None and not client.token:
                try:
                    self.saved_sessions.forget(key)
                except LibraryError:
                    pass
            return
        previous = self.views.get(key, {})
        combined = {row['deck_id']: row for row in (previous.get('rows', []) if more else [])}
        combined.update({row['deck_id']: row for row in rows})
        self.views[key] = {'rows': list(combined.values()), 'filters': filters,
                           'offset': offset, 'more': len(rows) == 50}
        self.states[key] = ''
        self.connection_errors.pop(key, None)

    @C.pyqtSlot(str, object)
    def library_progress(self, job_id, value):
        if job_id != self._job or not isinstance(value, dict) or 'library_outcome' not in value:
            return
        self.apply_library_outcome(value['library_outcome'], value['library_filters'], value['library_more'])
        self.render_shared()

    def render(self, rows):
        selected = self.results.currentItem()
        selected = selected.data(C.Qt.ItemDataRole.UserRole) if selected else None
        key = self.row_key(selected) if selected else None
        rows = list(rows)
        if self.sort.currentIndex() == 1:
            rows.sort(key=lambda row: row['deck']['name'].casefold())
        elif self.sort.currentIndex() == 2:
            rows.sort(key=lambda row: -sum(entry['quantity'] for entry in row['deck']['entries']))
        self.results.clear()
        for source in rows:
            row = dict(source)
            deck = row['deck']
            cover = next((entry for entry in deck['entries'] if entry['entry_id'] in deck['commander_entry_ids']),
                         next(iter(deck['entries']), None))
            count = sum(entry['quantity'] for entry in deck['entries'])
            colors = ', '.join(COLOR_NAMES[color] for color in row['color_identity']) or 'Colorless'
            footer = ', '.join(deck['tags']) or 'No tags'
            follow = row.get('follow')
            if follow:
                footer = f"Update available · revision {follow['pending_revision']}" if follow['pending_revision'] else (
                    'Offline copy · following stopped' if not follow['active'] else f"Following · revision {row['revision']}")
            source_name = row.get('library', {}).get('name') or row.get('follow', {}).get('server_name')
            if row.get('cached'):
                footer = 'Cached preview - library unavailable or signed out'
            row.update(name=deck['name'], cover=(cover.get('card_id'), None) if cover else (None, None),
                       summary_lines=[f"{row['owner']} - {source_name or deck['format']}",
                                      f"{deck['format']} - {count} cards - {colors}", footer])
            label = deck['name'] + '\n' + '\n'.join(row['summary_lines'])
            if follow:
                label += '\nFollowed · ' + follow['server_name']
            item = W.QListWidgetItem(label)
            item.setData(C.Qt.ItemDataRole.UserRole, row)
            item.setToolTip(label)
            self.results.addItem(item)
            if self.row_key(row) == key:
                self.results.setCurrentItem(item)
        if self.view_mode.currentIndex() == 1:
            self.filter_followed_rows()
        self.refresh_icons()
        self.update_controls()

    def refresh_icons(self, *_):
        keys = []
        viewport = self.results.viewport().rect()
        for index in range(self.results.count()):
            item = self.results.item(index)
            if not item.isHidden() and self.results.visualItemRect(item).intersects(viewport):
                key = item.data(C.Qt.ItemDataRole.UserRole).get('cover', (None, None))
                if any(key):
                    keys.append(key)
        self.thumbnails.set_visible(id(self), keys)
        self.results.viewport().update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'results'):
            C.QTimer.singleShot(0, self.refresh_icons)

    def preview(self, current=None, previous=None):
        if current is None:
            self.details.clear()
            self.preview_dialog.row = None
            self.update_controls()
            return
        row = current.data(C.Qt.ItemDataRole.UserRole)
        follow = row.get('follow')
        hint = ('Read-only - Make an editable copy to change this deck. Available offline. ' + follow['message']) if follow else (
            'Cached preview. Refresh or sign in to its library for the latest version.' if row.get('cached') else '')
        self.preview_dialog.set_publication(row, hint=hint or 'Read-only - Make an editable copy to change this deck. Follow to keep it available offline.')
        self.update_controls()

    def open_preview(self, *_):
        if self._job or self.jobs.busy or self.results.currentItem() is None:
            return
        self.preview(self.results.currentItem())
        self.preview_dialog.show_for()

    def show_review(self, publication, *, scope, hint, parent=None):
        self.preview_dialog.set_publication(publication, scope=scope, hint=hint)
        self.preview_dialog.show_for(parent)
        self.update_preview_actions()

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
            if entry['notes']:
                lines.append('  ' + entry['notes'])
        return '\n'.join(lines)

    def copy_selected(self):
        connection, item = self.selected_connection(), self.results.currentItem()
        if item is None:
            return
        publication = item.data(C.Qt.ItemDataRole.UserRole)
        source = publication.get('follow') or publication.get('library') or connection
        if not source:
            return
        def complete(path):
            message = 'Independent copy saved in My Decks. Opening your editable deck.'
            self.message = message
            if connection:
                self.states[connection['id']] = message
            self.preview_dialog.hide()
            self.copyCreated.emit(path)
        self.submit('Copying deck to My Decks', lambda: copy_publication(publication,
                    server_id=source['server_id'], server_address=source.get('server_url') or source['url'],
                    deck_root=self.deck_root, library_name=source.get('name') or source.get('server_name')
                    or (connection or {}).get('name') or 'Library'), complete)

    def follow_selected(self):
        connection, item = self.selected_connection(), self.results.currentItem()
        client = self.clients.get(connection['id']) if connection else None
        if not item or not client or not client.token or self.view_mode.currentIndex() != 0:
            return
        deck_id = item.data(C.Qt.ItemDataRole.UserRole)['deck_id']
        def work():
            client.check()
            return self.followed.add(client.download(deck_id), server_id=connection['server_id'],
                                     address=connection['url'], name=connection['name'])
        def complete(_):
            self.states[connection['id']] = 'Deck followed. Available offline in Following.'
            self.preview_dialog.hide()
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
        self.view_mode.setTabText(1, f'Following ({count} updates)' if count else 'Following')
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
        self.master_timer.stop()
        self.following.timer.stop()
        self.search_timer.stop()
        if self._signin_dialog is not None:
            self._signin_dialog.reject()
        self.preview_dialog.hide()
        self.publishing.hide()
        self.thumbnails.stopping = True
        self.thumbnails.pending.clear()
        self.thumbnails.next_timer.stop()
        return self.thumbnails.worker is None
