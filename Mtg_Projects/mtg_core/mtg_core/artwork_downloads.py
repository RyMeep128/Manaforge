"""Shared artwork filling, checkpoints and safe optional-cache maintenance."""

from contextlib import closing
import hashlib
import json
from pathlib import Path
import time

from .bulk_install import cancelled
from .downloads import file_sha256, get_download_manager


def image_url(payload, face=0):
    faces = payload.get("card_faces") or []
    if face and face < len(faces):
        urls = faces[face].get("image_uris") or {}
    else:
        urls = (
            payload.get("image_uris")
            or (faces[0].get("image_uris") if faces else {})
            or {}
        )
    return urls.get("png") or urls.get("large") or urls.get("normal")


def cache_image(
    service, card_id, face=0, *, cancel, progress=None, refresh=False, downloader=None
):
    """Called under the service's shared per-printing lock; one image in memory."""
    cancelled(cancel)
    variant = "default" if not face else f"face-{face}"
    record = service.database.get_image_record(card_id, variant)
    old = service.get_image_path(card_id, variant)
    if old and record and record.source != "scryfall":
        return old  # A user-selected/custom image is not replaceable remote data.
    if old and not refresh:
        return old
    payload = (
        service.get_card(card_id=card_id)
        or service.fetch_missing_card(card_id=card_id)
        or {}
    )
    url = image_url(payload, face)
    if not url:
        return old
    if old and record and record.asset_id:
        previous = service.database.get_sync_state(f"artwork:{card_id}:{face}")
        if previous and previous["version"] == url:
            return old
        with closing(service.database.connect()) as db:
            row = db.execute(
                "SELECT source_url FROM image_assets WHERE asset_id=?",
                (record.asset_id,),
            ).fetchone()
        if previous is None and row and row[0] == url:
            return old
    key = hashlib.sha256((card_id + ":" + str(face) + ":" + url).encode()).hexdigest()
    root = Path(service.image_root) / "downloads"
    root.mkdir(parents=True, exist_ok=True)
    path = root / (key + ".image")
    manager = downloader or get_download_manager()

    def validate(candidate):
        from PIL import Image

        # Reject HTML/error documents before installing them as artwork.
        with candidate.open("rb") as stream:
            header = stream.read(16)
        if not (
            header.startswith(b"\x89PNG\r\n\x1a\n")
            or header.startswith(b"\xff\xd8\xff")
        ):
            raise ValueError("Scryfall did not return a supported card image")
        with Image.open(candidate) as image:
            image.verify()

    manager.download(
        url,
        path,
        cancel=cancel,
        progress=progress,
        max_bytes=32 * 1024**2,
        validate=validate,
    )
    cancelled(cancel)
    extension = "png" if ".png" in url.split("?", 1)[0] else "jpg"
    asset = service.database.store_image_asset(
        path.read_bytes(), extension=extension, source="scryfall", source_url=url
    )
    stored = service.database._resolve_image_asset_storage_path(asset.storage_path)
    for name in [variant, "back"] if face == 1 else [variant]:
        service.database.upsert_image_record(
            card_id,
            variant=name,
            asset_id=asset.asset_id,
            path=str(stored),
            status="ready",
            source="scryfall",
            checksum=asset.checksum,
        )
    service.database.upsert_sync_state(
        f"artwork:{card_id}:{face}", version=url, last_sync_at=time.time()
    )
    path.unlink(missing_ok=True)
    return str(stored)


def fill_artwork(service, state, *, cancel, report, downloader=None):
    row = service.database.get_sync_state("installed-default_cards")
    version = row["version"] if row else "local"
    checkpoint = state.get("artwork_checkpoint", {})
    last = (
        checkpoint.get("last_card", "") if checkpoint.get("version") == version else ""
    )
    scanned, downloaded = 0, 0
    failed = checkpoint.get("failed", 0) if checkpoint.get("version") == version else 0
    with closing(service.database.connect()) as db:
        total = db.execute("SELECT count(*) FROM prints").fetchone()[0]
        done = (
            db.execute(
                "SELECT count(*) FROM prints WHERE card_id<=?", (last,)
            ).fetchone()[0]
            if last
            else 0
        )
    while True:
        cancelled(cancel)
        with closing(service.database.connect()) as db:
            batch = db.execute(
                "SELECT card_id,payload_json FROM prints WHERE card_id>? ORDER BY card_id LIMIT 100",
                (last,),
            ).fetchall()
        if not batch:
            break
        for card_id, raw in batch:
            cancelled(cancel)
            payload = json.loads(raw)
            faces = payload.get("card_faces") or []
            indexes = (
                range(len(faces))
                if faces and any(face.get("image_uris") for face in faces)
                else range(1)
            )
            for face in indexes:
                cancelled(cancel)
                if not image_url(payload, face):
                    continue
                try:
                    service.cache_artwork(
                        card_id,
                        face,
                        cancel=cancel,
                        refresh=True,
                        downloader=downloader,
                    )
                    downloaded += 1
                except (OSError, ValueError):
                    # Keep the last working image, continue other independent
                    # images, and retry missing/changed entries on the next run.
                    failed += 1
            last = card_id
            scanned += 1
            state.set(
                "artwork_checkpoint",
                dict(version=version, last_card=last, failed=failed),
            )
            report(
                dict(
                    operation="Downloading offline artwork",
                    current=done + scanned,
                    total=total,
                    phase="artwork",
                    failed=failed,
                )
            )
    state.set(
        "artwork_checkpoint", {}
    )  # Future runs detect changed URLs, not just new cards.
    state.set(
        "last_artwork_result",
        dict(images=downloaded, failed=failed, updated=time.time()),
    )
    if failed:
        raise ValueError(
            f"{failed} artwork downloads failed. Existing images were preserved. Use Download missing artwork to retry."
        )
    return downloaded


def artwork_usage(service, *, cancel):
    """Count only cache-owned files and metadata; never crawl a user-selected root."""
    cancelled(cancel)
    count, total = 0, 0
    with closing(service.database.connect()) as db:
        for storage, legacy in db.execute(
            "SELECT storage_path,length(payload) FROM image_assets WHERE source='scryfall'"
        ):
            cancelled(cancel)
            path = service.database._resolve_image_asset_storage_path(storage)
            try:
                size = path.stat().st_size if path else 0
            except OSError:
                size = 0
            size = size or legacy or 0
            if size:
                count += 1
                total += size
    return dict(images=count, bytes=total)


def clear_optional_artwork(service, *, cancel, report):
    """Only Scryfall assets unreferenced by manifests/favorites are candidates.

    Referenced image IDs can also live in user documents outside the catalog;
    retain canonical assets. Clear only reproducible materialized copies that
    differ from their canonical asset path. No deck or asset record is deleted.
    """
    root = (Path(service.image_root) / "mtg_core_cache").resolve()
    if not root.exists():
        return 0
    removed = 0
    with closing(service.database.connect()) as db:
        cursor = db.execute(
            "SELECT path,asset_id FROM image_manifest WHERE source='scryfall' AND asset_id IS NOT NULL"
        )
        for path, asset_id in cursor:
            cancelled(cancel)
            if not path:
                continue
            candidate = Path(path).resolve()
            if (
                candidate.parent != root
                or not candidate.is_file()
                or candidate.is_symlink()
            ):
                continue
            row = db.execute(
                "SELECT storage_path,checksum FROM image_assets WHERE asset_id=?",
                (asset_id,),
            ).fetchone()
            canonical = (
                service.database._resolve_image_asset_storage_path(row[0])
                if row
                else None
            )
            if (
                canonical
                and canonical.is_file()
                and canonical.resolve() != candidate
                and file_sha256(canonical) == row[1]
            ):
                candidate.unlink()
                removed += 1
                report(
                    dict(
                        operation="Clearing optional artwork copies",
                        current=removed,
                        total=None,
                        phase="cleanup",
                    )
                )
    return removed
