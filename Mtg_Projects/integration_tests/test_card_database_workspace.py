"""Workspace lifecycle regressions; tests run only in CI."""

import threading
import time

from PyQt6 import QtWidgets as W

from mtg_core.datasets import InstallationState
from mtg_core.installation import InstallationEngine
from mtg_core.services import CardService
from mtg_ui.card_database import CardDatabaseWorkspace
from mtg_ui.jobs import JobQueue


def drain(app, queue):
    deadline = time.monotonic() + 5
    while queue.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.001)
    app.processEvents()
    assert not queue.busy


def test_workspace_close_and_tab_navigation_keep_shared_job_running(tmp_path):
    app = W.QApplication.instance() or W.QApplication([])
    service = CardService(
        db_path=str(tmp_path / "cards.sqlite3"), image_root=str(tmp_path / "images")
    )
    engine = InstallationEngine(
        InstallationState(tmp_path / "state.sqlite3"), service=service
    )
    jobs = JobQueue()
    window = CardDatabaseWorkspace(engine=engine, jobs=jobs)
    stop = threading.Event()
    cancellation = []

    def work(cancel, report):
        stop.wait(5)
        cancellation.append(cancel.is_set())

    try:
        window.start_job("artwork_selection", work)
        app.processEvents()
        window.browser.search.setText("o:draw")
        window.tabs.setCurrentIndex(1)
        window.tabs.setCurrentIndex(0)
        assert window.browser.search.text() == "o:draw"
        assert window.tabs.count() == 3
        window.reject()
        assert jobs.busy
    finally:
        stop.set()
        window.browser.timer.stop()
        drain(app, jobs)
        drain(app, window.browser.reads)
        drain(app, window.summary_jobs)
    assert cancellation == [False]


def test_download_coordination_rejects_second_operation(tmp_path, monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    service = CardService(db_path=str(tmp_path / "cards.sqlite3"))
    engine = InstallationEngine(
        InstallationState(tmp_path / "state.sqlite3"), service=service
    )
    jobs = JobQueue()
    window = CardDatabaseWorkspace(engine=engine, jobs=jobs)
    stop = threading.Event()
    jobs.submit(lambda cancel, report: stop.wait(5))
    monkeypatch.setattr(
        W.QMessageBox,
        "question",
        lambda *args: (_ for _ in ()).throw(
            AssertionError("Busy work must not prompt")
        ),
    )
    try:
        window.request_download("scope", lambda cancel, report: None)
        assert "running" in window.status.text()
    finally:
        stop.set()
        window.browser.timer.stop()
        drain(app, jobs)
        drain(app, window.browser.reads)
        drain(app, window.summary_jobs)
