"""Transactional read-only subscriptions using the native DeckDocument format."""
from copy import deepcopy
import hashlib
import json
import time
import uuid

from mtg_core.decks import Deck, DeckDocument, ENTRY_PRINT_FIELDS
from mtg_core.downloads import DownloadCancelled
from . import LibraryError
from .client import LibraryClient, identifier, server_url
from .payload import shared_deck, text


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def public_fingerprint(document, deck_id):
    deck = shared_deck(document.deck.to_dict())
    deck['deck_id'] = deck_id
    return fingerprint(deck)


def same_card(left, right):
    for key in ('oracle_id', 'card_id'):
        if getattr(left, key) and getattr(right, key):
            return getattr(left, key) == getattr(right, key)
    return left.name.casefold() == right.name.casefold()


def merge_local_state(previous, publication):
    """Remote public fields change; existing local print fields/extras never upload."""
    document = deepcopy(previous)
    incoming = Deck.from_dict(publication['deck'])
    incoming.deck_id = previous.deck.deck_id
    incoming.extras = deepcopy(previous.deck.extras)
    by_id = {entry.entry_id: entry for entry in previous.deck.entries}
    consumed = set()
    for entry in incoming.entries:
        old = by_id.get(entry.entry_id)
        if old is None or not same_card(old, entry):
            # Handle a reimport that regenerated entry IDs, only when unambiguous.
            matches = [item for item in previous.deck.entries if item.section == entry.section and same_card(item, entry)]
            incoming_matches = [item for item in incoming.entries if item.section == entry.section and same_card(item, entry)]
            old = matches[0] if len(matches) == len(incoming_matches) == 1 else None
        if old is None or old.entry_id in consumed:
            continue
        consumed.add(old.entry_id)
        entry.extras = deepcopy(old.extras)
        for key in ('owned', 'do_not_print', 'image_asset_id', 'art_override', *ENTRY_PRINT_FIELDS):
            setattr(entry, key, deepcopy(getattr(old, key)))
    document.deck = incoming
    return document


class FollowedDecks:
    def __init__(self, connections):
        self.connections = connections
        with connections.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS followed_decks (
                server_id TEXT, deck_id TEXT, server_url TEXT NOT NULL, server_name TEXT NOT NULL,
                local_id TEXT UNIQUE NOT NULL, revision INTEGER NOT NULL, document TEXT NOT NULL,
                owner TEXT NOT NULL, colors TEXT NOT NULL, baseline TEXT NOT NULL, pending TEXT,
                active INTEGER NOT NULL DEFAULT 1, state TEXT NOT NULL, message TEXT NOT NULL,
                checked REAL, PRIMARY KEY(server_id, deck_id))''')
            db.execute('''CREATE TABLE IF NOT EXISTS followed_history (
                server_id TEXT, deck_id TEXT, revision INTEGER, document TEXT NOT NULL,
                PRIMARY KEY(server_id, deck_id, revision))''')
            db.execute('CREATE TABLE IF NOT EXISTS follow_preferences (server_id TEXT PRIMARY KEY, auto_check INTEGER NOT NULL)')

    @staticmethod
    def _decode(row):
        result = dict(row)
        result['document'] = DeckDocument.from_dict(json.loads(result['document']))
        result['pending'] = json.loads(result['pending']) if result['pending'] else None
        return result

    def get(self, server_id, deck_id):
        with self.connections.db() as db:
            row = db.execute('SELECT * FROM followed_decks WHERE server_id=? AND deck_id=?',
                             (identifier(server_id), identifier(deck_id))).fetchone()
            if row is None:
                raise LibraryError(404, 'Followed deck is not cached.')
            return self._decode(row)

    def list(self, server_id=None, *, active_only=False):
        clauses, args = [], []
        if server_id:
            clauses.append('server_id=?')
            args.append(identifier(server_id))
        if active_only:
            clauses.append('active=1')
        with self.connections.db() as db:
            rows = db.execute('SELECT * FROM followed_decks' + (' WHERE ' + ' AND '.join(clauses) if clauses else '')
                              + ' ORDER BY server_name, local_id', args)
            return [self._decode(row) for row in rows]

    @staticmethod
    def publication(record):
        return LibraryClient.publication({'deck_id': record['deck_id'], 'revision': record['revision'],
            'owner': record['owner'], 'color_identity': list(record['colors']),
            'deck': record['document'].deck.to_dict()})

    def add(self, publication, *, server_id, address, name):
        publication = LibraryClient.publication(publication)
        server_id, deck_id = identifier(server_id), publication['deck_id']
        address = server_url(address, allow_lan=address.startswith('http:'))
        name = text(name)
        document = DeckDocument(deck=Deck.from_dict(publication['deck']))
        document.deck.deck_id = str(uuid.uuid4())
        with self.connections.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM followed_decks WHERE server_id=? AND deck_id=?', (server_id, deck_id)).fetchone()
            if row:
                # Re-following cannot replace the previously accepted cache or its local state.
                db.execute('UPDATE followed_decks SET active=1, server_url=?, server_name=? WHERE server_id=? AND deck_id=?',
                           (address, name, server_id, deck_id))
                self._stage(db, server_id, deck_id, publication)
            else:
                db.execute('''INSERT INTO followed_decks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 1, 'current', ?, ?)''',
                    (server_id, deck_id, address, name, document.deck.deck_id, publication['revision'],
                     json.dumps(document.to_dict()), publication['owner'], ''.join(publication['color_identity']),
                     public_fingerprint(document, deck_id), 'Cached for read-only offline viewing.', time.time()))
        return self.get(server_id, deck_id)

    @staticmethod
    def _stage(db, server_id, deck_id, publication):
        publication = LibraryClient.publication(publication)
        if publication['deck_id'] != deck_id:
            raise LibraryError(502, 'The library returned the wrong followed deck.')
        row = db.execute('SELECT * FROM followed_decks WHERE server_id=? AND deck_id=?', (server_id, deck_id)).fetchone()
        if row is None or not row['active']:
            return
        pending = json.loads(row['pending']) if row['pending'] else None
        revision = publication['revision']
        if revision < row['revision'] or (pending and revision < pending['revision']):
            state, message = 'source_changed', 'Server revision moved backward. Existing cache and staged update were kept.'
        elif revision == row['revision'] and fingerprint(publication['deck']) != row['baseline']:
            state, message = 'source_changed', 'Server changed deck content without a new revision. Existing cache was kept.'
        elif pending and revision == pending['revision'] and fingerprint(publication) != fingerprint(pending):
            state, message = 'source_changed', 'Server changed the staged revision. Previously downloaded update was kept.'
        elif revision > row['revision']:
            state, message = 'update_available', f'Revision {revision} is available. Review and accept it explicitly.'
            db.execute('UPDATE followed_decks SET pending=? WHERE server_id=? AND deck_id=?',
                       (json.dumps(publication), server_id, deck_id))
        else:
            state, message = 'current', 'No newer published revision.'
        db.execute('UPDATE followed_decks SET state=?, message=?, checked=? WHERE server_id=? AND deck_id=?',
                   (state, message, time.time(), server_id, deck_id))

    def _unavailable(self, server_id, deck_id, error):
        message = str(error)
        state = 'unavailable' if error.status in (401, 403, 404) else 'offline'
        with self.connections.db() as db:
            db.execute('UPDATE followed_decks SET state=?, message=?, checked=? WHERE server_id=? AND deck_id=?',
                       (state, message + ' Cached deck and staged updates remain available.', time.time(), server_id, deck_id))

    def check(self, client, *, cancel=None, report=None):
        server_id = identifier(client.server_id)
        rows = self.list(server_id, active_only=True)
        if not rows:
            return self.list(server_id)
        if cancel is not None and cancel.is_set():
            raise DownloadCancelled()
        failure = None
        try:
            client.check()  # Verify pinned server identity before using its deck IDs/session.
        except LibraryError as error:
            failure = error
        for index, record in enumerate(rows):
            if cancel is not None and cancel.is_set():
                raise DownloadCancelled()
            if report:
                report({'operation': 'Checking followed decks', 'current': index, 'total': len(rows)})
            if failure:
                self._unavailable(server_id, record['deck_id'], failure)
                continue
            try:
                publication = client.download(record['deck_id'])
                if cancel is not None and cancel.is_set():
                    raise DownloadCancelled()
                with self.connections.db() as db:
                    db.execute('BEGIN IMMEDIATE')
                    self._stage(db, server_id, record['deck_id'], publication)
            except LibraryError as error:
                self._unavailable(server_id, record['deck_id'], error)
                if error.status not in (403, 404):
                    failure = error  # Avoid repeating timeouts or expired authentication per deck.
        if report:
            report({'operation': 'Checking followed decks', 'current': len(rows), 'total': len(rows)})
        return self.list(server_id)

    def review(self, server_id, deck_id):
        record = self.get(server_id, deck_id)
        if record['pending'] is None:
            raise LibraryError(409, 'No staged update. Check for updates first.')
        return {'publication': record['pending'], 'fingerprint': fingerprint(record['pending'])}

    def accept(self, server_id, deck_id, reviewed_fingerprint):
        server_id, deck_id = identifier(server_id), identifier(deck_id)
        with self.connections.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM followed_decks WHERE server_id=? AND deck_id=?', (server_id, deck_id)).fetchone()
            if row is None or not row['active'] or not row['pending']:
                raise LibraryError(409, 'No active staged update to accept.')
            record = self._decode(row)
            publication = LibraryClient.publication(record['pending'])
            if fingerprint(publication) != reviewed_fingerprint or publication['revision'] <= record['revision']:
                raise LibraryError(409, 'Staged update changed. Review it again before accepting.')
            previous = record['document']
            if previous.deck.deck_id != record['local_id'] or public_fingerprint(previous, deck_id) != record['baseline']:
                raise LibraryError(409, 'Cached deck has local content changes. Cache kept; make an independent copy before repairing it.')
            document = merge_local_state(previous, publication)
            db.execute('INSERT OR REPLACE INTO followed_history VALUES (?, ?, ?, ?)',
                       (server_id, deck_id, record['revision'], row['document']))
            db.execute('''DELETE FROM followed_history WHERE server_id=? AND deck_id=? AND revision NOT IN
                (SELECT revision FROM followed_history WHERE server_id=? AND deck_id=? ORDER BY revision DESC LIMIT 5)''',
                (server_id, deck_id, server_id, deck_id))
            db.execute('''UPDATE followed_decks SET revision=?, document=?, owner=?, colors=?, baseline=?, pending=NULL,
                state='current', message='Update accepted. Local print metadata preserved.' WHERE server_id=? AND deck_id=?''',
                (publication['revision'], json.dumps(document.to_dict()), publication['owner'],
                 ''.join(publication['color_identity']), public_fingerprint(document, deck_id), server_id, deck_id))
        return self.get(server_id, deck_id)

    def stop(self, server_id, deck_id):
        with self.connections.db() as db:
            db.execute("UPDATE followed_decks SET active=0, pending=NULL, state='stopped', message='Following stopped. Offline copy retained.' WHERE server_id=? AND deck_id=?",
                       (identifier(server_id), identifier(deck_id)))

    def auto_check(self, server_id, enabled=None):
        server_id = identifier(server_id)
        with self.connections.db() as db:
            if enabled is not None:
                db.execute('INSERT INTO follow_preferences VALUES (?, ?) ON CONFLICT(server_id) DO UPDATE SET auto_check=excluded.auto_check',
                           (server_id, int(bool(enabled))))
            row = db.execute('SELECT auto_check FROM follow_preferences WHERE server_id=?', (server_id,)).fetchone()
            return bool(row and row[0])
