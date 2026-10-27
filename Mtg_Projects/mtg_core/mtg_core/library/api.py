"""Versioned JSON WSGI interface. No cookies, CORS, filesystem or desktop access."""
import json
import sqlite3
from urllib.parse import parse_qs

from . import API_VERSION, LibraryError
from .payload import MAX_BODY, text
from .store import REMEMBERED_SESSION_SECONDS, SESSION_SECONDS, digest


class LibraryAPI:
    def __init__(self, store):
        store.check_schema()
        self.store = store

    def __call__(self, environ, start_response):
        try:
            result = self.route(environ)
            status = 200
        except LibraryError as error:
            status, result = error.status, {'error': str(error)}
        except (sqlite3.Error, OSError):
            status, result = 503, {'error': 'Library storage is unavailable. Contact the administrator.'}
        except Exception:
            # Never reflect tracebacks, passwords, tokens or payloads to clients/logs.
            status, result = 500, {'error': 'Library server could not complete the request.'}
        reasons = {200: 'OK', 400: 'Bad Request', 401: 'Unauthorized', 403: 'Forbidden',
                   404: 'Not Found', 409: 'Conflict', 413: 'Content Too Large',
                   415: 'Unsupported Media Type', 426: 'Upgrade Required',
                   429: 'Too Many Requests', 500: 'Internal Server Error', 503: 'Service Unavailable'}
        body = json.dumps({'api_version': API_VERSION, **result}, allow_nan=False).encode('utf-8')
        headers = [('Content-Type', 'application/json; charset=utf-8'), ('Content-Length', str(len(body))),
                   ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff')]
        if status == 429:
            headers.append(('Retry-After', '300'))
        start_response(f'{status} {reasons[status]}', headers)
        return [body]

    @staticmethod
    def body(env):
        if env.get('CONTENT_TYPE', '').split(';')[0].strip().lower() != 'application/json':
            raise LibraryError(415, 'Use application/json.')
        try:
            size = int(env.get('CONTENT_LENGTH', ''))
        except ValueError:
            raise LibraryError(400, 'A valid Content-Length is required.') from None
        if not 0 < size <= MAX_BODY:
            raise LibraryError(413, 'Request exceeds the 1 MiB limit or is empty.')
        raw = env['wsgi.input'].read(size)
        if len(raw) != size:
            raise LibraryError(400, 'Request was interrupted. Retry the operation.')
        try:
            def reject_constant(value):
                raise ValueError('Non-finite JSON number')
            value = json.loads(raw, parse_constant=reject_constant)
        except (ValueError, UnicodeError, RecursionError):
            raise LibraryError(400, 'Invalid JSON.') from None
        if not isinstance(value, dict):
            raise LibraryError(400, 'Expected a JSON object.')
        return value

    def route(self, env):
        path = env.get('PATH_INFO', '')
        method = env.get('REQUEST_METHOD', '')
        if method == 'GET' and path == '/api/v1/info':
            return {**self.store.info(), 'registration': 'invitation', 'max_request_bytes': MAX_BODY,
                    'capabilities': ['publication_operations', 'persistent_sessions']}
        if not path.startswith('/api/v1/'):
            raise LibraryError(426, 'Unsupported API version. This server supports /api/v1/.')
        if len(path) > 256 or '..' in path or '\\' in path:
            raise LibraryError(400, 'Invalid resource path.')
        if method == 'POST' and path in ('/api/v1/login', '/api/v1/register'):
            # REMOTE_ADDR is set by the HTTP server; forwarded headers are not trusted.
            self.store.throttle('auth-ip:' + env.get('REMOTE_ADDR', 'unknown'), limit=30)
            body = self.body(env)
            if path.endswith('/login'):
                remember = body.get('remember', False)
                token = self.store.login(body.get('username'), body.get('password'), remember=remember)
                with self.store.db() as db:
                    user_id = self.store.actor(db, token)['id']
                return {'token': token, 'user_id': user_id,
                        'expires_in': REMEMBERED_SESSION_SECONDS if remember else SESSION_SECONDS}
            user_id = self.store.register(body.get('invitation'), body.get('username'), body.get('password'))
            return {'user_id': user_id}
        auth = env.get('HTTP_AUTHORIZATION', '')
        token = auth[7:] if auth.startswith('Bearer ') else ''
        # Authenticate every remaining route before request parsing or resource lookup.
        with self.store.db() as db:
            self.store.actor(db, token)
        self.store.throttle('request:' + digest(token), limit=300, seconds=300)
        if method == 'GET' and path == '/api/v1/session':
            return self.store.session(token)
        if method == 'POST' and path == '/api/v1/logout':
            self.store.logout(token)
            return {}
        if method == 'POST' and path == '/api/v1/invitations':
            return {'invitation': self.store.invite(token), 'expires_in': 86400}
        if method == 'GET' and path == '/api/v1/users':
            return {'users': self.store.users(token)}
        if method == 'POST' and path.startswith('/api/v1/users/') and path.endswith('/revoke'):
            user_id = path.removeprefix('/api/v1/users/').removesuffix('/revoke')
            self.store.revoke(token, user_id)
            return {}
        prefix = '/api/v1/decks'
        if path == prefix and method == 'GET':
            query = env.get('QUERY_STRING', '')
            if len(query) > 2048:
                raise LibraryError(400, 'Search query is too long.')
            try:
                params = parse_qs(query, max_num_fields=10, strict_parsing=True) if query else {}
                if any(len(values) != 1 for values in params.values()):
                    raise ValueError()
                allowed = {'query', 'commander', 'owner', 'tag', 'color', 'offset'}
                if not params.keys() <= allowed:
                    raise ValueError()
                filters = {key: text(values[0], empty=True) for key, values in params.items()}
                filters['offset'] = int(filters.get('offset', 0))
                if not 0 <= filters['offset'] <= 100000:
                    raise ValueError()
                if 'color' in filters and filters['color'] not in ('', 'C'):
                    from .payload import colors
                    filters['color'] = colors(list(filters['color']))
            except ValueError:
                raise LibraryError(400, 'Invalid search filters or offset.') from None
            return {'decks': self.store.browse(token, **filters)}
        if path == prefix and method == 'POST':
            body = self.body(env)
            return self.store.publish(token, body.get('deck'), body.get('color_identity', []),
                                      operation_id=body.get('operation_id'))
        if path.startswith(prefix + '/'):
            parts = path[len(prefix) + 1:].split('/')
            deck_id = parts[0]
            if len(parts) == 1 and method == 'GET':
                return {'publication': self.store.browse(token, deck_id=deck_id)[0]}
            if len(parts) == 3 and parts[1] == 'revisions' and method == 'GET':
                try:
                    revision = int(parts[2])
                except ValueError:
                    raise LibraryError(400, 'Invalid revision.') from None
                return {'publication': self.store.browse(token, deck_id=deck_id, revision=revision)[0]}
            if len(parts) == 1 and method == 'PUT':
                body = self.body(env)
                return self.store.publish(token, body.get('deck'), body.get('color_identity', []),
                                          deck_id=deck_id, expected_revision=body.get('expected_revision'),
                                          operation_id=body.get('operation_id'))
            if len(parts) == 1 and method == 'DELETE':
                body = self.body(env)
                return self.store.unpublish(token, deck_id, body.get('expected_revision'),
                                            operation_id=body.get('operation_id'))
        raise LibraryError(404, 'Endpoint not found.')

