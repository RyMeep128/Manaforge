"""Real, bounded offline starter snapshot. Never fetch or overwrite collected data."""
from contextlib import closing
import gzip
import json
from pathlib import Path
from threading import Lock

from .search.cancellation import check_cancelled

_LOCK = Lock()
BUNDLE = Path(__file__).with_name('data') / 'discovery-starter.json.gz'


def starter_data():
    with gzip.open(BUNDLE, 'rt', encoding='utf-8') as stream:
        return json.load(stream)


def snapshot_path(root, filename):
    """Use full collected data when present, otherwise materialize the bundled subset."""
    root = Path(root)
    collected = root / filename
    if collected.exists():
        return collected
    target = root / 'starter' / filename
    with _LOCK:
        if target.exists():
            return target
        from .edhrec import save_page
        from .edhrec_discovery import save_discovery_page
        from tempfile import TemporaryDirectory
        data = starter_data()
        target.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix='build-', dir=target.parent) as temporary:
            staged = Path(temporary) / filename
            if filename == 'edhrec.sqlite3':
                for page in data['pages']:
                    save_page(staged, page['data'], page['imported'])
            elif filename == 'edhrec-discovery.sqlite3':
                for cohort in data['cohorts']:
                    save_discovery_page(staged, cohort, cohort['imported'])
            else:
                raise ValueError('Unsupported starter snapshot')
            staged.replace(target)
    return target


def ensure_starter_catalog(service, *, should_cancel=None):
    """Fill missing cards only when using starter source coverage, in a worker."""
    database = getattr(service, 'database', None)
    if database is None or not callable(getattr(database, 'upsert_card_payload', None)):
        return
    if getattr(service, '_discovery_starter_loaded', False):
        return
    from .paths import core_data_root
    root = core_data_root() / 'recommendations'
    if (root / 'edhrec.sqlite3').exists() and (root / 'edhrec-discovery.sqlite3').exists():
        with closing(database.connect()) as db:
            populated = bool(db.execute('SELECT 1 FROM canonical_prints LIMIT 1').fetchone())
        if populated:
            service._discovery_starter_loaded = True
            return
    data = starter_data()
    with closing(database.connect()) as db:
        existing = {row[0] for row in db.execute('SELECT oracle_id FROM canonical_prints')}
    for card in data['cards']:
        check_cancelled(should_cancel)
        payload = card['payload']
        if payload['oracle_id'] in existing:
            continue
        database.upsert_card_payload(dict(payload, first_released_at=card['first_released_at']))
        # Add exact exported tags, never replace a user's catalog or tags.
        with closing(database.connect()) as db, db:
            db.executemany('INSERT OR IGNORE INTO oracle_tags VALUES (?, ?)',
                           [(payload['oracle_id'], tag) for tag in card['tags']])
    service._discovery_starter_loaded = True
