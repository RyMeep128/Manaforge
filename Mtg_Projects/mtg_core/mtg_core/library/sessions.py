"""Opt-in Windows-user-protected library sessions. Passwords are never stored."""
import ctypes
import json
import math
import os
from pathlib import Path
import tempfile
import time

from . import LibraryError
from .client import identifier


def _crypt(data, *, decrypt=False):
    if os.name != 'nt':
        raise LibraryError(503, 'Secure saved sign-in is available on Windows only.')
    from ctypes import wintypes as W
    class Blob(ctypes.Structure):
        _fields_ = [('size', W.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    source = ctypes.create_string_buffer(data)
    entropy = ctypes.create_string_buffer(b'Manaforge-library-session-v1')
    incoming = Blob(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
    extra = Blob(len(entropy.value), ctypes.cast(entropy, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p if decrypt else W.LPCWSTR,
                         ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, W.DWORD, ctypes.POINTER(Blob)]
    function.restype = W.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not function(ctypes.byref(incoming), None if decrypt else 'Manaforge library session',
                    ctypes.byref(extra), None, None, 1, ctypes.byref(output)):
        raise LibraryError(503, 'Windows could not unlock saved sign-in. Sign in again on this Windows account.')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel32.LocalFree(ctypes.cast(output.data, ctypes.c_void_p))


class SavedSessions:
    """One encrypted, atomically replaced file per connection, bound to its origin/UUID."""
    def __init__(self, root):
        self.root = Path(root) / 'library-sessions'
        self.available = os.name == 'nt'

    def _path(self, connection_id):
        return self.root / (identifier(connection_id) + '.dpapi')

    def has(self, connection_id):
        return self.available and self._path(connection_id).is_file()

    def forget(self, connection_id):
        try:
            self._path(connection_id).unlink(missing_ok=True)
        except OSError:
            raise LibraryError(503, 'Could not remove saved sign-in. Check local storage permissions.') from None

    def save(self, connection, client, username):
        if not self.available:
            raise LibraryError(503, 'Secure saved sign-in is unavailable on this system.')
        expires = getattr(client, 'expires_at', None)
        token = client.token
        if (not isinstance(token, str) or not 20 <= len(token) <= 200 or not token.isascii()
                or any(not (c.isalnum() or c in '-_') for c in token)
                or type(expires) not in (int, float) or not math.isfinite(expires) or expires <= time.time()):
            raise LibraryError(503, 'The server did not provide a session that can be saved. Sign in again.')
        payload = {'version': 1, 'connection_id': identifier(connection['id']),
                   'server_id': identifier(connection['server_id']), 'url': connection['url'],
                   'account_id': identifier(client.account_id), 'token': token,
                   'username': str(username)[:64], 'expires_at': expires}
        if client.server_id != payload['server_id'] or client.url != payload['url']:
            raise LibraryError(409, 'The saved connection does not match the signed-in library.')
        encrypted = _crypt(json.dumps(payload, allow_nan=False).encode('utf-8'))
        temporary = None
        try:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.NamedTemporaryFile(dir=self.root, prefix='.session-', delete=False) as handle:
                temporary = handle.name
                handle.write(encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path(connection['id']))
        except OSError:
            raise LibraryError(503, 'Could not securely save sign-in. Check local storage permissions.') from None
        finally:
            if temporary and Path(temporary).exists():
                Path(temporary).unlink(missing_ok=True)

    def load(self, connection):
        if not self.has(connection['id']):
            return None
        try:
            path = self._path(connection['id'])
            if path.stat().st_size > 65536:
                raise ValueError()
            value = json.loads(_crypt(path.read_bytes(), decrypt=True))
            if (not isinstance(value, dict) or value.get('version') != 1
                    or value.get('connection_id') != identifier(connection['id'])
                    or value.get('server_id') != identifier(connection['server_id'])
                    or value.get('url') != connection['url']):
                raise ValueError()
            identifier(value.get('account_id'))
            token, expires = value.get('token'), value.get('expires_at')
            if (not isinstance(token, str) or not 20 <= len(token) <= 200 or not token.isascii()
                    or any(not (c.isalnum() or c in '-_') for c in token)
                    or type(expires) not in (int, float) or not math.isfinite(expires)):
                raise ValueError()
            if expires <= time.time():
                self.forget(connection['id'])
                return None
            return value
        except (OSError, ValueError, TypeError, KeyError):
            raise LibraryError(503, 'Saved sign-in could not be unlocked for this library. Sign in again.') from None
