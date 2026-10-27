"""SQLite persistence and authorization, independent of HTTP and Qt."""
from contextlib import contextmanager
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
import uuid

from . import LibraryError
from .payload import colors, shared_deck, text

PASSWORD_ROUNDS = 600000
SESSION_SECONDS = 60 * 60 * 24
OPERATIONS_SQL = '''CREATE TABLE IF NOT EXISTS publication_operations (
    user_id TEXT REFERENCES users(id), operation_id TEXT, signature TEXT NOT NULL,
    result TEXT NOT NULL, PRIMARY KEY(user_id, operation_id))'''


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), PASSWORD_ROUNDS).hex()


def credentials(username, password):
    if not isinstance(username, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{3,64}', username):
        raise LibraryError(400, 'Username must be 3–64 letters, numbers, dots, underscores or hyphens.')
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise LibraryError(400, 'Password must contain 12–256 characters.')
    return username.casefold()


class LibraryStore:
    def __init__(self, directory):
        # Only a trusted operator chooses this directory. No request controls a path.
        self.directory = Path(directory).expanduser().resolve()
        self.path = self.directory / 'library.sqlite3'

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self, name, username, password):
        name = text(name)
        username = credentials(username, password)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Exclusive creation prevents accidental reinitialization or overwriting another DB.
        with self.path.open('xb'):
            pass
        self.path.chmod(0o600)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    salt TEXT NOT NULL, password TEXT NOT NULL, admin INTEGER NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE sessions (token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), expires REAL);
                CREATE TABLE invitations (token TEXT PRIMARY KEY, expires REAL);
                CREATE TABLE throttle (key TEXT PRIMARY KEY, attempts INTEGER, until REAL);
                CREATE TABLE decks (id TEXT PRIMARY KEY, owner TEXT REFERENCES users(id), revision INTEGER,
                    published INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE revisions (deck_id TEXT REFERENCES decks(id), revision INTEGER,
                    payload TEXT NOT NULL, colors TEXT NOT NULL, created REAL,
                    PRIMARY KEY(deck_id, revision));
            ''')
            db.executemany('INSERT INTO meta VALUES (?, ?)',
                           [('schema', '1'), ('name', name), ('server_id', str(uuid.uuid4()))])
            self._user(db, username, password, admin=True)
            db.execute(OPERATIONS_SQL)

    def check_schema(self):
        if not self.path.is_file():
            raise LibraryError(503, 'Library is not initialized. Run the init command first.')
        try:
            with self.db() as db:
                version = db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
                if version is None or version[0] != '1':
                    raise LibraryError(503, 'Unsupported library database version. Upgrade the server.')
                # Additive schema-v1 capability: preserve existing libraries and all history.
                db.execute(OPERATIONS_SQL)
        except sqlite3.Error:
            raise LibraryError(503, 'Library database is unreadable. Check permissions or restore a backup.') from None

    def info(self):
        with self.db() as db:
            return dict(db.execute("SELECT key, value FROM meta WHERE key IN ('name', 'server_id')"))

    @staticmethod
    def _user(db, username, password, *, admin=False):
        salt = secrets.token_hex(16)
        user_id = str(uuid.uuid4())
        db.execute('INSERT INTO users (id, username, salt, password, admin) VALUES (?, ?, ?, ?, ?)',
                   (user_id, username, salt, password_hash(password, salt), int(admin)))
        return user_id

    def throttle(self, key, *, limit=10, seconds=300):
        """Bound attempts before expensive password hashing; persistent across restarts."""
        now = time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM throttle WHERE until < ?', (now,))
            row = db.execute('SELECT attempts FROM throttle WHERE key=?', (key,)).fetchone()
            if row and row[0] >= limit:
                raise LibraryError(429, 'Too many attempts. Try again in five minutes.')
            db.execute('INSERT INTO throttle VALUES (?, 1, ?) ON CONFLICT(key) DO UPDATE SET attempts=attempts+1',
                       (key, now + seconds))

    def login(self, username, password):
        username = credentials(username, password)
        self.throttle('login:' + digest(username))
        with self.db() as db:
            row = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
            salt = row['salt'] if row else '0' * 32
            candidate = password_hash(password, salt)
            if not row or not hmac.compare_digest(candidate, row['password']) or not row['active']:
                raise LibraryError(401, 'Invalid credentials or disabled account.')
            token = secrets.token_urlsafe(32)
            db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES (?, ?, ?)',
                       (digest(token), row['id'], time.time() + SESSION_SECONDS))
            return token

    @staticmethod
    def actor(db, token, *, admin=False):
        if not isinstance(token, str) or not 20 <= len(token) <= 200:
            raise LibraryError(401, 'Sign in to this library.')
        row = db.execute('''SELECT users.* FROM users JOIN sessions ON sessions.user_id=users.id
                            WHERE sessions.token=? AND sessions.expires>? AND users.active=1''',
                         (digest(token), time.time())).fetchone()
        if row is None:
            raise LibraryError(401, 'Session expired or revoked. Sign in again.')
        if admin and not row['admin']:
            raise LibraryError(403, 'Administrator access required.')
        return row

    def invite(self, token):
        with self.db() as db:
            self.actor(db, token, admin=True)
            invitation = secrets.token_urlsafe(32)
            db.execute('DELETE FROM invitations WHERE expires < ?', (time.time(),))
            db.execute('INSERT INTO invitations VALUES (?, ?)', (digest(invitation), time.time() + 86400))
            return invitation

    def register(self, invitation, username, password):
        username = credentials(username, password)
        text(invitation, 200)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('DELETE FROM invitations WHERE token=? AND expires>? RETURNING token',
                             (digest(invitation), time.time())).fetchone()
            if not row:
                raise LibraryError(403, 'Invitation is invalid, expired or already used.')
            try:
                return self._user(db, username, password)
            except sqlite3.IntegrityError:
                raise LibraryError(409, 'Username is unavailable.') from None

    def logout(self, token):
        with self.db() as db:
            self.actor(db, token)
            db.execute('DELETE FROM sessions WHERE token=?', (digest(token),))

    def revoke(self, token, user_id):
        with self.db() as db:
            actor = self.actor(db, token, admin=True)
            if user_id == actor['id']:
                raise LibraryError(409, 'Administrators cannot disable their own account.')
            if not db.execute('UPDATE users SET active=0 WHERE id=?', (user_id,)).rowcount:
                raise LibraryError(404, 'Account not found.')
            db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))

    def users(self, token):
        with self.db() as db:
            self.actor(db, token, admin=True)
            return [dict(row) for row in db.execute('SELECT id, username, admin, active FROM users ORDER BY username')]

    @staticmethod
    def _operation(db, actor, operation_id, payload):
        if operation_id is None:
            return None, None
        try:
            if not isinstance(operation_id, str) or str(uuid.UUID(operation_id)) != operation_id:
                raise ValueError()
        except (ValueError, AttributeError):
            raise LibraryError(400, 'Invalid publication operation identifier.') from None
        signature = digest(json.dumps(payload, sort_keys=True, allow_nan=False))
        row = db.execute('SELECT signature, result FROM publication_operations WHERE user_id=? AND operation_id=?',
                         (actor['id'], operation_id)).fetchone()
        if row and row['signature'] != signature:
            raise LibraryError(409, 'Operation identifier already used for a different publication change.')
        return signature, json.loads(row['result']) if row else None

    @staticmethod
    def _record_operation(db, actor, operation_id, signature, result):
        if operation_id is not None:
            db.execute('INSERT INTO publication_operations VALUES (?, ?, ?, ?)',
                       (actor['id'], operation_id, signature, json.dumps(result)))
        return result

    def publish(self, token, value, color_identity, *, deck_id=None, expected_revision=0, operation_id=None):
        payload = shared_deck(value)
        color_identity = colors(color_identity)
        if type(expected_revision) is not int or expected_revision < 0:
            raise LibraryError(400, 'Expected revision must be a nonnegative integer.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            actor = self.actor(db, token)
            signature_deck = dict(payload)
            # A client's local deck ID has no meaning in a server publication.
            # Omit it so legacy payloads without a deck_id also retry deterministically.
            signature_deck.pop('deck_id', None)
            signature, replay = self._operation(db, actor, operation_id,
                {'action': 'publish', 'deck_id': deck_id, 'revision': expected_revision,
                 'deck': signature_deck, 'colors': color_identity})
            if replay is not None:
                return replay
            if deck_id is None:
                if expected_revision != 0:
                    raise LibraryError(409, 'A new publication must start at revision zero.')
                deck_id = str(uuid.uuid4())
                db.execute('INSERT INTO decks VALUES (?, ?, 0, 1)', (deck_id, actor['id']))
            row = db.execute('SELECT * FROM decks WHERE id=?', (deck_id,)).fetchone()
            if row is None:
                raise LibraryError(404, 'Deck not found.')
            if row['owner'] != actor['id'] and not actor['admin']:
                raise LibraryError(403, 'Only the owner or an administrator may change this deck.')
            if row['revision'] != expected_revision:
                raise LibraryError(409, 'Revision changed. Download the latest revision before publishing.')
            revision = row['revision'] + 1
            # The server identity is authoritative, independent of the author's local ID.
            payload['deck_id'] = deck_id
            db.execute('INSERT INTO revisions VALUES (?, ?, ?, ?, ?)',
                       (deck_id, revision, json.dumps(payload, allow_nan=False), color_identity, time.time()))
            db.execute('UPDATE decks SET revision=?, published=1 WHERE id=?', (revision, deck_id))
            return self._record_operation(db, actor, operation_id, signature,
                                          {'deck_id': deck_id, 'revision': revision})

    def unpublish(self, token, deck_id, expected_revision, *, operation_id=None):
        if type(expected_revision) is not int or expected_revision < 1:
            raise LibraryError(400, 'Expected revision must be a positive integer.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            actor = self.actor(db, token)
            signature, replay = self._operation(db, actor, operation_id,
                {'action': 'unpublish', 'deck_id': deck_id, 'revision': expected_revision})
            if replay is not None:
                return replay
            row = db.execute('SELECT * FROM decks WHERE id=?', (deck_id,)).fetchone()
            if not row:
                raise LibraryError(404, 'Deck not found.')
            if row['owner'] != actor['id'] and not actor['admin']:
                raise LibraryError(403, 'Only the owner or an administrator may unpublish this deck.')
            if type(expected_revision) is not int or row['revision'] != expected_revision:
                raise LibraryError(409, 'Revision changed. Refresh before unpublishing.')
            db.execute('UPDATE decks SET published=0 WHERE id=?', (deck_id,))
            return self._record_operation(db, actor, operation_id, signature,
                                          {'deck_id': deck_id, 'revision': expected_revision})

    def browse(self, token, *, deck_id=None, revision=None, query='', commander='', owner='', tag='', color='', offset=0):
        with self.db() as db:
            self.actor(db, token)
            params = []
            where = ['d.published=1', 'u.active=1']
            if deck_id is not None:
                where.append('d.id=?')
                params.append(deck_id)
            if revision is not None:
                if deck_id is None or type(revision) is not int or revision < 1:
                    raise LibraryError(400, 'Invalid revision.')
                join = 'r.revision=?'
                params.insert(0, revision)
            else:
                join = 'r.revision=d.revision'
            # Values are parameters; only fixed SQL fragments are interpolated.
            rows = db.execute('''SELECT d.id, d.revision AS latest_revision, u.username AS owner,
                                  r.revision, r.payload, r.colors, r.created FROM decks d
                                  JOIN users u ON u.id=d.owner JOIN revisions r ON r.deck_id=d.id AND '''
                              + join + ' WHERE ' + ' AND '.join(where) + ' ORDER BY d.id', params)
            results = []
            matched = 0
            for row in rows:
                deck = json.loads(row['payload'])
                commanders = [entry['name'] for entry in deck['entries']
                              if entry['entry_id'] in deck['commander_entry_ids']]
                if query.casefold() not in (deck['name'] + ' ' + deck['description']).casefold():
                    continue
                if commander.casefold() not in ' '.join(commanders).casefold():
                    continue
                if owner and owner.casefold() != row['owner'].casefold():
                    continue
                if tag and tag.casefold() not in [item.casefold() for item in deck['tags']]:
                    continue
                if color and ('' if color == 'C' else color) != row['colors']:
                    continue
                matched += 1
                if matched <= offset:
                    continue
                results.append({'deck_id': row['id'], 'revision': row['revision'],
                                'latest_revision': row['latest_revision'], 'owner': row['owner'],
                                'color_identity': list(row['colors']), 'created': row['created'], 'deck': deck})
                if len(results) == 50:
                    break
            if deck_id is not None and not results:
                raise LibraryError(404, 'Deck is unavailable, unpublished or inaccessible.')
            return results
