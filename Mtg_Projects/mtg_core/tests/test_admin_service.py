from __future__ import annotations

from mtg_core.admin_service import CardAdminService
from mtg_core.db import CardDatabase


def _service(tmp_path):
    db_path = tmp_path / "admin.sqlite3"
    database = CardDatabase(str(db_path))
    return CardAdminService(database=database), database


def test_create_update_delete_card(tmp_path):
    service, _database = _service(tmp_path)

    created = service.create_card(
        oracle_id="oracle-alpha",
        name="Lightning Bolt",
        layout="normal",
    )

    assert created.normalized_name == "lightning bolt"
    assert [card.name for card in service.list_cards()] == ["Lightning Bolt"]

    updated = service.update_card(
        "oracle-alpha",
        name="Lightning Bolt Prime",
        layout="split",
    )

    assert updated.name == "Lightning Bolt Prime"
    assert updated.normalized_name == "lightning bolt prime"
    assert service.delete_card("oracle-alpha") is True
    assert service.list_cards() == []


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

    assert len(service.list_image_manifest()) == 2

    assert service.delete_print(first.card_id) is True
    assert database.get_print_by_card_id(first.card_id) is None
    assert len(service.list_image_manifest()) == 1
    canonical = database.get_canonical_print("oracle-opt")
    assert canonical is not None
    assert canonical.card_id == second.card_id

    assert service.delete_card("oracle-opt") is True
    assert service.list_cards() == []
    assert service.list_prints() == []
    assert service.list_image_manifest() == []
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

    assert manifest_rows[0].asset_id == asset.asset_id
    assert manifest_rows[0].source_url == "https://img/ooze.png"
    assert any(row.source == "bulk_sync" for row in sync_rows)
    assert [row.card_id for row in print_rows] == ["print-ooze"]
