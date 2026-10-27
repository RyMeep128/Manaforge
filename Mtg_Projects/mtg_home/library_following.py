"""Offline subscription controls; checking never applies a staged revision."""
import time
import sqlite3

from PyQt6 import QtCore as C, QtWidgets as W


class FollowingPanel(W.QWidget):
    def __init__(self, workspace):
        super().__init__(workspace)
        self.workspace = workspace
        self.reviewed = None
        self.checked_at = {}
        layout = W.QVBoxLayout(self)
        self.status = W.QLabel('Followed decks are read-only offline caches. Copy one to My Decks to edit it.')
        self.status.setTextFormat(C.Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = W.QHBoxLayout()
        self.check_button = W.QPushButton('Check selected library for updates')
        self.check_button.clicked.connect(self.check)
        self.review_button = W.QPushButton('Review cached update')
        self.review_button.clicked.connect(self.review)
        self.accept_button = W.QPushButton('Accept reviewed update')
        self.accept_button.clicked.connect(self.accept)
        self.stop_button = W.QPushButton('Stop following (keep offline copy)')
        self.stop_button.clicked.connect(self.stop)
        for button in (self.check_button, self.review_button, self.accept_button, self.stop_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.automatic = W.QCheckBox('Check this library every 5 minutes while signed in')
        self.automatic.toggled.connect(self.set_automatic)
        layout.addWidget(self.automatic)
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
        if self.workspace._job or self.workspace.jobs.busy:
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
            message = f"{connection['name']}: {count} update(s) available; {errors} source issue(s). Accepted caches unchanged."
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
            self.workspace.details.setPlainText('STAGED FOLLOW UPDATE — ACCEPT EXPLICITLY TO REPLACE THE OFFLINE CACHE\n\n'
                + self.workspace.publication_text(result['publication']))
            self.status.setText('Review the new deck above. Accepting preserves existing local print metadata and keeps a recovery snapshot.')
        self.workspace.submit('Opening cached update for review', lambda: self.workspace.followed.review(*key), complete)

    def accept(self):
        selected, reviewed = self.selected(), self.reviewed
        if not selected or not reviewed or (selected['server_id'], selected['deck_id']) != reviewed['key']:
            return
        def complete(_):
            self.reviewed = None
            self.status.setText('Update accepted. Local print metadata preserved. The followed deck remains read-only.')
            self.workspace.refresh_follows()
        self.workspace.submit('Accepting reviewed follow update',
            lambda: self.workspace.followed.accept(*reviewed['key'], reviewed['fingerprint']), complete)

    def stop(self):
        selected = self.selected()
        if not selected:
            return
        def complete(_):
            self.reviewed = None
            self.status.setText('Following stopped. The offline cache is still viewable and can be copied to My Decks.')
            self.workspace.refresh_follows()
        self.workspace.submit('Stopping deck subscription',
            lambda: self.workspace.followed.stop(selected['server_id'], selected['deck_id']), complete)
