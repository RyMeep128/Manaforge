from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path

from mtg_core.models import ImageAssetRecord, ImageRecord, PrintRecord
from mtg_core.paths import core_data_root
from mtg_core.search import choose_canonical_print_key, normalized_search_text
from mtg_core.search.syntax import compile_query, text_expression
from mtg_core.sync import extract_image_urls


SCHEMA = """
CREATE TABLE IF NOT EXISTS cards_oracle (
    oracle_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    layout TEXT
);

CREATE TABLE IF NOT EXISTS prints (
    card_id TEXT PRIMARY KEY,
    oracle_id TEXT NOT NULL,
    name TEXT NOT NULL,
    set_code TEXT,
    set_name TEXT,
    collector_number TEXT,
    released_at TEXT,
    image_url TEXT,
    thumbnail_url TEXT,
    preview_url TEXT,
    is_double_faced INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL,
    updated_at REAL NOT NULL,
    cache_scope TEXT,
    cache_expires_at REAL,
    FOREIGN KEY (oracle_id) REFERENCES cards_oracle(oracle_id)
);

CREATE INDEX IF NOT EXISTS idx_prints_oracle_id ON prints(oracle_id);
CREATE INDEX IF NOT EXISTS idx_prints_name ON prints(name);
CREATE INDEX IF NOT EXISTS idx_prints_lower_name_updated ON prints(lower(name), updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_prints_set_collector_updated ON prints(lower(coalesce(set_code, '')), collector_number, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_prints_oracle_order ON prints(oracle_id, released_at, set_code, collector_number);
CREATE INDEX IF NOT EXISTS idx_prints_admin_order ON prints(name, released_at, set_code, collector_number, card_id);
CREATE INDEX IF NOT EXISTS idx_prints_online_cache ON prints(cache_scope, cache_expires_at);
CREATE INDEX IF NOT EXISTS idx_cards_oracle_name_order ON cards_oracle(name, oracle_id);

CREATE TABLE IF NOT EXISTS print_search_data (
    card_id TEXT PRIMARY KEY,
    search_json TEXT NOT NULL,
    FOREIGN KEY (card_id) REFERENCES prints(card_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS oracle_tags (
    oracle_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (oracle_id, tag)
);
CREATE INDEX IF NOT EXISTS idx_oracle_tags_tag ON oracle_tags(tag, oracle_id);

CREATE TABLE IF NOT EXISTS canonical_prints (
    oracle_id TEXT PRIMARY KEY,
    card_id TEXT NOT NULL,
    chosen_at REAL NOT NULL,
    FOREIGN KEY (oracle_id) REFERENCES cards_oracle(oracle_id),
    FOREIGN KEY (card_id) REFERENCES prints(card_id)
);

CREATE TABLE IF NOT EXISTS image_manifest (
    card_id TEXT NOT NULL,
    variant TEXT NOT NULL DEFAULT 'default',
    asset_id TEXT,
    path TEXT,
    status TEXT NOT NULL,
    source TEXT,
    checksum TEXT,
    updated_at REAL NOT NULL,
    PRIMARY KEY (card_id, variant),
    FOREIGN KEY (card_id) REFERENCES prints(card_id)
);

CREATE TABLE IF NOT EXISTS image_assets (
    asset_id TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    extension TEXT,
    mime_type TEXT,
    source TEXT,
    source_url TEXT,
    payload BLOB NOT NULL,
    payload_size INTEGER,
    storage_path TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_image_assets_checksum ON image_assets(checksum);
CREATE INDEX IF NOT EXISTS idx_image_assets_updated_asset ON image_assets(updated_at DESC, asset_id);

CREATE TABLE IF NOT EXISTS sync_state (
    source TEXT PRIMARY KEY,
    version TEXT,
    last_sync_at REAL,
    payload_json TEXT
);
"""


def default_db_path() -> str:
    return str(core_data_root() / "card_data.sqlite3")


class CardDatabase:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or default_db_path()
        if self.db_path != ":memory:":
            parent = os.path.dirname(self.db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def _ensure_schema(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._ensure_column(connection, "image_manifest", "asset_id", "TEXT")
            self._ensure_column(connection, "prints", "cache_scope", "TEXT")
            self._ensure_column(connection, "prints", "cache_expires_at", "REAL")
            self._ensure_column(connection, "image_assets", "payload_size", "INTEGER")
            self._ensure_column(connection, "image_assets", "storage_path", "TEXT")
            self._ensure_search_index(connection)
            self._ensure_search_data(connection)

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_type: str,
    ) -> None:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        if any(row["name"] == column_name for row in rows):
            return
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

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

    def upsert_card_payload(
        self,
        card_payload: dict,
        *,
        source: str = "remote_fill",
        cache_scope: str | None = None,
        cache_expires_at: float | None = None,
    ) -> PrintRecord:
        payload = dict(card_payload)
        name = str(payload.get("name") or "")
        if not name:
            raise ValueError("Card payload is missing a name.")

        oracle_id = str(payload.get("oracle_id") or "").strip()
        card_id = str(payload.get("id") or "").strip()
        set_code = str(payload.get("set") or "").strip().lower() or None
        collector_number = str(payload.get("collector_number") or "").strip() or None

        # Some tests and offline/manual payloads omit Scryfall ids. Generate stable
        # synthetic ids so the proxy app can still cache/search/print consistently.
        if not oracle_id:
            oracle_id = _synthesize_oracle_id(name)
        if not card_id:
            card_id = _synthesize_print_id(name, set_code, collector_number)

        payload["oracle_id"] = oracle_id
        payload["id"] = card_id

        normalized_name = normalized_search_text(name)
        image_url, thumbnail_url, preview_url = extract_image_urls(payload)
        now = time.time()

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO cards_oracle (oracle_id, name, normalized_name, layout)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(oracle_id) DO UPDATE SET
                    name=excluded.name,
                    normalized_name=excluded.normalized_name,
                    layout=excluded.layout
                """,
                (
                    oracle_id,
                    name,
                    normalized_name,
                    payload.get("layout"),
                ),
            )
            connection.execute(
                """
                INSERT INTO prints (
                    card_id, oracle_id, name, set_code, set_name, collector_number,
                    released_at, image_url, thumbnail_url, preview_url,
                    is_double_faced, payload_json, updated_at, cache_scope, cache_expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(card_id) DO UPDATE SET
                    oracle_id=excluded.oracle_id,
                    name=excluded.name,
                    set_code=excluded.set_code,
                    set_name=excluded.set_name,
                    collector_number=excluded.collector_number,
                    released_at=excluded.released_at,
                    image_url=excluded.image_url,
                    thumbnail_url=excluded.thumbnail_url,
                    preview_url=excluded.preview_url,
                    is_double_faced=excluded.is_double_faced,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at,
                    cache_scope=excluded.cache_scope,
                    cache_expires_at=excluded.cache_expires_at
                """,
                (
                    card_id,
                    oracle_id,
                    name,
                    set_code,
                    payload.get("set_name"),
                    collector_number,
                    payload.get("released_at"),
                    image_url,
                    thumbnail_url,
                    preview_url,
                    1 if payload.get("card_faces") else 0,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    now,
                    cache_scope,
                    cache_expires_at,
                ),
            )
            self._refresh_canonical_print(connection, oracle_id)
            connection.execute(
                """
                INSERT INTO sync_state (source, version, last_sync_at, payload_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    version=excluded.version,
                    last_sync_at=excluded.last_sync_at,
                    payload_json=excluded.payload_json
                """,
                (source, None, now, json.dumps({"last_card_id": card_id})),
            )
            self.refresh_search_index_for_print(connection, card_id)
            self.refresh_search_data_for_print(connection, card_id, payload)
            row = connection.execute(
                "SELECT * FROM prints WHERE card_id = ?",
                (card_id,),
            ).fetchone()
        return self._row_to_print_record(row)

    @staticmethod
    def refresh_search_data_for_print(connection, card_id, payload):
        connection.execute(
            'INSERT INTO print_search_data (card_id, search_json) VALUES (?, ?) '
            'ON CONFLICT(card_id) DO UPDATE SET search_json=excluded.search_json',
            (card_id, _compact_search_json(payload)))

    def _refresh_canonical_print(self, connection: sqlite3.Connection, oracle_id: str) -> None:
        rows = connection.execute(
            "SELECT payload_json FROM prints WHERE oracle_id = ?",
            (oracle_id,),
        ).fetchall()
        if not rows:
            return
        payloads = [json.loads(row["payload_json"]) for row in rows]
        payload = min(payloads, key=choose_canonical_print_key)
        connection.execute(
            """
            INSERT INTO canonical_prints (oracle_id, card_id, chosen_at)
            VALUES (?, ?, ?)
            ON CONFLICT(oracle_id) DO UPDATE SET
                card_id=excluded.card_id,
                chosen_at=excluded.chosen_at
            """,
            (oracle_id, str(payload.get("id")), time.time()),
        )

    def get_print_by_card_id(self, card_id: str) -> PrintRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM prints WHERE card_id = ?",
                (card_id,),
            ).fetchone()
        return self._row_to_print_record(row)

    def get_print_by_set_and_number(self, set_code: str, collector_number: str) -> PrintRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM prints
                WHERE lower(coalesce(set_code, '')) = lower(?)
                  AND collector_number = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (set_code, collector_number),
            ).fetchone()
        return self._row_to_print_record(row)

    def get_named_print(self, exact_name: str) -> PrintRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM prints
                WHERE lower(name) = lower(?)
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (exact_name,),
            ).fetchone()
        return self._row_to_print_record(row)

    def get_prints_for_oracle(self, oracle_id: str) -> list[PrintRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM prints WHERE oracle_id = ? ORDER BY released_at, set_code, collector_number",
                (oracle_id,),
            ).fetchall()
        return [self._row_to_print_record(row) for row in rows]

    def get_canonical_print(self, oracle_id: str) -> PrintRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT p.*
                FROM canonical_prints c
                JOIN prints p ON p.card_id = c.card_id
                WHERE c.oracle_id = ?
                """,
                (oracle_id,),
            ).fetchone()
        return self._row_to_print_record(row)

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
        return [self._row_to_print_record(row) for row in rows]

    def search_syntax(self, query: str, limit: int = 200, *, set_filter: str = '',
                      online_mode: bool = False) -> list[PrintRecord]:
        predicate, params = compile_query(query)
        if online_mode:
            predicate += " AND p.cache_scope = 'online_search' AND coalesce(p.cache_expires_at, 0) > ?"
            params.append(time.time())
        else:
            predicate += " AND coalesce(p.cache_scope, '') != 'online_search'"
        if set_filter:
            predicate += " AND (lower(p.set_code) = ? OR instr(lower(coalesce(p.set_name, '')), ?) > 0)"
            params.extend([set_filter.lower(), set_filter.lower()])
        with self.connect() as connection:
            rows = connection.execute(
                'WITH matches AS ('
                'SELECT p.*, ROW_NUMBER() OVER (PARTITION BY p.oracle_id ORDER BY '
                'CASE WHEN cp.card_id = p.card_id THEN 0 ELSE 1 END, '
                'p.released_at DESC, p.card_id) AS search_rank '
                'FROM prints p JOIN print_search_data s ON s.card_id = p.card_id '
                'LEFT JOIN canonical_prints cp ON cp.oracle_id = p.oracle_id '
                f'WHERE {predicate}) '
                'SELECT * FROM matches WHERE search_rank = 1 '
                'ORDER BY name COLLATE NOCASE, released_at, card_id LIMIT ?',
                [*params, max(1, min(10000, int(limit)))]).fetchall()
        return [self._row_to_print_record(row) for row in rows]

    def replace_oracle_tags(self, tag_records) -> int:
        tag_records = list(tag_records)
        records_by_id = {
            str(record.get('id')): record for record in tag_records if record.get('id')
        }
        def record_oracle_ids(record):
            oracle_ids = set(str(value) for value in record.get('oracle_ids') or [] if value)
            oracle_ids.update(
                str(tagging.get('oracle_id')) for tagging in record.get('taggings') or []
                if isinstance(tagging, dict) and tagging.get('oracle_id')
            )
            return oracle_ids

        direct_oracle_ids = {}
        for record in tag_records:
            oracle_ids = record_oracle_ids(record)
            direct_oracle_ids[str(record.get('id') or '')] = oracle_ids

        descendant_cache = {}
        def oracle_ids_with_descendants(record_id, visiting=None):
            if record_id in descendant_cache:
                return descendant_cache[record_id]
            visiting = set() if visiting is None else visiting
            if record_id in visiting:
                return set()
            visiting.add(record_id)
            result = set(direct_oracle_ids.get(record_id, ()))
            record = records_by_id.get(record_id, {})
            for child_id in record.get('child_ids') or []:
                result.update(oracle_ids_with_descendants(str(child_id), visiting))
            visiting.remove(record_id)
            descendant_cache[record_id] = result
            return result

        rows = []
        for record in tag_records:
            tag_names = {
                str(value or '').strip().casefold()
                for value in [record.get('label'), record.get('slug'), *(record.get('aliases') or [])]
                if str(value or '').strip()
            }
            if not tag_names:
                continue
            record_id = str(record.get('id') or '')
            oracle_ids = oracle_ids_with_descendants(record_id) if record_id else record_oracle_ids(record)
            for oracle_id in oracle_ids:
                oracle_id = str(oracle_id or '').strip()
                if oracle_id:
                    rows.extend((oracle_id, tag) for tag in tag_names)
        with self.connect() as connection:
            connection.execute('DELETE FROM oracle_tags')
            connection.executemany(
                'INSERT OR IGNORE INTO oracle_tags (oracle_id, tag) VALUES (?, ?)', rows)
        return len(rows)

    def oracle_tag_count(self) -> int:
        with self.connect() as connection:
            row = connection.execute('SELECT count(*) FROM oracle_tags').fetchone()
        return int(row[0] or 0)

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

    def upsert_image_record(
        self,
        card_id: str,
        *,
        variant: str = "default",
        asset_id: str | None = None,
        path: str | None,
        status: str,
        source: str | None = None,
        checksum: str | None = None,
    ) -> ImageRecord:
        updated_at = time.time()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO image_manifest (card_id, variant, asset_id, path, status, source, checksum, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(card_id, variant) DO UPDATE SET
                    asset_id=excluded.asset_id,
                    path=excluded.path,
                    status=excluded.status,
                    source=excluded.source,
                    checksum=excluded.checksum,
                    updated_at=excluded.updated_at
                """,
                (card_id, variant, asset_id, path, status, source, checksum, updated_at),
            )
        return ImageRecord(
            card_id=card_id,
            variant=variant,
            asset_id=asset_id,
            path=path,
            status=status,
            source=source,
            checksum=checksum,
            updated_at=updated_at,
        )

    def get_image_record(self, card_id: str, variant: str = "default") -> ImageRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT card_id, variant, asset_id, path, status, source, checksum, updated_at
                FROM image_manifest
                WHERE card_id = ? AND variant = ?
                """,
                (card_id, variant),
            ).fetchone()
        if row is None:
            return None
        return ImageRecord(
            card_id=row["card_id"],
            variant=row["variant"],
            asset_id=row["asset_id"],
            path=row["path"],
            status=row["status"],
            source=row["source"],
            checksum=row["checksum"],
            updated_at=row["updated_at"],
        )

    def get_image_records_for_cards(self, card_ids) -> dict[tuple[str, str], ImageRecord]:
        card_ids = list(dict.fromkeys(str(card_id) for card_id in card_ids if card_id))
        if not card_ids:
            return {}
        placeholders = ','.join('?' for _ in card_ids)
        with self.connect() as connection:
            rows = connection.execute(
                f'SELECT card_id, variant, asset_id, path, status, source, checksum, updated_at '
                f'FROM image_manifest WHERE card_id IN ({placeholders}) AND variant IN (\'default\', \'back\')',
                card_ids).fetchall()
        return {(row['card_id'], row['variant']): ImageRecord(
            card_id=row['card_id'], variant=row['variant'], asset_id=row['asset_id'],
            path=row['path'], status=row['status'], source=row['source'],
            checksum=row['checksum'], updated_at=row['updated_at']) for row in rows}

    def _image_asset_base_dir(self) -> Path:
        if self.db_path == ":memory:":
            return core_data_root()
        return Path(self.db_path).expanduser().resolve().parent

    def _image_asset_storage_root(self) -> Path:
        return self._image_asset_base_dir() / "images" / "assets"

    @staticmethod
    def _safe_asset_extension(extension: str | None) -> str:
        safe = re.sub(r"[^A-Za-z0-9]+", "", (extension or "").lstrip("."))
        return safe.lower() or "bin"

    def _image_asset_path(self, asset_id: str, checksum: str, extension: str | None) -> Path:
        filename = f"{asset_id}.{self._safe_asset_extension(extension)}"
        return self._image_asset_storage_root() / checksum[:2] / filename

    def _image_asset_storage_reference(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self._image_asset_base_dir()))
        except ValueError:
            return str(path.resolve())

    def _resolve_image_asset_storage_path(self, storage_path: str | None) -> Path | None:
        if not storage_path:
            return None
        path = Path(storage_path)
        if path.is_absolute():
            return path
        return self._image_asset_base_dir() / path

    @staticmethod
    def _row_blob(row: sqlite3.Row, column_name: str = "payload") -> bytes:
        value = row[column_name]
        if value is None:
            return b""
        return bytes(value)

    @staticmethod
    def _write_verified_image_asset_file(path: Path, payload: bytes, checksum: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f"{path.name}.tmp")
        with open(temp_path, "wb") as handle:
            handle.write(payload)
        with open(temp_path, "rb") as handle:
            written_checksum = hashlib.sha256(handle.read()).hexdigest()
        if written_checksum != checksum:
            try:
                temp_path.unlink()
            except OSError:
                pass
            raise OSError("Stored image asset checksum verification failed.")
        os.replace(temp_path, path)

    @staticmethod
    def _read_verified_image_asset_file(path: Path, checksum: str) -> bytes | None:
        try:
            with open(path, "rb") as handle:
                payload = handle.read()
        except OSError:
            return None
        if hashlib.sha256(payload).hexdigest() != checksum:
            return None
        return payload

    def _row_to_image_asset_record(
        self,
        row: sqlite3.Row,
        *,
        payload_override: bytes | None = None,
        payload_size_override: int | None = None,
    ) -> ImageAssetRecord:
        payload = self._row_blob(row) if payload_override is None else payload_override
        payload_size = row["payload_size"]
        if payload_size_override is not None:
            payload_size = payload_size_override
        if payload_size is None:
            payload_size = len(payload)
        return ImageAssetRecord(
            asset_id=row["asset_id"],
            checksum=row["checksum"],
            extension=row["extension"],
            mime_type=row["mime_type"],
            source=row["source"],
            source_url=row["source_url"],
            payload=payload,
            payload_size=int(payload_size or 0),
            storage_path=row["storage_path"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def store_image_asset(
        self,
        payload: bytes,
        *,
        extension: str | None = "png",
        mime_type: str | None = None,
        source: str | None = None,
        source_url: str | None = None,
    ) -> ImageAssetRecord:
        checksum = hashlib.sha256(payload).hexdigest()
        now = time.time()
        asset_id = f"img-{checksum[:20]}"
        asset_path = self._image_asset_path(asset_id, checksum, extension)
        self._write_verified_image_asset_file(asset_path, payload, checksum)
        storage_path = self._image_asset_storage_reference(asset_path)
        with self.connect() as connection:
            existing = connection.execute(
                """
                SELECT
                    asset_id, checksum, extension, mime_type, source, source_url,
                    payload, payload_size, storage_path, created_at, updated_at
                FROM image_assets
                WHERE checksum = ?
                """,
                (checksum,),
            ).fetchone()
            if existing is not None:
                existing_asset_path = self._image_asset_path(
                    existing["asset_id"],
                    checksum,
                    extension or existing["extension"],
                )
                if existing_asset_path != asset_path:
                    self._write_verified_image_asset_file(existing_asset_path, payload, checksum)
                    storage_path = self._image_asset_storage_reference(existing_asset_path)
                connection.execute(
                    """
                    UPDATE image_assets
                    SET extension = coalesce(?, extension),
                        mime_type = coalesce(?, mime_type),
                        source = coalesce(?, source),
                        source_url = coalesce(?, source_url),
                        payload = ?,
                        payload_size = ?,
                        storage_path = ?,
                        updated_at = ?
                    WHERE asset_id = ?
                    """,
                    (
                        extension,
                        mime_type,
                        source,
                        source_url,
                        b"",
                        len(payload),
                        storage_path,
                        now,
                        existing["asset_id"],
                    ),
                )
                row = connection.execute(
                    """
                    SELECT
                        asset_id, checksum, extension, mime_type, source, source_url,
                        payload, payload_size, storage_path, created_at, updated_at
                    FROM image_assets
                    WHERE asset_id = ?
                    """,
                    (existing["asset_id"],),
                ).fetchone()
                return self._row_to_image_asset_record(row, payload_override=payload)

            connection.execute(
                """
                INSERT INTO image_assets (
                    asset_id, checksum, extension, mime_type, source, source_url,
                    payload, payload_size, storage_path, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    checksum,
                    extension,
                    mime_type,
                    source,
                    source_url,
                    b"",
                    len(payload),
                    storage_path,
                    now,
                    now,
                ),
            )
            return ImageAssetRecord(
                asset_id=asset_id,
                checksum=checksum,
                extension=extension,
                mime_type=mime_type,
                source=source,
                source_url=source_url,
                payload=bytes(payload),
                payload_size=len(payload),
                storage_path=storage_path,
                created_at=now,
                updated_at=now,
            )

    def get_image_asset(self, asset_id: str) -> ImageAssetRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    asset_id, checksum, extension, mime_type, source, source_url,
                    payload, payload_size, storage_path, created_at, updated_at
                FROM image_assets
                WHERE asset_id = ?
                """,
                (asset_id,),
            ).fetchone()
        if row is None:
            return None
        payload = None
        path = self._resolve_image_asset_storage_path(row["storage_path"])
        if path is not None:
            payload = self._read_verified_image_asset_file(path, row["checksum"])
        if payload is None:
            blob = self._row_blob(row)
            payload = blob if blob else b""
        return self._row_to_image_asset_record(row, payload_override=payload)

    def get_sync_state(self, source: str) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT source, version, last_sync_at, payload_json
                FROM sync_state
                WHERE source = ?
                """,
                (source,),
            ).fetchone()

    def upsert_sync_state(
        self,
        source: str,
        *,
        version: str | None = None,
        last_sync_at: float | None = None,
        payload: dict | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO sync_state (source, version, last_sync_at, payload_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    version=excluded.version,
                    last_sync_at=excluded.last_sync_at,
                    payload_json=excluded.payload_json
                """,
                (
                    source,
                    version,
                    last_sync_at,
                    None if payload is None else json.dumps(payload, ensure_ascii=False, sort_keys=True),
                ),
            )

    @staticmethod
    def _row_to_print_record(row: sqlite3.Row | None) -> PrintRecord | None:
        if row is None:
            return None
        return PrintRecord(
            card_id=row["card_id"],
            oracle_id=row["oracle_id"],
            name=row["name"],
            set_code=row["set_code"],
            set_name=row["set_name"],
            collector_number=row["collector_number"],
            released_at=row["released_at"],
            image_url=row["image_url"],
            thumbnail_url=row["thumbnail_url"],
            preview_url=row["preview_url"],
            is_double_faced=bool(row["is_double_faced"]),
            payload=json.loads(row["payload_json"]),
        )


def _synthesize_oracle_id(name: str) -> str:
    normalized = normalized_search_text(name) or "card"
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    return f"proxy-oracle-{digest}"


def _synthesize_print_id(name: str, set_code: str | None, collector_number: str | None) -> str:
    normalized = "|".join(
        [
            normalized_search_text(name) or "card",
            set_code or "unknown",
            collector_number or "0",
        ]
    )
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    return f"proxy-print-{digest}"


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
