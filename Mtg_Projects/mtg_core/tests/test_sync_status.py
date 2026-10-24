"""Compatibility coverage for persisted bulk-download checkpoints."""

import json

import pytest

from mtg_core.models import BulkDownloadStatus
from mtg_core.services import CardService, FIXED_CATALOG_SOURCE, FIXED_CATALOG_VERSION
from mtg_core.sync_status import SyncStatus


@pytest.mark.parametrize("value", [*SyncStatus, "future-checkpoint"])
def test_checkpoint_strings_round_trip(tmp_path, value):
    service = CardService(db_path=str(tmp_path / "sync.sqlite3"))
    service.database.upsert_sync_state(
        FIXED_CATALOG_SOURCE,
        version=FIXED_CATALOG_VERSION,
        last_sync_at=123.0,
        payload={"status": str(value), "page_offset": 7, "total_scanned": 12},
    )

    loaded = service.get_bulk_download_status()
    assert loaded.status == value
    if isinstance(value, SyncStatus):
        assert loaded.status is value
    service._save_bulk_download_status(loaded, chunk_number=2)

    row = service.database.get_sync_state(FIXED_CATALOG_SOURCE)
    payload = json.loads(row["payload_json"])
    assert payload["status"] == str(value)
    assert payload["page_offset"] == 7
    assert payload["total_scanned"] == 12
    assert payload["chunk_number"] == 2
    assert service.get_bulk_download_status().status == value


@pytest.mark.parametrize("value", [*SyncStatus, "future-checkpoint"])
@pytest.mark.parametrize("completed", [False, True])
def test_legacy_constructor_and_resume_behavior(value, completed):
    status = BulkDownloadStatus(
        source="test",
        query="test",
        chunk_size=1,
        min_image_bytes=1,
        status=str(value),
        total_scanned=0,
        total_downloaded=0,
        total_skipped=0,
        total_failed=0,
        chunk_number=0,
        completed=completed,
    )
    assert status.is_running == (value == SyncStatus.RUNNING)
    assert status.can_resume == (
        value in {SyncStatus.PAUSED, SyncStatus.FAILED} and not completed
    )
    assert json.loads(json.dumps({"status": status.status})) == {"status": str(value)}


def test_missing_checkpoint_status_defaults(tmp_path):
    service = CardService(db_path=str(tmp_path / "sync.sqlite3"))
    assert service.get_bulk_download_status().status is SyncStatus.IDLE
    service.database.upsert_sync_state(
        FIXED_CATALOG_SOURCE,
        version=FIXED_CATALOG_VERSION,
        last_sync_at=123.0,
        payload={},
    )
    assert service.get_bulk_download_status().status is SyncStatus.READY
