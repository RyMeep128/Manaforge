from PyQt6 import QtWidgets as W
from mtg_ui.loading import _Activity


def test_background_activity_does_not_cover_result_message(monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    window = W.QWidget()
    message = W.QMessageBox(window)
    activity = _Activity(app)
    monkeypatch.setattr(W.QApplication, 'activeModalWidget', lambda: None)
    monkeypatch.setattr(W.QApplication, 'activeWindow', lambda: window)
    activity.begin()
    assert not activity.indicator.isHidden()
    monkeypatch.setattr(W.QApplication, 'activeModalWidget', lambda: message)
    activity.refresh()
    assert activity.indicator.isHidden()
    assert activity.count == 1
    monkeypatch.setattr(W.QApplication, 'activeModalWidget', lambda: None)
    activity.refresh()
    assert not activity.indicator.isHidden()
    activity.end()
    activity.deleteLater()
    window.deleteLater()
    app.processEvents()


def test_late_refresh_cannot_show_idle_indicator(monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    window = W.QWidget()
    activity = _Activity(app)
    monkeypatch.setattr(W.QApplication, 'activeModalWidget', lambda: None)
    monkeypatch.setattr(W.QApplication, 'activeWindow', lambda: window)
    activity.begin()
    activity.end()
    activity.refresh()
    assert activity.count == 0
    assert activity.indicator.isHidden()
    activity.deleteLater()
    window.deleteLater()
    app.processEvents()
