"""Focused publication dialog over Browse Online's existing sessions and journal."""
import sqlite3

from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.library import LibraryError
from mtg_core.library.payload import shared_deck
from .library_widgets import ColorChoices, plain_label


class PublishingPanel(W.QDialog):
    def __init__(self, workspace):
        super().__init__(workspace)
        self.workspace = workspace
        self.snapshot = None
        self.community = None
        self.reviewed = None
        self._destination_id = None
        self.setWindowTitle('Publish deck')
        self.setWindowModality(C.Qt.WindowModality.WindowModal)
        self.setMinimumWidth(480)
        self.resize(560, 360)
        form = W.QVBoxLayout(self)
        form.setContentsMargins(24, 20, 24, 20)
        form.setSpacing(12)
        self.title = plain_label('Publish deck', 'title')
        form.addWidget(self.title)
        self.summary = plain_label('', 'subtitle')
        form.addWidget(self.summary)
        destination_row = W.QHBoxLayout()
        self.destination = W.QComboBox()
        self.destination.setAccessibleName('Destination library')
        self.destination.currentIndexChanged.connect(self.choose_library)
        destination_row.addWidget(self.destination, 1)
        self.connect_button = W.QPushButton('Join library')
        self.connect_button.setProperty('buttonRole', 'primary')
        self.connect_button.clicked.connect(self.connect_library)
        destination_row.addWidget(self.connect_button)
        form.addLayout(destination_row)
        self.color_label = plain_label('Color identity', 'subtitle')
        form.addWidget(self.color_label)
        self.colors = ColorChoices(allow_any=False)
        form.addWidget(self.colors)
        self.error = plain_label('', 'warning')
        self.error.hide()
        form.addWidget(self.error)
        form.addStretch()
        form.addWidget(plain_label('Your local printing status stays private.', 'muted'))
        footer = W.QHBoxLayout()
        self.more_button = W.QToolButton()
        self.more_button.setText('More')
        self.more_button.setPopupMode(W.QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = W.QMenu(self.more_button)
        self.review_button = menu.addAction('Review published deck', self.review)
        self.unpublish_button = menu.addAction('Unpublish deck', lambda: self.publish(unpublish=True))
        self.more_button.setMenu(menu)
        footer.addWidget(self.more_button)
        footer.addStretch()
        self.close_button = W.QPushButton('Cancel')
        self.close_button.clicked.connect(self.reject)
        self.publish_button = W.QPushButton('Publish deck')
        self.publish_button.setProperty('buttonRole', 'primary')
        self.publish_button.clicked.connect(self.publish)
        footer.addWidget(self.close_button)
        footer.addWidget(self.publish_button)
        form.addLayout(footer)
        self.accept_button = W.QPushButton('Use this revision')
        self.accept_button.setProperty('buttonRole', 'primary')
        self.accept_button.clicked.connect(self.accept_review)
        self.accept_button.hide()

    def prepare(self, deck, color_identity):
        if self.workspace._job or self.workspace.jobs.busy:
            self.workspace.connection_status.setText('Wait for the current operation, then publish again.')
            return False
        try:
            snapshot = shared_deck(deck)
        except LibraryError as error:
            self.workspace.connection_status.setText('Cannot prepare publication: ' + str(error))
            return False
        self.snapshot = snapshot
        self.community = deck.get('_manual_category_evidence')
        records = self.workspace.connections.list()
        self._destination_id = records[0]['id'] if len(records) == 1 else None
        self.colors.setText(color_identity)
        self.reviewed = None
        self.error.hide()
        self.refresh()
        self.open()
        return True

    def use_connection(self, connection_id):
        self._destination_id = connection_id
        self.refresh()

    def choose_library(self):
        selected = self.destination.currentData()
        if selected == '__join__':
            self.workspace.sign_in(new=True)
        else:
            self._destination_id = selected
        self.refresh()

    def connect_library(self):
        connection = self.workspace.connection(self._destination_id) if self._destination_id else None
        self.workspace.sign_in(new=connection is None, connection=connection)

    def context(self):
        connection = self.workspace.connection(self._destination_id) if self._destination_id else None
        if not connection or not self.snapshot:
            return None, None, None
        client = self.workspace.clients.get(connection['id'])
        link = self.workspace.publications.get(connection['server_id'], self.snapshot['deck_id'])
        return connection, client, link

    def refresh(self):
        if self.snapshot is None:
            return
        busy = bool(self.workspace._job) or self.workspace.jobs.busy
        try:
            connection, client, link = self.context()
            rows = self.workspace.connections.list()
        except (sqlite3.Error, OSError):
            self.show_error('Publication tracking is unavailable. Check local storage and retry.')
            self.publish_button.setEnabled(False)
            return
        self.title.setText(self.snapshot['name'])
        self.destination.blockSignals(True)
        self.destination.clear()
        if self._destination_id is None and rows:
            self.destination.addItem('Choose a library', None)
        for row in rows:
            self.destination.addItem(row['name'], row['id'])
            if connection and row['id'] == connection['id']:
                self.destination.setCurrentIndex(self.destination.count()-1)
        self.destination.addItem('Join another library...', '__join__')
        self.destination.blockSignals(False)
        self.destination.setVisible(bool(rows))
        self.destination.setEnabled(not busy)
        signed_in = bool(client and client.token)
        self.connect_button.setVisible(not signed_in and (bool(connection) or not rows))
        self.connect_button.setText('Sign in' if connection else 'Join library')
        self.connect_button.setEnabled(not busy)
        self.connect_button.setDefault(not signed_in)
        self.colors.setVisible(signed_in)
        self.color_label.setVisible(signed_in)
        pending = link['pending'] if link else None
        if not connection:
            caption = 'Choose the destination library.' if rows else 'Join a library to share this deck with friends.'
        elif not signed_in:
            caption = 'Sign in to ' + connection['name'] + ' to publish this deck.'
        elif pending:
            name = pending.get('deck', {}).get('name', self.snapshot['name'])
            caption = 'An earlier upload is unfinished. Retry sends "' + name + '"; newer local edits stay on this computer.'
            if pending['kind'] == 'publish':
                self.colors.setText(''.join(pending['color_identity']) or 'C')
        elif link and link['deck_id']:
            caption = f"Publish a new version to {connection['name']}. Last published revision: {link['revision']}."
        else:
            caption = 'Share this deck in ' + connection['name'] + '.'
        self.summary.setText(caption)
        self.publish_button.setText('Retry upload' if pending and pending['kind'] == 'publish' else 'Publish deck')
        self.publish_button.setVisible(signed_in)
        self.publish_button.setDefault(signed_in)
        self.publish_button.setEnabled(signed_in and not busy and (not pending or pending['kind'] == 'publish'))
        self.unpublish_button.setEnabled(signed_in and not busy and bool(link and link['deck_id'])
                                         and (not pending or pending['kind'] == 'unpublish'))
        self.review_button.setEnabled(signed_in and not busy and bool(link and link['deck_id']))
        self.more_button.setVisible(bool(link and link['deck_id']))
        self.more_button.setEnabled(not busy)
        self.colors.setEnabled(not busy and not pending)
        self.close_button.setEnabled(not busy)
        reviewed_here = bool(self.reviewed and connection and self.reviewed['server_id'] == connection['server_id']
                             and self.reviewed['local_id'] == self.snapshot['deck_id'])
        self.accept_button.setEnabled(signed_in and not busy and reviewed_here)
        if reviewed_here:
            self.accept_button.setText(f"Use revision {self.reviewed['publication']['revision']}")

    def show_error(self, message):
        self.error.setText(message)
        self.error.show()

    def reject(self):
        if not self.workspace._job:
            super().reject()

    def publish(self, *, unpublish=False):
        connection, client, link = self.context()
        if not connection or not client or not client.token:
            return
        self.error.hide()
        local_id, snapshot = self.snapshot['deck_id'], self.snapshot
        value = self.colors.text().strip().upper()
        color_identity = [] if value == 'C' else list(value)
        def work():
            community = self.community if self.workspace.category_evidence.consent(connection['server_id']) else None
            return self.workspace.publications.send(client, connection['server_id'], local_id,
                                                    deck=snapshot, color_identity=color_identity, unpublish=unpublish,
                                                    community=community)
        def complete(result):
            self.reviewed = None
            action = 'Unpublished' if unpublish else 'Published'
            self.workspace.states[connection['id']] = f"{action} {self.snapshot['name']}."
            self.workspace.preview_dialog.hide()
            self.accept()
            if callable(getattr(client, 'browse', None)):
                self.workspace._load_after_signin = True
        self.workspace.submit('Unpublishing deck' if unpublish else 'Publishing deck snapshot', work, complete)

    def review(self):
        connection, client, link = self.context()
        if not client or not client.token or not link or not link['deck_id']:
            return
        local_id = self.snapshot['deck_id']
        def complete(publication):
            self.reviewed = {'server_id': connection['server_id'], 'local_id': local_id, 'publication': publication}
            self.workspace.show_review(publication, scope='publication_review', parent=self,
                hint='Review the published deck. Using this revision leaves your local deck unchanged; your next publish replaces the shared version.')
            self.workspace.states[connection['id']] = 'Review the published deck before replacing it.'
        self.workspace.submit('Loading latest publication for review', lambda: client.download(link['deck_id']), complete)

    def accept_review(self):
        connection, client, link = self.context()
        reviewed = self.reviewed
        if (not reviewed or not connection or reviewed['server_id'] != connection['server_id']
                or reviewed['local_id'] != self.snapshot['deck_id']):
            return
        def work():
            self.workspace.publications.accept_reviewed_revision(connection['server_id'], reviewed['local_id'], reviewed['publication'])
        def complete(_):
            self.reviewed = None
            self.workspace.preview_dialog.hide()
            self.workspace.states[connection['id']] = 'Published revision reviewed. Choose Publish deck to share your local version.'
            self.error.hide()
        self.workspace.submit('Saving reviewed publication revision', work, complete)
