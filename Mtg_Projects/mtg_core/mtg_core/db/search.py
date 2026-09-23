"""Local queries and their full-text/structured search indexes."""
from __future__ import annotations

import json
import re
import sqlite3
import time
from mtg_core.models import PrintRecord
from mtg_core.search import normalized_search_text
from mtg_core.search.syntax import compile_query, text_expression
from mtg_core.search.cancellation import search_connection


class SearchOperations:
    def _ensure_search_index(self, connection: sqlite3.Connection) -> None:
        try:
            columns = connection.execute('PRAGMA table_info(print_search_fts)').fetchall()
            if columns and 'oracle_text' not in {row['name'] for row in columns}:
                connection.execute('DROP TABLE print_search_fts')
            connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS print_search_fts USING fts5(
                    card_id UNINDEXED,
                    name,
                    normalized_name,
                    type_line,
                    oracle_text,
                    layout,
                    set_code,
                    collector_number,
                    cache_scope UNINDEXED,
                    cache_expires_at UNINDEXED
                )
                """
            )
            print_count = connection.execute("SELECT count(*) FROM prints").fetchone()[0]
            fts_count = connection.execute("SELECT count(*) FROM print_search_fts").fetchone()[0]
            if int(print_count or 0) != int(fts_count or 0):
                self.rebuild_search_index(connection)
        except sqlite3.DatabaseError:
            # FTS is an optimization. The regular LIKE search remains the fallback.
            return

    def _ensure_search_data(self, connection: sqlite3.Connection) -> None:
        print_count = int(connection.execute('SELECT count(*) FROM prints').fetchone()[0] or 0)
        search_count = int(connection.execute('SELECT count(*) FROM print_search_data').fetchone()[0] or 0)
        sample = connection.execute('SELECT search_json FROM print_search_data LIMIT 1').fetchone()
        current_format = sample is None or 'oracle_text_search' in json.loads(sample['search_json'])
        if print_count == search_count and current_format:
            return
        connection.execute('DELETE FROM print_search_data')
        rows = connection.execute('SELECT card_id, payload_json FROM prints').fetchall()
        connection.executemany(
            'INSERT INTO print_search_data (card_id, search_json) VALUES (?, ?)',
            ((row['card_id'], _compact_search_json(json.loads(row['payload_json']))) for row in rows))

    def rebuild_search_index(self, connection: sqlite3.Connection | None = None) -> None:
        owns_connection = connection is None
        if connection is None:
            connection = self.connect()
        try:
            connection.execute("DELETE FROM print_search_fts")
            connection.execute(
                """
                INSERT INTO print_search_fts (
                    card_id, name, normalized_name, type_line, oracle_text, layout,
                    set_code, collector_number, cache_scope, cache_expires_at
                )
                SELECT
                    p.card_id,
                    p.name,
                    c.normalized_name,
                    coalesce(json_extract(p.payload_json, '$.type_line'), ''),
                    coalesce(json_extract(p.payload_json, '$.oracle_text'), '') || ' ' ||
                    coalesce((SELECT group_concat(json_extract(face.value, '$.oracle_text'), ' ')
                              FROM json_each(p.payload_json, '$.card_faces') face), ''),
                    coalesce(json_extract(p.payload_json, '$.layout'), ''),
                    coalesce(p.set_code, ''),
                    coalesce(p.collector_number, ''),
                    coalesce(p.cache_scope, ''),
                    coalesce(p.cache_expires_at, '')
                FROM prints p
                JOIN cards_oracle c ON c.oracle_id = p.oracle_id
                """
            )
            if owns_connection:
                connection.commit()
        finally:
            if owns_connection:
                connection.close()

    def refresh_search_index_for_print(
        self,
        connection: sqlite3.Connection,
        card_id: str,
    ) -> None:
        try:
            connection.execute("DELETE FROM print_search_fts WHERE card_id = ?", (card_id,))
            connection.execute(
                """
                INSERT INTO print_search_fts (
                    card_id, name, normalized_name, type_line, oracle_text, layout,
                    set_code, collector_number, cache_scope, cache_expires_at
                )
                SELECT
                    p.card_id,
                    p.name,
                    c.normalized_name,
                    coalesce(json_extract(p.payload_json, '$.type_line'), ''),
                    coalesce(json_extract(p.payload_json, '$.oracle_text'), '') || ' ' ||
                    coalesce((SELECT group_concat(json_extract(face.value, '$.oracle_text'), ' ')
                              FROM json_each(p.payload_json, '$.card_faces') face), ''),
                    coalesce(json_extract(p.payload_json, '$.layout'), ''),
                    coalesce(p.set_code, ''),
                    coalesce(p.collector_number, ''),
                    coalesce(p.cache_scope, ''),
                    coalesce(p.cache_expires_at, '')
                FROM prints p
                JOIN cards_oracle c ON c.oracle_id = p.oracle_id
                WHERE p.card_id = ?
                """,
                (card_id,),
            )
        except sqlite3.DatabaseError:
            return

    def delete_search_index_for_print(
        self,
        connection: sqlite3.Connection,
        card_id: str,
    ) -> None:
        try:
            connection.execute("DELETE FROM print_search_fts WHERE card_id = ?", (card_id,))
        except sqlite3.DatabaseError:
            return

    def delete_search_data_for_print(
        self,
        connection: sqlite3.Connection,
        card_id: str,
    ) -> None:
        connection.execute("DELETE FROM print_search_data WHERE card_id = ?", (card_id,))

    def refresh_search_index_for_oracle(
        self,
        connection: sqlite3.Connection,
        oracle_id: str,
    ) -> None:
        rows = connection.execute(
            "SELECT card_id FROM prints WHERE oracle_id = ?",
            (oracle_id,),
        ).fetchall()
        for row in rows:
            self.refresh_search_index_for_print(connection, row["card_id"])

    @staticmethod
    def refresh_search_data_for_print(connection, card_id, payload):
        connection.execute(
            'INSERT INTO print_search_data (card_id, search_json) VALUES (?, ?) '
            'ON CONFLICT(card_id) DO UPDATE SET search_json=excluded.search_json',
            (card_id, _compact_search_json(payload)))

    def search_prints(
        self,
        query: str,
        limit: int = 60,
        *,
        token_mode: bool = False,
        online_mode: bool = False,
        cache_ttl_seconds: int | None = None,
    ) -> list[PrintRecord]:
        normalized = normalized_search_text(query)
        like = f"%{normalized}%"
        prefix_like = f"{normalized}%"
        display_trim_chars = "\"'+- "
        cache_clause = (
            "AND p.cache_scope = 'online_search' AND coalesce(p.cache_expires_at, 0) > ?"
            if online_mode
            else "AND coalesce(p.cache_scope, '') != 'online_search'"
        )
        token_clause = """
                    AND (
                        lower(coalesce(json_extract(p.payload_json, '$.layout'), '')) = 'token'
                        OR lower(coalesce(json_extract(p.payload_json, '$.type_line'), '')) LIKE 'token%'
                    )
                """ if token_mode else """
                    AND NOT (
                        lower(coalesce(json_extract(p.payload_json, '$.layout'), '')) = 'token'
                        OR lower(coalesce(json_extract(p.payload_json, '$.type_line'), '')) LIKE 'token%'
                    )
                """
        params = [like, like, like, like]
        if online_mode:
            params.append(time.time())
        params.extend(
            [
                normalized,
                query,
                display_trim_chars,
                prefix_like,
                display_trim_chars,
                prefix_like,
                display_trim_chars,
                max(1, int(limit)),
            ]
        )
        with self.connect() as connection:
            rows = self._search_prints_fts(
                connection,
                normalized=normalized,
                query=query,
                limit=limit,
                token_clause=token_clause,
                cache_clause=cache_clause,
                online_mode=online_mode,
                display_trim_chars=display_trim_chars,
                prefix_like=prefix_like,
            )
            if rows is None:
                rows = connection.execute(
                    f"""
                    SELECT p.*
                    FROM prints p
                    JOIN cards_oracle c ON c.oracle_id = p.oracle_id
                    JOIN print_search_data s ON s.card_id = p.card_id
                    WHERE (
                        c.normalized_name LIKE ?
                        OR lower(p.name) LIKE lower(?)
                        OR lower(coalesce(json_extract(p.payload_json, '$.type_line'), '')) LIKE lower(?)
                        OR lower({text_expression('oracle_text')}) LIKE lower(?)
                    )
                    {token_clause}
                    {cache_clause}
                    ORDER BY
                        CASE
                            WHEN c.normalized_name = ? OR lower(p.name) = lower(?) THEN 0
                            WHEN ltrim(c.normalized_name, ?) LIKE ? OR lower(ltrim(p.name, ?)) LIKE lower(?) THEN 1
                            ELSE 2
                        END,
                        lower(ltrim(p.name, ?)),
                        p.released_at,
                        p.set_code,
                        p.collector_number
                    LIMIT ?
                    """,
                    tuple(params),
                ).fetchall()
        return [self.row_to_print_record(row) for row in rows]

    def _syntax_predicate(self, query, set_filter, online_mode):
        predicate, params = compile_query(query)
        if online_mode:
            predicate += " AND p.cache_scope = 'online_search' AND coalesce(p.cache_expires_at, 0) > ?"
            params.append(time.time())
        if set_filter:
            predicate += " AND (lower(p.set_code) = ? OR instr(lower(coalesce(p.set_name, '')), ?) > 0)"
            params.extend([set_filter.lower(), set_filter.lower()])
        return predicate, params

    def count_syntax(self, query: str, *, set_filter: str = '',
                     online_mode: bool = False) -> int:
        predicate, params = self._syntax_predicate(query, set_filter, online_mode)
        with self.connect() as connection:
            row = connection.execute(
                'SELECT count(DISTINCT p.oracle_id) FROM prints p '
                'JOIN print_search_data s ON s.card_id = p.card_id '
                f'WHERE {predicate}', params).fetchone()
        return int(row[0] or 0)

    def search_syntax(self, query: str, limit: int = 200, *, offset: int = 0,
                      set_filter: str = '', online_mode: bool = False,
                      should_cancel=None) -> list[PrintRecord]:
        predicate, params = self._syntax_predicate(query, set_filter, online_mode)
        with search_connection(self, should_cancel) as connection:
            rows = connection.execute(
                'WITH matches AS ('
                'SELECT p.*, ROW_NUMBER() OVER (PARTITION BY p.oracle_id ORDER BY '
                'CASE WHEN cp.card_id = p.card_id THEN 0 ELSE 1 END, '
                'p.released_at DESC, p.card_id) AS search_rank '
                'FROM prints p JOIN print_search_data s ON s.card_id = p.card_id '
                'LEFT JOIN canonical_prints cp ON cp.oracle_id = p.oracle_id '
                f'WHERE {predicate}) '
                'SELECT * FROM matches WHERE search_rank = 1 '
                'ORDER BY name COLLATE NOCASE, released_at, card_id LIMIT ? OFFSET ?',
                [*params, max(1, min(10000, int(limit))), max(0, int(offset))]).fetchall()
        return [self.row_to_print_record(row) for row in rows]

    def _search_prints_fts(
        self,
        connection: sqlite3.Connection,
        *,
        normalized: str,
        query: str,
        limit: int,
        token_clause: str,
        cache_clause: str,
        online_mode: bool,
        display_trim_chars: str,
        prefix_like: str,
    ) -> list[sqlite3.Row] | None:
        fts_query = _fts_query(normalized)
        if fts_query is None:
            return None

        params: list[object] = [fts_query]
        if online_mode:
            params.append(time.time())
        params.extend(
            [
                normalized,
                query,
                display_trim_chars,
                prefix_like,
                display_trim_chars,
                prefix_like,
                display_trim_chars,
                max(1, int(limit)),
            ]
        )
        try:
            return connection.execute(
                f"""
                SELECT p.*
                FROM print_search_fts f
                JOIN prints p ON p.card_id = f.card_id
                JOIN cards_oracle c ON c.oracle_id = p.oracle_id
                WHERE print_search_fts MATCH ?
                {token_clause}
                {cache_clause}
                ORDER BY
                    CASE
                        WHEN c.normalized_name = ? OR lower(p.name) = lower(?) THEN 0
                        WHEN ltrim(c.normalized_name, ?) LIKE ? OR lower(ltrim(p.name, ?)) LIKE lower(?) THEN 1
                        ELSE 2
                    END,
                    lower(ltrim(p.name, ?)),
                    p.released_at,
                    p.set_code,
                    p.collector_number
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        except sqlite3.DatabaseError:
            return None


_SEARCH_PAYLOAD_FIELDS = (
    'type_line', 'oracle_text', 'flavor_text', 'cmc', 'power', 'toughness',
    'loyalty', 'colors', 'color_identity', 'rarity', 'layout', 'lang',
    'artist', 'legalities', 'keywords', 'games', 'foil', 'digital', 'reserved',
    'reprint', 'promo', 'prices', 'card_faces',
)


def _compact_search_json(payload: dict) -> str:
    compact = {key: payload[key] for key in _SEARCH_PAYLOAD_FIELDS if key in payload}
    compact['oracle_text_search'] = _without_reminder_text(payload.get('oracle_text') or '')
    if isinstance(compact.get('card_faces'), list):
        face_fields = ('name', 'type_line', 'oracle_text', 'flavor_text', 'power',
                       'toughness', 'loyalty', 'colors')
        compact['card_faces'] = [
            ({key: face[key] for key in face_fields if key in face} | {
                'oracle_text_search': _without_reminder_text(face.get('oracle_text') or '')})
            for face in compact['card_faces'] if isinstance(face, dict)
        ]
    return json.dumps(compact, ensure_ascii=False, separators=(',', ':'))


def _without_reminder_text(text: str) -> str:
    """Remove balanced parenthetical reminder text from searchable Oracle text."""
    result = []
    depth = 0
    for character in str(text):
        if character == '(':
            depth += 1
        elif character == ')' and depth:
            depth -= 1
        elif depth == 0:
            result.append(character)
    return ''.join(result)


def _fts_query(normalized: str) -> str | None:
    terms = re.findall(r"[\w]+", normalized or "", flags=re.UNICODE)
    if not terms or any(len(term) < 2 for term in terms):
        return None
    return " ".join(f"{term}*" for term in terms)
