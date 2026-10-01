"""Separately versioned, offline card rulings retrieved from Scryfall."""
from contextlib import closing
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import UUID


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
            if (not isinstance(row, dict) or row.get('object') != 'ruling'
                    or row.get('oracle_id') != oracle_id
                    or row.get('source') not in ('wotc', 'scryfall')
                    or not isinstance(row.get('comment'), str)
                    or not isinstance(row.get('published_at'), str)):
                raise ValueError('Scryfall returned an invalid card ruling')
            date.fromisoformat(row['published_at'])
            rulings.append({key: row[key] for key in ('source', 'published_at', 'comment')})
        rulings.sort(key=lambda row: row['published_at'], reverse=True)
        return RulingsStore(self.rulings_path).replace(oracle_id, rulings)
