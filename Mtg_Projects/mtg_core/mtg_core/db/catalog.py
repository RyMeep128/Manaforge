"""Transactional catalog mutations and their dependent-record invariants."""
from contextlib import contextmanager
import json
import time
import uuid

from mtg_core.models import CardRecord
from mtg_core.search import normalized_search_text


class CatalogRepository:
    def __init__(self, database):
        self.database = database

    @contextmanager
    def transaction(self):
        connection = self.database.connect()
        try:
            with connection:
                connection.execute('BEGIN IMMEDIATE')
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _card(connection, oracle_id):
        row = connection.execute('SELECT * FROM cards_oracle WHERE oracle_id = ?', (oracle_id,)).fetchone()
        return CardRecord(row['oracle_id'], row['name'], row['normalized_name'], row['layout']) if row else None

    def get_card(self, oracle_id):
        connection = self.database.connect()
        try:
            return self._card(connection, oracle_id)
        finally:
            connection.close()

    def create_card(self, *, oracle_id, name, normalized_name=None, layout=None):
        name = (name or '').strip()
        if not name:
            raise ValueError('Card name is required.')
        oracle_id = (oracle_id or '').strip() or _generated_id('admin-oracle')
        normalized_name = (normalized_name or '').strip() or normalized_search_text(name)
        with self.transaction() as connection:
            connection.execute('INSERT INTO cards_oracle (oracle_id, name, normalized_name, layout) VALUES (?, ?, ?, ?)',
                               (oracle_id, name, normalized_name, layout or None))
            return self._card(connection, oracle_id)

    def update_card(self, oracle_id, *, name, normalized_name=None, layout=None):
        with self.transaction() as connection:
            if self._card(connection, oracle_id) is None:
                raise ValueError(f"Card '{oracle_id}' was not found.")
            name = (name or '').strip()
            if not name:
                raise ValueError('Card name is required.')
            normalized_name = (normalized_name or '').strip() or normalized_search_text(name)
            connection.execute('UPDATE cards_oracle SET name = ?, normalized_name = ?, layout = ? WHERE oracle_id = ?',
                               (name, normalized_name, layout or None, oracle_id))
            self.database.refresh_search_index_for_oracle(connection, oracle_id)
            return self._card(connection, oracle_id)

    def _delete_print_rows(self, connection, card_ids):
        for card_id in card_ids:
            self.database.delete_search_index_for_print(connection, card_id)
            self.database.delete_search_data_for_print(connection, card_id)
            connection.execute('DELETE FROM image_manifest WHERE card_id = ?', (card_id,))
            connection.execute('DELETE FROM artwork_favorites WHERE card_id = ?', (card_id,))
            connection.execute('DELETE FROM canonical_prints WHERE card_id = ?', (card_id,))
            connection.execute('DELETE FROM prints WHERE card_id = ?', (card_id,))

    def delete_card(self, oracle_id):
        with self.transaction() as connection:
            if self._card(connection, oracle_id) is None:
                return False
            rows = connection.execute('SELECT card_id FROM prints WHERE oracle_id = ?', (oracle_id,)).fetchall()
            self._delete_print_rows(connection, [row['card_id'] for row in rows])
            self.database.refresh_canonical_print(connection, oracle_id)
            connection.execute('DELETE FROM oracle_tags WHERE oracle_id = ?', (oracle_id,))
            connection.execute('DELETE FROM artwork_favorites WHERE oracle_id = ?', (oracle_id,))
            connection.execute('DELETE FROM cards_oracle WHERE oracle_id = ?', (oracle_id,))
            return True

    def create_print(self, **fields):
        return self._save_print(create=True, **fields)

    def update_print(self, **fields):
        return self._save_print(create=False, **fields)

    def _save_print(self, *, create, card_id, oracle_id, name, set_code=None, set_name=None,
                    collector_number=None, released_at=None, image_url=None, thumbnail_url=None,
                    preview_url=None, is_double_faced=False, payload=None):
        with self.transaction() as connection:
            existing = None
            if not create:
                existing = connection.execute('SELECT * FROM prints WHERE card_id = ?', (card_id,)).fetchone()
                if existing is None:
                    raise ValueError(f"Print '{card_id}' was not found.")
            oracle_card = self._card(connection, oracle_id)
            if oracle_card is None:
                raise ValueError(f"Card '{oracle_id}' does not exist.")
            name = (name or '').strip()
            if not name:
                raise ValueError('Print name is required.')
            if create:
                card_id = (card_id or '').strip() or _generated_id('admin-print')
            payload_json = _build_print_payload_json(card_id=card_id, oracle_card=oracle_card,
                name=name, set_code=set_code, set_name=set_name, collector_number=collector_number,
                released_at=released_at, image_url=image_url, thumbnail_url=thumbnail_url,
                preview_url=preview_url, is_double_faced=is_double_faced,
                existing_payload=payload if create else json.loads(existing['payload_json']))
            fields = dict(oracle_id=oracle_id, name=name, set_code=_blank_to_none(set_code),
                set_name=_blank_to_none(set_name), collector_number=_blank_to_none(collector_number),
                released_at=_blank_to_none(released_at), image_url=_blank_to_none(image_url),
                thumbnail_url=_blank_to_none(thumbnail_url), preview_url=_blank_to_none(preview_url),
                is_double_faced=int(bool(is_double_faced)), payload_json=payload_json, updated_at=time.time())
            # Column names are fixed above; all user-supplied values are bound parameters.
            if create:
                columns = ', '.join(fields)
                marks = ', '.join('?' for _ in fields)
                connection.execute(f'INSERT INTO prints (card_id, {columns}) VALUES (?, {marks})',
                                   (card_id, *fields.values()))
            else:
                assignments = ', '.join(f'{column} = ?' for column in fields)
                connection.execute(f'UPDATE prints SET {assignments} WHERE card_id = ?',
                                   (*fields.values(), card_id))
            self.database.refresh_print_state(connection, card_id, existing['oracle_id'] if existing else None)
            row = connection.execute('SELECT * FROM prints WHERE card_id = ?', (card_id,)).fetchone()
            return self.database.row_to_print_record(row)

    def delete_print(self, card_id):
        with self.transaction() as connection:
            row = connection.execute('SELECT oracle_id FROM prints WHERE card_id = ?', (card_id,)).fetchone()
            if row is None:
                return False
            self._delete_print_rows(connection, [card_id])
            self.database.refresh_canonical_print(connection, row['oracle_id'])
            return True


def _generated_id(prefix):
    return f'{prefix}-{uuid.uuid4().hex[:12]}'


def _blank_to_none(value):
    return (value or '').strip() or None


def _build_print_payload_json(
    *,
    card_id: str,
    oracle_card: CardRecord,
    name: str,
    set_code: str | None,
    set_name: str | None,
    collector_number: str | None,
    released_at: str | None,
    image_url: str | None,
    thumbnail_url: str | None,
    preview_url: str | None,
    is_double_faced: bool,
    existing_payload: dict | None,
) -> str:
    payload = dict(existing_payload or {})
    payload["id"] = card_id
    payload["oracle_id"] = oracle_card.oracle_id
    payload["name"] = name
    payload["layout"] = oracle_card.layout
    payload["set"] = _blank_to_none(set_code)
    payload["set_name"] = _blank_to_none(set_name)
    payload["collector_number"] = _blank_to_none(collector_number)
    payload["released_at"] = _blank_to_none(released_at)
    image_uris = {}
    if image_url:
        image_uris["png"] = image_url.strip()
    if preview_url:
        image_uris["normal"] = preview_url.strip()
    if thumbnail_url:
        image_uris["small"] = thumbnail_url.strip()
    if image_uris:
        payload["image_uris"] = image_uris
    else:
        payload.pop("image_uris", None)
    if is_double_faced:
        payload["card_faces"] = payload.get("card_faces") or [{"name": name}]
    else:
        payload.pop("card_faces", None)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
