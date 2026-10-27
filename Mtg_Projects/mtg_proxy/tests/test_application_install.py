"""Updater failure/ownership contracts; real installers are exercised only in CI."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import threading

import pytest

from mtg_print import application_install as install
from mtg_print.update_service import parse_latest_release


OLD = '0.3.41-alpha.1'
NEW = '0.3.42-alpha.1'


@pytest.fixture
def roots(tmp_path, monkeypatch):
    monkeypatch.setattr(install, 'applications_root', lambda: tmp_path / 'versions')
    monkeypatch.setattr(install, 'data_root', lambda: tmp_path / 'data')
    monkeypatch.setenv('PRINT_PROXY_PREP_DATA_DIR', str(tmp_path / 'data'))
    return tmp_path


def managed(version):
    root = install.version_path(version)
    (root / '_internal').mkdir(parents=True)
    payload = {'Manaforge.exe': b'app', '_internal/runtime.dll': b'runtime'}
    for name, content in payload.items():
        (root / name).write_bytes(content)
    (root / 'manaforge-files.json').write_text(json.dumps(dict(version=version,
        files={name: hashlib.sha256(content).hexdigest() for name, content in payload.items()})))
    (root / 'manaforge-install.json').write_text(json.dumps(dict(version=version, update_id='a' * 32)))
    return root


def record(old, new):
    return dict(update_id='a' * 32, old_version=OLD, new_version=NEW,
                old_install_path=str(old), new_install_path=str(new), cleanup_pending=True)


def test_installer_preferred_to_portable_and_checksum_selected():
    result = parse_latest_release(dict(tag_name='v' + NEW, assets=[
        dict(name='Manaforge-Windows.zip', browser_download_url='https://example.test/app.zip'),
        dict(name='Manaforge-Setup.exe', browser_download_url='https://example.test/setup.exe', size=123),
        dict(name='SHA256SUMS.txt', browser_download_url='https://example.test/sums')]), OLD)
    assert result.asset_name == 'Manaforge-Setup.exe'
    assert result.checksum_url == 'https://example.test/sums'
    assert result.asset_size == 123


def test_cleanup_removes_only_owned_application_files(roots):
    old, new = managed(OLD), managed(NEW)
    assert install.cleanup_old(record(old, new))
    assert not old.exists()
    assert (new / 'Manaforge.exe').exists()


def test_cleanup_preserves_modified_files_and_user_content(roots):
    old, new = managed(OLD), managed(NEW)
    (old / 'deck.json').write_text('user deck')
    (old / 'Manaforge.exe').write_bytes(b'modified')
    assert install.cleanup_old(record(old, new))
    assert (old / 'deck.json').read_text() == 'user deck'
    assert (old / 'Manaforge.exe').read_bytes() == b'modified'
    assert not (old / '_internal/runtime.dll').exists()


def test_cleanup_preserves_portable_and_configured_data(roots):
    portable = roots / 'portable'
    portable.mkdir()
    (portable / 'deck.json').write_text('deck')
    assert install.cleanup_old(record(portable, install.version_path(NEW)))
    assert (portable / 'deck.json').exists()
    old = managed(OLD)
    assert install.cleanup_old(record(old, install.version_path(NEW)), [old / 'custom-art'])
    assert (old / 'Manaforge.exe').exists()


def test_cleanup_rejects_manifest_traversal(roots):
    old = managed(OLD)
    victim = roots / 'personal.txt'
    victim.write_text('keep')
    (old / 'manaforge-files.json').write_text(json.dumps(dict(version=OLD,
        files={'../../personal.txt': hashlib.sha256(b'keep').hexdigest()})))
    assert install.cleanup_old(record(old, install.version_path(NEW)))
    assert victim.read_text() == 'keep'
    assert (old / 'Manaforge.exe').exists()


def test_locked_cleanup_retries_without_losing_inventory(roots, monkeypatch):
    old = managed(OLD)
    unlink = Path.unlink
    def locked(path, *args, **kwargs):
        if path.name == 'runtime.dll':
            raise PermissionError('locked')
        return unlink(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'unlink', locked)
        assert not install.cleanup_old(record(old, install.version_path(NEW)))
    assert (old / 'manaforge-files.json').exists()
    assert install.cleanup_old(record(old, install.version_path(NEW)))
    assert not old.exists()


def test_missing_or_wrong_receipt_never_cleans_old_install(roots, monkeypatch):
    old, new = managed(OLD), managed(NEW)
    install.save_record(record(old, new), 'pending_install')
    monkeypatch.setattr(install.sys, 'executable', str(new / 'Manaforge.exe'))
    (new / 'manaforge-install.json').write_text(json.dumps(dict(version=NEW, update_id='b' * 32)))
    with pytest.raises(ValueError, match='receipt'):
        install.finish_startup(NEW, cancel=threading.Event(), report=lambda p: None, initialize=lambda: None)
    assert (old / 'Manaforge.exe').exists()
    assert install.read_record()['status'] == 'pending_install'


def test_startup_failure_preserves_old_and_pending_record(roots, monkeypatch):
    old, new = managed(OLD), managed(NEW)
    install.save_record(record(old, new), 'pending_install')
    monkeypatch.setattr(install.sys, 'executable', str(new / 'Manaforge.exe'))
    def fail():
        raise RuntimeError('required service failed')
    with pytest.raises(RuntimeError, match='required service'):
        install.finish_startup(NEW, cancel=threading.Event(), report=lambda p: None, initialize=fail)
    assert old.exists()
    assert install.read_record()['status'] == 'pending_install'


def test_successful_startup_finalizes_and_clears_record(roots, monkeypatch):
    from mtg_core import health
    old, new = managed(OLD), managed(NEW)
    install.save_record(record(old, new), 'pending_install')
    monkeypatch.setattr(install.sys, 'executable', str(new / 'Manaforge.exe'))
    monkeypatch.setattr(health, 'run_checks', lambda *a, **k: [SimpleNamespace(status='Healthy')])
    message = install.finish_startup(NEW, cancel=threading.Event(), report=lambda p: None, initialize=lambda: None)
    assert 'successfully' in message
    assert not old.exists()
    assert install.read_record() is None
    assert json.loads((install.state_path().parent / 'last-success.json').read_text())['status'] == 'successful'


def test_legacy_release_cannot_be_executed(roots):
    with pytest.raises(ValueError, match='legacy release'):
        install.prepare(SimpleNamespace(asset_name='Manaforge-Windows.zip'),
                        cancel=threading.Event(), progress=lambda p: None)
    assert install.read_record() is None


def test_launch_rechecks_installer_before_process_creation(roots, monkeypatch):
    value = record(install.version_path(OLD), install.version_path(NEW))
    install.save_record(value, 'ready', installer_sha256=hashlib.sha256(b'expected').hexdigest())
    directory = install.state_path().parent / value['update_id']
    directory.mkdir()
    (directory / 'Manaforge-Setup.exe').write_bytes(b'incomplete')
    monkeypatch.setattr(install.subprocess, 'Popen', lambda *a, **k: pytest.fail('Must not execute'))
    with pytest.raises(ValueError, match='verification changed'):
        install.launch(value)


def test_data_health_failure_prevents_cleanup(roots, monkeypatch):
    from mtg_core import health
    old, new = managed(OLD), managed(NEW)
    install.save_record(record(old, new), 'pending_install')
    monkeypatch.setattr(install.sys, 'executable', str(new / 'Manaforge.exe'))
    monkeypatch.setattr(health, 'run_checks', lambda *a, **k: [SimpleNamespace(status='Error')])
    with pytest.raises(ValueError, match='data checks failed'):
        install.finish_startup(NEW, cancel=threading.Event(), report=lambda p: None, initialize=lambda: None)
    assert (old / 'Manaforge.exe').exists()


def test_linked_install_is_preserved(roots, monkeypatch):
    old = managed(OLD)
    original = install._linked
    monkeypatch.setattr(install, '_linked', lambda p: p == old or original(p))
    assert install.cleanup_old(record(old, install.version_path(NEW)))
    assert (old / 'Manaforge.exe').exists()


@pytest.mark.parametrize('failure', ['checksum', 'cancel', 'network'])
def test_interrupted_transfer_never_launches_and_can_retry(roots, monkeypatch, failure):
    from mtg_core.downloads import DownloadCancelled, IntegrityError
    monkeypatch.setattr(install.sys, 'platform', 'win32')
    monkeypatch.setattr(install.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(install.sys, 'executable', str(roots / 'portable/Manaforge.exe'))
    value = SimpleNamespace(asset_name='Manaforge-Setup.exe', checksum_url='https://example.test/sums',
        asset_url='https://example.test/setup', asset_size=3, current_version=OLD, latest_version=NEW)
    class Downloader:
        def download(self, url, destination, **kwargs):
            if destination.name == 'SHA256SUMS.txt':
                destination.write_text(hashlib.sha256(b'app').hexdigest() + '  Manaforge-Setup.exe\n')
            else:
                if failure == 'checksum':
                    raise IntegrityError('checksum failed')
                if failure == 'cancel':
                    raise DownloadCancelled('canceled')
                raise ConnectionError('network failed')
    monkeypatch.setattr(install.subprocess, 'Popen', lambda *a, **k: pytest.fail('Must not execute'))
    with pytest.raises((IntegrityError, DownloadCancelled, ConnectionError)):
        install.prepare(value, cancel=threading.Event(), progress=lambda p: None, downloader=Downloader())
    pending = install.read_record()
    assert pending['status'] == 'interrupted'
    previous_id = pending['update_id']
    class Successful:
        def download(self, url, destination, **kwargs):
            if destination.name == 'SHA256SUMS.txt':
                destination.write_text(hashlib.sha256(b'app').hexdigest() + '  Manaforge-Setup.exe\n')
            else:
                assert kwargs['sha256'] == hashlib.sha256(b'app').hexdigest()
                destination.write_bytes(b'app')
    ready = install.prepare(value, cancel=threading.Event(), progress=lambda p: None, downloader=Successful())
    assert ready['update_id'] == previous_id
    assert install.read_record()['status'] == 'ready'


def test_installer_failure_keeps_retryable_record(roots, monkeypatch):
    value = record(install.version_path(OLD), install.version_path(NEW))
    install.save_record(value, 'ready', installer_sha256=hashlib.sha256(b'app').hexdigest())
    directory = install.state_path().parent / value['update_id']
    directory.mkdir()
    (directory / 'Manaforge-Setup.exe').write_bytes(b'app')
    def fail(*args, **kwargs):
        raise OSError('installer could not launch')
    monkeypatch.setattr(install.subprocess, 'Popen', fail)
    with pytest.raises(OSError):
        install.launch(value)
    assert install.read_record()['status'] == 'interrupted'
