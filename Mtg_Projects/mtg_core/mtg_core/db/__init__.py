from __future__ import annotations

import json
import os
import sqlite3
import time

from mtg_core.models import ImageRecord, PrintRecord
from mtg_core.paths import core_root
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
    path TEXT,
    status TEXT NOT NULL,
    source TEXT,
    checksum TEXT,
    updated_at REAL NOT NULL,
    PRIMARY KEY (card_id, variant),
    FOREIGN KEY (card_id) REFERENCES prints(card_id)
);

CREATE TABLE IF NOT EXISTS sync_state (
    source TEXT PRIMARY KEY,
    version TEXT,
    last_sync_at REAL,
    payload_json TEXT
);
"""


def default_db_path() -> str:
    return str(core_root() / "card_data.sqlite3")


class CardDatabase:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or default_db_path()
        if self.db_path != ":memory:":
            parent = os.path.dirname(self.db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def upsert_card_payload(self, card_payload: dict, *, source: str = "remote_fill") -> PrintRecord:
        oracle_id = str(card_payload.get("oracle_id") or card_payload.get("id") or "")
        card_id = str(card_payload.get("id") or "")
        if not oracle_id or not card_id:
            raise ValueError("Card payload is missing oracle or card identity.")

        name = str(card_payload.get("name") or "")
        if not name:
            raise ValueError("Card payload is missing a name.")

        normalized_name = normalized_search_text(name)
        image_url, thumbnail_url, preview_url = extract_image_urls(card_payload)
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
                    card_payload.get("layout"),
                ),
            )
            connection.execute(
                """
                INSERT INTO prints (
                    card_id, oracle_id, name, set_code, set_name, collector_number,
                    released_at, image_url, thumbnail_url, preview_url,
                    is_double_faced, payload_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    updated_at=excluded.updated_at
                """,
                (
                    card_id,
                    oracle_id,
                    name,
                    card_payload.get("set"),
                    card_payload.get("set_name"),
                    str(card_payload.get("collector_number") or "") or None,
                    card_payload.get("released_at"),
                    image_url,
                    thumbnail_url,
                    preview_url,
                    1 if card_payload.get("card_faces") else 0,
                    json.dumps(card_payload, ensure_ascii=False, sort_keys=True),
                    now,
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

    def search_prints(self, query: str, limit: int = 60) -> list[PrintRecord]:
        normalized = normalized_search_text(query)
        like = f"%{normalized}%"
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT p.*
                FROM prints p
                JOIN cards_oracle c ON c.oracle_id = p.oracle_id
                WHERE c.normalized_name LIKE ? OR lower(p.name) LIKE lower(?)
                ORDER BY p.name, p.released_at, p.set_code, p.collector_number
                LIMIT ?
                """,
                (like, like, max(1, int(limit))),
            ).fetchall()
        return [self._row_to_print_record(row) for row in rows]

    def upsert_image_record(
        self,
        card_id: str,
        *,
        variant: str = "default",
        path: str | None,
        status: str,
        source: str | None = None,
        checksum: str | None = None,
    ) -> ImageRecord:
        updated_at = time.time()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO image_manifest (card_id, variant, path, status, source, checksum, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(card_id, variant) DO UPDATE SET
                    path=excluded.path,
                    status=excluded.status,
                    source=excluded.source,
                    checksum=excluded.checksum,
                    updated_at=excluded.updated_at
                """,
                (card_id, variant, path, status, source, checksum, updated_at),
            )
        return ImageRecord(
            card_id=card_id,
            variant=variant,
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
                SELECT card_id, variant, path, status, source, checksum, updated_at
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
            path=row["path"],
            status=row["status"],
            source=row["source"],
            checksum=row["checksum"],
            updated_at=row["updated_at"],
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
