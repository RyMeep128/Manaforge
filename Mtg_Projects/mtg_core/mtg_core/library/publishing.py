"""Durable per-library publication links and retry journal, independent of Qt.

Journal only the allowlisted public snapshot. Never retain local document extras,
printing state, credentials, or the user's subsequent edits in a pending request.
"""
import json
import uuid

from . import LibraryError
from .client import identifier
from .payload import colors, shared_deck, text


class PublicationJournal:
    def __init__(self, connections):
        self.connections = connections
        with self.connections.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS publication_links (
                server_id TEXT, local_id TEXT, deck_id TEXT, revision INTEGER NOT NULL,
                published INTEGER NOT NULL, pending TEXT,
                PRIMARY KEY(server_id, local_id))''')

    def get(self, server_id, local_id):
        with self.connections.db() as db:
            row = db.execute('SELECT * FROM publication_links WHERE server_id=? AND local_id=?',
                             (identifier(server_id), text(local_id))).fetchone()
            if row is None:
                return None
            result = dict(row)
            result['pending'] = json.loads(result['pending']) if result['pending'] else None
            return result

    def begin(self, server_id, local_id, account_id, *, deck=None, color_identity=None, unpublish=False, community=None):
        server_id, local_id, account_id = identifier(server_id), text(local_id), identifier(account_id)
        kind = 'unpublish' if unpublish else 'publish'
        with self.connections.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM publication_links WHERE server_id=? AND local_id=?',
                             (server_id, local_id)).fetchone()
            if row and row['pending']:
                operation = json.loads(row['pending'])
                if operation['account_id'] != account_id:
                    raise LibraryError(409, 'This pending operation belongs to another account. Sign in to the account that started it.')
                if operation['kind'] != kind:
                    raise LibraryError(409, 'Finish or review the pending publication operation first.')
                return operation
            if unpublish and (row is None or not row['deck_id']):
                raise LibraryError(409, 'This local deck has not been published to this library.')
            operation = {'operation_id': str(uuid.uuid4()), 'kind': kind,
                         'account_id': account_id,
                         'deck_id': row['deck_id'] if row else None,
                         'expected_revision': row['revision'] if row else 0}
            if not unpublish:
                operation.update(deck=shared_deck(deck), color_identity=list(colors(color_identity)))
                if community is not None:
                    from .category_evidence import clean_snapshot
                    operation['community'] = clean_snapshot(community)
            if row is None:
                db.execute('INSERT INTO publication_links VALUES (?, ?, NULL, 0, 0, ?)',
                           (server_id, local_id, json.dumps(operation)))
            else:
                db.execute('UPDATE publication_links SET pending=? WHERE server_id=? AND local_id=?',
                           (json.dumps(operation), server_id, local_id))
            return operation

    def send(self, client, server_id, local_id, **snapshot):
        if client.server_id != identifier(server_id):
            raise LibraryError(409, 'Select the original library connection before publishing.')
        if not getattr(client, 'account_id', None):
            raise LibraryError(426, 'Reconnect to an updated library server before publishing. Account identity is required for safe retries.')
        operation = self.begin(server_id, local_id, client.account_id, **snapshot)
        result = client.publish_operation(operation)
        from .category_evidence import CategoryEvidence, CAPABILITY
        cache = CategoryEvidence(self.connections.path.parent / 'library-category-evidence.sqlite3')
        if (operation['kind'] == 'publish' and operation.get('community') is not None
                and cache.consent(server_id) and CAPABILITY in client.check()['capabilities']):
            # Retain pending state on failure. Publication replay and replacement
            # evidence batches are idempotent, including after a lost response.
            client.request('PUT', 'decks/' + result['deck_id'] + '/category-evidence',
                           {'revision': result['revision'], 'evidence': operation['community']})
        with self.connections.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT pending FROM publication_links WHERE server_id=? AND local_id=?',
                             (server_id, local_id)).fetchone()
            if row is None or not row['pending'] or json.loads(row['pending'])['operation_id'] != operation['operation_id']:
                raise LibraryError(409, 'Local publication tracking changed. Reopen the publication panel.')
            db.execute('''UPDATE publication_links SET deck_id=?, revision=?, published=?, pending=NULL
                          WHERE server_id=? AND local_id=?''',
                       (result['deck_id'], result['revision'], int(operation['kind'] == 'publish'), server_id, local_id))
        return result

    def accept_reviewed_revision(self, server_id, local_id, publication):
        """Explicit conflict resolution changes the next publish base, never the local deck."""
        from .client import LibraryClient
        publication = LibraryClient.publication(publication)
        with self.connections.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT deck_id FROM publication_links WHERE server_id=? AND local_id=?',
                             (identifier(server_id), text(local_id))).fetchone()
            if row is None or row['deck_id'] != publication['deck_id']:
                raise LibraryError(409, 'Reviewed deck does not match the saved publication.')
            db.execute('''UPDATE publication_links SET revision=?, published=1, pending=NULL
                          WHERE server_id=? AND local_id=?''',
                       (publication['revision'], server_id, local_id))


def suggested_colors(deck):
    found = set()
    for entry in deck.entries:
        facts = entry.extras.get('facts', {})
        if isinstance(facts, dict):
            identity = facts.get('color_identity')
            if isinstance(identity, (list, tuple)):
                found.update(item for item in identity if item in ('W', 'U', 'B', 'R', 'G'))
    return ''.join(item for item in 'WUBRG' if item in found) or 'C'
