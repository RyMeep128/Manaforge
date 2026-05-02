from __future__ import annotations

import json
import time
import uuid

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
from mtg_core.search import choose_canonical_print_key, normalized_search_text
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
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT oracle_id, name, normalized_name, layout
                FROM cards_oracle
                WHERE oracle_id = ?
                """,
                (oracle_id,),
            ).fetchone()
        return _row_to_card_record(row)

    def create_card(
        self,
        *,
        oracle_id: str | None,
        name: str,
        normalized_name: str | None = None,
        layout: str | None = None,
    ) -> CardRecord:
        name = (name or "").strip()
        if not name:
            raise ValueError("Card name is required.")
        oracle_id = (oracle_id or "").strip() or _generated_id("admin-oracle")
        normalized_name = (normalized_name or "").strip() or normalized_search_text(name)
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO cards_oracle (oracle_id, name, normalized_name, layout)
                VALUES (?, ?, ?, ?)
                """,
                (oracle_id, name, normalized_name, layout or None),
            )
        return CardRecord(
            oracle_id=oracle_id,
            name=name,
            normalized_name=normalized_name,
            layout=layout or None,
        )

    def update_card(
        self,
        oracle_id: str,
        *,
        name: str,
        normalized_name: str | None = None,
        layout: str | None = None,
    ) -> CardRecord:
        existing = self.get_card(oracle_id)
        if existing is None:
            raise ValueError(f"Card '{oracle_id}' was not found.")
        name = (name or "").strip()
        if not name:
            raise ValueError("Card name is required.")
        normalized_name = (normalized_name or "").strip() or normalized_search_text(name)
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE cards_oracle
                SET name = ?, normalized_name = ?, layout = ?
                WHERE oracle_id = ?
                """,
                (name, normalized_name, layout or None, oracle_id),
            )
            self.database.refresh_search_index_for_oracle(connection, oracle_id)
        return CardRecord(
            oracle_id=oracle_id,
            name=name,
            normalized_name=normalized_name,
            layout=layout or None,
        )

    def delete_card(self, oracle_id: str) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM cards_oracle WHERE oracle_id = ?",
                (oracle_id,),
            ).fetchone()
            if row is None:
                return False
            print_rows = connection.execute(
                "SELECT card_id FROM prints WHERE oracle_id = ?",
                (oracle_id,),
            ).fetchall()
            for print_row in print_rows:
                self.database.delete_search_index_for_print(connection, print_row["card_id"])
                connection.execute(
                    "DELETE FROM image_manifest WHERE card_id = ?",
                    (print_row["card_id"],),
                )
            connection.execute(
                "DELETE FROM canonical_prints WHERE oracle_id = ?",
                (oracle_id,),
            )
            connection.execute(
                "DELETE FROM prints WHERE oracle_id = ?",
                (oracle_id,),
            )
            connection.execute(
                "DELETE FROM cards_oracle WHERE oracle_id = ?",
                (oracle_id,),
            )
        return True

    def list_prints(
        self,
        *,
        query: str = "",
        set_code: str = "",
        oracle_id: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> PaginatedResult[PrintRecord]:
        conditions: list[str] = []
        params: list[object] = []
        normalized_query = normalized_search_text(query)
        page = max(1, int(page))
        page_size = max(1, int(page_size))
        if normalized_query:
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
        with self.database.connect() as connection:
            count_row = connection.execute(
                f"""
                SELECT count(*) AS count
                FROM prints p
                JOIN cards_oracle c ON c.oracle_id = p.oracle_id
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
                {where_clause}
                ORDER BY p.name, p.released_at, p.set_code, p.collector_number, p.card_id
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, offset),
            ).fetchall()
        return PaginatedResult(
            items=[_row_to_print_record(row) for row in rows],
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
        oracle_card = self.get_card(oracle_id)
        if oracle_card is None:
            raise ValueError(f"Card '{oracle_id}' does not exist.")
        name = (name or "").strip()
        if not name:
            raise ValueError("Print name is required.")
        card_id = (card_id or "").strip() or _generated_id("admin-print")
        payload_json = _build_print_payload_json(
            card_id=card_id,
            oracle_card=oracle_card,
            name=name,
            set_code=set_code,
            set_name=set_name,
            collector_number=collector_number,
            released_at=released_at,
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            preview_url=preview_url,
            is_double_faced=is_double_faced,
            existing_payload=payload,
        )
        now = time.time()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO prints (
                    card_id, oracle_id, name, set_code, set_name, collector_number,
                    released_at, image_url, thumbnail_url, preview_url,
                    is_double_faced, payload_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card_id,
                    oracle_id,
                    name,
                    _blank_to_none(set_code),
                    _blank_to_none(set_name),
                    _blank_to_none(collector_number),
                    _blank_to_none(released_at),
                    _blank_to_none(image_url),
                    _blank_to_none(thumbnail_url),
                    _blank_to_none(preview_url),
                    1 if is_double_faced else 0,
                    payload_json,
                    now,
                ),
            )
            _refresh_canonical_print(connection, oracle_id)
            self.database.refresh_search_index_for_print(connection, card_id)
            row = connection.execute(
                "SELECT * FROM prints WHERE card_id = ?",
                (card_id,),
            ).fetchone()
        return _row_to_print_record(row)

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
        existing = self.get_print(card_id)
        if existing is None:
            raise ValueError(f"Print '{card_id}' was not found.")
        oracle_card = self.get_card(oracle_id)
        if oracle_card is None:
            raise ValueError(f"Card '{oracle_id}' does not exist.")
        name = (name or "").strip()
        if not name:
            raise ValueError("Print name is required.")
        payload_json = _build_print_payload_json(
            card_id=card_id,
            oracle_card=oracle_card,
            name=name,
            set_code=set_code,
            set_name=set_name,
            collector_number=collector_number,
            released_at=released_at,
            image_url=image_url,
            thumbnail_url=thumbnail_url,
            preview_url=preview_url,
            is_double_faced=is_double_faced,
            existing_payload=existing.payload,
        )
        old_oracle_id = existing.oracle_id
        now = time.time()
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE prints
                SET oracle_id = ?,
                    name = ?,
                    set_code = ?,
                    set_name = ?,
                    collector_number = ?,
                    released_at = ?,
                    image_url = ?,
                    thumbnail_url = ?,
                    preview_url = ?,
                    is_double_faced = ?,
                    payload_json = ?,
                    updated_at = ?
                WHERE card_id = ?
                """,
                (
                    oracle_id,
                    name,
                    _blank_to_none(set_code),
                    _blank_to_none(set_name),
                    _blank_to_none(collector_number),
                    _blank_to_none(released_at),
                    _blank_to_none(image_url),
                    _blank_to_none(thumbnail_url),
                    _blank_to_none(preview_url),
                    1 if is_double_faced else 0,
                    payload_json,
                    now,
                    card_id,
                ),
            )
            if old_oracle_id != oracle_id:
                _refresh_canonical_or_delete(connection, old_oracle_id)
            _refresh_canonical_print(connection, oracle_id)
            self.database.refresh_search_index_for_print(connection, card_id)
            row = connection.execute(
                "SELECT * FROM prints WHERE card_id = ?",
                (card_id,),
            ).fetchone()
        return _row_to_print_record(row)

    def delete_print(self, card_id: str) -> bool:
        existing = self.get_print(card_id)
        if existing is None:
            return False
        with self.database.connect() as connection:
            self.database.delete_search_index_for_print(connection, card_id)
            connection.execute(
                "DELETE FROM image_manifest WHERE card_id = ?",
                (card_id,),
            )
            connection.execute(
                "DELETE FROM canonical_prints WHERE card_id = ?",
                (card_id,),
            )
            connection.execute(
                "DELETE FROM prints WHERE card_id = ?",
                (card_id,),
            )
            _refresh_canonical_or_delete(connection, existing.oracle_id)
        return True

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


def _generated_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _blank_to_none(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


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


def _row_to_print_record(row) -> PrintRecord:
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


def _refresh_canonical_print(connection, oracle_id: str) -> None:
    rows = connection.execute(
        "SELECT payload_json FROM prints WHERE oracle_id = ?",
        (oracle_id,),
    ).fetchall()
    if not rows:
        connection.execute(
            "DELETE FROM canonical_prints WHERE oracle_id = ?",
            (oracle_id,),
        )
        return
    payloads = [json.loads(row["payload_json"]) for row in rows]
    payload = min(payloads, key=choose_canonical_print_key)
    connection.execute(
        """
        INSERT INTO canonical_prints (oracle_id, card_id, chosen_at)
        VALUES (?, ?, ?)
        ON CONFLICT(oracle_id) DO UPDATE SET
            card_id = excluded.card_id,
            chosen_at = excluded.chosen_at
        """,
        (oracle_id, str(payload.get("id")), time.time()),
    )


def _refresh_canonical_or_delete(connection, oracle_id: str) -> None:
    count_row = connection.execute(
        "SELECT count(*) AS count FROM prints WHERE oracle_id = ?",
        (oracle_id,),
    ).fetchone()
    if count_row is None or int(count_row["count"] or 0) == 0:
        connection.execute(
            "DELETE FROM canonical_prints WHERE oracle_id = ?",
            (oracle_id,),
        )
        return
    _refresh_canonical_print(connection, oracle_id)
