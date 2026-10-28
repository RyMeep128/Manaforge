"""Explicit library transport, saved connection metadata and independent copies.

No requests at import. Passwords are never persisted. Each connection has an
isolated session; optional saved sessions are handled by library.sessions.
"""
import ipaddress
import json
import math
from pathlib import Path
import socket
import sqlite3
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import build_opener, HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request
import uuid

import certifi

from mtg_core.decks import Deck, DeckDocument, DeckStore
from . import API_VERSION, LibraryError
from .payload import MAX_BODY, colors, shared_deck, text

MAX_RESPONSE = 8 * 1024 * 1024
USER_AGENT = f'Manaforge-Library/{API_VERSION}'


def server_url(value, *, allow_lan=False):
    """Accept HTTPS origins, or explicitly allowed HTTP on literal private IPs."""
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 33 for c in value):
        raise LibraryError(400, 'Enter a server URL without spaces or control characters.')
    try:
        parsed = urlsplit(value)
        host, port = parsed.hostname, parsed.port
        if (parsed.scheme not in ('https', 'http') or not host or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or parsed.path not in ('', '/') or '\\' in value or '%' in host):
            raise ValueError()
        if parsed.scheme == 'http':
            address = ipaddress.ip_address(host)
            if not allow_lan or not (address.is_private or address.is_loopback) or address.is_unspecified or address.is_multicast:
                raise ValueError()
        if port is not None and not 1 <= port <= 65535:
            raise ValueError()
        host = host.encode('idna').decode('ascii').lower()
        authority = f'[{host}]' if ':' in host else host
        if port is not None:
            authority += f':{port}'
        return urlunsplit((parsed.scheme, authority, '', '', ''))
    except (ValueError, UnicodeError):
        raise LibraryError(400, 'Use an HTTPS server origin, or explicitly allow LAN HTTP with a private IP address.') from None


def identifier(value):
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise LibraryError(400, 'The library returned an invalid identifier.') from None


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LibraryClient:
    def __init__(self, url, *, allow_lan=False, server_id=None, opener=None):
        self.url = server_url(url, allow_lan=allow_lan)
        self.server_id = identifier(server_id) if server_id else None
        self.token = None
        self.account_id = None
        self.expires_at = None
        self.opener = opener or build_opener(
            ProxyHandler({}), _NoRedirects(),
            HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))

    def request(self, method, path, body=None, *, authenticated=True):
        if authenticated and not self.token:
            raise LibraryError(401, 'Sign in to this library first.')
        data = json.dumps(body, allow_nan=False).encode('utf-8') if body is not None else None
        if data is not None and len(data) > MAX_BODY:
            raise LibraryError(413, 'Deck exceeds the 1 MiB upload limit.')
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json',
                   'User-Agent': USER_AGENT}
        if authenticated:
            headers['Authorization'] = 'Bearer ' + self.token
        request = Request(self.url + '/api/v1/' + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=15) as response:
                chunks, size, started = [], 0, time.monotonic()
                while True:
                    chunk = response.read1(65536)
                    size += len(chunk)
                    if size > MAX_RESPONSE or time.monotonic() - started > 30:
                        raise LibraryError(413, 'Library response is too large or too slow. Narrow the search and retry.')
                    if not chunk:
                        break
                    chunks.append(chunk)
                result = json.loads(b''.join(chunks))
        except HTTPError as error:
            status = error.code
            error.close()
            if status == 401:
                self.token = None
                self.account_id = None
                self.expires_at = None
            messages = {401: 'Session expired or credentials were rejected. Sign in again.',
                        403: 'This account does not have permission to perform that action.',
                        404: 'The requested deck or endpoint is unavailable.',
                        409: 'The library changed or the username is unavailable. Refresh and retry.',
                        413: 'The server rejected the request size.',
                        426: 'Client and library API versions are incompatible.',
                        429: 'Library request limit reached. Try again in five minutes.'}
            if status == 403:
                if path == 'info':
                    messages[403] = 'This library address rejected the connection before sign-in. Ask the host to check its access restrictions.'
                elif path == 'login':
                    messages[403] = 'The server rejected the sign-in request. Ask the library host to check its access restrictions.'
                elif path == 'register':
                    messages[403] = 'The invitation is invalid, expired, or already used. Ask the administrator for a new invitation.'
            elif status == 401 and path == 'login':
                messages[401] = 'The username or password was rejected, or the account is disabled.'
            if status == 409 and path.startswith('decks') and method in ('POST', 'PUT', 'DELETE'):
                messages[409] = 'Publication conflict. Review the latest publication before publishing or unpublishing again.'
            raise LibraryError(status, messages.get(status, 'The library could not complete the request. Check server status.')) from None
        except (URLError, OSError, socket.timeout):
            raise LibraryError(503, 'Cannot reach the library. Check its URL, HTTPS certificate and connection, then retry.') from None
        except (ValueError, UnicodeError, RecursionError):
            raise LibraryError(502, 'The library returned an invalid response.') from None
        if not isinstance(result, dict) or type(result.get('api_version')) is not int or result['api_version'] != API_VERSION:
            raise LibraryError(426, 'Client and library API versions are incompatible.')
        return result

    def check(self):
        result = self.request('GET', 'info', authenticated=False)
        server_id = identifier(result.get('server_id'))
        if self.server_id and self.server_id != server_id:
            self.token = None
            self.account_id = None
            self.expires_at = None
            raise LibraryError(409, 'This address now identifies a different library. Remove the old connection and add it explicitly.')
        self.server_id = server_id
        capabilities = result.get('capabilities', [])
        if not isinstance(capabilities, list) or len(capabilities) > 100 or any(not isinstance(item, str) for item in capabilities):
            raise LibraryError(502, 'The library returned invalid capabilities.')
        lifetime = result.get('max_remember_seconds', 30 * 86400)
        if type(lifetime) is not int or not 1 <= lifetime <= 730 * 86400:
            raise LibraryError(502, 'The library returned an invalid remembered session lifetime.')
        return {'server_id': server_id, 'name': text(result.get('name')), 'capabilities': capabilities,
                'max_remember_seconds': lifetime}

    def login(self, username, password, *, invitation='', remember=False):
        info = self.check()  # Pin identity before sending credentials on each reconnect.
        if invitation:
            self.request('POST', 'register', {'invitation': invitation, 'username': username,
                                             'password': password}, authenticated=False)
        body = {'username': username, 'password': password, 'remember': remember}
        if remember:
            body['session_lifetime'] = info['max_remember_seconds']
        result = self.request('POST', 'login', body, authenticated=False)
        token = result.get('token')
        if (not isinstance(token, str) or not 20 <= len(token) <= 200 or not token.isascii()
                or any(not (c.isalnum() or c in '-_') for c in token)):
            raise LibraryError(502, 'The library returned an invalid session.')
        self.token = token
        self.account_id = identifier(result['user_id']) if result.get('user_id') else None
        expires = result.get('expires_in', 86400)
        if type(expires) is not int or not 1 <= expires <= 730 * 86400:
            self.token = None
            raise LibraryError(502, 'The library returned an invalid session expiry.')
        self.expires_at = time.time() + expires
        return info

    def resume(self, saved):
        info = self.check()  # Never send a stored token before checking the pinned origin.
        if saved['server_id'] != self.server_id or saved['url'] != self.url:
            raise LibraryError(409, 'Saved sign-in belongs to a different library address.')
        token, expires = saved.get('token'), saved.get('expires_at')
        if (not isinstance(token, str) or not 20 <= len(token) <= 200 or not token.isascii()
                or any(not (c.isalnum() or c in '-_') for c in token)
                or type(expires) not in (int, float) or not math.isfinite(expires) or expires <= time.time()):
            raise LibraryError(401, 'Saved sign-in expired or is invalid. Sign in again.')
        self.token, self.account_id = saved['token'], identifier(saved['account_id'])
        self.expires_at = saved['expires_at']
        try:
            if 'persistent_sessions' in info['capabilities']:
                result = self.request('GET', 'session')
                expires = result.get('expires_at')
                if (identifier(result.get('user_id')) != self.account_id or type(expires) not in (int, float)
                        or not math.isfinite(expires) or expires <= time.time()):
                    raise LibraryError(401, 'Saved sign-in is no longer valid. Sign in again.')
                self.expires_at = min(self.expires_at, expires)
            else:
                self.browse()  # Older v1 servers validate their existing 24-hour token.
        except Exception:
            self.token, self.account_id, self.expires_at = None, None, None
            raise
        return info

    def disconnect(self):
        try:
            if self.token:
                self.request('POST', 'logout')
        finally:
            self.token = None
            self.account_id = None
            self.expires_at = None

    @staticmethod
    def publication(value):
        if not isinstance(value, dict):
            raise LibraryError(502, 'Invalid publication.')
        deck_id = identifier(value.get('deck_id'))
        revision = value.get('revision')
        if type(revision) is not int or revision < 1:
            raise LibraryError(502, 'Invalid publication revision.')
        deck = shared_deck(value.get('deck'))
        deck['deck_id'] = deck_id
        return {'deck_id': deck_id, 'revision': revision, 'deck': deck,
                'owner': text(value.get('owner')), 'color_identity': list(colors(value.get('color_identity', [])))}

    def browse(self, filters=None, *, offset=0):
        result = self.request('GET', 'decks?' + urlencode({**(filters or {}), 'offset': offset}))
        rows = result.get('decks')
        if not isinstance(rows, list) or len(rows) > 50:
            raise LibraryError(502, 'Invalid library search results.')
        return [self.publication(row) for row in rows]

    def download(self, deck_id):
        result = self.request('GET', 'decks/' + identifier(deck_id))
        publication = self.publication(result.get('publication'))
        if publication['deck_id'] != deck_id:
            raise LibraryError(502, 'The library returned the wrong deck.')
        return publication

    def publish_operation(self, operation):
        """Send one durable journal operation; retrying the same operation is safe."""
        info = self.check()
        if 'publication_operations' not in info['capabilities']:
            raise LibraryError(426, 'Upgrade this library server before publishing from Manaforge. Safe publication retries are required.')
        kind = operation['kind']
        if kind not in ('publish', 'unpublish'):
            raise LibraryError(400, 'Invalid publication operation.')
        deck_id = operation.get('deck_id')
        expected = operation['expected_revision']
        if type(expected) is not int or expected < 0:
            raise LibraryError(400, 'Invalid publication revision.')
        body = {'operation_id': identifier(operation['operation_id']), 'expected_revision': expected}
        if deck_id:
            path = 'decks/' + identifier(deck_id)
            method = 'DELETE' if kind == 'unpublish' else 'PUT'
        else:
            if kind == 'unpublish' or expected != 0:
                raise LibraryError(400, 'Invalid publication target.')
            path, method = 'decks', 'POST'
        if kind == 'publish':
            body.update(deck=shared_deck(operation['deck']), color_identity=list(colors(operation['color_identity'])))
        result = self.request(method, path, body)
        remote_id, revision = identifier(result.get('deck_id')), result.get('revision')
        wanted_revision = expected + 1 if kind == 'publish' else expected
        if type(revision) is not int or revision != wanted_revision or (deck_id and remote_id != deck_id):
            raise LibraryError(502, 'Publication response did not match the request. Retry the pending operation to recover its result.')
        return {'deck_id': remote_id, 'revision': revision}


class LibraryConnections:
    """Saved public connection metadata only. No passwords or session tokens."""
    def __init__(self, root):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / 'library-connections.sqlite3'
        with self.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS connections (
                id TEXT PRIMARY KEY, url TEXT UNIQUE, name TEXT, server_id TEXT, allow_lan INTEGER)''')

    def db(self):
        # Callers use closing as well as the transaction context to release handles on Windows.
        from contextlib import closing, contextmanager
        @contextmanager
        def connection():
            with closing(sqlite3.connect(self.path, timeout=10)) as db:
                db.row_factory = sqlite3.Row
                with db:
                    yield db
        return connection()

    def list(self):
        with self.db() as db:
            return [dict(row) for row in db.execute('SELECT * FROM connections ORDER BY name, id')]

    def add(self, client, info):
        record = {'id': str(uuid.uuid4()), 'url': client.url, 'name': text(info['name']),
                  'server_id': identifier(info['server_id']), 'allow_lan': int(client.url.startswith('http:'))}
        with self.db() as db:
            try:
                db.execute('INSERT INTO connections VALUES (:id, :url, :name, :server_id, :allow_lan)', record)
            except sqlite3.IntegrityError:
                raise LibraryError(409, 'This library address is already saved. Select it and sign in.') from None
        return record

    def remove(self, connection_id):
        with self.db() as db:
            db.execute('DELETE FROM connections WHERE id=?', (connection_id,))


def copy_publication(publication, *, server_id, server_address, deck_root, store=None, library_name=None):
    """Save an independent deck atomically. No server-controlled filenames/settings."""
    publication = LibraryClient.publication(publication)
    document = DeckDocument(deck=Deck.from_dict(publication['deck']))
    document.deck.deck_id = str(uuid.uuid4())
    if library_name:
        document.deck.name += ' [' + str(library_name).strip() + ']'
    document.deck.extras['manual_name'] = True
    document.deck.extras['library_source'] = {
        'server_id': identifier(server_id), 'server_url': server_address,
        'deck_id': publication['deck_id'], 'revision': publication['revision'],
        'owner': publication['owner'], 'kind': 'independent_copy', 'library_name': library_name}
    destination = Path(deck_root) / f'{document.deck.deck_id}.manaforge.json'
    return (store or DeckStore()).save(destination, document)
