"""Read-only, extensible installation checks. No card service is constructed here."""
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import configparser
import json
import os
import platform
import re
import shutil
import sqlite3
import sys
from tempfile import TemporaryFile
import time

from .bulk_install import cancelled
from .db.schema import SCHEMA_VERSION
from .paths import core_data_root
from .recommendation_distribution import APPROVED_SOURCES, DEFAULT_MANIFEST_URL, validate_bundle


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=3)


def catalog_check(state, cancel):
    path = Path(state.get('catalog_path', str(core_data_root() / 'card_data.sqlite3')))
    if not path.is_file():
        return Check('Card database', 'Error', 'Card data is missing. Resume installation to download it.')
    with closing(readonly(path)) as db:
        db.set_progress_handler(lambda: int(cancel.is_set()), 10000)
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version > SCHEMA_VERSION:
            return Check('Card database', 'Error', f'Schema {version} needs a newer Manaforge. Keep this database and update the app.')
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            return Check('Card database', 'Error', 'Database is damaged. Keep a backup; automatic replacement is unsafe because preferences may be stored here.')
        count = db.execute('SELECT count(*) FROM prints').fetchone()[0]
        sync = db.execute("SELECT payload_json FROM sync_state WHERE source='installed-default_cards'").fetchone()
        expected = json.loads(sync[0] or '{}').get('cards', 0) if sync else 0
        if count < expected:
            return Check('Card database', 'Warning', f'{count:,} printings; expected at least {expected:,}. Repair missing card data to restore records.')
    return Check('Card database', 'Healthy' if count and version == SCHEMA_VERSION else 'Warning',
                 f'Schema {version}/{SCHEMA_VERSION}; {count:,} printings. ' +
                 ('Ready.' if count else 'Resume installation to populate card data.'))


def storage_check(state, cancel):
    details = []
    low = False
    roots = {state.path.parent, *(state.storage_root(c) for c in ('cards', 'recommendations', 'artwork'))}
    catalog = Path(state.get('catalog_path', str(core_data_root() / 'card_data.sqlite3')))
    roots.add(catalog.parent)
    for root in roots:
        cancelled(cancel)
        existing = root
        while not existing.exists() and existing != existing.parent:
            existing = existing.parent
        with TemporaryFile(dir=existing):
            pass
        usage = shutil.disk_usage(existing)
        low |= usage.free < 1024**3
        managed_bytes = 0
        if root == catalog.parent and catalog.is_file():
            managed_bytes += catalog.stat().st_size
        for item in root.glob('*.bulk') if root.is_dir() else ():
            cancelled(cancel)
            managed_bytes += item.stat().st_size
        details.append(f'Managed card/bulk usage: {managed_bytes / 1024**2:.1f} MiB; {root}: {usage.free / 1024**3:.1f} GiB free / {usage.total / 1024**3:.1f} GiB capacity' +
                       ('; directory will be created during installation' if root != existing else '; writable'))
    return Check('Storage and permissions', 'Warning' if low else 'Healthy', '\n'.join(details))


def installation_check(state, cancel):
    pending = state.get('update_pending', False) or not state.get('setup_complete', False)
    return Check('Installation / migration', 'Warning' if pending else 'Healthy',
                 ('Installation is incomplete. Resume to reuse verified downloads.' if pending else 'Setup complete.') +
                 f" Artwork mode: {state.get('artwork_mode', 'on_demand')}. " +
                 f"Data versions: {state.get('bulk_versions', {})}. " +
                 f"Last successful synchronization: {state.get('last_successful_dataset_update', 'never')}. " +
                 f"Artwork checkpoint: {state.get('artwork_checkpoint', {})}.")


def recommendations_check(state, cancel):
    details, missing = [], False
    for source in APPROVED_SOURCES:
        cancelled(cancel)
        entry = state.installed('recommendations-' + source)
        if not entry:
            missing = True
            details.append(source + ': no managed bundle; legacy local datasets may still be available')
        else:
            metadata = validate_bundle(entry['path'], source)
            details.append(source + ': ' + str(metadata['generated_at']) + ' (schema 1, verified)')
    return Check('Recommendations', 'Warning' if missing else 'Healthy', '\n'.join(details))


def downloads_check(state, cancel):
    # Inspect only application-owned transfer roots, never recursively crawl artwork/user folders.
    size, count = 0, 0
    roots = [state.path.parent, state.storage_root('cards')]
    roots += [state.storage_root('recommendations') / ('recommendations-' + s) for s in APPROVED_SOURCES]
    roots += [state.storage_root('artwork') / 'downloads']
    for root in roots:
        if not root.is_dir():
            continue
        for item in root.glob('*.part'):
            cancelled(cancel)
            count += 1
            size += item.stat().st_size
    return Check('Interrupted downloads', 'Warning' if count else 'Healthy',
                 f'{count} partial downloads; {size / 1024**2:.1f} MiB retained. Resume installation to retry.' if count else 'No partial downloads found.')


def configuration_check(state, cancel):
    from .paths import data_root
    parser = configparser.ConfigParser()
    parser.read(data_root() / 'config.ini', encoding='utf-8')
    online = parser['DEFAULT'].getboolean('Online.Mode', True)
    return Check('Configuration', 'Healthy', f'Online search: {online}; artwork mode: {state.get("artwork_mode", "on_demand")}. Local diagnostics do not contact online services.')


def artwork_metadata_check(state, cancel):
    path = Path(state.get('catalog_path', str(core_data_root() / 'card_data.sqlite3')))
    if not path.is_file():
        return Check('Artwork cache', 'Not Checked', 'Card database is needed to inspect the artwork manifest. Cache location is covered by storage checks.')
    with closing(readonly(path)) as db:
        count, size = db.execute("SELECT count(*),coalesce(sum(payload_size),0) FROM image_assets WHERE source='scryfall'").fetchone()
    return Check('Artwork cache', 'Healthy', f'{count:,} recorded remote assets; {size / 1024**2:.1f} MiB recorded canonical usage. File checksums require Verify artwork cache; actual disk usage can include optional copies.')


CHECKS = (storage_check, configuration_check, installation_check, catalog_check, recommendations_check, downloads_check, artwork_metadata_check)


def run_checks(state, *, version, cancel, report, online=False, fetch=None, extra_checks=()):
    runtime_files = [Path(sys.executable)]
    if not getattr(sys, 'frozen', False):
        runtime_files += [Path(__file__), Path(__file__).with_name('installation.py')]
    readable = all(p.is_file() and os.access(p, os.R_OK) for p in runtime_files)
    valid_version = bool(version and re.fullmatch(r'\d+\.\d+\.\d+(?:-(?:alpha|beta)\.\d+)?', version))
    results = [Check('Application', 'Healthy' if readable and valid_version else 'Error',
                     f'Manaforge {version}; {"packaged" if getattr(sys, "frozen", False) else "source"} build. Runtime files readable: {readable}; version valid: {valid_version}. Distribution signatures are not verified.')] if version is not None else []
    for check in (*CHECKS, *extra_checks):
        cancelled(cancel)
        name = check.__name__.replace('_check', '').replace('_', ' ').title()
        report(dict(operation='Checking ' + name, phase='diagnostics', current=len(results), total=None))
        try:
            results.append(check(state, cancel))
        except Exception as exc:
            cancelled(cancel)
            results.append(Check(name, 'Error', f'{type(exc).__name__}: {exc}. Retry diagnostics or use a supported repair.'))
    results.append(Check('Artwork integrity', 'Not Checked', 'Use Verify artwork cache for an explicit checksum scan. Ordinary checks avoid scanning a large offline library.'))
    if online:
        from .sync import fetch_json
        fetch = fetch or fetch_json
        for name, url in [('Scryfall / internet', 'https://api.scryfall.com/bulk-data/default_cards'),
                          ('Recommendation update source', DEFAULT_MANIFEST_URL)]:
            cancelled(cancel)
            try:
                fetch(url)
                results.append(Check(name, 'Healthy', 'Source reachable.'))
            except Exception as exc:
                results.append(Check(name, 'Warning', f'Source unavailable: {exc}. Cached data remains usable offline.'))
    else:
        results.append(Check('Connectivity and update sources', 'Not Checked', 'Local checks only. Offline use does not require a connection. Select Check online services to contact Scryfall and the recommendation source.'))
    return results


def overall(results):
    return next((s for s in ('Error', 'Warning', 'Healthy') if any(r.status == s for r in results)), 'Not Checked')


def report_text(results, *, version, events=(), roots=()):
    from .repair import redact
    body = [f'Manaforge diagnostic report — {version}',
            time.strftime('%Y-%m-%d %H:%M:%S %Z'),
            f'OS: {platform.system()} {platform.release()} / {platform.machine()}',
            f'Build: {"packaged" if getattr(sys, "frozen", False) else "source"}; Python {platform.python_version()}',
            'Overall health: ' + overall(results)]
    body += [f'\n[{r.status}] {r.name}\n{r.detail}' for r in results]
    body.append('\nRecent operations and repair outcomes')
    body += [str(event) for event in events]
    body.append('\nRecent diagnostic log excerpts (bounded)')
    try:
        logs = sorted((core_data_root() / 'logs').glob('diagnostics-*.log'), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
        for log in logs:
            with log.open('rb') as stream:
                stream.seek(max(0, log.stat().st_size - 8192))
                body.append(stream.read(8192).decode('utf-8', errors='replace'))
    except OSError:
        body.append('Log files unavailable.')
    return redact('\n'.join(body), roots=roots)
