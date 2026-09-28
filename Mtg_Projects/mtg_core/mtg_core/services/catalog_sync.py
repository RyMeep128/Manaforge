"""Internal catalog sync operations for CardService."""
from __future__ import annotations

import gzip
import json
import time
from typing import Callable
from mtg_core.images import checksum_bytes
from mtg_core.models import BulkDownloadStatus
from mtg_core.sync_status import SyncStatus
from mtg_core.network import RateLimitExceeded, get_download_logger
from mtg_core.sync import build_print_search_url
from .constants import (
    FIXED_CATALOG_QUERY, FIXED_CATALOG_SOURCE, FIXED_CATALOG_ITEM_SOURCE,
    FIXED_CATALOG_VERSION, FIXED_CATALOG_CHUNK_SIZE, FIXED_CATALOG_MIN_IMAGE_BYTES,
    ORACLE_TAGS_SOURCE, ORACLE_TAGS_METADATA_URL,
)
from .images import _extension_from_url


class CatalogSyncOperations:
    """Operation group sharing the facade dependencies; not instantiated alone."""

    def sync_bulk_data(self) -> dict:
        if self.fetch_bulk_fn is None:
            return {"synced": 0, "status": "noop"}
        synced = 0
        for payload in self.fetch_bulk_fn():
            self.database.upsert_card_payload(payload, source="bulk_sync")
            synced += 1
        return {"synced": synced, "status": "ok"}

    def sync_oracle_tags(self) -> dict:
        metadata = self.fetch_json_fn(ORACLE_TAGS_METADATA_URL)
        download_url = metadata.get('jsonl_download_uri') or metadata.get('download_uri')
        if not download_url:
            raise ValueError('Scryfall did not provide an Oracle Tags download URL.')
        payload = self.fetch_bytes_fn(download_url)
        if payload[:2] == b'\x1f\x8b':
            payload = gzip.decompress(payload)
        text = payload.decode('utf-8-sig')
        if text.lstrip().startswith('['):
            records = json.loads(text)
        else:
            records = [json.loads(line) for line in text.splitlines() if line.strip()]
        tagging_count = self.database.replace_oracle_tags(records)
        tag_count = sum(1 for record in records if record.get('label'))
        updated_at = metadata.get('updated_at')
        now = time.time()
        self.database.upsert_sync_state(
            ORACLE_TAGS_SOURCE,
            version=str(updated_at or ''),
            last_sync_at=now,
            payload={'updated_at': updated_at, 'tags': tag_count,
                     'taggings': tagging_count, 'download_url': download_url},
        )
        return {'tags': tag_count, 'taggings': tagging_count,
                'updated_at': updated_at, 'last_sync_at': now}

    def ensure_oracle_tags(self) -> dict | None:
        if self.database.oracle_tag_count() > 0:
            return None
        return self.sync_oracle_tags()

    def get_bulk_download_status(
        self,
        *,
        source_key: str = FIXED_CATALOG_SOURCE,
        query: str = FIXED_CATALOG_QUERY,
        chunk_size: int = FIXED_CATALOG_CHUNK_SIZE,
        min_image_bytes: int = FIXED_CATALOG_MIN_IMAGE_BYTES,
    ) -> BulkDownloadStatus:
        row = self.database.get_sync_state(source_key)
        if row is not None and row["version"] != FIXED_CATALOG_VERSION:
            row = None
        payload = {} if row is None or not row["payload_json"] else json.loads(row["payload_json"])
        return BulkDownloadStatus(
            source=source_key,
            query=str(payload.get("query") or query),
            chunk_size=int(payload.get("chunk_size") or chunk_size),
            min_image_bytes=int(payload.get("min_image_bytes") or min_image_bytes),
            status=str(payload.get("status") or (SyncStatus.IDLE if row is None else SyncStatus.READY)),
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
        if status.query != (query or "").strip():
            status = self.reset_bulk_download_status(
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
            if status.status in {SyncStatus.PAUSED, SyncStatus.FAILED}:
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
                status=SyncStatus.COMPLETED,
                last_error=None,
            )

        current_page_url = status.current_page_url or build_print_search_url(query, include_extras=True)
        status = self._save_bulk_download_status(
            status,
            query=query,
            chunk_size=chunk_size,
            min_image_bytes=min_image_bytes,
            status=SyncStatus.RUNNING,
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
                    status=SyncStatus.COMPLETED,
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
                    status=SyncStatus.RUNNING if next_page_url else SyncStatus.COMPLETED,
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
                                raise ValueError("No image URL available for this printing")
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
                        except RateLimitExceeded:
                            get_download_logger().exception("card_rate_limited card_id=%s name=%s set=%s collector=%s", card_id, payload.get("name"), payload.get("set"), payload.get("collector_number"))
                            raise
                        except Exception:
                            get_download_logger().exception("card_failed card_id=%s name=%s set=%s collector=%s", card_id, payload.get("name"), payload.get("set"), payload.get("collector_number"))
                            failed += 1

                page_offset += 1
                if should_pause is not None and should_pause():
                    return self._save_bulk_download_status(
                        status,
                        status=SyncStatus.PAUSED,
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

            get_download_logger().info("batch scanned=%s downloaded=%s skipped=%s failed=%s page=%s offset=%s", scanned, downloaded, skipped, failed, status.current_page_url, page_offset)
            chunk_number = status.chunk_number + 1
            advance_to_next = page_offset >= len(chunk_records)
            current_page_url = next_page_url if advance_to_next else status.current_page_url
            status_name = SyncStatus.RUNNING
            completed = False
            completed_at = None
            if advance_to_next and not next_page_url:
                status_name = SyncStatus.COMPLETED
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
            get_download_logger().exception("bulk_stopped page=%s offset=%s", status.current_page_url, status.page_offset)
            return self._save_bulk_download_status(
                status,
                status=SyncStatus.FAILED,
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
            status=SyncStatus.PAUSED,
            last_error=None if status.status != SyncStatus.FAILED else status.last_error,
        )

    def reset_bulk_download_status(
        self,
        *,
        source_key: str = FIXED_CATALOG_SOURCE,
        query: str = FIXED_CATALOG_QUERY,
        chunk_size: int = FIXED_CATALOG_CHUNK_SIZE,
        min_image_bytes: int = FIXED_CATALOG_MIN_IMAGE_BYTES,
    ) -> BulkDownloadStatus:
        stripped_query = (query or "").strip()
        if not stripped_query:
            raise ValueError("Scryfall query is required.")
        status = BulkDownloadStatus(
            source=source_key,
            query=stripped_query,
            chunk_size=max(1, int(chunk_size)),
            min_image_bytes=max(1, int(min_image_bytes)),
            status=SyncStatus.IDLE,
            total_scanned=0,
            total_downloaded=0,
            total_skipped=0,
            total_failed=0,
            chunk_number=0,
            current_page_url=None,
            next_page_url=None,
            page_offset=0,
            completed=False,
            completed_at=None,
            last_error=None,
        )
        return self._save_bulk_download_status(status)

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
