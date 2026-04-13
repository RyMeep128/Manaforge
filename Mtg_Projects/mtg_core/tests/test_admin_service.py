from __future__ import annotations

import time

from mtg_core.admin_service import CardAdminService
from mtg_core.db import CardDatabase
from mtg_core.services import (
    FIXED_CATALOG_MIN_IMAGE_BYTES,
    FIXED_CATALOG_QUERY,
    FIXED_CATALOG_SOURCE,
    FIXED_CATALOG_VERSION,
    CardService,
)
from mtg_core.sync import build_print_search_url


def _service(tmp_path):
    db_path = tmp_path / "admin.sqlite3"
    database = CardDatabase(str(db_path))
    return CardAdminService(database=database), database


def _bulk_service(tmp_path, *, fetch_json, fetch_bytes):
    db_path = tmp_path / "bulk.sqlite3"
    database = CardDatabase(str(db_path))
    card_service = CardService(
        db_path=str(db_path),
        image_root=str(tmp_path / "images"),
        fetch_json_fn=fetch_json,
        fetch_bytes_fn=fetch_bytes,
    )
    return CardAdminService(database=database, card_service=card_service), database


def _print_payload(index: int) -> dict:
    return {
        "id": f"print-{index}",
        "oracle_id": f"oracle-{index}",
        "name": f"Card {index}",
        "set": "seta",
        "set_name": "Set A",
        "collector_number": str(index),
        "released_at": "2024-01-01",
        "image_uris": {
            "png": f"https://img.test/card-{index}.png",
            "normal": f"https://img.test/card-{index}-normal.png",
            "small": f"https://img.test/card-{index}-small.png",
        },
    }


def test_create_update_delete_card(tmp_path):
    service, _database = _service(tmp_path)

    created = service.create_card(
        oracle_id="oracle-alpha",
        name="Lightning Bolt",
        layout="normal",
    )

    assert created.normalized_name == "lightning bolt"
    assert [card.name for card in service.list_cards().items] == ["Lightning Bolt"]

    updated = service.update_card(
        "oracle-alpha",
        name="Lightning Bolt Prime",
        layout="split",
    )

    assert updated.name == "Lightning Bolt Prime"
    assert updated.normalized_name == "lightning bolt prime"
    assert service.delete_card("oracle-alpha") is True
    assert service.list_cards().items == []


def test_print_crud_keeps_payload_in_sync_and_recomputes_canonical(tmp_path):
    service, database = _service(tmp_path)
    service.create_card(
        oracle_id="oracle-bolt",
        name="Lightning Bolt",
        layout="normal",
    )

    alpha = service.create_print(
        card_id="print-alpha",
        oracle_id="oracle-bolt",
        name="Lightning Bolt",
        set_code="lea",
        set_name="Limited Edition Alpha",
        collector_number="161",
        released_at="1993-08-05",
        image_url="https://img/alpha.png",
        thumbnail_url="https://img/alpha-small.png",
        preview_url="https://img/alpha-normal.png",
        is_double_faced=False,
    )
    beta = service.create_print(
        card_id="print-beta",
        oracle_id="oracle-bolt",
        name="Lightning Bolt",
        set_code="clu",
        set_name="Ravnica Clue Edition",
        collector_number="141",
        released_at="2024-02-23",
        image_url="https://img/beta.png",
        thumbnail_url="https://img/beta-small.png",
        preview_url="https://img/beta-normal.png",
        is_double_faced=True,
    )

    canonical = database.get_canonical_print("oracle-bolt")
    assert canonical is not None
    assert canonical.card_id == "print-alpha"

    updated = service.update_print(
        beta.card_id,
        oracle_id="oracle-bolt",
        name="Lightning Bolt",
        set_code="2x2",
        set_name="Double Masters 2022",
        collector_number="117",
        released_at="1992-01-01",
        image_url="https://img/updated.png",
        thumbnail_url="https://img/updated-small.png",
        preview_url="https://img/updated-normal.png",
        is_double_faced=False,
    )

    assert updated.payload["id"] == "print-beta"
    assert updated.payload["set"] == "2x2"
    assert updated.payload["collector_number"] == "117"
    assert updated.payload["image_uris"]["png"] == "https://img/updated.png"
    assert "card_faces" not in updated.payload

    canonical = database.get_canonical_print("oracle-bolt")
    assert canonical is not None
    assert canonical.card_id == "print-beta"


def test_delete_card_and_print_remove_related_manifest_rows(tmp_path):
    service, database = _service(tmp_path)
    service.create_card(
        oracle_id="oracle-opt",
        name="Opt",
        layout="normal",
    )
    first = service.create_print(
        card_id="print-opt-a",
        oracle_id="oracle-opt",
        name="Opt",
        set_code="eld",
        collector_number="59",
    )
    second = service.create_print(
        card_id="print-opt-b",
        oracle_id="oracle-opt",
        name="Opt",
        set_code="dom",
        collector_number="60",
    )
    asset = database.store_image_asset(
        b"image-bytes",
        source="test",
        source_url="https://img/opt.png",
    )
    database.upsert_image_record(
        first.card_id,
        variant="default",
        asset_id=asset.asset_id,
        path=None,
        status="stored",
        source="test",
        checksum=asset.checksum,
    )
    database.upsert_image_record(
        second.card_id,
        variant="default",
        asset_id=asset.asset_id,
        path=None,
        status="stored",
        source="test",
        checksum=asset.checksum,
    )

    assert len(service.list_image_manifest().items) == 2

    assert service.delete_print(first.card_id) is True
    assert database.get_print_by_card_id(first.card_id) is None
    assert len(service.list_image_manifest().items) == 1
    canonical = database.get_canonical_print("oracle-opt")
    assert canonical is not None
    assert canonical.card_id == second.card_id

    assert service.delete_card("oracle-opt") is True
    assert service.list_cards().items == []
    assert service.list_prints().items == []
    assert service.list_image_manifest().items == []
    assert service.list_image_assets()


def test_read_only_listing_views_include_images_and_sync_rows(tmp_path):
    service, database = _service(tmp_path)
    service.create_card(
        oracle_id="oracle-ooze",
        name="Scavenging Ooze",
        layout="normal",
    )
    created = service.create_print(
        card_id="print-ooze",
        oracle_id="oracle-ooze",
        name="Scavenging Ooze",
        set_code="tmid",
        collector_number="10",
        image_url="https://img/ooze.png",
    )
    asset = database.store_image_asset(
        b"asset-bytes",
        source="remote_fill",
        source_url="https://img/ooze.png",
    )
    database.upsert_image_record(
        created.card_id,
        variant="default",
        asset_id=asset.asset_id,
        path=None,
        status="stored",
        source="remote_fill",
        checksum=asset.checksum,
    )
    database.upsert_card_payload(
        {
            "id": "print-bulk",
            "oracle_id": "oracle-ooze",
            "name": "Scavenging Ooze",
            "set": "tsoi",
            "collector_number": "8",
            "released_at": "2022-01-01",
            "image_uris": {"png": "https://img/ooze-2.png"},
        },
        source="bulk_sync",
    )

    manifest_rows = service.list_image_manifest()
    sync_rows = service.list_sync_state()
    print_rows = service.list_prints(query="ooze", set_code="tmid")

    assert manifest_rows.items[0].asset_id == asset.asset_id
    assert manifest_rows.items[0].source_url == "https://img/ooze.png"
    assert any(row.source == "bulk_sync" for row in sync_rows)
    assert [row.card_id for row in print_rows.items] == ["print-ooze"]


def test_bulk_download_processes_chunks_and_resumes_from_checkpoint(tmp_path):
    cards = [_print_payload(index) for index in range(150)]
    calls: list[str] = []

    def fake_fetch_json(url: str) -> dict:
        calls.append(url)
        return {
            "object": "list",
            "data": cards,
            "has_more": False,
        }

    def fake_fetch_bytes(_url: str) -> bytes:
        return b"x" * (FIXED_CATALOG_MIN_IMAGE_BYTES + 200)

    service, database = _bulk_service(
        tmp_path,
        fetch_json=fake_fetch_json,
        fetch_bytes=fake_fetch_bytes,
    )

    for index in range(5):
        payload = cards[index]
        database.upsert_card_payload(payload, source="seed")
        asset = database.store_image_asset(
            b"y" * (FIXED_CATALOG_MIN_IMAGE_BYTES + 50),
            source="seed",
            source_url=payload["image_uris"]["png"],
        )
        database.upsert_image_record(
            payload["id"],
            variant="default",
            asset_id=asset.asset_id,
            path=None,
            status="ready",
            source="seed",
            checksum=asset.checksum,
        )

    database.upsert_card_payload(cards[10], source="seed")
    tiny_asset = database.store_image_asset(
        b"tiny",
        source="seed",
        source_url=cards[11]["image_uris"]["png"],
    )
    database.upsert_card_payload(cards[11], source="seed")
    database.upsert_image_record(
        cards[11]["id"],
        variant="default",
        asset_id=tiny_asset.asset_id,
        path=None,
        status="ready",
        source="seed",
        checksum=tiny_asset.checksum,
    )

    first = service.download_fixed_catalog_chunked(max_chunks=1)
    resumed = service.download_fixed_catalog_chunked(max_chunks=1)
    final = service.get_bulk_download_status()

    assert first.status == "running"
    assert first.total_scanned == 100
    assert first.total_skipped == 5
    assert first.total_downloaded == 95
    assert first.page_offset == 100
    assert resumed.status == "completed"
    assert resumed.total_scanned == 150
    assert resumed.total_downloaded == 145
    assert final.completed is True
    assert final.current_page_url is None
    assert final.source == FIXED_CATALOG_SOURCE
    sync_row = database.get_sync_state(FIXED_CATALOG_SOURCE)
    assert sync_row is not None
    assert sync_row["version"] == FIXED_CATALOG_VERSION
    assert calls == [
        build_print_search_url(FIXED_CATALOG_QUERY, include_extras=True),
        build_print_search_url(FIXED_CATALOG_QUERY, include_extras=True),
    ]


def test_bulk_download_persists_partial_progress_when_a_later_page_fails(tmp_path):
    first_page = [_print_payload(index) for index in range(100)]
    first_url = build_print_search_url(FIXED_CATALOG_QUERY, include_extras=True)
    second_url = "https://api.scryfall.com/cards/search?page=2"

    def fake_fetch_json(url: str) -> dict:
        if url == first_url:
            return {
                "object": "list",
                "data": first_page,
                "has_more": True,
                "next_page": second_url,
            }
        raise ValueError("page 2 failed")

    service, _database = _bulk_service(
        tmp_path,
        fetch_json=fake_fetch_json,
        fetch_bytes=lambda _url: b"z" * (FIXED_CATALOG_MIN_IMAGE_BYTES + 200),
    )

    status = service.download_fixed_catalog_chunked()
    persisted = service.get_bulk_download_status()

    assert status.status == "failed"
    assert status.total_scanned == 100
    assert status.total_downloaded == 100
    assert persisted.last_error == "page 2 failed"
    assert persisted.current_page_url == second_url
    assert persisted.completed is False


def test_bulk_download_pause_preserves_resume_checkpoint(tmp_path):
    cards = [_print_payload(index) for index in range(120)]

    def fake_fetch_json(_url: str) -> dict:
        return {
            "object": "list",
            "data": cards,
            "has_more": False,
        }

    service, _database = _bulk_service(
        tmp_path,
        fetch_json=fake_fetch_json,
        fetch_bytes=lambda _url: b"q" * (FIXED_CATALOG_MIN_IMAGE_BYTES + 32),
    )

    first = service.process_bulk_download_chunk()
    paused = service.pause_bulk_download()
    resumed = service.process_bulk_download_chunk()

    assert first.status == "running"
    assert first.page_offset == 100
    assert paused.status == "paused"
    assert paused.page_offset == 100
    assert paused.can_resume is True
    assert resumed.status == "completed"
    assert resumed.total_scanned == 120


def test_bulk_download_callback_pause_stops_mid_chunk_and_can_resume(tmp_path):
    cards = [_print_payload(index) for index in range(5)]
    calls = {"count": 0}

    def fake_fetch_json(_url: str) -> dict:
        return {
            "object": "list",
            "data": cards,
            "has_more": False,
        }

    def should_pause() -> bool:
        calls["count"] += 1
        return calls["count"] >= 2

    service, _database = _bulk_service(
        tmp_path,
        fetch_json=fake_fetch_json,
        fetch_bytes=lambda _url: b"pause-test-bytes" * 400,
    )

    paused = service.process_bulk_download_chunk(should_pause=should_pause)
    resumed = service.process_bulk_download_chunk()

    assert paused.status == "paused"
    assert paused.page_offset == 2
    assert paused.total_scanned == 2
    assert paused.can_resume is True
    assert resumed.status == "completed"
    assert resumed.total_scanned == 5


def test_cards_pagination_returns_counts_and_offsets(tmp_path):
    service, _database = _service(tmp_path)
    for index in range(205):
        service.create_card(
            oracle_id=f"oracle-{index}",
            name=f"Card {index:03d}",
            layout="normal",
        )

    first = service.list_cards(page=1, page_size=100)
    third = service.list_cards(page=3, page_size=100)

    assert first.page == 1
    assert first.total_count == 205
    assert first.total_pages == 3
    assert len(first.items) == 100
    assert third.page == 3
    assert len(third.items) == 5


def test_prints_pagination_filters_before_paginating(tmp_path):
    service, _database = _service(tmp_path)
    service.create_card(
        oracle_id="oracle-bolt",
        name="Lightning Bolt",
        layout="normal",
    )
    service.create_card(
        oracle_id="oracle-opt",
        name="Opt",
        layout="normal",
    )
    for index in range(130):
        service.create_print(
            card_id=f"bolt-{index}",
            oracle_id="oracle-bolt",
            name="Lightning Bolt",
            set_code="lea" if index < 110 else "m11",
            collector_number=str(index),
        )
    for index in range(30):
        service.create_print(
            card_id=f"opt-{index}",
            oracle_id="oracle-opt",
            name="Opt",
            set_code="eld",
            collector_number=str(index),
        )

    filtered = service.list_prints(query="lightning", set_code="lea", page=2, page_size=100)

    assert filtered.total_count == 110
    assert filtered.total_pages == 2
    assert filtered.page == 2
    assert len(filtered.items) == 10
    assert all(item.set_code == "lea" for item in filtered.items)


def test_image_pagination_returns_counts_and_offsets(tmp_path):
    service, database = _service(tmp_path)
    for index in range(205):
        service.create_card(
            oracle_id=f"oracle-image-{index}",
            name=f"Image Card {index:03d}",
            layout="normal",
        )
        created = service.create_print(
            card_id=f"image-print-{index}",
            oracle_id=f"oracle-image-{index}",
            name=f"Image Card {index:03d}",
            set_code="lea",
            collector_number=str(index),
        )
        asset = database.store_image_asset(
            f"image-{index}".encode("utf-8"),
            source="test",
            source_url=f"https://img.test/{index}.png",
        )
        database.upsert_image_record(
            created.card_id,
            variant="default",
            asset_id=asset.asset_id,
            path=None,
            status="ready",
            source="test",
            checksum=asset.checksum,
        )

    manifests = service.list_image_manifest(page=3, page_size=100)
    assets = service.list_image_assets(page=3, page_size=100)

    assert manifests.total_count == 205
    assert manifests.total_pages == 3
    assert manifests.page == 3
    assert len(manifests.items) == 5
    assert assets.total_count == 205
    assert assets.total_pages == 3
    assert assets.page == 3
    assert len(assets.items) == 5
