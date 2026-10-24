"""All three apps use one editor and persisted artwork selection rules."""
from types import SimpleNamespace

from PyQt6.QtWidgets import QApplication, QDialog

from mtg_core.preferences import ArtworkPreferenceRules
from mtg_core.services import CardService
from mtg_ui import artwork_preferences


def test_shared_editor_save_cancel_and_reload_across_services(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    path = str(tmp_path / 'shared.sqlite3')
    core, editor, printer = [CardService(db_path=path) for _ in range(3)]
    for card_id, set_code in [('old', 'old'), ('preferred', 'new')]:
        core.database.upsert_card_payload({
            'id': card_id, 'oracle_id': 'oracle', 'name': 'Card',
            'set': set_code, 'collector_number': '1', 'lang': 'en',
        })

    def save(dialog):
        dialog.sets.setText('new')
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(artwork_preferences.ArtworkPreferencesDialog, 'exec', save)
    saved = artwork_preferences.edit_artwork_preferences(None, core)
    assert saved.preferred_sets == ('new',)
    for service in (core, editor, printer):
        assert service.get_artwork_preferences() == saved
        assert service.choose_preferred_print('oracle')['id'] == 'preferred'

    def cancel(dialog):
        assert dialog.sets.text() == 'new'
        dialog.sets.setText('old')
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(artwork_preferences.ArtworkPreferencesDialog, 'exec', cancel)
    assert artwork_preferences.edit_artwork_preferences(None, editor) is None
    assert printer.get_artwork_preferences() == saved
    app.processEvents()


def test_app_entry_points_use_the_shared_editor(monkeypatch):
    from mtg_core_gui.window import CoreAdminMainWindow
    from mtg_editor.gui import EditorWindow
    from mtg_ui import print_dialogs

    calls = []
    rules = ArtworkPreferenceRules(minimum_dpi=600)

    def edit(parent, service):
        calls.append(service)
        return rules

    monkeypatch.setattr(artwork_preferences, 'edit_artwork_preferences', edit)
    monkeypatch.setattr(print_dialogs, 'edit_artwork_preferences', edit)
    services = [object(), object(), object()]
    CoreAdminMainWindow.artwork_preferences(SimpleNamespace(
        admin_service=SimpleNamespace(card_service=services[0])))
    EditorWindow.artwork_preferences(SimpleNamespace(service=services[1]))
    dpi, refresh = [], []
    picker = SimpleNamespace(
        _card_service=services[2], _min_dpi=SimpleNamespace(setValue=dpi.append),
        refresh_results=lambda **kwargs: refresh.append(kwargs),
    )
    print_dialogs.HighResPickerDialog._edit_artwork_preferences(picker)
    assert calls == services
    assert picker._preferences == rules
    assert dpi == [600] and refresh == [{'reset_page': True}]
    assert print_dialogs.ArtworkPreferencesDialog is artwork_preferences.ArtworkPreferencesDialog


def test_preference_save_error_is_reported(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    service = CardService(db_path=str(tmp_path / 'shared.sqlite3'))
    before = service.get_artwork_preferences()
    monkeypatch.setattr(artwork_preferences.ArtworkPreferencesDialog, 'exec',
                        lambda dialog: QDialog.DialogCode.Accepted)
    def fail(rules):
        raise OSError('Could not save preferences')
    monkeypatch.setattr(service, 'set_artwork_preferences', fail)
    errors = []
    monkeypatch.setattr(artwork_preferences.QMessageBox, 'critical',
                        lambda *args: errors.append(args[-1]))
    assert artwork_preferences.edit_artwork_preferences(None, service) is None
    assert errors == ['Could not save preferences']
    assert service.get_artwork_preferences() == before
    app.processEvents()
