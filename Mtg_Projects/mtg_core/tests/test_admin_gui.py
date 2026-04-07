from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox

from mtg_core.admin_service import CardAdminService
from mtg_core.db import CardDatabase
from mtg_core.models import BulkDownloadStatus
from mtg_core_gui.window import CoreAdminMainWindow


def _app():
    return QApplication.instance() or QApplication([])


def _spin(app, predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return predicate()


def _window(tmp_path):
    database = CardDatabase(str(tmp_path / "gui.sqlite3"))
    service = CardAdminService(database=database)
    for index in range(130):
        oracle_id = f"oracle-{index}"
        service.create_card(
            oracle_id=oracle_id,
            name=f"Card {index:03d}",
            layout="normal",
        )
        service.create_print(
            card_id=f"print-{index}",
            oracle_id=oracle_id,
            name=f"Card {index:03d}",
            set_code="lea",
            collector_number=str(index),
        )
    return CoreAdminMainWindow(service), service


def test_admin_window_opens_and_cards_tab_populates(tmp_path):
    app = _app()
    window, _service = _window(tmp_path)

    window.show()
    app.processEvents()

    assert window.cards_tab.table.rowCount() == 100
    assert "Page 1 of 2" in window.cards_tab.page_label.text()
    window.centralWidget().setCurrentWidget(window.prints_tab)
    app.processEvents()
    assert window.prints_tab.table.rowCount() == 100
    assert "Page 1 of 2" in window.prints_tab.page_label.text()
    assert "DB:" in window._db_label.text()


def test_selecting_and_saving_cards_and_prints_refreshes_forms(tmp_path, monkeypatch):
    app = _app()
    window, service = _window(tmp_path)

    window.cards_tab.table.selectRow(0)
    app.processEvents()
    assert window.cards_tab.name_edit.text() == "Card 000"

    window.cards_tab._new_card()
    window.cards_tab.name_edit.setText("Opt")
    window.cards_tab.oracle_id_edit.setText("oracle-opt")
    window.cards_tab.layout_edit.setText("normal")
    window.cards_tab._save_card()
    app.processEvents()
    assert service.get_card("oracle-opt") is not None

    window.centralWidget().setCurrentWidget(window.prints_tab)
    app.processEvents()
    window.prints_tab.table.selectRow(0)
    app.processEvents()
    assert window.prints_tab.card_id_edit.text() == "print-0"

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window.prints_tab._delete_print()
    app.processEvents()
    assert service.get_print("print-0") is None


def test_cards_and_prints_support_pagination_controls(tmp_path):
    app = _app()
    window, _service = _window(tmp_path)

    assert window.cards_tab.next_button.isEnabled()
    window.cards_tab._next_page()
    app.processEvents()
    assert "Page 2 of 2" in window.cards_tab.page_label.text()
    assert window.cards_tab.prev_button.isEnabled()

    window.centralWidget().setCurrentWidget(window.prints_tab)
    app.processEvents()
    assert window.prints_tab.next_button.isEnabled()
    window.prints_tab._next_page()
    app.processEvents()
    assert "Page 2 of 2" in window.prints_tab.page_label.text()


def test_filters_reset_tabs_back_to_page_one(tmp_path):
    app = _app()
    window, _service = _window(tmp_path)

    window.cards_tab._next_page()
    app.processEvents()
    assert window.cards_tab.page_label.text().startswith("Page 2")
    window.cards_tab.search_edit.setText("Card 00")
    app.processEvents()
    assert window.cards_tab.page_label.text().startswith("Page 1")

    window.centralWidget().setCurrentWidget(window.prints_tab)
    app.processEvents()
    window.prints_tab._next_page()
    app.processEvents()
    assert window.prints_tab.page_label.text().startswith("Page 2")
    window.prints_tab.set_code_edit.setText("lea")
    app.processEvents()
    assert window.prints_tab.page_label.text().startswith("Page 1")


def test_images_tab_loads_full_asset_bytes_for_preview(tmp_path):
    app = _app()
    window, service = _window(tmp_path)
    payload = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        b"\x1f\x15\xc4\x89"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00"
        b"\xc9\xfe\x92\xef"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    asset_id = service.card_service.store_image_bytes(
        payload,
        extension="png",
        mime_type="image/png",
        source="test",
        source_url="https://img.test/preview.png",
    )

    window.centralWidget().setCurrentWidget(window.images_tab)
    app.processEvents()
    window.images_tab.refresh_views()
    app.processEvents()

    target_row = None
    for row_index in range(window.images_tab.assets_table.rowCount()):
        item = window.images_tab.assets_table.item(row_index, 0)
        if item and item.text() == asset_id:
            target_row = row_index
            break

    assert target_row is not None
    window.images_tab.assets_table.selectRow(target_row)
    app.processEvents()

    assert window.images_tab.asset_preview.pixmap() is not None


def test_images_tab_supports_manifest_and_asset_pagination(tmp_path):
    app = _app()
    window, service = _window(tmp_path)
    for index in range(130):
        asset_id = service.card_service.store_image_bytes(
            f"payload-{index}".encode("utf-8"),
            extension="png",
            mime_type="image/png",
            source="test",
            source_url=f"https://img.test/paged-{index}.png",
        )
        service.card_service.database.upsert_image_record(
            f"print-{index}",
            variant="default",
            asset_id=asset_id,
            path=None,
            status="ready",
            source="test",
            checksum=service.card_service.database.get_image_asset(asset_id).checksum,
        )

    window.centralWidget().setCurrentWidget(window.images_tab)
    app.processEvents()

    assert "Page 1 of 2" in window.images_tab.manifest_page_label.text()
    assert "Page 1 of 2" in window.images_tab.asset_page_label.text()
    assert window.images_tab.manifest_next_button.isEnabled()
    assert window.images_tab.asset_next_button.isEnabled()

    window.images_tab._next_manifest_page()
    window.images_tab._next_asset_page()
    app.processEvents()

    assert "Page 2 of 2" in window.images_tab.manifest_page_label.text()
    assert "Page 2 of 2" in window.images_tab.asset_page_label.text()


def test_sync_tab_download_controls_refresh_status(tmp_path, monkeypatch):
    app = _app()
    window, service = _window(tmp_path)
    states = [
        BulkDownloadStatus(
            source="catalog_download_all_cards",
            query="l:eng game:paper -is:reprint",
            chunk_size=100,
            min_image_bytes=4096,
            status="idle",
            total_scanned=0,
            total_downloaded=0,
            total_skipped=0,
            total_failed=0,
            chunk_number=0,
        ),
        BulkDownloadStatus(
            source="catalog_download_all_cards",
            query="l:eng game:paper -is:reprint",
            chunk_size=100,
            min_image_bytes=4096,
            status="completed",
            total_scanned=100,
            total_downloaded=95,
            total_skipped=5,
            total_failed=0,
            chunk_number=1,
            completed=True,
        ),
    ]

    current = {"status": states[0]}

    monkeypatch.setattr(service, "get_bulk_download_status", lambda: current["status"])
    monkeypatch.setattr(
        service,
        "process_bulk_download_chunk",
        lambda should_pause=None: current.update(status=states[1]) or states[1],
    )
    monkeypatch.setattr(service, "pause_bulk_download", lambda: current["status"])

    window.sync_tab._refresh_download_status()
    assert window.sync_tab.job_status_label.text() == "idle"
    assert window.sync_tab.start_button.isEnabled()

    window.sync_tab._start_download_job()
    assert _spin(app, lambda: window.sync_tab.job_status_label.text() == "completed")

    assert window.sync_tab.job_status_label.text() == "completed"
    assert "downloaded=95" in window.sync_tab.counts_label.text()
    assert window.sync_tab.pause_button.isEnabled() is False


def test_sync_tab_pause_stops_after_current_chunk(tmp_path, monkeypatch):
    app = _app()
    window, service = _window(tmp_path)

    running = BulkDownloadStatus(
        source="catalog_download_all_cards",
        query="l:eng game:paper -is:reprint",
        chunk_size=100,
        min_image_bytes=4096,
        status="running",
        total_scanned=100,
        total_downloaded=100,
        total_skipped=0,
        total_failed=0,
        chunk_number=1,
        page_offset=100,
        current_page_url="page-1",
        next_page_url="page-1",
        last_sync_at=1.0,
    )
    paused = BulkDownloadStatus(
        source="catalog_download_all_cards",
        query="l:eng game:paper -is:reprint",
        chunk_size=100,
        min_image_bytes=4096,
        status="paused",
        total_scanned=100,
        total_downloaded=100,
        total_skipped=0,
        total_failed=0,
        chunk_number=1,
        page_offset=100,
        current_page_url="page-1",
        next_page_url="page-1",
        last_sync_at=2.0,
    )
    current = {"status": running}

    def fake_process(should_pause=None):
        time.sleep(0.05)
        if should_pause is not None and should_pause():
            current["status"] = paused
            return paused
        current["status"] = running
        return running

    def fake_pause():
        current["status"] = paused
        return paused

    monkeypatch.setattr(service, "get_bulk_download_status", lambda: current["status"])
    monkeypatch.setattr(service, "process_bulk_download_chunk", fake_process)
    monkeypatch.setattr(service, "pause_bulk_download", fake_pause)

    window.sync_tab._start_download_job()
    assert _spin(app, lambda: window.sync_tab.is_download_running())

    window.sync_tab._pause_download_job()
    assert _spin(app, lambda: window.sync_tab.job_status_label.text() == "paused")
    assert window.sync_tab.resume_button.isEnabled()


def test_sync_tab_enables_resume_for_stale_running_state(tmp_path, monkeypatch):
    app = _app()
    window, service = _window(tmp_path)
    stale_running = BulkDownloadStatus(
        source="catalog_download_all_cards",
        query="l:eng game:paper -is:reprint",
        chunk_size=100,
        min_image_bytes=4096,
        status="running",
        total_scanned=100,
        total_downloaded=100,
        total_skipped=0,
        total_failed=0,
        chunk_number=1,
        page_offset=100,
        current_page_url="page-1",
        next_page_url="page-1",
        last_sync_at=1.0,
    )

    monkeypatch.setattr(service, "get_bulk_download_status", lambda: stale_running)

    window.sync_tab._refresh_download_status()

    assert window.sync_tab.job_status_label.text() == "paused"
    assert window.sync_tab.resume_button.isEnabled()
    assert window.sync_tab.start_button.isEnabled() is False


def test_closing_window_with_stale_running_state_allows_exit(tmp_path, monkeypatch):
    app = _app()
    window, service = _window(tmp_path)
    window.show()
    stale_running = BulkDownloadStatus(
        source="catalog_download_all_cards",
        query="l:eng game:paper -is:reprint",
        chunk_size=100,
        min_image_bytes=4096,
        status="running",
        total_scanned=100,
        total_downloaded=100,
        total_skipped=0,
        total_failed=0,
        chunk_number=1,
        page_offset=100,
        current_page_url="page-1",
        next_page_url="page-1",
        last_sync_at=1.0,
    )
    paused = BulkDownloadStatus(
        source="catalog_download_all_cards",
        query="l:eng game:paper -is:reprint",
        chunk_size=100,
        min_image_bytes=4096,
        status="paused",
        total_scanned=100,
        total_downloaded=100,
        total_skipped=0,
        total_failed=0,
        chunk_number=1,
        page_offset=100,
        current_page_url="page-1",
        next_page_url="page-1",
        last_sync_at=2.0,
    )
    current = {"status": stale_running}

    monkeypatch.setattr(service, "get_bulk_download_status", lambda: current["status"])
    monkeypatch.setattr(
        service,
        "pause_bulk_download",
        lambda: current.update(status=paused) or paused,
    )

    window.close()

    assert _spin(app, lambda: not window.isVisible())


def test_closing_window_while_running_pauses_and_then_closes(tmp_path, monkeypatch):
    app = _app()
    window, service = _window(tmp_path)
    window.show()

    running = BulkDownloadStatus(
        source="catalog_download_all_cards",
        query="l:eng game:paper -is:reprint",
        chunk_size=100,
        min_image_bytes=4096,
        status="running",
        total_scanned=100,
        total_downloaded=100,
        total_skipped=0,
        total_failed=0,
        chunk_number=1,
        page_offset=100,
        current_page_url="page-1",
        next_page_url="page-1",
        last_sync_at=1.0,
    )
    paused = BulkDownloadStatus(
        source="catalog_download_all_cards",
        query="l:eng game:paper -is:reprint",
        chunk_size=100,
        min_image_bytes=4096,
        status="paused",
        total_scanned=100,
        total_downloaded=100,
        total_skipped=0,
        total_failed=0,
        chunk_number=1,
        page_offset=100,
        current_page_url="page-1",
        next_page_url="page-1",
        last_sync_at=2.0,
    )
    current = {"status": running}

    def fake_process(should_pause=None):
        time.sleep(0.05)
        if should_pause is not None and should_pause():
            current["status"] = paused
            return paused
        current["status"] = running
        return running

    def fake_pause():
        current["status"] = paused
        return paused

    monkeypatch.setattr(service, "get_bulk_download_status", lambda: current["status"])
    monkeypatch.setattr(service, "process_bulk_download_chunk", fake_process)
    monkeypatch.setattr(service, "pause_bulk_download", fake_pause)

    window.sync_tab._start_download_job()
    assert _spin(app, lambda: window.sync_tab.is_download_running())

    window.close()
    assert _spin(app, lambda: not window.isVisible())
