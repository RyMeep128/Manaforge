"""Indexed, disk-backed ranked candidates with a bounded cache of viewed pages."""
from collections import OrderedDict
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import time
from tempfile import TemporaryDirectory

from mtg_core.decks import DeckEntry
from mtg_core.search.cancellation import check_cancelled
from .organization import in_deck_entries
from .recommendation_categories import categories, card_types
from mtg_core.discovery_themes import theme_matches
from mtg_core.card_pool import in_card_pool, pool_context


class RecommendationPages:
    def __init__(self):
        self.directory = TemporaryDirectory(prefix='manaforge-recommendations-')
        self.path = Path(self.directory.name) / 'pages.sqlite3'
        self.cache = OrderedDict()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE TABLE cards (oracle TEXT PRIMARY KEY, score REAL, text TEXT, '
                       'types TEXT, roles TEXT, categories TEXT, identity TEXT, mana REAL, payload TEXT)')
            db.execute('CREATE INDEX ranked ON cards(score DESC, oracle)')
            db.commit()

    def append(self, rows):
        self.cache.clear()
        with closing(sqlite3.connect(self.path)) as db:
            # Rebuildable scratch pages: avoid a durable disk flush per small batch.
            db.execute('PRAGMA synchronous=OFF')
            db.execute('PRAGMA journal_mode=MEMORY')
            for row in rows:
                entry = row['entry']
                facts = entry.extras.get('facts') or {}
                text = (entry.name + ' ' + str(facts.get('oracle_text') or '')).casefold()
                payload = dict(row, browse_categories=sorted(categories(row)), entry=entry.to_dict())
                db.execute('INSERT OR REPLACE INTO cards VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                           (row['oracle_id'], row['score'], text, json.dumps(sorted(card_types(entry))),
                            json.dumps([role['name'] for role in row['roles']]),
                            json.dumps(payload['browse_categories']),
                            json.dumps(facts.get('color_identity')), facts.get('cmc'), json.dumps(payload)))
            db.commit()

    def reranked(self, service, document, *, sources=None, should_cancel=None):
        """Reuse enriched candidates after deck edits; do not reload sources or printings."""
        from mtg_core.recommendation_scoring import settings
        from .recommendations import rank_recommendations, recommendation_context
        context = recommendation_context(service, document)
        result = RecommendationPages()
        preferences = dict(settings(document), dismissed=[])
        batch = []
        associations, provider_id = {}, None
        if sources is not None:
            from mtg_core.sections import DeckSection
            seeds = [e.oracle_id for e in document.deck.entries if e.oracle_id and e.quantity > 0
                     and e.section == DeckSection.MAINBOARD
                     and 'Basic Land' not in ((e.extras.get('facts') or {}).get('type_line') or '')]
            with closing(sqlite3.connect(self.path)) as db:
                identities = [row[0] for row in db.execute('SELECT oracle FROM cards')]
                active = {row[0] for row in db.execute(
                    "SELECT DISTINCT evidence.key FROM cards, json_each(cards.payload, '$.source_evidence') evidence")}

            if seeds:
                for source in sorted(sources, key=lambda item: item.source_id):
                    if source.source_id in active and callable(getattr(source, 'associations', None)):
                        check_cancelled(should_cancel)
                        try:
                            associations = source.associations(seeds, identities)
                            provider_id = source.source_id
                        except (OSError, ValueError, sqlite3.DatabaseError):
                            associations = {}
                        break
        with closing(sqlite3.connect(self.path)) as db:
            for (payload,) in db.execute('SELECT payload FROM cards ORDER BY score DESC, oracle'):
                check_cancelled(should_cancel)
                row = json.loads(payload)
                if sources is not None:
                    association = dict(associations.get(row['oracle_id'], {}))
                    if association:
                        association['source'] = provider_id
                        association.setdefault('baseline', row.get('source_evidence', {}).get(provider_id, {}).get('baseline', 0))
                    row['association'] = association
                row['entry'] = DeckEntry.from_dict(row['entry'])
                batch.append(row)
                if len(batch) == 200:
                    result.append(rank_recommendations(batch, context, preferences))
                    batch = []
        if batch:
            result.append(rank_recommendations(batch, context, preferences))
        return result

    def roles(self):
        with closing(sqlite3.connect(self.path)) as db:
            return [row[0] for row in db.execute(
                'SELECT DISTINCT value FROM cards, json_each(cards.roles) ORDER BY value')]

    def available_categories(self):
        with closing(sqlite3.connect(self.path)) as db:
            return dict(db.execute('SELECT value, count(*) FROM cards, json_each(cards.categories) GROUP BY value'))

    def page(self, document, *, limit=50, kind='All Card Types', text='', role='All roles',
             membership=1, dismissed=(), category='Top Cards', identity=None, mana_value=-1,
             theme=None, should_cancel=None, collection='Top Cards'):
        check_cancelled(should_cancel)
        # Quantity/printing changes that do not change membership can reuse pages.
        deck_key = tuple(sorted((e.oracle_id or '', e.card_id or '', ' '.join(e.name.casefold().split()))
                                for e in document.deck.entries if e.quantity > 0))
        key = (deck_key, pool_context(document), limit, kind, text, role, membership, tuple(sorted(dismissed)), category,
               identity, mana_value, json.dumps(theme, sort_keys=True), collection)
        # Shared evidence must be checked even for a previously viewed page:
        # disconnects, permission changes and expiry can invalidate it at any time.
        if key in self.cache and not any(row.get('source_evidence', {}).get('library')
                                         for row in self.cache[key][0]):
            self.cache.move_to_end(key)
            return deepcopy(self.cache[key])
        clauses, parameters = ['instr(text, ?) > 0'], [text.casefold().strip()]
        for column, value, all_value in [('types', kind, 'All Card Types'), ('roles', role, 'All roles'),
                                         ('categories', category, None), ('categories', collection, 'Top Cards')]:
            if value != all_value:
                clauses.append(f'EXISTS (SELECT 1 FROM json_each(cards.{column}) WHERE value=?)')
                parameters.append(value)
        if mana_value >= 0:
            clauses.append('mana=?')
            parameters.append(mana_value)
        if identity is not None:
            clauses.append("json_type(identity)='array' AND NOT EXISTS "
                           "(SELECT 1 FROM json_each(cards.identity) WHERE instr(?, value)=0)")
            parameters.append(identity)
        rows, dismissed = [], set(dismissed)
        with closing(sqlite3.connect(self.path, timeout=0.1)) as db:
            if should_cancel:
                db.set_progress_handler(lambda: int(should_cancel()), 1000)
            try:
                cursor = db.execute('SELECT payload FROM cards WHERE ' + ' AND '.join(clauses) +
                                    " ORDER BY coalesce(json_extract(payload, '$.fallback'), 0), score DESC, oracle", parameters)
                for (payload,) in cursor:
                    check_cancelled(should_cancel)
                    row = json.loads(payload)
                    shared = row.get('source_evidence', {}).get('library')
                    if shared:
                        try:
                            permitted = (shared.get('cache_deadline', 0) > time.time()
                                         and Path(shared['cache_file']).stat().st_mtime_ns == shared['cache_mtime'])
                        except (OSError, KeyError):
                            permitted = False
                        if not permitted:
                            continue
                    if row['oracle_id'] in dismissed:
                        continue
                    row['entry'] = DeckEntry.from_dict(row['entry'])
                    if not in_card_pool(row['entry'].extras.get('facts') or {}, document):
                        continue
                    if not theme_matches(row, theme):
                        continue
                    present = bool(in_deck_entries(document, [row['entry']]))
                    if membership and present != (membership == 2):
                        continue
                    if rows and row.get('fallback') and not rows[0].get('fallback'):
                        break
                    rows.append(row)
                    if len(rows) > limit:
                        break
            except sqlite3.OperationalError:
                check_cancelled(should_cancel)
                raise
        check_cancelled(should_cancel)
        result = rows[:limit], len(rows) > limit
        if limit <= 500:
            self.cache[key] = deepcopy(result)
            while len(self.cache) > 12:
                self.cache.popitem(last=False)
        return result
