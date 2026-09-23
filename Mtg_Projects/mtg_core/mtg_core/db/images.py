"""Image manifests and verified filesystem/blob asset persistence."""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import time
from pathlib import Path
from mtg_core.models import ImageAssetRecord, ImageRecord
from mtg_core.paths import core_data_root


class ImageOperations:
    def upsert_image_record(
        self,
        card_id: str,
        *,
        variant: str = "default",
        asset_id: str | None = None,
        path: str | None,
        status: str,
        source: str | None = None,
        checksum: str | None = None,
    ) -> ImageRecord:
        updated_at = time.time()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO image_manifest (card_id, variant, asset_id, path, status, source, checksum, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(card_id, variant) DO UPDATE SET
                    asset_id=excluded.asset_id,
                    path=excluded.path,
                    status=excluded.status,
                    source=excluded.source,
                    checksum=excluded.checksum,
                    updated_at=excluded.updated_at
                """,
                (card_id, variant, asset_id, path, status, source, checksum, updated_at),
            )
        return ImageRecord(
            card_id=card_id,
            variant=variant,
            asset_id=asset_id,
            path=path,
            status=status,
            source=source,
            checksum=checksum,
            updated_at=updated_at,
        )

    def get_image_record(self, card_id: str, variant: str = "default") -> ImageRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT card_id, variant, asset_id, path, status, source, checksum, updated_at
                FROM image_manifest
                WHERE card_id = ? AND variant = ?
                """,
                (card_id, variant),
            ).fetchone()
        if row is None:
            return None
        return ImageRecord(
            card_id=row["card_id"],
            variant=row["variant"],
            asset_id=row["asset_id"],
            path=row["path"],
            status=row["status"],
            source=row["source"],
            checksum=row["checksum"],
            updated_at=row["updated_at"],
        )

    def get_image_records_for_cards(self, card_ids) -> dict[tuple[str, str], ImageRecord]:
        card_ids = list(dict.fromkeys(str(card_id) for card_id in card_ids if card_id))
        if not card_ids:
            return {}
        placeholders = ','.join('?' for _ in card_ids)
        with self.connect() as connection:
            rows = connection.execute(
                f'SELECT card_id, variant, asset_id, path, status, source, checksum, updated_at '
                f'FROM image_manifest WHERE card_id IN ({placeholders}) AND variant IN (\'default\', \'back\')',
                card_ids).fetchall()
        return {(row['card_id'], row['variant']): ImageRecord(
            card_id=row['card_id'], variant=row['variant'], asset_id=row['asset_id'],
            path=row['path'], status=row['status'], source=row['source'],
            checksum=row['checksum'], updated_at=row['updated_at']) for row in rows}

    def _image_asset_base_dir(self) -> Path:
        if self.db_path == ":memory:":
            return core_data_root()
        return Path(self.db_path).expanduser().resolve().parent

    def _image_asset_storage_root(self) -> Path:
        return self._image_asset_base_dir() / "images" / "assets"

    @staticmethod
    def _safe_asset_extension(extension: str | None) -> str:
        safe = re.sub(r"[^A-Za-z0-9]+", "", (extension or "").lstrip("."))
        return safe.lower() or "bin"

    def _image_asset_path(self, asset_id: str, checksum: str, extension: str | None) -> Path:
        filename = f"{asset_id}.{self._safe_asset_extension(extension)}"
        return self._image_asset_storage_root() / checksum[:2] / filename

    def _image_asset_storage_reference(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self._image_asset_base_dir()))
        except ValueError:
            return str(path.resolve())

    def _resolve_image_asset_storage_path(self, storage_path: str | None) -> Path | None:
        if not storage_path:
            return None
        path = Path(storage_path)
        if path.is_absolute():
            return path
        return self._image_asset_base_dir() / path

    @staticmethod
    def _row_blob(row: sqlite3.Row, column_name: str = "payload") -> bytes:
        value = row[column_name]
        if value is None:
            return b""
        return bytes(value)

    @staticmethod
    def _write_verified_image_asset_file(path: Path, payload: bytes, checksum: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f"{path.name}.tmp")
        with open(temp_path, "wb") as handle:
            handle.write(payload)
        with open(temp_path, "rb") as handle:
            written_checksum = hashlib.sha256(handle.read()).hexdigest()
        if written_checksum != checksum:
            try:
                temp_path.unlink()
            except OSError:
                pass
            raise OSError("Stored image asset checksum verification failed.")
        os.replace(temp_path, path)

    @staticmethod
    def _read_verified_image_asset_file(path: Path, checksum: str) -> bytes | None:
        try:
            with open(path, "rb") as handle:
                payload = handle.read()
        except OSError:
            return None
        if hashlib.sha256(payload).hexdigest() != checksum:
            return None
        return payload

    def _row_to_image_asset_record(
        self,
        row: sqlite3.Row,
        *,
        payload_override: bytes | None = None,
        payload_size_override: int | None = None,
    ) -> ImageAssetRecord:
        payload = self._row_blob(row) if payload_override is None else payload_override
        payload_size = row["payload_size"]
        if payload_size_override is not None:
            payload_size = payload_size_override
        if payload_size is None:
            payload_size = len(payload)
        return ImageAssetRecord(
            asset_id=row["asset_id"],
            checksum=row["checksum"],
            extension=row["extension"],
            mime_type=row["mime_type"],
            source=row["source"],
            source_url=row["source_url"],
            payload=payload,
            payload_size=int(payload_size or 0),
            storage_path=row["storage_path"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def store_image_asset(
        self,
        payload: bytes,
        *,
        extension: str | None = "png",
        mime_type: str | None = None,
        source: str | None = None,
        source_url: str | None = None,
    ) -> ImageAssetRecord:
        checksum = hashlib.sha256(payload).hexdigest()
        now = time.time()
        asset_id = f"img-{checksum[:20]}"
        asset_path = self._image_asset_path(asset_id, checksum, extension)
        self._write_verified_image_asset_file(asset_path, payload, checksum)
        storage_path = self._image_asset_storage_reference(asset_path)
        with self.connect() as connection:
            existing = connection.execute(
                """
                SELECT
                    asset_id, checksum, extension, mime_type, source, source_url,
                    payload, payload_size, storage_path, created_at, updated_at
                FROM image_assets
                WHERE checksum = ?
                """,
                (checksum,),
            ).fetchone()
            if existing is not None:
                existing_asset_path = self._image_asset_path(
                    existing["asset_id"],
                    checksum,
                    extension or existing["extension"],
                )
                if existing_asset_path != asset_path:
                    self._write_verified_image_asset_file(existing_asset_path, payload, checksum)
                    storage_path = self._image_asset_storage_reference(existing_asset_path)
                connection.execute(
                    """
                    UPDATE image_assets
                    SET extension = coalesce(?, extension),
                        mime_type = coalesce(?, mime_type),
                        source = coalesce(?, source),
                        source_url = coalesce(?, source_url),
                        payload = ?,
                        payload_size = ?,
                        storage_path = ?,
                        updated_at = ?
                    WHERE asset_id = ?
                    """,
                    (
                        extension,
                        mime_type,
                        source,
                        source_url,
                        b"",
                        len(payload),
                        storage_path,
                        now,
                        existing["asset_id"],
                    ),
                )
                row = connection.execute(
                    """
                    SELECT
                        asset_id, checksum, extension, mime_type, source, source_url,
                        payload, payload_size, storage_path, created_at, updated_at
                    FROM image_assets
                    WHERE asset_id = ?
                    """,
                    (existing["asset_id"],),
                ).fetchone()
                return self._row_to_image_asset_record(row, payload_override=payload)

            connection.execute(
                """
                INSERT INTO image_assets (
                    asset_id, checksum, extension, mime_type, source, source_url,
                    payload, payload_size, storage_path, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    checksum,
                    extension,
                    mime_type,
                    source,
                    source_url,
                    b"",
                    len(payload),
                    storage_path,
                    now,
                    now,
                ),
            )
            return ImageAssetRecord(
                asset_id=asset_id,
                checksum=checksum,
                extension=extension,
                mime_type=mime_type,
                source=source,
                source_url=source_url,
                payload=bytes(payload),
                payload_size=len(payload),
                storage_path=storage_path,
                created_at=now,
                updated_at=now,
            )

    def get_image_asset(self, asset_id: str) -> ImageAssetRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    asset_id, checksum, extension, mime_type, source, source_url,
                    payload, payload_size, storage_path, created_at, updated_at
                FROM image_assets
                WHERE asset_id = ?
                """,
                (asset_id,),
            ).fetchone()
        if row is None:
            return None
        payload = None
        path = self._resolve_image_asset_storage_path(row["storage_path"])
        if path is not None:
            payload = self._read_verified_image_asset_file(path, row["checksum"])
        if payload is None:
            blob = self._row_blob(row)
            payload = blob if blob else b""
        return self._row_to_image_asset_record(row, payload_override=payload)
