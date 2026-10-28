"""Offline update highlights and acknowledgment lifecycle (executed by CI)."""
from PyQt6 import QtWidgets as W
from mtg_ui import whats_new as ui
from mtg_ui.release_notes import load_notes


class Settings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=''):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value

    def sync(self):
        pass


def test_skipped_notes_are_combined_and_safe():
    releases = [
        {'version': '0.3.2-alpha.1', 'features': ['Shared', 'Older']},
        {'version': 'invalid', 'features': ['Invalid']},
        {'version': '0.3.4-alpha.1', 'features': ['Future']},
        {'version': '0.3.3-alpha.1', 'features': ['New', ' shared '], 'fixes': None},
    ]
    notes = load_notes('0.3.3-alpha.1', '0.3.1-alpha.1', releases)
    assert notes['groups']['features'] == ['New', 'shared', 'Older']
    assert notes['versions'] == ['0.3.3-alpha.1', '0.3.2-alpha.1']
    assert load_notes('0.3.3-alpha.1', releases=releases)['versions'] == ['0.3.3-alpha.1']


def test_fresh_install_update_dismissal_and_manual_access(monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    settings = Settings()
    monkeypatch.setattr(ui.C, 'QSettings', lambda *args: settings)
    monkeypatch.setattr(ui, 'APP_VERSION', '0.3.59-alpha.1')
    ui.WhatsNew(app).startup()
    assert not settings.value('whatsNew/acknowledgedVersion')
    monkeypatch.setattr(ui, 'APP_VERSION', '0.3.60-alpha.1')
    controller = ui.WhatsNew(app)
    controller.show()  # Manual viewing does not consume the automatic notice.
    controller.dialog.reject()
    assert not settings.value('whatsNew/acknowledgedVersion')
    controller.startup()
    assert controller.dialog is not None
    controller.dialog.reject()
    assert settings.value('whatsNew/acknowledgedVersion') == ui.APP_VERSION
    reopened = ui.WhatsNew(app)
    reopened.startup()
    assert reopened.dialog is None


def test_interrupted_display_is_retried_and_missing_notes_are_quiet(monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    settings = Settings()
    settings.setValue('whatsNew/lastSuccessfulVersion', '0.3.59-alpha.1')
    monkeypatch.setattr(ui.C, 'QSettings', lambda *args: settings)
    monkeypatch.setattr(ui, 'APP_VERSION', '0.3.60-alpha.1')
    controller = ui.WhatsNew(app)
    shown = []
    controller.show = lambda *args, **kwargs: shown.append(kwargs)
    controller.startup()
    retry = ui.WhatsNew(app)
    retry.show = controller.show
    retry.startup()
    assert len(shown) == 2
    monkeypatch.setattr(ui, 'load_notes', lambda *args: {'groups': {}})
    quiet = ui.WhatsNew(app)
    quiet.show = controller.show
    quiet.startup()
    assert len(shown) == 2
