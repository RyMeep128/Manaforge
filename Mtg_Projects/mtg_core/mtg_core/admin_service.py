from __future__ import annotations

import json

from mtg_core.db import CardDatabase
from mtg_core.models import (
    BulkDownloadStatus,
    CardRecord,
    ImageAssetRecord,
    ImageManifestView,
    PaginatedResult,
    PrintRecord,
    SyncMetadata,
)
from mtg_core.search import normalized_search_text
from mtg_core.services import CardService


class CardAdminService:
    def __init__(
        self,
        *,
        database: CardDatabase | None = None,
        db_path: str | None = None,
        card_service: CardService | None = None,
    ) -> None:
        self.database = database or CardDatabase(db_path)
        self.card_service = card_service or CardService(db_path=self.database.db_path)

    def list_cards(
        self,
        query: str = "",
        *,
        page: int = 1,
        page_size: int = 100,
    ) -> PaginatedResult[CardRecord]:
        normalized_query = normalized_search_text(query)
        like = f"%{normalized_query}%"
        page = max(1, int(page))
        page_size = max(1, int(page_size))
        with self.database.connect() as connection:
            if normalized_query:
                count_row = connection.execute(
                    """
                    SELECT count(*) AS count
                    FROM cards_oracle
                    WHERE normalized_name LIKE ? OR lower(name) LIKE lower(?)
                    """,
                    (like, like),
                ).fetchone()
                total_count = int(count_row["count"] or 0)
                total_pages = max(1, (total_count + page_size - 1) // page_size)
                page = min(page, total_pages)
                offset = (page - 1) * page_size
                rows = connection.execute(
                    """
                    SELECT oracle_id, name, normalized_name, layout
                    FROM cards_oracle
                    WHERE normalized_name LIKE ? OR lower(name) LIKE lower(?)
                    ORDER BY name, oracle_id
                    LIMIT ? OFFSET ?
                    """,
                    (like, like, page_size, offset),
                ).fetchall()
            else:
                count_row = connection.execute(
                    "SELECT count(*) AS count FROM cards_oracle"
                ).fetchone()
                total_count = int(count_row["count"] or 0)
                total_pages = max(1, (total_count + page_size - 1) // page_size)
                page = min(page, total_pages)
                offset = (page - 1) * page_size
                rows = connection.execute(
                    """
                    SELECT oracle_id, name, normalized_name, layout
                    FROM cards_oracle
                    ORDER BY name, oracle_id
                    LIMIT ? OFFSET ?
                    """,
                    (page_size, offset),
                ).fetchall()
        return PaginatedResult(
            items=[_row_to_card_record(row) for row in rows],
            page=page,
            page_size=page_size,
            total_count=total_count,
            total_pages=total_pages,
        )

    def get_card(self, oracle_id: str) -> CardRecord | None:
        return self.database.get_oracle_card(oracle_id=oracle_id)

    def create_card(
        self,
        *,
        oracle_id: str | None,
        name: str,
        normalized_name: str | None = None,
        layout: str | None = None,
    ) -> CardRecord:
        return self.database.create_oracle_card(
            oracle_id=oracle_id, name=name, normalized_name=normalized_name, layout=layout)

    def update_card(
        self,
        oracle_id: str,
        *,
        name: str,
        normalized_name: str | None = None,
        layout: str | None = None,
    ) -> CardRecord:
        return self.database.update_oracle_card(
            oracle_id=oracle_id, name=name, normalized_name=normalized_name, layout=layout)

    def delete_card(self, oracle_id: str) -> bool:
        return self.database.delete_oracle_card(oracle_id=oracle_id)

    def list_prints(
        self,
        *,
        query: str = "",
        set_code: str = "",
        oracle_id: str = "",
        page: int = 1,
        page_size: int = 100,
        syntax: bool = False,
    ) -> PaginatedResult[PrintRecord]:
        conditions: list[str] = []
        params: list[object] = []
        normalized_query = normalized_search_text(query)
        page = max(1, int(page))
        page_size = max(1, int(page_size))
        if normalized_query:
            if syntax:
                from mtg_core.search.syntax import compile_query
                predicate, query_params = compile_query(query)
                conditions.append(predicate)
                params.extend(query_params)
            else:
                like = f"%{normalized_query}%"
                conditions.append("(c.normalized_name LIKE ? OR lower(p.name) LIKE lower(?))")
                params.extend([like, like])
        if set_code.strip():
            conditions.append("lower(coalesce(p.set_code, '')) = lower(?)")
            params.append(set_code.strip())
        if oracle_id.strip():
            conditions.append("p.oracle_id = ?")
            params.append(oracle_id.strip())
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)
        search_join = 'JOIN print_search_data s ON s.card_id = p.card_id' if syntax and normalized_query else ''
        with self.database.connect() as connection:
            count_row = connection.execute(
                f"""
                SELECT count(*) AS count
                FROM prints p
                JOIN cards_oracle c ON c.oracle_id = p.oracle_id
                {search_join}
                {where_clause}
                """,
                tuple(params),
            ).fetchone()
            total_count = int(count_row["count"] or 0)
            total_pages = max(1, (total_count + page_size - 1) // page_size)
            page = min(page, total_pages)
            offset = (page - 1) * page_size
            rows = connection.execute(
                f"""
                SELECT p.*
                FROM prints p
                JOIN cards_oracle c ON c.oracle_id = p.oracle_id
                {search_join}
                {where_clause}
                ORDER BY p.name, p.released_at, p.set_code, p.collector_number, p.card_id
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, offset),
            ).fetchall()
        return PaginatedResult(
            items=[self.database.row_to_print_record(row) for row in rows],
            page=page,
            page_size=page_size,
            total_count=total_count,
            total_pages=total_pages,
        )

    def get_print(self, card_id: str) -> PrintRecord | None:
        return self.database.get_print_by_card_id(card_id)

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
        return self.database.create_print(
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
        return self.database.update_print(
            card_id=card_id, oracle_id=oracle_id, name=name, set_code=set_code, set_name=set_name,
            collector_number=collector_number, released_at=released_at, image_url=image_url,
            thumbnail_url=thumbnail_url, preview_url=preview_url, is_double_faced=is_double_faced)

    def delete_print(self, card_id: str) -> bool:
        return self.database.delete_print(card_id=card_id)

    def list_image_manifest(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
    ) -> PaginatedResult[ImageManifestView]:
        page = max(1, int(page))
        page_size = max(1, int(page_size))
        with self.database.connect() as connection:
            count_row = connection.execute(
                "SELECT count(*) AS count FROM image_manifest"
            ).fetchone()
            total_count = int(count_row["count"] or 0)
            total_pages = max(1, (total_count + page_size - 1) // page_size)
            page = min(page, total_pages)
            offset = (page - 1) * page_size
            rows = connection.execute(
                """
                SELECT
                    m.card_id,
                    p.name AS card_name,
                    m.variant,
                    m.asset_id,
                    m.path,
                    m.status,
                    m.source,
                    m.checksum,
                    a.source_url,
                    m.updated_at,
                    a.created_at
                FROM image_manifest m
                LEFT JOIN prints p ON p.card_id = m.card_id
                LEFT JOIN image_assets a ON a.asset_id = m.asset_id
                ORDER BY p.name, m.card_id, m.variant
                LIMIT ? OFFSET ?
                """,
                (page_size, offset),
            ).fetchall()
        return PaginatedResult(
            items=[
                ImageManifestView(
                    card_id=row["card_id"],
                    card_name=row["card_name"],
                    variant=row["variant"],
                    asset_id=row["asset_id"],
                    path=row["path"],
                    status=row["status"],
                    source=row["source"],
                    checksum=row["checksum"],
                    source_url=row["source_url"],
                    updated_at=row["updated_at"],
                    created_at=row["created_at"],
                )
                for row in rows
            ],
            page=page,
            page_size=page_size,
            total_count=total_count,
            total_pages=total_pages,
        )

    def list_image_assets(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
    ) -> PaginatedResult[ImageAssetRecord]:
        page = max(1, int(page))
        page_size = max(1, int(page_size))
        with self.database.connect() as connection:
            count_row = connection.execute(
                "SELECT count(*) AS count FROM image_assets"
            ).fetchone()
            total_count = int(count_row["count"] or 0)
            total_pages = max(1, (total_count + page_size - 1) // page_size)
            page = min(page, total_pages)
            offset = (page - 1) * page_size
            rows = connection.execute(
                """
                SELECT
                    asset_id, checksum, extension, mime_type, source, source_url,
                    coalesce(payload_size, length(payload)) AS payload_size,
                    storage_path, created_at, updated_at
                FROM image_assets
                ORDER BY updated_at DESC, asset_id
                LIMIT ? OFFSET ?
                """,
                (page_size, offset),
            ).fetchall()
        return PaginatedResult(
            items=[
                ImageAssetRecord(
                    asset_id=row["asset_id"],
                    checksum=row["checksum"],
                    extension=row["extension"],
                    mime_type=row["mime_type"],
                    source=row["source"],
                    source_url=row["source_url"],
                    payload=b"",
                    payload_size=int(row["payload_size"] or 0),
                    storage_path=row["storage_path"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ],
            page=page,
            page_size=page_size,
            total_count=total_count,
            total_pages=total_pages,
        )

    def get_image_asset(self, asset_id: str) -> ImageAssetRecord | None:
        return self.database.get_image_asset(asset_id)

    def list_sync_state(self) -> list[SyncMetadata]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT source, version, last_sync_at, payload_json
                FROM sync_state
                ORDER BY source
                """
            ).fetchall()
        return [
            SyncMetadata(
                source=row["source"],
                version=row["version"],
                last_sync_at=row["last_sync_at"],
                payload=_loads_json(row["payload_json"]),
            )
            for row in rows
        ]

    def get_bulk_download_status(self) -> BulkDownloadStatus:
        return self.card_service.get_bulk_download_status()

    def reset_bulk_download_status(self, *, query: str) -> BulkDownloadStatus:
        return self.card_service.reset_bulk_download_status(query=query)

    def download_fixed_catalog_chunked(self, *, max_chunks: int | None = None) -> BulkDownloadStatus:
        return self.card_service.download_fixed_catalog_chunked(max_chunks=max_chunks)

    def sync_oracle_tags(self) -> dict:
        return self.card_service.sync_oracle_tags()

    def run_bulk_query_download(self, *, query: str, max_chunks: int | None = None) -> BulkDownloadStatus:
        return self.card_service.run_bulk_query_download(query=query, max_chunks=max_chunks)

    def process_bulk_download_chunk(self, *, query: str | None = None, should_pause=None) -> BulkDownloadStatus:
        kwargs = {"should_pause": should_pause}
        if query is not None:
            kwargs["query"] = query
        return self.card_service.process_bulk_download_chunk(**kwargs)

    def pause_bulk_download(self, *, query: str | None = None) -> BulkDownloadStatus:
        if query is None:
            return self.card_service.pause_bulk_download()
        return self.card_service.pause_bulk_download(query=query)


def _loads_json(value: str | None) -> dict | None:
    if not value:
        return None
    return json.loads(value)


def _row_to_card_record(row) -> CardRecord:
    return CardRecord(
        oracle_id=row["oracle_id"],
        name=row["name"],
        normalized_name=row["normalized_name"],
        layout=row["layout"],
    )
