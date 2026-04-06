from __future__ import annotations

from dataclasses import dataclass


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
