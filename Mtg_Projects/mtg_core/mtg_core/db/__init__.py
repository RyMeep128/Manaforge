from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time

from mtg_core.models import ImageAssetRecord, ImageRecord, PrintRecord
from mtg_core.paths import core_data_root
from mtg_core.search import choose_canonical_print_key, normalized_search_text
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
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_image_assets_checksum ON image_assets(checksum);

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
            row = connection.execute(
                "SELECT * FROM prints WHERE card_id = ?",
                (card_id,),
            ).fetchone()
        return self._row_to_print_record(row)

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
                  AND coalesce(collector_number, '') = ?
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
        params = [like, like, like]
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
            rows = connection.execute(
                f"""
                SELECT p.*
                FROM prints p
                JOIN cards_oracle c ON c.oracle_id = p.oracle_id
                WHERE (
                    c.normalized_name LIKE ?
                    OR lower(p.name) LIKE lower(?)
                    OR lower(coalesce(json_extract(p.payload_json, '$.type_line'), '')) LIKE lower(?)
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
        with self.connect() as connection:
            existing = connection.execute(
                """
                SELECT asset_id, checksum, extension, mime_type, source, source_url, payload, created_at, updated_at
                FROM image_assets
                WHERE checksum = ?
                """,
                (checksum,),
            ).fetchone()
            if existing is not None:
                connection.execute(
                    """
                    UPDATE image_assets
                    SET extension = coalesce(?, extension),
                        mime_type = coalesce(?, mime_type),
                        source = coalesce(?, source),
                        source_url = coalesce(?, source_url),
                        updated_at = ?
                    WHERE asset_id = ?
                    """,
                    (
                        extension,
                        mime_type,
                        source,
                        source_url,
                        now,
                        existing["asset_id"],
                    ),
                )
                return ImageAssetRecord(
                    asset_id=existing["asset_id"],
                    checksum=existing["checksum"],
                    extension=extension or existing["extension"],
                    mime_type=mime_type or existing["mime_type"],
                    source=source or existing["source"],
                    source_url=source_url or existing["source_url"],
                    payload=bytes(existing["payload"]),
                    payload_size=len(bytes(existing["payload"])),
                    created_at=existing["created_at"],
                    updated_at=now,
                )

            asset_id = f"img-{checksum[:20]}"
            connection.execute(
                """
                INSERT INTO image_assets (
                    asset_id, checksum, extension, mime_type, source, source_url, payload, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (asset_id, checksum, extension, mime_type, source, source_url, payload, now, now),
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
                created_at=now,
                updated_at=now,
            )

    def get_image_asset(self, asset_id: str) -> ImageAssetRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT asset_id, checksum, extension, mime_type, source, source_url, payload, created_at, updated_at
                FROM image_assets
                WHERE asset_id = ?
                """,
                (asset_id,),
            ).fetchone()
        if row is None:
            return None
        return ImageAssetRecord(
            asset_id=row["asset_id"],
            checksum=row["checksum"],
            extension=row["extension"],
            mime_type=row["mime_type"],
            source=row["source"],
            source_url=row["source_url"],
            payload=bytes(row["payload"]),
            payload_size=len(bytes(row["payload"])),
            created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

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
