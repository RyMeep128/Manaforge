from __future__ import annotations

import json
import os
import re
import time
from typing import Callable

from mtg_core.db import CardDatabase
from mtg_core.images import checksum_bytes, ensure_parent_dir
from mtg_core.models import BulkDownloadStatus, ImageAssetRecord, PrintRecord, SearchCardResult
from mtg_core.paths import core_data_root
from mtg_core.sync import (
    RemoteLookupUnavailable,
    build_print_search_url,
    fetch_bytes,
    fetch_json,
    resolve_card_payload,
    search_prints_payloads,
)


FIXED_CATALOG_QUERY = "l:eng game:paper -is:reprint"
FIXED_CATALOG_SOURCE = "catalog_download_all_cards_include_extras"
FIXED_CATALOG_ITEM_SOURCE = "catalog_download_all_cards_include_extras_item"
FIXED_CATALOG_VERSION = "catalog-download-v2"
FIXED_CATALOG_CHUNK_SIZE = 100
FIXED_CATALOG_MIN_IMAGE_BYTES = 4096


def _materialized_asset_filename(asset: ImageAssetRecord, preferred_name: str | None) -> str:
    extension = (asset.extension or "png").lstrip(".") or "png"
    if not preferred_name:
        return f"{asset.asset_id}.{extension}"

    preferred_base = os.path.basename(str(preferred_name))
    preferred_stem, _preferred_extension = os.path.splitext(preferred_base)
    readable_stem = preferred_stem or preferred_base or asset.asset_id
    readable_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", readable_stem).strip(".-_")
    if not readable_stem:
        readable_stem = asset.asset_id
    return f"{readable_stem}__{asset.asset_id}.{extension}"


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
        self.image_root = image_root or str(core_data_root() / "images")
        self.fetch_json_fn = fetch_json_fn or fetch_json
        self.fetch_bytes_fn = fetch_bytes_fn or fetch_bytes
        self.fetch_bulk_fn = fetch_bulk_fn

    def search_cards(self, query: str, filters: dict | None = None) -> list[SearchCardResult]:
        filters = filters or {}
        search_query, token_mode = _parse_token_search_query(query)
        set_filter = (filters.get("set_filter") or "").strip().casefold()
        limit = max(1, int(filters.get("limit", 200)))
        online_mode = bool(filters.get("online_mode", False))
        cache_ttl_seconds = max(1, int(filters.get("cache_ttl_seconds", 60 * 60)))
        local_rows = self.database.search_prints(
            search_query,
            limit=limit,
            token_mode=token_mode,
            online_mode=online_mode,
            cache_ttl_seconds=cache_ttl_seconds,
        )
        filtered_rows = _filter_print_rows(local_rows, set_filter)
        if (
            (filters.get("force_remote", False) or not filtered_rows)
            and filters.get("allow_remote", True)
        ):
            try:
                remote_query = _build_token_remote_query(search_query) if token_mode else search_query
                cache_expires_at = time.time() + cache_ttl_seconds if online_mode else None
                for payload in search_prints_payloads(
                    remote_query,
                    self.fetch_json_fn,
                    include_extras=token_mode,
                    exact_first=not token_mode,
                ):
                    self.database.upsert_card_payload(
                        payload,
                        cache_scope="online_search" if online_mode else None,
                        cache_expires_at=cache_expires_at,
                    )
            except RemoteLookupUnavailable:
                if filters.get("raise_remote_unavailable") or not filtered_rows:
                    raise
            local_rows = self.database.search_prints(
                search_query,
                limit=limit,
                token_mode=token_mode,
                online_mode=online_mode,
                cache_ttl_seconds=cache_ttl_seconds,
            )
            filtered_rows = _filter_print_rows(local_rows, set_filter)
        results = []
        for row in filtered_rows:
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
        if record is None:
            return None
        if record.asset_id:
            return self.materialize_image_asset(
                record.asset_id,
                preferred_name=f"{card_id}_{variant}",
            )
        if record.path and os.path.exists(record.path):
            return record.path
        return record.path

    def ensure_image(self, card_id: str, variant: str = "default", allow_remote: bool = True) -> str | None:
        record = self.database.get_image_record(card_id, variant)
        if record is not None:
            if record.asset_id:
                return self.materialize_image_asset(
                    record.asset_id,
                    preferred_name=f"{card_id}_{variant}",
                )
            if record.path and os.path.exists(record.path):
                return record.path
        if not allow_remote or self.fetch_bytes_fn is None:
            return None
        card = self.get_card(card_id=card_id)
        if not card:
            card = self.fetch_missing_card(card_id=card_id)
        if not card:
            return None
        print_record = self.database.get_print_by_card_id(card_id)
        image_url = None if print_record is None else print_record.image_url
        if not image_url:
            return None
        payload = self.fetch_bytes_fn(image_url)
        extension = _extension_from_url(image_url) or "png"
        asset_id = self.store_image_bytes(
            payload,
            extension=extension,
            source="scryfall",
            source_url=image_url,
        )
        path = self.materialize_image_asset(
            asset_id,
            preferred_name=f"{card_id}_{variant}",
        )
        self.database.upsert_image_record(
            card_id,
            variant=variant,
            asset_id=asset_id,
            path=path,
            status="ready",
            source="scryfall",
            checksum=checksum_bytes(payload),
        )
        return path

    def store_image_bytes(
        self,
        payload: bytes,
        *,
        extension: str | None = "png",
        mime_type: str | None = None,
        source: str | None = None,
        source_url: str | None = None,
    ) -> str:
        asset = self.database.store_image_asset(
            payload,
            extension=extension,
            mime_type=mime_type,
            source=source,
            source_url=source_url,
        )
        return asset.asset_id

    def get_image_bytes(self, asset_id: str) -> bytes | None:
        asset = self.database.get_image_asset(asset_id)
        return None if asset is None else asset.payload

    def materialize_image_asset(
        self,
        asset_id: str,
        *,
        preferred_name: str | None = None,
        output_root: str | None = None,
    ) -> str | None:
        asset = self.database.get_image_asset(asset_id)
        if asset is None:
            return None
        filename = _materialized_asset_filename(asset, preferred_name)
        root = output_root or os.path.join(self.image_root, "mtg_core_cache")
        path = os.path.join(root, filename)
        ensure_parent_dir(path)
        should_write = True
        if os.path.exists(path):
            try:
                with open(path, "rb") as handle:
                    should_write = checksum_bytes(handle.read()) != asset.checksum
            except OSError:
                should_write = True
        if should_write:
            with open(path, "wb") as handle:
                handle.write(asset.payload)
        return path

    def set_print_image_asset(
        self,
        card_id: str,
        asset_id: str,
        *,
        variant: str = "default",
        source: str | None = None,
        preferred_name: str | None = None,
    ) -> str | None:
        asset = self.database.get_image_asset(asset_id)
        if asset is None:
            return None
        path = self.materialize_image_asset(asset_id, preferred_name=preferred_name or f"{card_id}_{variant}")
        self.database.upsert_image_record(
            card_id,
            variant=variant,
            asset_id=asset_id,
            path=path,
            status="ready",
            source=source or asset.source,
            checksum=asset.checksum,
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

    def get_bulk_download_status(
        self,
        *,
        source_key: str = FIXED_CATALOG_SOURCE,
        query: str = FIXED_CATALOG_QUERY,
        chunk_size: int = FIXED_CATALOG_CHUNK_SIZE,
        min_image_bytes: int = FIXED_CATALOG_MIN_IMAGE_BYTES,
    ) -> BulkDownloadStatus:
        row = self.database.get_sync_state(source_key)
        payload = {} if row is None or not row["payload_json"] else json.loads(row["payload_json"])
        return BulkDownloadStatus(
            source=source_key,
            query=str(payload.get("query") or query),
            chunk_size=int(payload.get("chunk_size") or chunk_size),
            min_image_bytes=int(payload.get("min_image_bytes") or min_image_bytes),
            status=str(payload.get("status") or ("idle" if row is None else "ready")),
            total_scanned=int(payload.get("total_scanned") or 0),
            total_downloaded=int(payload.get("total_downloaded") or 0),
            total_skipped=int(payload.get("total_skipped") or 0),
            total_failed=int(payload.get("total_failed") or 0),
            chunk_number=int(payload.get("chunk_number") or 0),
            current_page_url=payload.get("current_page_url"),
            next_page_url=payload.get("next_page_url"),
            page_offset=int(payload.get("page_offset") or 0),
            completed=bool(payload.get("completed")),
            completed_at=payload.get("completed_at"),
            last_error=payload.get("last_error"),
            last_sync_at=None if row is None else row["last_sync_at"],
        )

    def download_fixed_catalog_chunked(self, *, max_chunks: int | None = None) -> BulkDownloadStatus:
        return self.run_bulk_query_download(
            source_key=FIXED_CATALOG_SOURCE,
            query=FIXED_CATALOG_QUERY,
            chunk_size=FIXED_CATALOG_CHUNK_SIZE,
            min_image_bytes=FIXED_CATALOG_MIN_IMAGE_BYTES,
            max_chunks=max_chunks,
        )

    def run_bulk_query_download(
        self,
        *,
        source_key: str = FIXED_CATALOG_SOURCE,
        query: str = FIXED_CATALOG_QUERY,
        chunk_size: int = FIXED_CATALOG_CHUNK_SIZE,
        min_image_bytes: int = FIXED_CATALOG_MIN_IMAGE_BYTES,
        max_chunks: int | None = None,
    ) -> BulkDownloadStatus:
        status = self.get_bulk_download_status(
            source_key=source_key,
            query=query,
            chunk_size=chunk_size,
            min_image_bytes=min_image_bytes,
        )
        processed_chunks = 0
        while not status.completed:
            if max_chunks is not None and processed_chunks >= max(1, int(max_chunks)):
                break
            status = self.process_bulk_download_chunk(
                source_key=source_key,
                query=query,
                chunk_size=chunk_size,
                min_image_bytes=min_image_bytes,
            )
            processed_chunks += 1
            if status.status in {"paused", "failed"}:
                break
        return status

    def process_bulk_download_chunk(
        self,
        *,
        source_key: str = FIXED_CATALOG_SOURCE,
        query: str = FIXED_CATALOG_QUERY,
        chunk_size: int = FIXED_CATALOG_CHUNK_SIZE,
        min_image_bytes: int = FIXED_CATALOG_MIN_IMAGE_BYTES,
        should_pause: Callable[[], bool] | None = None,
    ) -> BulkDownloadStatus:
        status = self.get_bulk_download_status(
            source_key=source_key,
            query=query,
            chunk_size=chunk_size,
            min_image_bytes=min_image_bytes,
        )
        if status.completed:
            return self._save_bulk_download_status(
                status,
                status="completed",
                last_error=None,
            )

        current_page_url = status.current_page_url or build_print_search_url(query, include_extras=True)
        status = self._save_bulk_download_status(
            status,
            query=query,
            chunk_size=chunk_size,
            min_image_bytes=min_image_bytes,
            status="running",
            current_page_url=current_page_url,
            last_error=None,
            completed=False,
            completed_at=None,
        )

        try:
            page_payload = self.fetch_json_fn(status.current_page_url)
            chunk_records = page_payload.get("data") or []
            page_offset = min(status.page_offset, len(chunk_records))
            next_page_url = page_payload.get("next_page") if page_payload.get("has_more") else None
            if not chunk_records and not next_page_url:
                return self._save_bulk_download_status(
                    status,
                    status="completed",
                    completed=True,
                    completed_at=time.time(),
                    current_page_url=None,
                    next_page_url=None,
                    page_offset=0,
                    last_error=None,
                )
            if page_offset >= len(chunk_records):
                return self._save_bulk_download_status(
                    status,
                    current_page_url=next_page_url,
                    next_page_url=next_page_url,
                    page_offset=0,
                    status="running" if next_page_url else "completed",
                    completed=not bool(next_page_url),
                    completed_at=None if next_page_url else time.time(),
                    last_error=None,
                )

            chunk = chunk_records[page_offset : page_offset + max(1, int(chunk_size))]
            scanned = status.total_scanned
            downloaded = status.total_downloaded
            skipped = status.total_skipped
            failed = status.total_failed
            for payload in chunk:
                scanned += 1
                card_id = str(payload.get("id") or "")
                if not card_id:
                    failed += 1
                else:
                    self.database.upsert_card_payload(payload, source=FIXED_CATALOG_ITEM_SOURCE)
                    if self._has_valid_local_image(card_id, min_image_bytes=min_image_bytes):
                        skipped += 1
                    else:
                        try:
                            image_url = self._resolve_image_url(card_id, payload)
                            if not image_url:
                                failed += 1
                                continue
                            image_payload = self.fetch_bytes_fn(image_url)
                            extension = _extension_from_url(image_url) or "png"
                            asset_id = self.store_image_bytes(
                                image_payload,
                                extension=extension,
                                source="scryfall",
                                source_url=image_url,
                            )
                            path = self.materialize_image_asset(
                                asset_id,
                                preferred_name=f"{card_id}_default",
                            )
                            self.database.upsert_image_record(
                                card_id,
                                variant="default",
                                asset_id=asset_id,
                                path=path,
                                status="ready",
                                source="scryfall",
                                checksum=checksum_bytes(image_payload),
                            )
                            downloaded += 1
                        except Exception:
                            failed += 1

                page_offset += 1
                if should_pause is not None and should_pause():
                    return self._save_bulk_download_status(
                        status,
                        status="paused",
                        total_scanned=scanned,
                        total_downloaded=downloaded,
                        total_skipped=skipped,
                        total_failed=failed,
                        chunk_number=status.chunk_number,
                        current_page_url=status.current_page_url,
                        next_page_url=next_page_url,
                        page_offset=page_offset,
                        completed=False,
                        completed_at=None,
                        last_error=None,
                    )

            chunk_number = status.chunk_number + 1
            advance_to_next = page_offset >= len(chunk_records)
            current_page_url = next_page_url if advance_to_next else status.current_page_url
            status_name = "running"
            completed = False
            completed_at = None
            if advance_to_next and not next_page_url:
                status_name = "completed"
                completed = True
                current_page_url = None
                completed_at = time.time()

            return self._save_bulk_download_status(
                status,
                status=status_name,
                total_scanned=scanned,
                total_downloaded=downloaded,
                total_skipped=skipped,
                total_failed=failed,
                chunk_number=chunk_number,
                current_page_url=current_page_url,
                next_page_url=next_page_url,
                page_offset=0 if advance_to_next else page_offset,
                completed=completed,
                completed_at=completed_at,
                last_error=None,
            )
        except Exception as exc:
            return self._save_bulk_download_status(
                status,
                status="failed",
                last_error=str(exc),
            )

    def pause_bulk_download(
        self,
        *,
        source_key: str = FIXED_CATALOG_SOURCE,
        query: str = FIXED_CATALOG_QUERY,
        chunk_size: int = FIXED_CATALOG_CHUNK_SIZE,
        min_image_bytes: int = FIXED_CATALOG_MIN_IMAGE_BYTES,
    ) -> BulkDownloadStatus:
        status = self.get_bulk_download_status(
            source_key=source_key,
            query=query,
            chunk_size=chunk_size,
            min_image_bytes=min_image_bytes,
        )
        if status.completed:
            return status
        return self._save_bulk_download_status(
            status,
            query=query,
            chunk_size=chunk_size,
            min_image_bytes=min_image_bytes,
            status="paused",
            last_error=None if status.status != "failed" else status.last_error,
        )

    def _resolve_image_url(self, card_id: str, payload: dict) -> str | None:
        print_record = self.database.get_print_by_card_id(card_id)
        if print_record and print_record.image_url:
            return print_record.image_url
        card = self.database.upsert_card_payload(payload)
        return card.image_url

    def _has_valid_local_image(self, card_id: str, *, min_image_bytes: int) -> bool:
        print_record = self.database.get_print_by_card_id(card_id)
        if print_record is None:
            return False
        record = self.database.get_image_record(card_id, "default")
        if record is None or not record.asset_id:
            return False
        asset = self.database.get_image_asset(record.asset_id)
        if asset is None:
            return False
        return len(asset.payload) >= max(1, int(min_image_bytes))

    def _save_bulk_download_status(self, existing: BulkDownloadStatus, **updates) -> BulkDownloadStatus:
        status = BulkDownloadStatus(
            source=updates.get("source", existing.source),
            query=updates.get("query", existing.query),
            chunk_size=int(updates.get("chunk_size", existing.chunk_size)),
            min_image_bytes=int(updates.get("min_image_bytes", existing.min_image_bytes)),
            status=updates.get("status", existing.status),
            total_scanned=int(updates.get("total_scanned", existing.total_scanned)),
            total_downloaded=int(updates.get("total_downloaded", existing.total_downloaded)),
            total_skipped=int(updates.get("total_skipped", existing.total_skipped)),
            total_failed=int(updates.get("total_failed", existing.total_failed)),
            chunk_number=int(updates.get("chunk_number", existing.chunk_number)),
            current_page_url=updates.get("current_page_url", existing.current_page_url),
            next_page_url=updates.get("next_page_url", existing.next_page_url),
            page_offset=int(updates.get("page_offset", existing.page_offset)),
            completed=bool(updates.get("completed", existing.completed)),
            completed_at=updates.get("completed_at", existing.completed_at),
            last_error=updates.get("last_error", existing.last_error),
            last_sync_at=time.time(),
        )
        self.database.upsert_sync_state(
            status.source,
            version=FIXED_CATALOG_VERSION,
            last_sync_at=status.last_sync_at,
            payload={
                "query": status.query,
                "chunk_size": status.chunk_size,
                "min_image_bytes": status.min_image_bytes,
                "status": status.status,
                "total_scanned": status.total_scanned,
                "total_downloaded": status.total_downloaded,
                "total_skipped": status.total_skipped,
                "total_failed": status.total_failed,
                "chunk_number": status.chunk_number,
                "current_page_url": status.current_page_url,
                "next_page_url": status.next_page_url,
                "page_offset": status.page_offset,
                "completed": status.completed,
                "completed_at": status.completed_at,
                "last_error": status.last_error,
            },
        )
        return status


_DEFAULT_CARD_SERVICE: CardService | None = None


def get_default_card_service() -> CardService:
    global _DEFAULT_CARD_SERVICE
    if _DEFAULT_CARD_SERVICE is None:
        _DEFAULT_CARD_SERVICE = CardService()
    return _DEFAULT_CARD_SERVICE


def _parse_token_search_query(query: str) -> tuple[str, bool]:
    stripped = (query or "").strip()
    parts = stripped.split()
    if parts and parts[-1].casefold() == "token":
        return " ".join(parts[:-1]).strip(), True
    return stripped, False


def _build_token_remote_query(query: str) -> str:
    stripped = (query or "").strip()
    return f"t:token {stripped}".strip()


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


def _extension_from_url(url: str | None) -> str | None:
    if not url:
        return None
    basename = os.path.basename(url.split("?", 1)[0])
    if "." not in basename:
        return None
    return basename.rsplit(".", 1)[-1].lower()
