"""Internal images operations for CardService."""
from __future__ import annotations

import os
import re
from mtg_core.images import checksum_bytes, ensure_parent_dir
from mtg_core.models import ImageAssetRecord


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


def _extension_from_url(url: str | None) -> str | None:
    if not url:
        return None
    basename = os.path.basename(url.split("?", 1)[0])
    if "." not in basename:
        return None
    return basename.rsplit(".", 1)[-1].lower()


class ImageOperations:
    """Operation group sharing the facade dependencies; not instantiated alone."""

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
