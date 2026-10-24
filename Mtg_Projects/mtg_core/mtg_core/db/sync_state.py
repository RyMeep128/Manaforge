"""Persistent catalog synchronization checkpoints."""
from __future__ import annotations

import json
import sqlite3


class SyncStateOperations:
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
