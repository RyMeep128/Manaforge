"""The audit completes without implicitly reclaiming any artwork."""

import os
from pathlib import Path
import time

from PyQt6 import QtWidgets as W

from mtg_core.services import CardService
from mtg_ui.artwork_storage import ArtworkStorageDialog
from mtg_ui.jobs import JobQueue


def test_audit_requires_explicit_review_before_reclaiming(tmp_path):
    app = W.QApplication.instance() or W.QApplication([])
    root = tmp_path / "images"
    service = CardService(db_path=str(tmp_path / "cards.sqlite3"), image_root=str(root))
    service.database.image_storage_root = root / "assets"
    service.database.upsert_card_payload(
        dict(id="card", name="Card", set="tst", collector_number="1")
    )
    asset = service.store_image_bytes(b"artwork", source="scryfall")
    canonical = Path(service.materialize_image_asset(asset))
    legacy = Path(
        service.materialize_image_asset(asset, output_root=str(root / "mtg_core_cache"))
    )
    checksum = service.database.get_image_asset(asset).checksum
    service.database.upsert_image_record(
        "card",
        asset_id=asset,
        path=str(legacy),
        status="ready",
        source="scryfall",
        checksum=checksum,
    )
    jobs = JobQueue()
    dialog = ArtworkStorageDialog(None, service, jobs)
    assert not dialog.reclaim_button.isEnabled()
    dialog.audit()
    deadline = time.monotonic() + 5
    while jobs.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.001)
    app.processEvents()
    assert not jobs.busy
    assert dialog.reclaim_button.isEnabled()
    assert "Verified duplicates: 1" in dialog.review.toPlainText()
    assert dialog.progress.isHidden()
    assert not os.path.samefile(canonical, legacy)
    dialog.reject()
