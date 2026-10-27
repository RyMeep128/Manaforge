"""Verified application transfers and conservative, restartable binary cleanup.

No recursive deletion: only unchanged files in an installer-authored inventory
may be removed. Unknown files (including portable user data) always survive.
"""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import time
import uuid

from mtg_core.downloads import atomic_json, file_sha256, get_download_manager
from mtg_core.paths import data_root


def applications_root():
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'Programs/Manaforge/versions'


def version_path(version):
    if not re.fullmatch(r'\d+\.\d+\.\d+-(?:alpha|beta)\.\d+', version):
        raise ValueError('Unsupported installer version')
    return applications_root() / version


def state_path():
    return data_root() / 'application-updates/pending.json'


def read_record():
    try:
        value = json.loads(state_path().read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    if (not isinstance(value, dict) or not isinstance(value.get('update_id'), str)
            or not re.fullmatch(r'[a-f0-9]{32}', value['update_id'])
            or any(not isinstance(value.get(key), str) or not value[key]
                   for key in ('old_version', 'new_version', 'old_install_path', 'new_install_path', 'status'))):
        raise ValueError('Invalid pending application update; no files were removed')
    return value


def save_record(record, status, **values):
    record.update(values, status=status, updated_at=time.time())
    atomic_json(state_path(), record)


def prepare(result, *, cancel, progress, downloader=None):
    """Called only after Download & Install confirmation, on a worker thread."""
    if result.asset_name != 'Manaforge-Setup.exe' or not result.checksum_url:
        raise ValueError('This legacy release has no verified installer. Select a newer installer release; the portable installation is preserved.')
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        raise ValueError('Install updates from a packaged Windows copy of Manaforge.')
    target = version_path(result.latest_version).resolve()
    try:
        record = read_record()
    except ValueError:
        # Confirmation permits a fresh attempt, but keep malformed records for recovery.
        state_path().replace(state_path().with_name('invalid-' + uuid.uuid4().hex + '.json'))
        record = None
    if record and record.get('status') in {'cleanup_pending', 'verified'}:
        raise ValueError('A previous installation is awaiting startup verification. Launch the installed version before starting another update.')
    if not record or record.get('new_version') != result.latest_version:
        from mtg_core.datasets import InstallationState
        state = InstallationState()
        locations = [data_root(), state.path,
                     *(state.storage_root(c) for c in ('cards', 'recommendations', 'artwork'))]
        if state.get('catalog_path'):
            locations.append(Path(state.get('catalog_path')))
        record = dict(update_id=uuid.uuid4().hex, old_version=result.current_version,
                      new_version=result.latest_version,
                      old_install_path=str(Path(sys.executable).resolve().parent),
                      new_install_path=str(target), cleanup_pending=True,
                      data_paths=[str(p.resolve()) for p in locations if p.exists()])
    save_record(record, 'downloading')
    directory = _transfer_directory(record)
    directory.mkdir(parents=True, exist_ok=True)
    downloader = downloader or get_download_manager()
    try:
        checksum = directory / 'SHA256SUMS.txt'
        downloader.download(result.checksum_url, checksum, max_bytes=65536, cancel=cancel)
        matches = re.findall(r'^([a-fA-F0-9]{64})  \*?Manaforge-Setup\.exe\s*$',
                             checksum.read_text(encoding='utf-8'), re.MULTILINE)
        if len(matches) != 1:
            raise ValueError('Release does not publish a unique installer SHA-256 checksum')
        installer = directory / 'Manaforge-Setup.exe'
        downloader.download(result.asset_url, installer, sha256=matches[0],
                            size=result.asset_size, max_bytes=4 * 1024**3,
                            cancel=cancel, progress=progress)
        if cancel.is_set():
            from mtg_core.downloads import DownloadCancelled
            raise DownloadCancelled('Update cancelled; retry to resume.')
        save_record(record, 'ready', installer_sha256=matches[0].lower())
        return record
    except Exception as exc:
        save_record(record, 'interrupted', error=str(exc))
        raise


def launch(record):
    installer = _transfer_directory(record) / 'Manaforge-Setup.exe'
    if _linked(installer):
        raise ValueError('Linked installers are not supported')
    if read_record() != record or file_sha256(installer) != record['installer_sha256']:
        raise ValueError('Installer verification changed. Download the update again.')
    if Path(record['new_install_path']).resolve() != version_path(record['new_version']).resolve():
        raise ValueError('Invalid installation destination')
    save_record(record, 'pending_install')
    try:
        subprocess.Popen([str(installer), '/SILENT', '/NORESTART', '/NOCLOSEAPPLICATIONS',
                          '/DIR=' + record['new_install_path'],
                          '/UPDATEID=' + record['update_id'], '/OLDPID=' + str(os.getpid())],
                         close_fds=True)
    except OSError as exc:
        save_record(record, 'interrupted', error=str(exc))
        raise


def _linked(path):
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _transfer_directory(record):
    parent = state_path().parent
    directory = parent / record['update_id']
    for path in (parent, directory):
        if (path.exists() or path.is_symlink()) and _linked(path):
            raise ValueError('Linked updater directories are not supported')
    return directory


def _inventory(root, version):
    """Require an exact managed root, no junctions, and an installer receipt."""
    expected = version_path(version).absolute()
    if root.absolute() != expected or root.resolve() != expected:
        raise ValueError('Preserved an unmanaged installation')
    for path in (root, *root.parents):
        if _linked(path):
            raise ValueError('Preserved a linked installation')
    receipt = json.loads((root / 'manaforge-install.json').read_text(encoding='utf-8-sig'))
    manifest = json.loads((root / 'manaforge-files.json').read_text(encoding='utf-8'))
    if receipt['version'] != version or manifest['version'] != version:
        raise ValueError('Installation ownership does not match')
    files = manifest['files']
    if not isinstance(files, dict) or not files:
        raise ValueError('Missing installation inventory')
    for name, digest in files.items():
        parts = PurePosixPath(name)
        if (not parts.parts or parts.is_absolute() or '..' in parts.parts or ':' in name
                or '\\' in name or not re.fullmatch('[a-f0-9]{64}', digest)):
            raise ValueError('Invalid installation inventory')
    return receipt, files


def cleanup_old(record, protected=()):
    """Retry locked files later; never traverse or delete unknown content."""
    old = Path(record['old_install_path'])
    if not old.exists():
        return True
    try:
        _, files = _inventory(old, record['old_version'])
    except (OSError, ValueError, KeyError, TypeError):
        record['preserved_old_install'] = str(old)
        return True  # Portable/unmanaged folders require manual review.
    current = Path(record['new_install_path']).resolve()
    if old.resolve() == current:
        raise ValueError('Cannot clean the running installation')
    for protected_path in (data_root(), *protected):
        path = Path(protected_path).resolve()
        if path == old.resolve() or old.resolve() in path.parents:
            record['preserved_old_install'] = str(old)
            return True
    pending = False
    directories = set()
    # Validate the whole tree of each candidate before touching it. Do not use rmtree.
    for name, digest in files.items():
        path = old / name
        ancestors = [p for p in path.parents if p != old and old in p.parents]
        directories.update(ancestors)
        if not path.exists() and not path.is_symlink():
            continue
        try:
            if any(_linked(p) for p in [path, *ancestors]):
                continue
            if file_sha256(path) != digest:
                continue
            path.unlink()
            directories.update(ancestors)
        except OSError:
            pending = True
    if pending:
        return False
    for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
        try:
            if not _linked(directory):
                directory.rmdir()
        except OSError:
            pass
    # Keep ownership metadata if unknown files remain for explicit user review.
    if set(p.name for p in old.iterdir()) <= {'manaforge-files.json', 'manaforge-install.json'}:
        (old / 'manaforge-files.json').unlink(missing_ok=True)
        (old / 'manaforge-install.json').unlink(missing_ok=True)
        old.rmdir()
    else:
        record['preserved_old_install'] = str(old)
    return True


def finish_startup(version, *, cancel, report, initialize):
    """Only invoked after the main window and required components initialize."""
    record = read_record()
    if not record:
        return ''
    if record.get('new_version') != version:
        return 'Previous update has not completed. The working installation is retained; retry is available.'
    root = Path(sys.executable).resolve().parent
    if root != Path(record['new_install_path']).resolve():
        return 'Update verification is waiting for the installed application.'
    receipt, _ = _inventory(root, version)
    if receipt.get('update_id') != record['update_id']:
        raise ValueError('Installer completion receipt does not match; old application retained')
    from mtg_core.datasets import InstallationState
    from mtg_core.health import run_checks
    state = InstallationState()
    for name in record.get('data_paths', []):
        path = Path(name)
        if not path.exists() or not os.access(path, os.R_OK | os.W_OK):
            raise ValueError('Existing data location is inaccessible; previous application retained: ' + name)
    initialize()
    checks = run_checks(state, version=version, cancel=cancel, report=report)
    if any(check.status == 'Error' for check in checks):
        raise ValueError('Startup data checks failed; old application retained. Open Diagnostics & Repair.')
    protected = [state.path, *(state.storage_root(c) for c in ('cards', 'recommendations', 'artwork'))]
    if state.get('catalog_path'):
        protected.append(state.get('catalog_path'))
    save_record(record, 'verified')
    if not cleanup_old(record, protected):
        save_record(record, 'cleanup_pending')
        return 'Update installed. Locked application files will be cleaned on next startup.'
    # Only fixed transfer filenames in this update's private directory are removed.
    directory = _transfer_directory(record)
    try:
        for name in ('Manaforge-Setup.exe', 'SHA256SUMS.txt'):
            for suffix in ('', '.part', '.part.json'):
                (directory / (name + suffix)).unlink(missing_ok=True)
        if directory.exists():
            directory.rmdir()
    except OSError:
        save_record(record, 'cleanup_pending')
        return 'Update installed. Temporary installer cleanup will retry next startup.'
    atomic_json(state_path().parent / 'last-success.json', dict(record, status='successful', cleanup_pending=False))
    state_path().unlink()
    return 'Update installed successfully.' + (' Portable or modified application files were preserved.' if record.get('preserved_old_install') else '')
