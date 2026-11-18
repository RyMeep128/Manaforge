import threading
import time
from PyQt6 import QtCore as C, QtWidgets as W

from mtg_ui import xmage_updates as ui


def drain(app, condition):
    deadline = time.monotonic() + 5
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.001)
    assert condition()


def test_shared_engine_panels_check_off_thread_and_offer_explicit_install(monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    manifest = dict(component_version="1.0.1-alpha.1", size=1024**2)
    monkeypatch.setattr(ui.service, "installed_manifest", lambda: dict(component_version="1.0.0-alpha.1"))
    updates = ui.EngineUpdates(app)
    monkeypatch.setattr(app, "_xmage_updates", updates, raising=False)
    checks, installs = [], []

    def check(**kwargs):
        assert C.QThread.currentThread() != app.thread()
        checks.append(True)
        return manifest

    def install(offer, **kwargs):
        assert C.QThread.currentThread() != app.thread()
        installs.append(offer)
        return offer

    monkeypatch.setattr(ui.service, "check", check)
    monkeypatch.setattr(ui.service, "install", install)
    first, second = ui.XmageUpdatePanel(), ui.XmageUpdatePanel()
    first.check.click()
    drain(app, lambda: updates.worker is None)
    assert checks == [True] and installs == []
    assert first.updates is second.updates
    assert "1.0.1-alpha.1" in second.status.text()
    second.install.click()
    drain(app, lambda: updates.worker is None)
    assert installs == [manifest]
    assert "Installed: 1.0.1-alpha.1" in first.status.text()
    first.deleteLater()
    second.deleteLater()
    updates.deleteLater()
    app.processEvents()


def test_engine_cancel_is_cooperative_and_preserves_installed_version(monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    monkeypatch.setattr(ui.service, "installed_manifest", lambda: dict(component_version="1.0.0-alpha.1"))
    updates = ui.EngineUpdates(app)
    started = threading.Event()

    def check(*, cancel):
        started.set()
        if not cancel.wait(5):
            raise ValueError("Cancellation did not arrive")
        raise ui.DownloadCancelled()

    monkeypatch.setattr(ui.service, "check", check)
    updates.start("check")
    drain(app, started.is_set)
    updates.start("check")
    drain(app, lambda: updates.worker is None)
    assert "Cancelled" in updates.message
    assert updates.installed_version == "1.0.0-alpha.1"
    updates.deleteLater()
    app.processEvents()
