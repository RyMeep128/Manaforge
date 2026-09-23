"""Card identities, print records, tags, and canonical-state maintenance."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from mtg_core.models import CardRecord, PrintRecord
from mtg_core.search import choose_canonical_print_key, normalized_search_text
from mtg_core.search.cancellation import search_connection
from mtg_core.sync import extract_image_urls


class CardOperations:
    def get_oracle_card(self, oracle_id: str) -> CardRecord | None:
        return self._catalog.get_card(oracle_id=oracle_id)

    def create_oracle_card(
        self,
        *,
        oracle_id: str | None,
        name: str,
        normalized_name: str | None = None,
        layout: str | None = None,
    ) -> CardRecord:
        return self._catalog.create_card(oracle_id=oracle_id, name=name, normalized_name=normalized_name, layout=layout)

    def update_oracle_card(
        self,
        oracle_id: str,
        *,
        name: str,
        normalized_name: str | None = None,
        layout: str | None = None,
    ) -> CardRecord:
        return self._catalog.update_card(oracle_id=oracle_id, name=name, normalized_name=normalized_name, layout=layout)

    def delete_oracle_card(self, oracle_id: str) -> bool:
        return self._catalog.delete_card(oracle_id=oracle_id)

    def create_print(
        self,
        *,
        card_id: str | None,
        oracle_id: str,
        name: str,
        set_code: str | None = None,
        set_name: str | None = None,
        collector_number: str | None = None,
        released_at: str | None = None,
        image_url: str | None = None,
        thumbnail_url: str | None = None,
        preview_url: str | None = None,
        is_double_faced: bool = False,
        payload: dict | None = None,
    ) -> PrintRecord:
        return self._catalog.create_print(
            card_id=card_id, oracle_id=oracle_id, name=name, set_code=set_code, set_name=set_name,
            collector_number=collector_number, released_at=released_at, image_url=image_url,
            thumbnail_url=thumbnail_url, preview_url=preview_url, is_double_faced=is_double_faced,
            payload=payload)

    def update_print(
        self,
        card_id: str,
        *,
        oracle_id: str,
        name: str,
        set_code: str | None = None,
        set_name: str | None = None,
        collector_number: str | None = None,
        released_at: str | None = None,
        image_url: str | None = None,
        thumbnail_url: str | None = None,
        preview_url: str | None = None,
        is_double_faced: bool = False,
    ) -> PrintRecord:
        return self._catalog.update_print(
            card_id=card_id, oracle_id=oracle_id, name=name, set_code=set_code, set_name=set_name,
            collector_number=collector_number, released_at=released_at, image_url=image_url,
            thumbnail_url=thumbnail_url, preview_url=preview_url, is_double_faced=is_double_faced)

    def delete_print(self, card_id: str) -> bool:
        return self._catalog.delete_print(card_id=card_id)

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
            previous = connection.execute("SELECT oracle_id FROM prints WHERE card_id = ?", (card_id,)).fetchone()
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
            self.refresh_print_state(connection, card_id,
                previous["oracle_id"] if previous is not None else None)
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
        return self.row_to_print_record(row)

    def refresh_print_state(self, connection, card_id, previous_oracle_id=None):
        """Maintain search and canonical state after a print write in this transaction."""
        row = connection.execute('SELECT oracle_id, payload_json FROM prints WHERE card_id = ?', (card_id,)).fetchone()
        oracle_id = row['oracle_id']
        self.refresh_search_index_for_print(connection, card_id)
        self.refresh_search_data_for_print(connection, card_id, json.loads(row['payload_json']))
        if previous_oracle_id is not None and previous_oracle_id != oracle_id:
            connection.execute('DELETE FROM artwork_favorites WHERE oracle_id = ? AND card_id = ?',
                               (previous_oracle_id, card_id))
            self.refresh_canonical_print(connection, previous_oracle_id)
        self.refresh_canonical_print(connection, oracle_id)

    def refresh_canonical_print(self, connection: sqlite3.Connection, oracle_id: str) -> None:
        """Recompute the canonical mapping in the caller's transaction, or remove it."""
        rows = connection.execute(
            "SELECT payload_json FROM prints WHERE oracle_id = ?",
            (oracle_id,),
        ).fetchall()
        if not rows:
            connection.execute("DELETE FROM canonical_prints WHERE oracle_id = ?", (oracle_id,))
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
        return self.row_to_print_record(row)

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
        return self.row_to_print_record(row)

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
        return self.row_to_print_record(row)

    def get_prints_for_oracle(self, oracle_id: str) -> list[PrintRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM prints WHERE oracle_id = ? ORDER BY released_at, set_code, collector_number",
                (oracle_id,),
            ).fetchall()
        return [self.row_to_print_record(row) for row in rows]

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
        return self.row_to_print_record(row)

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

    def legality_data(self, card_ids):
        """Exact local printing payloads and cache dates for explainable deck checks."""
        values = list(dict.fromkeys(value for value in card_ids if value))
        result = {}
        with self.connect() as connection:
            for offset in range(0, len(values), 400):
                batch = values[offset:offset + 400]
                marks = ','.join('?' for _ in batch)
                rows = connection.execute(
                    f'SELECT card_id, payload_json, updated_at FROM prints WHERE card_id IN ({marks})', batch)
                for row in rows:
                    result[row['card_id']] = {'payload': json.loads(row['payload_json']),
                                               'cached_at': row['updated_at']}
        return result

    def categorization_data(self, card_ids, oracle_ids, *, should_cancel=None):
        """Read local role inputs in bounded batches on a single connection."""
        cards, tags = {}, {}
        with search_connection(self, should_cancel) as connection:
            for column, values in (('card_id', card_ids), ('oracle_id', oracle_ids)):
                if column == 'oracle_id':
                    values = list(values) + [payload.get('oracle_id') for payload in cards.values()]
                values = list(dict.fromkeys(value for value in values if value))
                for offset in range(0, len(values), 400):
                    batch = values[offset:offset + 400]
                    marks = ','.join('?' for _ in batch)
                    if column == 'card_id':
                        rows = connection.execute(f'SELECT card_id, payload_json FROM prints WHERE card_id IN ({marks})', batch)
                        for row in rows:
                            cards[row['card_id']] = json.loads(row['payload_json'])
                    else:
                        rows = connection.execute(f'SELECT oracle_id, tag FROM oracle_tags WHERE oracle_id IN ({marks}) ORDER BY tag', batch)
                        for row in rows:
                            tags.setdefault(row['oracle_id'], []).append(row['tag'])
        return {'cards': cards, 'tags': tags}

    def oracle_tags_for_card(self, oracle_id: str) -> list[str]:
        if not str(oracle_id or '').strip():
            return []
        with self.connect() as connection:
            rows = connection.execute(
                'SELECT tag FROM oracle_tags WHERE oracle_id = ? '
                'ORDER BY tag COLLATE NOCASE', (str(oracle_id),)).fetchall()
        return [str(row['tag']) for row in rows]

    @staticmethod
    def row_to_print_record(row: sqlite3.Row | None) -> PrintRecord | None:
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
