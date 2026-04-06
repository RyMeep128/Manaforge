from __future__ import annotations

import os
from typing import Callable

from mtg_core.db import CardDatabase
from mtg_core.images import checksum_bytes, ensure_parent_dir
from mtg_core.models import PrintRecord, SearchCardResult
from mtg_core.paths import core_root
from mtg_core.sync import fetch_json, resolve_card_payload, search_prints_payloads


class CardService:
    def __init__(
        self,
        *,
        db_path: str | None = None,
        image_root: str | None = None,
        fetch_json_fn: Callable[[str], dict] | None = None,
        fetch_bytes_fn: Callable[[str], bytes] | None = None,
        fetch_bulk_fn: Callable[[], list[dict]] | None = None,
    ):
        self.database = CardDatabase(db_path)
        self.image_root = image_root or str(core_root() / "images")
        self.fetch_json_fn = fetch_json_fn or fetch_json
        self.fetch_bytes_fn = fetch_bytes_fn
        self.fetch_bulk_fn = fetch_bulk_fn

    def search_cards(self, query: str, filters: dict | None = None) -> list[SearchCardResult]:
        filters = filters or {}
        set_filter = (filters.get("set_filter") or "").strip().casefold()
        limit = max(1, int(filters.get("limit", 200)))
        local_rows = self.database.search_prints(query, limit=limit)
        if (not _filter_print_rows(local_rows, set_filter)) and filters.get("allow_remote", True):
            for payload in search_prints_payloads(query, self.fetch_json_fn):
                self.database.upsert_card_payload(payload)
            local_rows = self.database.search_prints(query, limit=limit)
        results = []
        for row in _filter_print_rows(local_rows, set_filter):
            results.append(
                SearchCardResult(
                    card_id=row.card_id,
                    oracle_id=row.oracle_id,
                    name=row.name,
                    set_code=row.set_code,
                    set_name=row.set_name,
                    collector_number=row.collector_number,
                    preview_url=row.preview_url,
                    thumbnail_url=row.thumbnail_url,
                    payload=row.payload,
                )
            )
        return results

    def get_card(
        self,
        *,
        exact_name: str | None = None,
        oracle_id: str | None = None,
        card_id: str | None = None,
    ) -> dict | None:
        record: PrintRecord | None = None
        if card_id:
            record = self.database.get_print_by_card_id(card_id)
        elif oracle_id:
            record = self.database.get_canonical_print(oracle_id)
        elif exact_name:
            record = self.database.get_named_print(exact_name)
        return None if record is None else dict(record.payload)

    def get_print(self, *, set_code: str, collector_number: str) -> dict | None:
        record = self.database.get_print_by_set_and_number(set_code, collector_number)
        return None if record is None else dict(record.payload)

    def get_prints(self, oracle_id: str) -> list[dict]:
        return [dict(row.payload) for row in self.database.get_prints_for_oracle(oracle_id)]

    def get_canonical_print(self, oracle_id: str) -> dict | None:
        record = self.database.get_canonical_print(oracle_id)
        return None if record is None else dict(record.payload)

    def get_image_path(self, card_id: str, variant: str = "default") -> str | None:
        record = self.database.get_image_record(card_id, variant)
        return None if record is None else record.path

    def ensure_image(self, card_id: str, variant: str = "default") -> str | None:
        record = self.database.get_image_record(card_id, variant)
        if record is not None and record.path and os.path.exists(record.path):
            return record.path
        if self.fetch_bytes_fn is None:
            return None
        card = self.get_card(card_id=card_id)
        if not card:
            card = self.fetch_missing_card(card_id=card_id)
        if not card:
            return None
        image_url = self.database.get_print_by_card_id(card_id).image_url
        if not image_url:
            return None
        payload = self.fetch_bytes_fn(image_url)
        filename = f"{card_id}_{variant}.png"
        path = os.path.join(self.image_root, "mtg_core_cache", filename)
        ensure_parent_dir(path)
        with open(path, "wb") as handle:
            handle.write(payload)
        self.database.upsert_image_record(
            card_id,
            variant=variant,
            path=path,
            status="ready",
            source="scryfall",
            checksum=checksum_bytes(payload),
        )
        return path

    def sync_bulk_data(self) -> dict:
        if self.fetch_bulk_fn is None:
            return {"synced": 0, "status": "noop"}
        synced = 0
        for payload in self.fetch_bulk_fn():
            self.database.upsert_card_payload(payload, source="bulk_sync")
            synced += 1
        return {"synced": synced, "status": "ok"}

    def fetch_missing_card(
        self,
        *,
        exact_name: str | None = None,
        set_code: str | None = None,
        collector_number: str | None = None,
        card_id: str | None = None,
    ) -> dict:
        payload = resolve_card_payload(
            exact_name=exact_name,
            set_code=set_code,
            collector_number=collector_number,
            card_id=card_id,
            fetch_json_fn=self.fetch_json_fn,
        )
        return dict(self.database.upsert_card_payload(payload).payload)


_DEFAULT_CARD_SERVICE: CardService | None = None


def get_default_card_service() -> CardService:
    global _DEFAULT_CARD_SERVICE
    if _DEFAULT_CARD_SERVICE is None:
        _DEFAULT_CARD_SERVICE = CardService()
    return _DEFAULT_CARD_SERVICE


def _filter_print_rows(rows: list[PrintRecord], set_filter: str) -> list[PrintRecord]:
    if not set_filter:
        return list(rows)
    filtered: list[PrintRecord] = []
    for row in rows:
        row_set_code = (row.set_code or "").casefold()
        row_set_name = (row.set_name or "").casefold()
        if row_set_code == set_filter or set_filter in row_set_name:
            filtered.append(row)
    return filtered
