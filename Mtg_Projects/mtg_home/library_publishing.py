"""Explicit publication controls over the existing Browse Online session/queue."""
import sqlite3

from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.library import LibraryError
from mtg_core.library.payload import shared_deck


class PublishingPanel(W.QGroupBox):
    def __init__(self, workspace):
        super().__init__('Publish a local deck snapshot', workspace)
        self.workspace = workspace
        self.snapshot = None
        self.reviewed = None
        form = W.QVBoxLayout(self)
        self.summary = W.QLabel()
        self.summary.setTextFormat(C.Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        form.addWidget(self.summary)
        colors_row = W.QHBoxLayout()
        colors_row.addWidget(W.QLabel('Color identity (WUBRG letters, or C)'))
        self.colors = W.QLineEdit()
        self.colors.setMaxLength(5)
        colors_row.addWidget(self.colors)
        form.addLayout(colors_row)
        actions = W.QHBoxLayout()
        self.publish_button = W.QPushButton('Publish snapshot')
        self.publish_button.clicked.connect(self.publish)
        self.unpublish_button = W.QPushButton('Unpublish')
        self.unpublish_button.clicked.connect(lambda: self.publish(unpublish=True))
        self.review_button = W.QPushButton('Review latest publication')
        self.review_button.clicked.connect(self.review)
        self.close_button = W.QPushButton('Close publication panel')
        self.close_button.clicked.connect(self.hide)
        for button in (self.publish_button, self.unpublish_button, self.review_button, self.close_button):
            actions.addWidget(button)
        form.addLayout(actions)
        self.accept_button = W.QPushButton('Use reviewed revision as the next publish base')
        self.accept_button.clicked.connect(self.accept_review)
        self.accept_button.hide()
        form.addWidget(self.accept_button)
        self.hide()

    def prepare(self, deck, color_identity):
        if self.workspace._job or self.workspace.jobs.busy:
            self.workspace.connection_status.setText('Wait for the current background operation, then choose Publish to Library again.')
            return False
        try:
            snapshot = shared_deck(deck)
        except LibraryError as error:
            self.workspace.connection_status.setText('Cannot prepare publication: ' + str(error))
            return False
        self.snapshot = snapshot
        self.colors.setText(color_identity)
        self.reviewed = None
        self.show()
        self.refresh()
        return True

    def context(self):
        connection = self.workspace.connection()
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
        except (sqlite3.Error, OSError):
            self.summary.setText('Publication tracking is unavailable. Check local storage and reopen Browse Online.')
            for button in (self.publish_button, self.unpublish_button, self.review_button, self.accept_button):
                button.setEnabled(False)
            return
        connected = bool(client and client.token) and not busy
        pending = link['pending'] if link else None
        caption = 'Snapshot: ' + self.snapshot['name'] + '. Choose a library above, then publish explicitly.'
        if link and link['deck_id']:
            caption += f"\nLast acknowledged publication: {link['deck_id']} · revision {link['revision']}"
            caption += ' · published.' if link['published'] else ' · unpublished.'
        if pending:
            if pending['kind'] == 'publish':
                self.colors.setText(''.join(pending['color_identity']) or 'C')
            name = pending.get('deck', {}).get('name', self.snapshot['name'])
            caption += '\nA previous operation is pending. Retry sends its original snapshot (' + name + '), including its original color identity.'
            caption += ' Local edits made afterward are not included. Review the latest publication to resolve a revision conflict.'
        caption += '\nPublishing shares card notes, descriptions and tags. Personal print statuses and private artwork paths are excluded.'
        self.summary.setText(caption)
        self.publish_button.setText('Retry pending publish' if pending and pending['kind'] == 'publish' else 'Publish snapshot')
        self.unpublish_button.setText('Retry pending unpublish' if pending and pending['kind'] == 'unpublish' else 'Unpublish')
        self.publish_button.setEnabled(connected and (not pending or pending['kind'] == 'publish'))
        self.unpublish_button.setEnabled(connected and bool(link and link['deck_id'])
                                         and (not pending or pending['kind'] == 'unpublish'))
        self.review_button.setEnabled(connected and bool(link and link['deck_id']))
        self.colors.setEnabled(not busy and not pending)
        self.close_button.setEnabled(not busy)
        reviewed_here = bool(self.reviewed and connection and self.reviewed['server_id'] == connection['server_id']
                             and self.reviewed['local_id'] == self.snapshot['deck_id'])
        self.accept_button.setVisible(reviewed_here)
        self.accept_button.setEnabled(connected and reviewed_here)
        if reviewed_here:
            self.accept_button.setText(f"Use reviewed revision {self.reviewed['publication']['revision']} as the next publish base")

    def publish(self, *, unpublish=False):
        connection, client, link = self.context()
        if not connection or not client or not client.token:
            return
        local_id, snapshot = self.snapshot['deck_id'], self.snapshot
        value = self.colors.text().strip().upper()
        color_identity = [] if value == 'C' else list(value)
        def work():
            return self.workspace.publications.send(client, connection['server_id'], local_id,
                                                    deck=snapshot, color_identity=color_identity, unpublish=unpublish)
        def complete(result):
            self.reviewed = None
            action = 'Unpublished' if unpublish else 'Published'
            self.workspace.states[connection['id']] = f"{action} revision {result['revision']}. Local editing remains independent. Search / Refresh to update results."
        self.workspace.submit('Unpublishing deck' if unpublish else 'Publishing deck snapshot', work, complete)

    def review(self):
        connection, client, link = self.context()
        if not client or not client.token or not link or not link['deck_id']:
            return
        local_id = self.snapshot['deck_id']
        def complete(publication):
            self.reviewed = {'server_id': connection['server_id'], 'local_id': local_id, 'publication': publication}
            self.workspace.details.setPlainText(
                'LATEST REMOTE PUBLICATION — REVIEW BEFORE CHANGING THE PUBLISH BASE\n'
                'Accepting the reviewed revision keeps your local deck unchanged. Your next explicit publish '
                'will replace this remote deck with the selected local snapshot.\n\n'
                + self.workspace.publication_text(publication))
            self.workspace.states[connection['id']] = 'Review the remote deck in the preview, then explicitly accept its revision if you intend to replace it.'
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
            self.workspace.states[connection['id']] = 'Reviewed revision accepted. Local deck unchanged. Choose Publish snapshot or Unpublish explicitly to continue.'
        self.workspace.submit('Saving reviewed publication revision', work, complete)
