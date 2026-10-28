"""Compact permission-scoped manual evidence; transport stays outside scoring."""
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import time

from . import LibraryError
from .payload import text, strings

CAPABILITY = 'manual_category_evidence_v1'
PAGE_SIZE = 10  # Bound worst-case responses even for 2,000-card publications.
SERVER_SQL = '''CREATE TABLE IF NOT EXISTS category_evidence (
    deck TEXT PRIMARY KEY REFERENCES decks(id), revision INTEGER, payload TEXT NOT NULL)'''


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def category_roles():
    from ..categorization import ROLE_TAGS
    from ..strategy_analysis import THEMES
    return {name for name, _ in ROLE_TAGS} | set(THEMES) | {'Tribal'}


def manual_snapshot(document):
    """Allowlist deliberate local decisions, never imported/legacy category labels."""
    from ..categorization import category_origin, category_key, selected_theme_keys
    roles = {category_key(name): name for name in category_roles()}
    categories = {c.category_id: roles.get(category_key(c.name)) for c in document.deck.categories}
    assignments = []
    for entry in document.deck.entries:
        if category_origin(entry) != 'manual' or not entry.oracle_id or not entry.category_ids:
            continue
        category = categories.get(entry.category_ids[0])
        if (category and entry.category_ids[0] in entry.extras['auto_categories'].get('manual_ids', [])
                and entry.quantity > 0 and entry.section == 'mainboard'):
            from ..categorization import classify
            functions = [m['name'] for m in classify(entry.extras.get('facts', {})) if m.get('layer') == 'function']
            assignments.append({'oracle': entry.oracle_id, 'category': category,
                                'function': functions[0] if functions else ''})
    themes = selected_theme_keys(document)[:30]
    choices = {}
    for assignment in assignments:
        choices.setdefault(assignment['oracle'], []).append(assignment)
    # Different printings of one Oracle card are not independent decisions.
    # Contradictory local choices abstain instead of blocking deck publication.
    assignments = [items[0] for _, items in sorted(choices.items())
                   if len({item['category'] for item in items}) == 1]
    return {'assignments': assignments, 'themes': themes}


def clean_snapshot(value):
    if not isinstance(value, dict):
        raise LibraryError(400, 'Invalid manual category evidence.')
    roles = category_roles()
    items = value.get('assignments', [])
    themes = strings(value.get('themes', []), 30)
    if not isinstance(items, list) or len(items) > 2000:
        raise LibraryError(400, 'Invalid manual category evidence.')
    result = {}
    for item in items:
        if not isinstance(item, dict):
            raise LibraryError(400, 'Invalid manual category evidence.')
        from .client import identifier
        oracle = identifier(item.get('oracle'))
        category = text(item.get('category'))
        function = text(item.get('function', ''), 256, empty=True)
        if function and function not in roles:
            raise LibraryError(400, 'Invalid primary function.')
        assignment = {'oracle': oracle, 'category': category, 'function': function}
        if category not in roles or (oracle in result and result[oracle] != assignment):
            raise LibraryError(400, 'Invalid manual category evidence.')
        result[oracle] = assignment
    return {'assignments': [item for _, item in sorted(result.items())],
            'themes': sorted(set(themes))}


def enabled(store):
    with store.db() as db:
        row = db.execute("SELECT value FROM meta WHERE key='community_categories'").fetchone()
        return row is None or row[0] != 'disabled'


def contribute(store, token, deck_id, revision, value):
    """One replacement batch per published revision, authenticated as its owner."""
    snapshot = clean_snapshot(value)
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        actor = store.actor(db, token)
        row = db.execute('''SELECT d.*, r.payload FROM decks d JOIN revisions r
            ON r.deck_id=d.id AND r.revision=d.revision WHERE d.id=?''', (deck_id,)).fetchone()
        if row is None or not row['published'] or row['owner'] != actor['id']:
            raise LibraryError(403, 'Only the owner of a published deck can contribute.')
        if type(revision) is not int or revision != row['revision']:
            raise LibraryError(409, 'Publish the current deck before contributing.')
        deck = json.loads(row['payload'])
        members = {e.get('oracle_id') for e in deck['entries'] if e.get('quantity', 0) > 0
                   and e.get('section') == 'mainboard'}
        if any(item['oracle'] not in members for item in snapshot['assignments']):
            raise LibraryError(400, 'Evidence must refer to cards in this published deck.')
        db.execute('INSERT OR REPLACE INTO category_evidence VALUES (?, ?, ?)',
                   (deck_id, revision, json.dumps(snapshot)))
    return {}


def feed(store, token, *, offset=0, version=''):
    """Paginated full authorized snapshot; unchanged versions avoid downloading records."""
    if type(offset) is not int or not 0 <= offset <= 1000000:
        raise LibraryError(400, 'Invalid evidence offset.')
    with store.db() as db:
        store.actor(db, token)
        rows = db.execute('''SELECT d.id, d.owner, r.payload, e.payload FROM category_evidence e
            JOIN decks d ON d.id=e.deck AND d.revision=e.revision
            JOIN revisions r ON r.deck_id=d.id AND r.revision=d.revision
            JOIN users u ON u.id=d.owner WHERE d.published=1 AND u.active=1 ORDER BY d.id''').fetchall()
    records = []
    server = store.info()['server_id']
    for deck_id, owner, raw_deck, raw_evidence in rows:
        deck, evidence = json.loads(raw_deck), json.loads(raw_evidence)
        commanders = sorted({e['oracle_id'] for e in deck['entries'] if e.get('oracle_id')
            and (e['entry_id'] in deck['commander_entry_ids'] or e.get('section') == 'commander')})
        members = sorted({e.get('oracle_id') or e['name'] for e in deck['entries'] if e.get('quantity', 0) > 0})
        # No names, local IDs, notes, decklists, or behavioral telemetry leave this endpoint.
        records.append({'author': fingerprint([server, owner]), 'deck': fingerprint([members, commanders]),
                        'commanders': commanders, 'format': deck['format'], **evidence})
    current = fingerprint(records)
    if version == current and offset == 0:
        return {'version': current, 'unchanged': True, 'records': [], 'next': None}
    if offset and version != current:
        raise LibraryError(409, 'Evidence changed during download. Retry later.')
    end = offset + PAGE_SIZE
    return {'version': current, 'unchanged': False, 'records': records[offset:end],
            'next': end if end < len(records) else None}


class CategoryEvidence:
    def __init__(self, path=None, *, initialize=True):
        if path is None:
            from ..paths import data_root
            path = data_root() / 'library-category-evidence.sqlite3'
        self.path = Path(path)
        if not initialize:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS settings (server TEXT PRIMARY KEY, contribute INTEGER DEFAULT 0, attempted REAL DEFAULT 0, version TEXT DEFAULT "")')
            db.execute('CREATE TABLE IF NOT EXISTS evidence (server TEXT, author TEXT, deck TEXT, oracle TEXT, category TEXT, commanders TEXT, themes TEXT, format TEXT, function TEXT, PRIMARY KEY(server, author, deck, oracle))')
            db.execute('CREATE INDEX IF NOT EXISTS category_oracle ON evidence(oracle)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=1)

    def consent(self, server, value=None):
        with closing(self.connect()) as db, db:
            if value is not None:
                db.execute('INSERT OR IGNORE INTO settings(server) VALUES (?)', (server,))
                db.execute('UPDATE settings SET contribute=? WHERE server=?', (int(bool(value)), server))
            row = db.execute('SELECT contribute FROM settings WHERE server=?', (server,)).fetchone()
            return bool(row and row[0])

    def revoke(self, server):
        with closing(self.connect()) as db, db:
            db.execute('DELETE FROM evidence WHERE server=?', (server,))
            db.execute('DELETE FROM settings WHERE server=?', (server,))

    def sync(self, client, *, force=False, should_cancel=lambda: False):
        from urllib.parse import urlencode
        server = getattr(client, 'server_id', None)
        if (not server or not getattr(client, 'token', None) or
                not callable(getattr(client, 'check', None)) or not callable(getattr(client, 'request', None))):
            return
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO settings(server) VALUES (?)', (server,))
            attempted, version = db.execute('SELECT attempted, version FROM settings WHERE server=?', (server,)).fetchone()
            if not force and time.time() - attempted < 86400:
                return
            db.execute('UPDATE settings SET attempted=? WHERE server=?', (time.time(), server))
        try:
            if CAPABILITY not in client.check()['capabilities']:
                self.clear_records(server)
                return
            offset, staged = 0, []
            while not should_cancel():
                page = client.request('GET', 'category-evidence?' + urlencode({'offset': offset, 'version': version}))
                if page.get('unchanged') is True:
                    return
                new_version = text(page.get('version'), 64)
                if offset and version != new_version:
                    raise LibraryError(409, 'Evidence changed during download.')
                version = new_version
                records = page.get('records')
                if not isinstance(records, list) or len(records) > PAGE_SIZE:
                    raise LibraryError(502, 'Invalid category evidence response.')
                for record in records:
                    snapshot = clean_snapshot(record)
                    author, deck = text(record.get('author'), 64), text(record.get('deck'), 64)
                    commanders = strings(record.get('commanders', []), 10)
                    fmt = text(record.get('format'))
                    for item in snapshot['assignments']:
                        staged.append((server, author, deck, item['oracle'], item['category'],
                                       json.dumps(sorted(commanders)), json.dumps(snapshot['themes']), fmt, item['function']))
                following = page.get('next')
                if following is None:
                    break
                if type(following) is not int or following != offset + PAGE_SIZE or following > 100000:
                    raise LibraryError(502, 'Invalid category evidence pagination.')
                offset = following
            else:
                return
            if should_cancel():
                return
            with closing(self.connect()) as db, db:
                db.execute('DELETE FROM evidence WHERE server=?', (server,))
                db.executemany('INSERT OR REPLACE INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', staged)
                db.execute('UPDATE settings SET version=? WHERE server=?', (version, server))
        except LibraryError as error:
            if error.status in (401, 403, 404, 426):
                self.clear_records(server)
            raise

    def clear_records(self, server):
        with closing(self.connect()) as db, db:
            db.execute('DELETE FROM evidence WHERE server=?', (server,))
            db.execute('UPDATE settings SET version="" WHERE server=?', (server,))

    def for_cards(self, oracles):
        """One indexed batch read per categorization operation; no transport."""
        if not oracles:
            return {}
        with closing(sqlite3.connect(self.path, timeout=0)) as db:
            rows = db.execute('''SELECT author, deck, oracle, category, commanders, themes, format, function
                FROM evidence WHERE oracle IN (SELECT value FROM json_each(?))''', (json.dumps(sorted(set(oracles))),)).fetchall()
        result = {}
        for author, deck, oracle, category, commanders, themes, fmt, function in rows:
            result.setdefault(oracle, []).append(dict(author=author, deck=deck, category=category,
                commanders=json.loads(commanders), themes=json.loads(themes), format=fmt, function=function))
        return result


def refine(evidence, records, *, commanders=(), themes=(), format=''):
    """Bounded tie refinement inside a detected role layer, never a popularity override."""
    from ..categorization_policy import ordered_evidence
    if len(evidence) < 2 or not records:
        return evidence
    commanders, themes = set(commanders), set(themes)
    # A copied list contributes once across authors/libraries. Each author has one vote.
    authors, decks, votes, counts = set(), set(), {}, {}
    functions = {m['name'] for m in evidence if m.get('layer') == 'function'}
    eligible, author_roles, deck_roles = [], {}, {}
    for record in records:
        if record['format'] != format:
            continue
        if record.get('function') and record['function'] not in functions:
            continue
        same_commander = bool(commanders) and commanders == set(record['commanders'])
        same_theme = bool(themes.intersection(record['themes']))
        if not same_commander and not same_theme:
            continue
        eligible.append((record, 1.0 if same_commander else 0.6))
        author_roles.setdefault(record['author'], set()).add(record['category'])
        deck_roles.setdefault(record['deck'], set()).add(record['category'])
    for record, weight in sorted(eligible, key=lambda item: (-item[1], item[0]['deck'], item[0]['author'])):
        if (record['author'] in authors or record['deck'] in decks or
                len(author_roles[record['author']]) != 1 or len(deck_roles[record['deck']]) != 1):
            continue  # Conflicting copies/assignments abstain rather than winning by order.
        authors.add(record['author'])
        decks.add(record['deck'])
        votes[record['category']] = votes.get(record['category'], 0) + weight
        counts[record['category']] = counts.get(record['category'], 0) + 1
    if len(authors) < 3 or not votes:
        return evidence
    winner = max(votes, key=votes.get)
    if counts[winner] < 3 or votes[winner] / sum(votes.values()) < 0.75:
        return evidence
    primary = evidence[0]
    result = []
    for match in evidence:
        item = dict(match)
        if (item['name'] == winner and item.get('layer') == primary.get('layer')
                and primary.get('score', 100) - item.get('score', 100) <= 3):
            item['score'] = item.get('score', 100) + 4
            item['reason'] = item.get('reason', '') + '; relevant independent manual assignments (+4)'
        result.append(item)
    return ordered_evidence(result)
