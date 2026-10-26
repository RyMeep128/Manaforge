"""Internal images operations for CardService."""
from __future__ import annotations

import os
import re
from functools import wraps
import threading
import uuid
from pathlib import Path
from mtg_core.images import checksum_bytes, ensure_parent_dir
from mtg_core.models import ImageAssetRecord


_image_locks = [threading.RLock() for _ in range(64)]


def _serialized_image(method):
    @wraps(method)
    def invoke(self, card_id, *args, **kwargs):
        # Bounded striped locks shared across service instances for this catalog.
        # Reentrant because alternate-face resolution can fall back to the front.
        key = (os.path.abspath(self.database.db_path), card_id)
        with _image_locks[hash(key) % len(_image_locks)]:
            return method(self, card_id, *args, **kwargs)
    return invoke


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

    @_serialized_image
    def cache_artwork(self, card_id, face_index=0, **kwargs):
        from mtg_core.artwork_downloads import cache_image
        return cache_image(self,card_id,face_index,**kwargs)

    @_serialized_image
    def ensure_face_image(self, card_id: str, face_index: int = 0, *, allow_remote=True):
        """Cache alternate-face artwork without changing the printing's front."""
        if not face_index:
            return self.ensure_image(card_id, allow_remote=allow_remote)
        if getattr(self,'streaming_artwork',False) and allow_remote:
            return self.cache_artwork(card_id,face_index,cancel=threading.Event())
        variant = f'face-{face_index}'
        path = self.get_image_path(card_id, variant)
        if path and os.path.isfile(path):
            return path
        payload = self.get_card(card_id=card_id) or {}
        faces = payload.get('card_faces') or []
        if not 0 <= face_index < len(faces):
            return None
        urls = faces[face_index].get('image_uris') or {}
        if not urls:
            return self.ensure_image(card_id, allow_remote=allow_remote)
        url = urls.get('normal') or urls.get('large') or urls.get('png')
        if not url or not allow_remote or self.fetch_bytes_fn is None:
            return None
        data = self.fetch_bytes_fn(url)
        asset = self.store_image_bytes(data, extension=_extension_from_url(url) or 'png',
                                      source='scryfall', source_url=url)
        path = self.materialize_image_asset(asset, preferred_name=f'{card_id}_{variant}')
        self.database.upsert_image_record(card_id, variant=variant, asset_id=asset, path=path,
                                          status='ready', source='scryfall', checksum=checksum_bytes(data))
        return path

    def get_image_path(self, card_id: str, variant: str = "default") -> str | None:
        record = self.database.get_image_record(card_id, variant)
        if record is None:
            return None
        if record.path and Path(record.path).is_file():
            from mtg_core.downloads import file_sha256
            if not record.checksum or file_sha256(record.path)==record.checksum:
                return record.path
        if record.asset_id:
            return self.materialize_image_asset(
                record.asset_id,
                preferred_name=f"{card_id}_{variant}",
            )
        if record.path and os.path.exists(record.path):
            return record.path
        return None

    @_serialized_image
    def ensure_image(self, card_id: str, variant: str = "default", allow_remote: bool = True) -> str | None:
        existing=self.get_image_path(card_id,variant)
        if existing:
            return existing
        if variant=='default' and getattr(self,'streaming_artwork',False) and allow_remote:
            return self.cache_artwork(card_id,cancel=threading.Event())
        record = self.database.get_image_record(card_id, variant)
        if record is not None:
            if record.asset_id:
                path = self.materialize_image_asset(
                    record.asset_id,
                    preferred_name=f"{card_id}_{variant}",
                )
                if path:
                    return path
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
        if asset is None or not asset.payload or checksum_bytes(asset.payload) != asset.checksum:
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
            temporary = path + '.' + uuid.uuid4().hex + '.tmp'
            try:
                with open(temporary, "wb") as handle:
                    handle.write(asset.payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
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
