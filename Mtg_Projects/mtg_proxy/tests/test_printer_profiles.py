from copy import deepcopy
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6 import QtWidgets
import pytest
from models import ProjectState
from services import printer_profiles as profiles, layout_service
from printer_profile_dialog import PrinterProfileDialog

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def storage(tmp_path, monkeypatch):
    target = tmp_path / 'printer_profiles.json'
    monkeypatch.setattr(profiles, 'path', lambda: target)
    return target


def test_profile_persistence_application_and_independent_projects(storage):
    source = ProjectState.from_dict({'pagesize': 'A4', 'orient': 'Landscape',
        'backside_offset': '-1.5', 'backside_enabled': True,
        'backside_separate_file': True, 'backside_reverse_page_order': True})
    settings = profiles.capture(source, 'Short edge')
    profiles.save_all({'Office printer': settings})
    assert profiles.load() == {'Office printer': settings}
    target = ProjectState.from_dict({'cards': {'a': 2}, 'filename': 'Keep me'})
    profiles.apply(target, profiles.load()['Office printer'])
    assert target.cards == {'a': 2}
    assert target.filename == 'Keep me'
    for data in (target.to_dict(), target.to_persisted_dict()):
        reloaded = ProjectState.from_dict(data)
        assert profiles.capture(reloaded, reloaded.printer_duplex) == settings
    profiles.save_all({})
    assert profiles.load() == {}
    assert target.backside_offset == '-1.5'


def test_bad_profile_storage_is_not_overwritten(storage):
    storage.write_text('{broken', encoding='utf-8')
    with pytest.raises(ValueError):
        profiles.load()
    assert storage.read_text() == '{broken'


def test_apply_reconciles_layout_and_rejects_impossible_footprint(storage):
    state = ProjectState.from_dict({'cards': {'wide': 1},
        'oversized_enabled': True, 'oversized': {'wide': True}})
    items, _ = layout_service.resolve(state, 3, 3)
    items[0].update(page=2, row=2, column=1)
    state.manual_layout = layout_service.record(items)
    settings = profiles.capture(state, 'Long edge')
    settings['orient'] = 'Landscape'
    assert profiles.apply(state, settings) == 1
    before = deepcopy(state.to_dict())
    settings['pagesize'] = 'A5'
    settings['orient'] = 'Portrait'
    # Increase bleed enough that A5 cannot fit a two-slot card.
    state.bleed_edge = '10'
    before = deepcopy(state.to_dict())
    with pytest.raises(ValueError):
        profiles.apply(state, settings)
    assert state.to_dict() == before


def test_dialog_save_cancel_apply_delete(storage, monkeypatch):
    state = ProjectState()
    dialog = PrinterProfileDialog(None, state)
    monkeypatch.setattr(QtWidgets.QInputDialog, 'getText', lambda *a: ('Desk printer', True))
    dialog.duplex.setCurrentText('Short edge')
    dialog.save_current()
    assert 'Desk printer' in profiles.load()
    state.backside_offset = '2'
    monkeypatch.setattr(QtWidgets.QMessageBox, 'question', lambda *a: QtWidgets.QMessageBox.StandardButton.No)
    dialog.apply_selected()
    assert state.backside_offset == '2'
    assert not dialog.applied
    monkeypatch.setattr(QtWidgets.QMessageBox, 'question', lambda *a: QtWidgets.QMessageBox.StandardButton.Yes)
    dialog.apply_selected()
    assert dialog.applied
    assert state.backside_offset == '0'
    assert state.printer_duplex == 'Short edge'
    dialog.delete_selected()
    assert profiles.load() == {}
    dialog.deleteLater()
    APP.processEvents()


def test_profile_write_failure_keeps_library(storage, monkeypatch):
    dialog = PrinterProfileDialog(None, ProjectState())
    warnings = []
    monkeypatch.setattr(QtWidgets.QMessageBox, 'warning', lambda *a: warnings.append(a))
    def fail(*args, **kwargs):
        raise OSError('disk full')
    monkeypatch.setattr(profiles, 'write_json_atomic', fail)
    dialog.write({'test': profiles.capture(dialog.state, 'Long edge')})
    assert dialog.profiles == {}
    assert warnings
    dialog.deleteLater()
    APP.processEvents()
