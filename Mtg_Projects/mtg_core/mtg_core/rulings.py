"""Separately versioned, offline card rulings retrieved from Scryfall."""
from contextlib import closing
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import UUID
import gzip


def normalize_ruling(row, oracle_id=None):
    """Validate both bulk and individual responses before touching cached data."""
    if (not isinstance(row, dict) or row.get('object') != 'ruling'
            or row.get('source') not in ('wotc', 'scryfall')
            or not isinstance(row.get('comment'), str)
            or not isinstance(row.get('published_at'), str)):
        raise ValueError('Scryfall returned an invalid card ruling')
    identity = str(UUID(row.get('oracle_id', '')))
    if oracle_id is not None and identity != oracle_id:
        raise ValueError('Scryfall returned a ruling for another card')
    date.fromisoformat(row['published_at'])
    return identity, {key: row[key] for key in ('source', 'published_at', 'comment')}


class RulingsStore:
    """Replace complete per-Oracle snapshots, including successful empty results."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise ValueError('Unsupported rulings dataset version')
            db.execute('''CREATE TABLE IF NOT EXISTS rulings (
                oracle_id TEXT PRIMARY KEY, fetched_at TEXT NOT NULL,
                payload TEXT NOT NULL)''')
            db.execute('PRAGMA user_version = 1')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def get(self, oracle_id):
        with closing(self.connect()) as db:
            row = db.execute('SELECT * FROM rulings WHERE oracle_id=?', (oracle_id,)).fetchone()
        if row is None:
            return None
        return {'fetched_at': row['fetched_at'], 'rulings': json.loads(row['payload'])}

    def replace(self, oracle_id, rulings):
        snapshot = {'fetched_at': datetime.now(timezone.utc).isoformat(), 'rulings': rulings}
        with closing(self.connect()) as db, db:
            db.execute('INSERT OR REPLACE INTO rulings VALUES (?, ?, ?)',
                       (oracle_id, snapshot['fetched_at'], json.dumps(rulings)))
        return snapshot


class RulingsOperations:
    """CardService operations; opening a reference never starts a network request."""

    def get_rulings(self, oracle_id):
        return RulingsStore(self.rulings_path).get(str(UUID(oracle_id)))

    def sync_all_rulings(self):
        """Refresh every local Oracle identity with one complete bulk download.

        Validate the entire export first; a failed download/import preserves every
        previous snapshot. Empty lists record confirmed absence of rulings.
        """
        with closing(self.database.connect()) as db:
            identities = set()
            skipped = 0
            for row in db.execute('SELECT oracle_id FROM cards_oracle'):
                try:
                    identities.add(str(UUID(row[0] or '')))
                except (ValueError, TypeError, AttributeError):
                    # Custom/imported cards may have a synthetic local identity.
                    skipped += 1
        if not identities:
            return {'cards': 0, 'rulings': 0, 'without_rulings': 0, 'skipped': skipped}
        metadata = self.fetch_json_fn('https://api.scryfall.com/bulk-data/rulings')
        url = (metadata.get('jsonl_download_uri') or metadata.get('download_uri')) if isinstance(metadata, dict) else None
        if (not isinstance(metadata, dict) or metadata.get('type') != 'rulings'
                or not isinstance(url, str)):
            raise ValueError('Scryfall did not provide a rulings bulk download')
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not (parsed.hostname or '').endswith('.scryfall.io'):
            raise ValueError('Unexpected Scryfall bulk download URL')
        raw = self.fetch_bytes_fn(url)
        if raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
        text = raw.decode('utf-8-sig')
        records = (json.loads(text) if text.lstrip().startswith('[') else
                   [json.loads(line) for line in text.splitlines() if line.strip()])
        if not isinstance(records, list) or not records:
            raise ValueError('Scryfall did not return a complete rulings export')
        grouped = {identity: [] for identity in identities}
        for row in records:
            identity, ruling = normalize_ruling(row)
            if identity in grouped:
                grouped[identity].append(ruling)
        fetched_at = datetime.now(timezone.utc).isoformat()
        store = RulingsStore(self.rulings_path)
        with closing(store.connect()) as db, db:
            db.executemany('INSERT OR REPLACE INTO rulings VALUES (?, ?, ?)',
                           ((identity, fetched_at, json.dumps(sorted(rows,
                             key=lambda row: row['published_at'], reverse=True)))
                            for identity, rows in grouped.items()))
        return {'cards': len(grouped), 'rulings': sum(map(len, grouped.values())),
                'without_rulings': sum(not rows for rows in grouped.values()),
                'skipped': skipped,
                'updated_at': metadata.get('updated_at')}

    def refresh_rulings(self, *, card_id, oracle_id):
        card_id, oracle_id = str(UUID(card_id)), str(UUID(oracle_id))
        payload = self.fetch_json_fn(f'https://api.scryfall.com/cards/{card_id}/rulings')
        # Refuse incomplete responses rather than replacing an offline snapshot
        # with a partial result. This endpoint normally returns one complete list.
        if (not isinstance(payload, dict) or payload.get('object') != 'list'
                or payload.get('has_more') is not False or not isinstance(payload.get('data'), list)):
            raise ValueError('Scryfall did not return a complete rulings list')
        rulings = []
        for row in payload['data']:
            _, ruling = normalize_ruling(row, oracle_id)
            rulings.append(ruling)
        rulings.sort(key=lambda row: row['published_at'], reverse=True)
        return RulingsStore(self.rulings_path).replace(oracle_id, rulings)
