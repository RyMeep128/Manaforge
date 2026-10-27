"""Shared activation metadata for the permanent Windows launcher.

Only verified, installer-owned payloads can enter this record. The native launcher
reads it; neither directory ordering nor download state determines what is active.
"""
import json
import re

from mtg_core.downloads import atomic_json, file_sha256
from . import application_install as install

APP_ID = 'Manaforge.Desktop'


def state_path():
    return install.applications_root().parent / 'active-install.json'


def read_state():
    for path in (state_path(), state_path().with_suffix('.backup.json')):
        try:
            value = json.loads(path.read_text(encoding='utf-8-sig'))
            entries = value['installations']
            if not isinstance(entries, list) or not 1 <= len(entries) <= 2:
                continue
            for entry in entries:
                install.version_path(entry['version'])
                if not isinstance(entry['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', entry['sha256']):
                    raise ValueError('Invalid launcher digest')
                if not isinstance(entry.get('files'), dict) or 'Manaforge.exe' not in entry['files']:
                    raise ValueError('Missing launcher payload metadata')
            return value
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return {'installations': []}


def activate(version):
    root = install.version_path(version)
    _, files = install._inventory(root, version)
    stamps = {}
    # Activation happens once per installation, never on the normal launch path.
    for name, digest in files.items():
        path = root / name
        if any(install._linked(p) for p in (path, *[p for p in path.parents if root in p.parents])):
            raise ValueError('Linked application payload')
        before = path.stat()
        actual = file_sha256(path)
        after = path.stat()
        if actual != digest or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('Application payload verification failed: ' + name)
        stamps[name] = {'size': before.st_size, 'modified': before.st_mtime_ns // 100 + 116444736000000000,
                        'sha256': digest}
    entry = {'version': version, 'sha256': files['Manaforge.exe'], 'files': stamps}
    previous = read_state()['installations']
    from .update_service import _version_parts
    entries = sorted([entry] + [item for item in previous if item['version'] != version],
                     key=lambda item: _version_parts(item['version']), reverse=True)[:2]
    value = {'installations': entries}
    # Both records describe only verified versions; a torn primary remains recoverable.
    atomic_json(state_path(), value)
    atomic_json(state_path().with_suffix('.backup.json'), value)


def retained_paths():
    return [install.version_path(item['version']) for item in read_state()['installations']]


def configure_windows_identity():
    import ctypes
    import sys
    if sys.platform == 'win32':
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)


def configure_window(window):
    """Tell Windows that a pin created from this window relaunches the stable EXE."""
    import ctypes as ct
    import sys
    import uuid
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        return
    launcher = install.applications_root().parent / 'Manaforge.exe'
    if not launcher.is_file():
        return

    class GUID(ct.Structure):
        _fields_ = [('data', ct.c_ubyte * 16)]

    class PropertyKey(ct.Structure):
        _fields_ = [('fmtid', GUID), ('pid', ct.c_ulong)]

    class Value(ct.Union):
        _fields_ = [('text', ct.c_wchar_p), ('padding', ct.c_ubyte * (16 if ct.sizeof(ct.c_void_p) == 8 else 8))]

    class Variant(ct.Structure):
        _fields_ = [('vt', ct.c_ushort), ('reserved', ct.c_ushort * 3), ('value', Value)]

    def guid(value):
        return GUID((ct.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le))

    iid = guid('886d8eeb-8cf2-4446-8d02-cdba1dbdcf99')  # IPropertyStore
    store = ct.c_void_p()
    get_store = ct.windll.shell32.SHGetPropertyStoreForWindow
    get_store.argtypes = [ct.c_void_p, ct.POINTER(GUID), ct.POINTER(ct.c_void_p)]
    get_store.restype = ct.c_long
    if get_store(int(window.winId()), ct.byref(iid), ct.byref(store)) < 0:
        return
    table = ct.cast(store, ct.POINTER(ct.POINTER(ct.c_void_p))).contents
    release = ct.WINFUNCTYPE(ct.c_ulong, ct.c_void_p)(table[2])
    set_value = ct.WINFUNCTYPE(ct.c_long, ct.c_void_p, ct.POINTER(PropertyKey), ct.POINTER(Variant))(table[6])
    commit = ct.WINFUNCTYPE(ct.c_long, ct.c_void_p)(table[7])
    try:
        fmtid = guid('9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3')
        for pid, text in ((2, f'"{launcher}"'), (3, f'{launcher},0'), (4, 'Manaforge'), (5, APP_ID)):
            key = PropertyKey(fmtid, pid)
            value = Variant()
            value.vt = 31  # VT_LPWSTR; memory belongs to Python for this call.
            value.value.text = text
            if set_value(store, ct.byref(key), ct.byref(value)) < 0:
                raise OSError('Could not configure Windows launcher identity')
        if commit(store) < 0:
            raise OSError('Could not commit Windows launcher identity')
    finally:
        release(store)
