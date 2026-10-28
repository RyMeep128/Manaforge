"""Permission-scoped shared samples, independent of owned and followed decks."""
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import time

from . import LibraryError
from ..sections import DeckSection


def cache_path():
    from ..paths import data_root
    return data_root() / 'library-recommendations.sqlite3'


class LibraryRecommendations:
    source_id = 'library'
    role = 'library'

    def __init__(self, path=None, *, document=None):
        self.path = Path(path or cache_path())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.document = document
        with closing(self.connect()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS access (server TEXT PRIMARY KEY, account TEXT, expires REAL)')
            db.execute('CREATE TABLE IF NOT EXISTS samples (server TEXT, deck TEXT, revision INTEGER, digest TEXT, commanders TEXT, colors TEXT, tags TEXT, PRIMARY KEY(server, deck))')
            db.execute('CREATE TABLE IF NOT EXISTS members (server TEXT, deck TEXT, oracle TEXT, PRIMARY KEY(server, deck, oracle))')
            db.execute('CREATE INDEX IF NOT EXISTS shared_oracle ON members(oracle)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def revoke(self, server):
        with closing(self.connect()) as db, db:
            for table in ('access', 'samples', 'members'):
                db.execute(f'DELETE FROM {table} WHERE server=?', (server,))

    def sync(self, client, *, should_cancel=lambda: False):
        """Stage a complete authorized listing; only changed samples are rewritten.

        Transport failures retain the last snapshot until session expiry. An access
        rejection purges it. Partial/cancelled listings never imply deck deletion.
        """
        from ..search.cancellation import check_cancelled
        if not all(getattr(client, field, None) for field in ('server_id', 'account_id', 'expires_at')):
            return False  # Adapters without a scoped, expiring session cannot authorize a cache.
        server = client.server_id
        with closing(self.connect()) as db:
            previous = db.execute('SELECT account FROM access WHERE server=?', (server,)).fetchone()
        if previous and previous[0] != client.account_id:
            self.revoke(server)
        publications = {}
        try:
            client.check()
            offset = 0
            while True:
                check_cancelled(should_cancel)
                rows = client.browse(offset=offset)
                for row in rows:
                    publications[row['deck_id']] = row
                if len(rows) < 50:
                    break
                offset += 50
            check_cancelled(should_cancel)
        except LibraryError as exc:
            if exc.status in (401, 403, 404, 409):
                self.revoke(server)
            raise
        with closing(self.connect()) as db, db:
            db.execute('INSERT OR REPLACE INTO access VALUES (?, ?, ?)',
                       (server, client.account_id, client.expires_at or time.time()))
            existing = dict(db.execute('SELECT deck, revision FROM samples WHERE server=?', (server,)))
            for deck_id in existing.keys() - publications.keys():
                db.execute('DELETE FROM samples WHERE server=? AND deck=?', (server, deck_id))
                db.execute('DELETE FROM members WHERE server=? AND deck=?', (server, deck_id))
            for deck_id, publication in publications.items():
                check_cancelled(should_cancel)
                if existing.get(deck_id) == publication['revision']:
                    continue
                deck = publication['deck']
                members, commanders = set(), set()
                for entry in deck['entries']:
                    if entry.get('quantity', 0) <= 0 or entry.get('section') not in (DeckSection.MAINBOARD.value, DeckSection.COMMANDER.value):
                        continue
                    oid = entry.get('oracle_id')
                    if not oid:
                        continue
                    members.add(oid)
                    if entry['entry_id'] in deck['commander_entry_ids'] or entry.get('section') == DeckSection.COMMANDER.value:
                        commanders.add(oid)
                digest = sha256(json.dumps([sorted(members), sorted(commanders)]).encode()).hexdigest()
                db.execute('INSERT OR REPLACE INTO samples VALUES (?, ?, ?, ?, ?, ?, ?)',
                           (server, deck_id, publication['revision'], digest, json.dumps(sorted(commanders)),
                            json.dumps(publication['color_identity']), json.dumps(deck.get('tags', []))))
                db.execute('DELETE FROM members WHERE server=? AND deck=?', (server, deck_id))
                if commanders:
                    db.executemany('INSERT INTO members VALUES (?, ?, ?)', [(server, deck_id, oid) for oid in members])

    def snapshot(self, commanders=(), *, exclude=(), limit=200):
        from ..card_pool import pool_context
        document = self.document
        identity = pool_context(document)[1] if document else None
        tags = {tag.casefold() for tag in document.deck.tags} if document else set()
        seeds = {e.oracle_id for e in document.deck.entries
                 if e.oracle_id and e.quantity > 0 and e.section == DeckSection.MAINBOARD} if document else set()
        # Rank/filter compact cached samples in SQL before joining card identities.
        # Duplicate lists contribute only once, even across multiple libraries.
        cohort_sql = '''WITH permitted AS (
            SELECT s.*,
              (SELECT count(*) FROM members m WHERE m.server=s.server AND m.deck=s.deck) AS size,
              (SELECT count(*) FROM members m WHERE m.server=s.server AND m.deck=s.deck
               AND m.oracle IN (SELECT value FROM json_each(:seeds))) AS overlap
            FROM samples s JOIN access a ON a.server=s.server WHERE a.expires>:now
              AND (:identity IS NULL OR NOT EXISTS (
                SELECT 1 FROM json_each(s.colors) WHERE instr(:identity,value)=0))
            ), weighted AS (
            SELECT *, CASE WHEN commanders=:commanders AND :commanders!='[]' THEN 1.0
              WHEN EXISTS (SELECT 1 FROM json_each(tags) WHERE lower(value) IN
                (SELECT value FROM json_each(:tags))) THEN 0.6
              ELSE 0.3*overlap/max(1,size+:seed_count-overlap) END AS weight FROM permitted
            ), copies AS (
            SELECT *, row_number() OVER (PARTITION BY digest ORDER BY weight DESC,server,deck) AS copy
            FROM weighted
            ), cohort AS (SELECT * FROM copies WHERE copy=1 AND weight>0)
        '''
        parameters = dict(now=time.time(), identity=identity,
                          commanders=json.dumps(sorted(set(commanders))), tags=json.dumps(sorted(tags)),
                          seeds=json.dumps(sorted(seed for seed in seeds if seed)), seed_count=len(seeds),
                          exclude=json.dumps([oid for oid in exclude if oid]), limit=max(0, min(limit, 2000)))
        cache_mtime = self.path.stat().st_mtime_ns
        with closing(self.connect()) as db:
            db.execute('BEGIN')
            deadline = db.execute('SELECT min(expires) FROM access WHERE expires>?', (time.time(),)).fetchone()[0]
            relevant, total = db.execute(cohort_sql + 'SELECT (SELECT count(*) FROM cohort), '
                                         '(SELECT count(*) FROM copies WHERE copy=1)', parameters).fetchone()
            rows = db.execute(cohort_sql + '''SELECT m.oracle, sum(c.weight), count(*) FROM cohort c
                JOIN members m ON m.server=c.server AND m.deck=c.deck
                WHERE m.oracle NOT IN (SELECT value FROM json_each(:exclude))
                  AND m.oracle NOT IN (SELECT value FROM json_each(c.commanders))
                GROUP BY m.oracle ORDER BY sum(c.weight) DESC,m.oracle LIMIT :limit''', parameters).fetchall()
        results = []
        for oid, weight, count in rows:
            item = dict(oracle_id=oid, shared_decks=count, score=weight / (relevant + 5))
            item['cache_deadline'] = deadline or 0
            item['cache_file'] = str(self.path)
            item['cache_mtime'] = cache_mtime
            results.append(item)
        return dict(results=results, decks=total, relevant_decks=relevant, sources=[],
                    status='Permitted cached shared decks')
