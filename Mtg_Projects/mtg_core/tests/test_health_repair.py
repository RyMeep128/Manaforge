"""Regression coverage for offline checks, privacy and safe repair routing."""
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
import sqlite3
import threading

import pytest

from mtg_core import health, repair
from mtg_core.datasets import InstallationState
from mtg_core.db import CardDatabase
from mtg_core.downloads import DownloadCancelled
from mtg_core.installation import InstallPlan


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(health, 'core_data_root', lambda: tmp_path)
    monkeypatch.setattr(repair, 'core_data_root', lambda: tmp_path)
    monkeypatch.setattr(repair, 'data_root', lambda: tmp_path)
    state = InstallationState(tmp_path / 'installation.sqlite3')
    state.set('catalog_path', str(tmp_path / 'cards.sqlite3'))
    for category in ('cards', 'recommendations', 'artwork'):
        state.set(category + '_root', str(tmp_path / category))
    return state


def check(state, **kwargs):
    return health.run_checks(state, version='0.3.1-alpha.1', cancel=threading.Event(), report=lambda p: None, **kwargs)


def test_fresh_checks_are_offline_and_do_not_create_catalog(state):
    def forbidden(url):
        pytest.fail('Local checks must not access the network')
    results = check(state, fetch=forbidden)
    assert any(r.name == 'Card database' and r.status == 'Error' for r in results)
    assert any(r.name == 'Connectivity and update sources' and r.status == 'Not Checked' for r in results)
    assert not Path(state.get('catalog_path')).exists()
    assert health.overall(results) == 'Error'


def test_online_checks_are_explicit_and_service_failure_is_independent(state):
    calls = []
    def fetch(url):
        calls.append(url)
        if 'scryfall' in url:
            raise OSError('No connection')
        return {}
    results = check(state, online=True, fetch=fetch)
    assert len(calls) == 2
    assert any(r.name == 'Scryfall / internet' and r.status == 'Warning' for r in results)
    assert any(r.name == 'Recommendation update source' and r.status == 'Healthy' for r in results)


def test_corrupt_catalog_is_reported_without_modification_and_other_checks_continue(state):
    path = Path(state.get('catalog_path'))
    path.write_bytes(b'broken sqlite database')
    results = check(state)
    assert path.read_bytes() == b'broken sqlite database'
    assert any(r.name == 'Catalog' and r.status == 'Error' for r in results)
    assert any(r.name == 'Interrupted downloads' for r in results)


def test_newer_schema_is_preserved(state):
    path = Path(state.get('catalog_path'))
    with closing(sqlite3.connect(path)) as db:
        db.execute('PRAGMA user_version=999')
    result = health.catalog_check(state, threading.Event())
    assert result.status == 'Error'
    assert 'newer Manaforge' in result.detail
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 999


def test_partial_download_and_cancelled_checks(state):
    root = state.storage_root('cards')
    root.mkdir()
    (root / 'cards.bulk.part').write_bytes(b'partial')
    assert health.downloads_check(state, threading.Event()).status == 'Warning'
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(DownloadCancelled):
        health.run_checks(state, version='0.3.1-alpha.1', cancel=cancel, report=lambda p: None)
    assert (root / 'cards.bulk.part').read_bytes() == b'partial'


def test_reports_and_history_redact_secrets_paths_and_urls(state):
    text = "token=supersecret password: hidden Bearer bearer-secret https://user:pass@example.com/data?key=secret C:\\Users\\Friend\\Decks\\private.json 'api_key': 'json-secret' friend@example.com"
    report = health.report_text([health.Check('Failure', 'Error', text)], version='0.3.1-alpha.1', roots=[state.path.parent])
    for secret in ('supersecret', 'hidden', 'bearer-secret', 'json-secret', 'user:pass', 'Friend', 'friend@example.com'):
        assert secret not in report
    repair.record_operation('Download', 'failed', text)
    assert 'supersecret' not in str(repair.recent_operations())


def test_defaults_backup_preserves_decks_installation_and_preferences(state):
    root = state.path.parent
    config = root / 'config.ini'
    config.write_text('[DEFAULT]\nOnline.Mode=False\n')
    deck = root / 'deck.json'
    deck.write_text('user deck')
    state.set('artwork_mode', 'full_offline')
    outcome = repair.RepairService(SimpleNamespace(state=state)).run('defaults', cancel=threading.Event(), report=lambda p: None)
    assert 'restart' in outcome
    assert not config.exists()
    assert next(root.glob('config.ini.backup-*')).read_text() == '[DEFAULT]\nOnline.Mode=False\n'
    assert deck.read_text() == 'user deck'
    assert state.get('artwork_mode') == 'full_offline'


def test_healthy_current_card_repair_does_not_download(state):
    db = CardDatabase(state.get('catalog_path'))
    db.upsert_card_payload(dict(id='print', oracle_id='oracle', name='Fixture'))
    plan = InstallPlan({'default_cards': {'updated_at': 'v1'}}, {}, 0, 0, 0)
    engine = SimpleNamespace(state=state, plan=lambda **kw: plan, _version=lambda kind: 'v1')
    # No run or downloader method: a valid repair must finish before invoking either.
    result = repair.RepairService(engine).run('cards', cancel=threading.Event(), report=lambda p: None)
    assert 'No card download' in result


def test_failed_repairs_have_retryable_history_without_changing_setup(state):
    state.set('setup_complete', False)
    def fail(**kwargs):
        raise OSError('Network unavailable')
    service = repair.RepairService(SimpleNamespace(state=state, run=fail))
    for _ in range(2):
        with pytest.raises(OSError):
            service.run('resume', cancel=threading.Event(), report=lambda p: None)
    assert not state.get('setup_complete')
    assert len([e for e in repair.recent_operations() if e['outcome'] == 'failed']) == 2


def test_artwork_verification_and_repair_preserve_custom_and_reuse_valid_bytes(state):
    from mtg_core.services import CardService
    service = CardService(db_path=state.get('catalog_path'), image_root=str(state.path.parent / 'artwork'))
    service.database.upsert_card_payload(dict(id='remote', oracle_id='o1', name='Remote'))
    service.database.upsert_card_payload(dict(id='custom', oracle_id='o2', name='Custom'))
    remote_asset = service.store_image_bytes(b'remote image', source='scryfall')
    service.set_print_image_asset('remote', remote_asset, source='scryfall')
    custom_asset = service.store_image_bytes(b'custom image', source='custom')
    service.set_print_image_asset('custom', custom_asset, source='custom')
    custom_record = service.database.get_image_record('custom')
    asset = service.database.get_image_asset(remote_asset)
    canonical = service.database._resolve_image_asset_storage_path(asset.storage_path)
    canonical.write_bytes(b'corrupted canonical')
    engine = SimpleNamespace(state=state, service=service)
    repairs = repair.RepairService(engine)
    result = repairs.run('artwork_verify', cancel=threading.Event(), report=lambda p: None)
    assert result[0].status == 'Warning'
    # The intact manifest copy repairs the canonical asset without a downloader.
    repairs.run('artwork', cancel=threading.Event(), report=lambda p: None)
    assert canonical.read_bytes() == b'remote image'
    assert service.database.get_image_record('custom') == custom_record
    assert Path(custom_record.path).read_bytes() == b'custom image'
    result = repairs.run('artwork_verify', cancel=threading.Event(), report=lambda p: None)
    assert result[0].status == 'Healthy'
