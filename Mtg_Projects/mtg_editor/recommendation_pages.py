"""Temporary disk-backed ranked candidates; only requested pages become UI rows."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from mtg_core.decks import DeckEntry
from .organization import in_deck_entries


class RecommendationPages:
    def __init__(self):
        self.directory = TemporaryDirectory(prefix='manaforge-recommendations-')
        self.path = Path(self.directory.name) / 'pages.sqlite3'
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE TABLE cards (oracle TEXT PRIMARY KEY, score REAL, text TEXT, '
                       'types TEXT, roles TEXT, payload TEXT)')
            db.execute('CREATE INDEX ranked ON cards(score DESC, oracle)')
            db.commit()

    def append(self, rows):
        from .recommendation_panel import card_types
        with closing(sqlite3.connect(self.path)) as db:
            for row in rows:
                entry = row['entry']
                text = (entry.name + ' ' + str(entry.extras.get('facts', {}).get('oracle_text') or '')).casefold()
                payload = dict(row, entry=entry.to_dict())
                db.execute('INSERT OR REPLACE INTO cards VALUES (?, ?, ?, ?, ?, ?)',
                           (row['oracle_id'], row['score'], text,
                            json.dumps(sorted(card_types(entry))),
                            json.dumps([role['name'] for role in row['roles']]), json.dumps(payload)))
            db.commit()

    def roles(self):
        with closing(sqlite3.connect(self.path)) as db:
            return [row[0] for row in db.execute(
                'SELECT DISTINCT value FROM cards, json_each(cards.roles) ORDER BY value')]

    def page(self, document, *, limit=50, kind='All Card Types', text='', role='All roles',
             membership=1, dismissed=(), category='Top Cards', identity=None, mana_value=-1):
        clauses, parameters = ['instr(text, ?) > 0'], [text.casefold().strip()]
        for column, value, all_value in [('types', kind, 'All Card Types'), ('roles', role, 'All roles')]:
            if value != all_value:
                clauses.append(f'EXISTS (SELECT 1 FROM json_each(cards.{column}) WHERE value=?)')
                parameters.append(value)
        # Filter before slicing, including membership in every deck section.
        rows, dismissed = [], set(dismissed)
        with closing(sqlite3.connect(self.path)) as db:
            cursor = db.execute('SELECT payload FROM cards WHERE ' + ' AND '.join(clauses) +
                                ' ORDER BY score DESC, oracle', parameters)
            for (payload,) in cursor:
                row = json.loads(payload)
                if row['oracle_id'] in dismissed:
                    continue
                row['entry'] = DeckEntry.from_dict(row['entry'])
                from .recommendation_categories import matches
                if not matches(row, category, identity, mana_value):
                    continue
                present = bool(in_deck_entries(document, [row['entry']]))
                if membership and present != (membership == 2):
                    continue
                rows.append(row)
                if len(rows) > limit:
                    break
        return rows[:limit], len(rows) > limit
