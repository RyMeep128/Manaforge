"""Shared artwork favorites and preference profiles."""
from __future__ import annotations

import json
import time


class PreferenceOperations:
    def set_artwork_favorite(self, oracle_id: str, card_id: str | None) -> None:
        with self.connect() as connection:
            if card_id is None:
                connection.execute(
                    'DELETE FROM artwork_favorites WHERE oracle_id = ?',
                    (oracle_id,))
                return
            connection.execute(
                """INSERT INTO artwork_favorites (oracle_id, card_id, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(oracle_id) DO UPDATE SET
                     card_id=excluded.card_id, updated_at=excluded.updated_at""",
                (oracle_id, card_id, time.time()))

    def get_artwork_favorite(self, oracle_id: str) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                'SELECT card_id FROM artwork_favorites WHERE oracle_id = ?',
                (oracle_id,)).fetchone()
        return None if row is None else str(row['card_id'])

    def set_artwork_preference_profile(self, payload: dict,
                                       profile_key: str = 'default') -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO artwork_preference_profiles
                     (profile_key, payload_json, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(profile_key) DO UPDATE SET
                     payload_json=excluded.payload_json,
                     updated_at=excluded.updated_at""",
                (profile_key, json.dumps(payload, ensure_ascii=False,
                                         sort_keys=True), time.time()))

    def get_artwork_preference_profile(
            self, profile_key: str = 'default') -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT payload_json FROM artwork_preference_profiles
                   WHERE profile_key = ?""", (profile_key,)).fetchone()
        if row is None:
            return None
        try:
            value = json.loads(row['payload_json'])
        except (TypeError, ValueError):
            return None
        return value if isinstance(value, dict) else None
