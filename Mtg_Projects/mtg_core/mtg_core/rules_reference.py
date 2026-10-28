"""Versioned local Comprehensive Rules snapshots, independent of card/deck data."""
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote, urljoin, urlsplit

RULES_PAGE = 'https://magic.wizards.com/en/rules'
FORMAT_VERSION = 1
HEADING = re.compile(r'^([1-9](?:\d{2}(?:\.\d+[a-z]?)?)?)\.?(?:[ \t]+)(\S.*)$')


def parse_rules(text):
    """Skip the repeated table of contents and retain examples with their rule."""
    text = text.replace('\r\n', '\n').replace('\r', '\n').lstrip('\ufeff')
    if 'Magic: The Gathering Comprehensive Rules' not in text[:200]:
        raise ValueError('This is not an English Magic Comprehensive Rules document.')
    effective = re.search(r'effective as of ([A-Za-z]+ \d{1,2}, \d{4})', text[:2000])
    if not effective:
        raise ValueError('The rules document has no recognized effective date.')
    effective_date = datetime.strptime(effective[1], '%B %d, %Y').date().isoformat()
    first = re.search(r'^100\.1\.\s', text, re.M)
    if not first:
        raise ValueError('The numbered rules are missing.')
    starts = list(re.finditer(r'^1\. Game Concepts\s*$', text[:first.start()], re.M))
    if not starts:
        raise ValueError('The Game Concepts section is missing.')
    body = text[starts[-1].start():]
    end = re.search(r'^Glossary\s*$', body, re.M)
    if not end or not re.search(r'^Credits\s*$', body[end.end():], re.M):
        raise ValueError('The rules download appears incomplete (missing glossary or credits).')
    body = body[:end.start()]
    entries, current = [], None
    for line in body.splitlines():
        match = HEADING.match(line)
        if match:
            number, title = match.groups()
            kind = 'section' if len(number) == 1 else 'chapter' if '.' not in number else 'rule'
            current = {'number': number, 'title': title, 'body': title,
                       'kind': kind, 'ordinal': len(entries)}
            entries.append(current)
        elif current is not None:
            current['body'] += '\n' + line
    numbers = [row['number'] for row in entries]
    if len(numbers) != len(set(numbers)) or not {'100.1', '702', '903.1'}.issubset(numbers):
        raise ValueError('The rules snapshot has missing or duplicate numbered sections.')
    for row in entries:
        row['body'] = row['body'].strip()
    keywords = [{'name': row['title'], 'number': row['number']} for row in entries
                if re.fullmatch(r'70[12]\.\d+', row['number'])
                and len(row['title']) <= 70 and not row['title'].endswith('.')]
    return effective_date, entries, keywords


class RulesStore:
    """Atomic installs keep the current and previous complete document snapshots."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, FORMAT_VERSION):
                raise ValueError('Unsupported rules cache format.')
            db.execute('''CREATE TABLE IF NOT EXISTS snapshots (
                checksum TEXT PRIMARY KEY, effective_date TEXT NOT NULL,
                fetched_at TEXT NOT NULL, source TEXT NOT NULL, document TEXT NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS rules (
                version TEXT NOT NULL, number TEXT NOT NULL, title TEXT NOT NULL,
                body TEXT NOT NULL, kind TEXT NOT NULL, ordinal INTEGER NOT NULL,
                PRIMARY KEY(version, number))''')
            db.execute('CREATE INDEX IF NOT EXISTS rules_order ON rules(version, ordinal)')
            db.execute('''CREATE VIRTUAL TABLE IF NOT EXISTS rules_fts USING fts5(
                version UNINDEXED, number UNINDEXED, body, tokenize='unicode61')''')
            db.execute('''CREATE TABLE IF NOT EXISTS keywords (
                version TEXT NOT NULL, name TEXT NOT NULL, number TEXT NOT NULL)''')
            db.execute('CREATE TABLE IF NOT EXISTS current_snapshot (id INTEGER PRIMARY KEY CHECK(id=1), version TEXT NOT NULL)')
            db.execute(f'PRAGMA user_version = {FORMAT_VERSION}')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _metadata(db):
        row = db.execute('''SELECT checksum,effective_date,fetched_at,source FROM snapshots
            WHERE checksum=(SELECT version FROM current_snapshot WHERE id=1)''').fetchone()
        return dict(row) if row else None

    def index(self):
        with closing(self.connect()) as db:
            metadata = self._metadata(db)
            if metadata is None:
                return {'metadata': None, 'sections': [], 'keywords': []}
            version = metadata['checksum']
            sections = [dict(row) for row in db.execute(
                "SELECT number,title,kind FROM rules WHERE version=? AND kind != 'rule' ORDER BY ordinal", (version,))]
            keywords = [dict(row) for row in db.execute(
                'SELECT name,number FROM keywords WHERE version=? ORDER BY name COLLATE NOCASE', (version,))]
        return {'metadata': metadata, 'sections': sections, 'keywords': keywords}

    def install(self, text, source):
        effective, rows, keywords = parse_rules(text)
        checksum = sha256(text.encode('utf-8')).hexdigest()
        stamp = datetime.now(timezone.utc).isoformat()
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            previous = self._metadata(db)
            if previous and previous['effective_date'] > effective:
                raise ValueError('The supplied rules are older than the installed snapshot; the installed rules were kept.')
            exists = db.execute('SELECT 1 FROM snapshots WHERE checksum=?', (checksum,)).fetchone()
            if not exists:
                db.execute('INSERT INTO snapshots VALUES (?,?,?,?,?)', (checksum, effective, stamp, source, text))
                db.executemany('INSERT INTO rules VALUES (?,?,?,?,?,?)', [
                    (checksum, row['number'], row['title'], row['body'], row['kind'], row['ordinal']) for row in rows])
                db.executemany('INSERT INTO rules_fts VALUES (?,?,?)', [(checksum, row['number'], row['body']) for row in rows])
                db.executemany('INSERT INTO keywords VALUES (?,?,?)', [(checksum, row['name'], row['number']) for row in keywords])
            else:
                db.execute('UPDATE snapshots SET fetched_at=?,source=? WHERE checksum=?', (stamp, source, checksum))
            db.execute('INSERT OR REPLACE INTO current_snapshot VALUES (1,?)', (checksum,))
            # A previous known-good version remains available in storage.
            stale = db.execute('SELECT checksum FROM snapshots ORDER BY effective_date DESC,fetched_at DESC LIMIT -1 OFFSET 2').fetchall()
            for row in stale:
                for table in ('rules', 'rules_fts', 'keywords'):
                    db.execute(f'DELETE FROM {table} WHERE version=?', (row[0],))
                db.execute('DELETE FROM snapshots WHERE checksum=?', (row[0],))
        return self.index()

    def search(self, query='', *, offset=0, limit=200):
        limit, offset = max(1, min(200, int(limit))), max(0, int(offset))
        query = query.strip()
        with closing(self.connect()) as db:
            metadata = self._metadata(db)
            if metadata is None:
                return []
            version = metadata['checksum']
            number = re.fullmatch(r'(?:rule\s+)?([1-9](?:\d{1,2}(?:\.\d+[a-z]?)?)?)\.?', query, re.I)
            if number:
                key = number[1].lower()
                return [dict(row) for row in db.execute('''SELECT * FROM rules WHERE version=?
                    AND (number=? OR number LIKE ? OR number GLOB ?) ORDER BY ordinal LIMIT ? OFFSET ?''',
                    (version, key, key + ('%' if len(key) <= 2 else '.%'), key + '[a-z]', limit, offset))]
            terms = re.findall(r'\w+', query, re.UNICODE)[:30]
            if terms:
                match = ' AND '.join('"' + word + '"*' for word in terms)
                return [dict(row) for row in db.execute('''SELECT r.* FROM rules_fts f JOIN rules r
                    ON r.version=f.version AND r.number=f.number WHERE rules_fts MATCH ?
                    AND f.version=? ORDER BY r.ordinal LIMIT ? OFFSET ?''', (match, version, limit, offset))]
            if query:
                return []
            return [dict(row) for row in db.execute(
                'SELECT * FROM rules WHERE version=? ORDER BY ordinal LIMIT ? OFFSET ?', (version, limit, offset))]


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.urls.extend(value for key, value in attrs if key == 'href' and value)


class RulesOperations:
    """Service boundary: reads are offline, downloads require an explicit action."""
    def rules_index(self):
        return RulesStore(self.rules_path).index()

    def search_rules(self, query='', *, offset=0):
        return RulesStore(self.rules_path).search(query, offset=offset)

    def import_rules(self, path):
        source = Path(path)
        if source.stat().st_size > 15 * 1024 * 1024:
            raise ValueError('The rules file exceeds 15 MB.')
        return RulesStore(self.rules_path).install(source.read_text(encoding='utf-8-sig'), str(source))

    def refresh_rules(self, *, fetch_bytes=None, cancel=None):
        from .artwork_storage_lock import cancelled
        fetch = fetch_bytes or self.fetch_bytes_fn
        cancelled(cancel)
        page = fetch(RULES_PAGE)
        cancelled(cancel)
        if len(page) > 15 * 1024 * 1024:
            raise ValueError('The rules download page exceeds 15 MB.')
        parser = _Links()
        parser.feed(page.decode('utf-8-sig'))
        # Wizards sometimes publishes literal spaces in TXT filenames. Preserve
        # existing percent escapes while encoding spaces and other unsafe bytes.
        urls = [quote(urljoin(RULES_PAGE, url.strip()), safe=':/%?=&#+') for url in parser.urls]
        source = next((url for url in urls if urlsplit(url).scheme == 'https'
                       and urlsplit(url).netloc == 'media.wizards.com'
                       and 'magiccomprules' in urlsplit(url).path.casefold()
                       and urlsplit(url).path.casefold().endswith('.txt')), None)
        if source is None:
            raise ValueError('No official English TXT link was found. Import a downloaded rules TXT file instead.')
        content = fetch(source)
        cancelled(cancel)
        if len(content) > 15 * 1024 * 1024:
            raise ValueError('The rules download exceeds 15 MB.')
        return RulesStore(self.rules_path).install(content.decode('utf-8-sig'), source)
