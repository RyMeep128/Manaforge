"""Activation contracts and real native launcher exercises, executed by Windows CI."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from mtg_print import application_launcher as launcher
from mtg_print import application_install as install
from test_application_install import OLD, NEW, managed, roots  # noqa: F401


def test_activation_retains_one_fallback_and_never_downgrades(roots):
    managed(OLD)
    managed(NEW)
    launcher.activate(OLD)
    launcher.activate(NEW)
    launcher.activate(OLD)
    assert [item['version'] for item in launcher.read_state()['installations']] == [NEW, OLD]


def test_activation_rejects_corruption_without_switching(roots):
    managed(OLD)
    new = managed(NEW)
    launcher.activate(OLD)
    (new / '_internal/runtime.dll').write_bytes(b'broken')
    with pytest.raises(ValueError, match='verification failed'):
        launcher.activate(NEW)
    assert launcher.read_state()['installations'][0]['version'] == OLD


def test_invalid_primary_uses_backup_and_rejects_traversal(roots):
    managed(OLD)
    launcher.activate(OLD)
    launcher.state_path().write_text('{broken')
    assert launcher.read_state()['installations'][0]['version'] == OLD
    launcher.state_path().write_text(json.dumps({'installations': [{'version': '../escape', 'sha256': 'a' * 64}]}))
    assert launcher.read_state()['installations'][0]['version'] == OLD


def test_second_update_cleans_displaced_fallback_only(roots, monkeypatch):
    from types import SimpleNamespace
    import threading
    from mtg_core import health
    from test_application_install import record
    oldest_version = '0.3.40-alpha.1'
    oldest, old, new = managed(oldest_version), managed(OLD), managed(NEW)
    launcher.activate(oldest_version)
    launcher.activate(OLD)
    install.save_record(record(old, new), 'pending_install')
    monkeypatch.setattr(install.sys, 'executable', str(new / 'Manaforge.exe'))
    monkeypatch.setattr(health, 'run_checks', lambda *a, **k: [SimpleNamespace(status='Healthy')])
    install.finish_startup(NEW, cancel=threading.Event(), report=lambda p: None, initialize=lambda: None)
    assert old.exists() and new.exists()
    assert not oldest.exists()
    assert [entry['version'] for entry in launcher.read_state()['installations']] == [NEW, OLD]


@pytest.fixture
def native(tmp_path):
    if sys.platform != 'win32':
        pytest.skip('Windows launcher integration')
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    source = Path(__file__).resolve().parents[3] / 'installer/Launcher.cs'
    exe = tmp_path / 'Manaforge.exe'
    subprocess.run([str(compiler), '/nologo', '/target:winexe', '/reference:System.Web.Extensions.dll',
                    '/reference:System.Windows.Forms.dll', '/reference:System.Core.dll', '/out:' + str(exe), str(source)], check=True)
    stub = tmp_path / 'Stub.cs'
    stub.write_text('''using System.IO; using System.Web.Script.Serialization;
class Stub { static void Main(string[] args) {
File.WriteAllText(args[0], new JavaScriptSerializer().Serialize(args));
} }''')
    payload = tmp_path / 'stub.exe'
    subprocess.run([str(compiler), '/nologo', '/target:winexe', '/reference:System.Web.Extensions.dll',
                    '/out:' + str(payload), str(stub)], check=True)
    entries = []
    for version in (NEW, OLD):
        directory = tmp_path / 'versions' / version
        (directory / '_internal').mkdir(parents=True)
        (directory / 'Manaforge.exe').write_bytes(payload.read_bytes())
        (directory / 'manaforge-install.json').write_text(json.dumps({'version': version}))
        digest = hashlib.sha256(payload.read_bytes()).hexdigest()
        entries.append({'version': version, 'sha256': digest, 'files': {
            'Manaforge.exe': {'size': payload.stat().st_size, 'modified': 0, 'sha256': digest}}})
    (tmp_path / 'active-install.json').write_text(json.dumps({'installations': entries}))
    return exe


@pytest.mark.parametrize('failure', ['none', 'missing', 'corrupt', 'metadata'])
def test_native_launcher_forwards_arguments_and_uses_fallback(native, failure):
    root = native.parent
    newest = root / 'versions' / NEW / 'Manaforge.exe'
    if failure == 'missing':
        newest.unlink()
    elif failure == 'corrupt':
        newest.write_bytes(b'corrupt executable')
    elif failure == 'metadata':
        (root / 'active-install.backup.json').write_bytes((root / 'active-install.json').read_bytes())
        (root / 'active-install.json').write_text('invalid')
    output = root / 'arguments.json'
    args = [str(output), '', 'with spaces', 'quoted"value', 'C:\\trailing slash\\', 'slash\\"quote', '日本語']
    subprocess.run([str(native), *args], check=True, timeout=30)
    assert json.loads(output.read_text(encoding='utf-8-sig')) == args
