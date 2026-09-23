"""Schema creation and compatibility checks."""
from __future__ import annotations

import sqlite3


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

CREATE TABLE IF NOT EXISTS artwork_favorites (
    oracle_id TEXT PRIMARY KEY,
    card_id TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS artwork_preference_profiles (
    profile_key TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""

class SchemaOperations:
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
