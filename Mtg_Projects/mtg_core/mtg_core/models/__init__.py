from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class CardRecord:
    oracle_id: str
    name: str
    normalized_name: str
    layout: str | None = None


@dataclass(frozen=True)
class PrintRecord:
    card_id: str
    oracle_id: str
    name: str
    set_code: str | None
    set_name: str | None
    collector_number: str | None
    released_at: str | None
    image_url: str | None
    thumbnail_url: str | None
    preview_url: str | None
    is_double_faced: bool
    payload: dict


@dataclass(frozen=True)
class SearchCardResult:
    card_id: str
    oracle_id: str
    name: str
    set_code: str | None
    set_name: str | None
    collector_number: str | None
    preview_url: str | None
    thumbnail_url: str | None
    payload: dict


@dataclass(frozen=True)
class ImageRecord:
    card_id: str
    variant: str
    asset_id: str | None
    path: str | None
    status: str
    source: str | None = None
    checksum: str | None = None
    updated_at: float | None = None


@dataclass(frozen=True)
class ImageAssetRecord:
    asset_id: str
    checksum: str
    extension: str | None
    mime_type: str | None
    source: str | None
    source_url: str | None
    payload: bytes
    payload_size: int | None = None
    storage_path: str | None = None
    created_at: float | None = None
    updated_at: float | None = None


@dataclass(frozen=True)
class SyncMetadata:
    source: str
    last_sync_at: float | None
    version: str | None
    payload: dict | None = None


@dataclass(frozen=True)
class ImageManifestView:
    card_id: str
    card_name: str | None
    variant: str
    asset_id: str | None
    path: str | None
    status: str
    source: str | None = None
    checksum: str | None = None
    source_url: str | None = None
    updated_at: float | None = None
    created_at: float | None = None


@dataclass(frozen=True)
class BulkDownloadStatus:
    source: str
    query: str
    chunk_size: int
    min_image_bytes: int
    status: str
    total_scanned: int
    total_downloaded: int
    total_skipped: int
    total_failed: int
    chunk_number: int
    current_page_url: str | None = None
    next_page_url: str | None = None
    page_offset: int = 0
    completed: bool = False
    completed_at: float | None = None
    last_error: str | None = None
    last_sync_at: float | None = None

    @property
    def is_running(self) -> bool:
        return self.status == "running"

    @property
    def can_resume(self) -> bool:
        return self.status in {"paused", "failed"} and not self.completed


@dataclass(frozen=True)
class PaginatedResult(Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total_count: int
    total_pages: int
