"""Offline subscription controls; checking never applies a staged revision."""
import time
import sqlite3

from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W


class FollowingPanel(W.QWidget):
    def __init__(self, workspace):
        super().__init__(workspace)
        self.workspace = workspace
        self.reviewed = None
        self.checked_at = {}
        layout = W.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.status = W.QLabel('Available offline. Open a deck to view it or review an update.')
        self.status.setTextFormat(C.Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = W.QHBoxLayout()
        self.check_button = W.QPushButton('Check for updates')
        self.check_button.clicked.connect(self.check)
        self.review_button = W.QPushButton('Review update')
        self.review_button.clicked.connect(self.review)
        self.accept_button = W.QPushButton('Accept update')
        self.accept_button.setProperty('buttonRole', 'primary')
        self.accept_button.clicked.connect(self.accept)
        self.stop_button = G.QAction('Stop following (keep offline copy)', self)
        self.stop_button.triggered.connect(self.stop)
        actions.addWidget(self.check_button)
        layout.addLayout(actions)
        self.automatic = G.QAction('Check followed decks every 5 minutes', self)
        self.automatic.setCheckable(True)
        self.automatic.toggled.connect(self.set_automatic)
        self.timer = C.QTimer(self)
        self.timer.setInterval(30000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def selected(self):
        item = self.workspace.results.currentItem()
        return item.data(C.Qt.ItemDataRole.UserRole).get('follow') if item else None

    def refresh(self):
        busy = bool(self.workspace._job) or self.workspace.jobs.busy
        connection, selected = self.workspace.connection(), self.selected()
        client = self.workspace.clients.get(connection['id']) if connection else None
        self.check_button.setEnabled(bool(client and client.token) and not busy)
        self.automatic.setEnabled(bool(connection) and not busy)
        self.automatic.blockSignals(True)
        try:
            self.automatic.setChecked(self.workspace.followed.auto_check(connection['server_id']) if connection else False)
        except (sqlite3.Error, OSError):
            self.automatic.setChecked(False)
            self.automatic.setEnabled(False)
            self.status.setText('Follow preferences are unavailable. Check local storage and retry.')
        self.automatic.blockSignals(False)
        pending = bool(selected and selected['pending_revision'])
        self.review_button.setEnabled(pending and not busy)
        reviewed_here = bool(selected and self.reviewed and (selected['server_id'], selected['deck_id']) == self.reviewed['key'])
        self.accept_button.setEnabled(reviewed_here and pending and not busy and bool(selected['active']))
        self.stop_button.setEnabled(bool(selected and selected['active']) and not busy)

    def set_automatic(self, enabled):
        connection = self.workspace.connection()
        if connection:
            try:
                self.workspace.followed.auto_check(connection['server_id'], enabled)
            except Exception:
                self.status.setText('Could not save automatic check preference. Check local storage and retry.')
                self.automatic.blockSignals(True)
                self.automatic.setChecked(not enabled)
                self.automatic.blockSignals(False)

    def tick(self):
        if (self.workspace._job or self.workspace.jobs.busy or self.workspace.preview_dialog.isVisible()
                or self.workspace.publishing.isVisible() or self.workspace._signin_dialog is not None):
            return
        now = time.monotonic()
        try:
            for connection in self.workspace.connections.list():
                client = self.workspace.clients.get(connection['id'])
                if (client and client.token and self.workspace.followed.auto_check(connection['server_id'])
                        and now - self.checked_at.get(connection['server_id'], 0) >= 300):
                    self.check(connection=connection)
                    return  # Other due libraries get a turn on the next timer tick.
        except (sqlite3.Error, OSError):
            self.status.setText('Automatic checks paused because local storage is unavailable.')

    def check(self, *, connection=None):
        connection = connection or self.workspace.connection()
        client = self.workspace.clients.get(connection['id']) if connection else None
        if not client or not client.token:
            return
        self.checked_at[connection['server_id']] = time.monotonic()
        def complete(records):
            count = sum(bool(row['pending']) for row in records)
            errors = sum(row['state'] in ('offline', 'unavailable', 'source_changed') for row in records)
            message = f"{count} update(s) available" + (f" · {errors} unavailable source(s)" if errors else ".")
            self.status.setText(message)
            self.workspace.message = message
            self.workspace.states[connection['id']] = message
            self.workspace.refresh_follows()
            if count:
                self.workspace.followUpdates.emit(connection['name'], count)
        self.workspace.submit('Checking followed decks',
            lambda cancel, report: self.workspace.followed.check(client, cancel=cancel, report=report),
            complete, with_context=True)

    def review(self):
        selected = self.selected()
        if not selected:
            return
        key = (selected['server_id'], selected['deck_id'])
        def complete(result):
            self.reviewed = {'key': key, 'fingerprint': result['fingerprint']}
            self.workspace.show_review(result['publication'], scope='follow_review',
                hint='Review this update before replacing the offline copy. Your local print status will be kept.')
            self.status.setText('Review the update, then accept it when ready.')
        self.workspace.submit('Opening cached update for review', lambda: self.workspace.followed.review(*key), complete)

    def accept(self):
        selected, reviewed = self.selected(), self.reviewed
        if not selected or not reviewed or (selected['server_id'], selected['deck_id']) != reviewed['key']:
            return
        def complete(_):
            self.reviewed = None
            self.status.setText('Deck updated. Available offline.')
            self.workspace.refresh_follows()
        self.workspace.submit('Accepting reviewed follow update',
            lambda: self.workspace.followed.accept(*reviewed['key'], reviewed['fingerprint']), complete)

    def stop(self):
        selected = self.selected()
        if not selected:
            return
        def complete(_):
            self.reviewed = None
            self.status.setText('Following stopped. Your offline copy is still available.')
            self.workspace.refresh_follows()
        self.workspace.submit('Stopping deck subscription',
            lambda: self.workspace.followed.stop(selected['server_id'], selected['deck_id']), complete)
