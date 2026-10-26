"""Reusable repairs over InstallationEngine; no deck deletion or database replacement."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time

from .bulk_install import cancelled
from .diagnostics import get_logger
from .downloads import atomic_json, file_sha256, DownloadCancelled
from .paths import core_data_root, data_root

_journal_lock = threading.Lock()


def redact(text, *, roots=()):
    text = str(text)
    for root in sorted({str(Path.home()), str(data_root()), *(str(p) for p in roots if p)}, key=len, reverse=True):
        text = re.sub(re.escape(root), '<private-path>', text, flags=re.I)
        text = re.sub(re.escape(root.replace('\\', '/')), '<private-path>', text, flags=re.I)
    text = re.sub(r'https?://[^\s\'"<>]+', '<remote-url>', text)
    text = re.sub(r'(?i)\b(bearer\s+)[\w.\-]+', r'\1<redacted>', text)
    text = re.sub(r'(?i)((?:password|passwd|token|secret|api[_-]?key|authorization|credential)\s*[=:]\s*)[^\s,;]+', r'\1<redacted>', text)
    text = re.sub(r'(?i)\b[A-Z]:[\\/][^\r\n;\'"<>]*', '<private-path>', text)
    text = re.sub(r'(?<![\w:])/(?:home|Users|mnt|media|tmp)/[^\s\'"<>]+', '<private-path>', text)
    text = re.sub(r'(?i)([\"\']?(?:password|token|secret|api[_-]?key|authorization)[\"\']?\s*[:=]\s*)[\"\']?[^\s,;}]+', r'\1<redacted>', text)
    text = re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]+)\b', '<redacted>', text)
    text = re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', '<private-email>', text)
    return text


def recent_operations():
    try:
        value = json.loads((core_data_root() / 'logs' / 'operations.json').read_text(encoding='utf-8'))
        return value[-40:] if isinstance(value, list) else []
    except (OSError, ValueError):
        return []


def record_operation(operation, outcome, detail=''):
    # Telemetry failure must never prevent recovery or hide the original error.
    try:
        with _journal_lock:
            events = recent_operations()
            events.append(dict(time=time.time(), operation=redact(operation)[:200], outcome=outcome, detail=redact(detail)[:4000]))
            atomic_json(core_data_root() / 'logs' / 'operations.json', events[-40:])
    except (OSError, ValueError):
        get_logger(__name__).warning('Could not save operation history')


ACTIONS = {
    'resume': ('Resume installation / retry downloads', 'Contact update sources and resume installation using existing checkpoints and verified files. Valid installed versions are skipped. Decks and preferences are preserved.'),
    'cards': ('Repair missing card data', 'Fetch current card metadata and reimport missing card records transactionally. Existing preferences and decks are preserved. Physically corrupt databases require manual recovery; they will never be overwritten.'),
    'recommendations': ('Repair recommendation data', 'Check the recommendation source and verify installed bundles. Download only missing, changed or damaged bundles, then activate a verified new generation. Previous generations are retained.'),
    'metadata': ('Refresh stale metadata', 'Contact Scryfall and the recommendation source to refresh metadata and size estimates. No card or artwork downloads.'),
    'verify': ('Verify databases', 'Run local database integrity and schema checks. This does not modify databases or require internet.'),
    'artwork_verify': ('Verify artwork cache', 'Check recorded artwork files against their checksums and show storage usage. This local scan may take time for a large library. No files are deleted.'),
    'artwork': ('Repair cached artwork', 'Verify cached Scryfall artwork and restore damaged or missing files using the existing image downloader. Valid images and custom artwork are kept. Internet is required for missing images.'),
    'cache': ('Rebuild optional caches', 'Remove only reproducible artwork copies whose canonical originals pass checksum verification. Copies are recreated when used. Canonical images, decks and preferences are kept.'),
    'defaults': ('Restore default application configuration', 'Back up config.ini, then restore application defaults on next restart. This resets online/print/display settings only. Installation location, artwork preferences, favorites and decks are kept.'),
}


class RepairService:
    def __init__(self, engine):
        self.engine = engine

    def run(self, action, *, cancel, report):
        if action not in ACTIONS:
            raise ValueError('Unsupported repair')
        record_operation(ACTIONS[action][0], 'started')
        try:
            cancelled(cancel)
            result = self._run(action, cancel, report)
            record_operation(ACTIONS[action][0], 'completed', result)
            return result
        except DownloadCancelled:
            record_operation(ACTIONS[action][0], 'cancelled', 'Completed work and partial downloads were preserved.')
            raise
        except Exception as exc:
            record_operation(ACTIONS[action][0], 'failed', str(exc))
            raise

    def _run(self, action, cancel, report):
        engine = self.engine
        if action == 'verify':
            from .health import run_checks
            return run_checks(engine.state, version=None, cancel=cancel, report=report)
        if action == 'defaults':
            path = data_root() / 'config.ini'
            if path.exists():
                # Exclusive backup; never overwrite an earlier configuration backup.
                backup = path.with_name('config.ini.backup-' + str(time.time_ns()))
                with path.open('rb') as source, backup.open('xb') as output:
                    output.write(source.read())
                    output.flush()
                    os.fsync(output.fileno())
                cancelled(cancel)
                # Atomic rename keeps the original recoverable if interrupted.
                os.replace(path, backup)
            return 'Defaults will apply after restart. Configuration backup retained.'
        if action == 'metadata':
            engine.plan(cancel=cancel, report=report)
            return 'Metadata refreshed.'
        if action == 'recommendations':
            from .datasets import parse_manifest
            from .recommendation_distribution import SUPPORTED_SCHEMAS
            document, _ = engine.distribution.check(cancel=cancel)
            for entry in parse_manifest(document):
                cancelled(cancel)
                if entry.dataset_id in SUPPORTED_SCHEMAS:
                    engine.distribution.install(entry, cancel=cancel, progress=lambda p: report(dict(operation='Repairing recommendations', phase=p.phase, current=p.downloaded, total=p.total)))
            return 'Recommendation bundles verified and repaired.'
        if action == 'cache':
            return f'{engine.clear_optional(cancel=cancel, report=report)} reproducible copies cleared.'
        if action in ('artwork_verify', 'artwork'):
            return self.artwork(cancel, report, repair=action == 'artwork')
        if action == 'cards':
            from .health import catalog_check
            health = catalog_check(engine.state, cancel)
            if health.status == 'Error' and 'missing' not in health.detail.lower():
                raise ValueError(health.detail)
            plan = engine.plan(cancel=cancel, report=report)
            if health.status == "Healthy" and engine._version("default_cards") == plan.bulk["default_cards"]["updated_at"]:
                return "Card data is already healthy and current. No card download was needed."
            # Force a transactional reimport without altering the installed version
            # checkpoint first. A failed repair leaves its previous value intact.
            from .installation import InstallPlan
            plan = InstallPlan({'default_cards': plan.bulk['default_cards']}, {'manifest_version': 1, 'datasets': []}, plan.download_bytes, plan.required_bytes, 0)
            engine.run(cancel=cancel, report=report, plan=plan, repair_cards=True)
            return 'Card data repaired.'
        engine.run(cancel=cancel, report=report, setup=not engine.state.get('setup_complete', False))
        return 'Installation resumed successfully.'

    def artwork(self, cancel, report, *, repair=False):
        service = self.engine.service
        total = damaged = used = unresolved = 0
        with closing(service.database.connect()) as db:
            rows = db.execute("SELECT card_id,variant,path,checksum,asset_id FROM image_manifest WHERE source='scryfall'")
            for card, variant, path, checksum, asset_id in rows:
                cancelled(cancel)
                total += 1
                candidate = Path(path) if path else None
                valid = candidate and candidate.is_file() and checksum and file_sha256(candidate) == checksum
                asset = service.database.get_image_asset(asset_id) if asset_id else None
                canonical_valid = bool(asset and asset.payload and hashlib.sha256(asset.payload).hexdigest() == asset.checksum)
                if canonical_valid and not valid and repair:
                    restored = service.materialize_image_asset(asset_id)
                    if restored:
                        service.database.upsert_image_record(
                            card, variant=variant, asset_id=asset_id, path=restored,
                            status='ready', source='scryfall', checksum=asset.checksum)
                        candidate = Path(restored)
                        valid = True
                if valid and not canonical_valid and asset and repair:
                    service.database.store_image_asset(candidate.read_bytes(), extension=asset.extension,
                        source='scryfall', source_url=asset.source_url)
                    canonical_valid = True
                if valid and canonical_valid:
                    used += candidate.stat().st_size
                else:
                    damaged += 1
                    if repair:
                        face = 0 if variant == 'default' else 1 if variant == 'back' else int(variant[5:]) if variant.startswith('face-') and variant[5:].isdigit() else None
                        if face is not None:
                            result = service.cache_artwork(card, face, cancel=cancel, refresh=True, downloader=self.engine.downloader)
                            if not result:
                                raise ValueError('Artwork could not be restored. Retry after refreshing card data.')
                            record = service.database.get_image_record(card, variant)
                            if not record or not record.path or not record.checksum or file_sha256(record.path) != record.checksum:
                                unresolved += 1
                        else:
                            unresolved += 1
                report(dict(operation='Repairing artwork' if repair else 'Verifying artwork', phase='artwork', current=total, total=None))
        from .health import Check
        detail = f'{total} cached records checked; {damaged} missing or damaged; {used / 1024**2:.1f} MiB verified. '
        detail += (f'{unresolved} unresolved after repair.' if repair else 'Use Repair cached artwork to restore remote images. Custom artwork was kept.')
        return [Check('Artwork integrity', 'Warning' if (unresolved if repair else damaged) else 'Healthy', detail)]
