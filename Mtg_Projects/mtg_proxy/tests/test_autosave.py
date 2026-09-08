import os
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6 import QtGui, QtWidgets, QtTest
import pytest
import main_window
from models import ProjectState

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class Dashboard(QtWidgets.QWidget):
    def __init__(self, application):
        super().__init__()

    def refresh_projects(self):
        pass

    def import_project(self):
        pass


class Editor(QtWidgets.QLabel):
    def set_project_name(self, name):
        self.setText(name)


@pytest.fixture
def window(monkeypatch):
    monkeypatch.setattr(main_window, 'ProjectDashboardPage', Dashboard)
    warnings, writes = [], []
    application = SimpleNamespace(warn_nonfatal=lambda *args: warnings.append(args))
    shell = main_window.AppShellWindow(application)
    state = ProjectState.from_dict({'cards': {'a': 1}})
    shell._set_active_editor(Editor(), dict(state=state, managed=True, project_id='test',
        display_name='[Greg] Group Hug', project_path='test.json', img_dict={}))
    def save(project_id, state):
        writes.append((project_id, state.to_persisted_dict()))
        return dict(path='test.json', display_name='[Greg] Group Hug', thumbnail_card=None)
    monkeypatch.setattr(main_window.project_library, 'save_project', save)
    shell.writes, shell.warnings = writes, warnings
    yield shell
    shell._clear_active_session()
    shell.close()
    shell.deleteLater()
    APP.processEvents()


def test_dirty_marker_and_debounced_autosave(window):
    state = window._active_session['state']
    assert not window._project_dirty
    state.set_card_count('a', 2)
    window.project_changed()
    assert window._editor_page.text() == '[Greg] Group Hug*'
    assert window.windowTitle().startswith('[Greg] Group Hug*')
    assert window._autosave_timer.isActive()
    assert window._autosave_timer.interval() == 2000
    assert window.writes == []
    # Use a short actual Qt timer for deterministic event-loop coverage.
    window._autosave_timer.start(10)
    QtTest.QTest.qWait(50)
    assert len(window.writes) == 1
    assert window.writes[0][1]['card_entries'][0]['count'] == 2
    assert window._editor_page.text() == '[Greg] Group Hug'
    assert not window._project_dirty
    window._autosave_managed_session()
    assert len(window.writes) == 1


def test_idle_poll_does_not_copy_or_serialize_project(window, monkeypatch):
    def unexpected(*args):
        raise AssertionError('Idle polling must not copy or serialize')
    monkeypatch.setattr(main_window, 'deepcopy', unexpected)
    monkeypatch.setattr(window, '_project_snapshot', unexpected)
    for _ in range(20):
        window.project_changed()
    assert window.writes == []


def test_edit_at_timeout_restarts_debounce_and_revert_clears_star(window):
    state = window._active_session['state']
    state.set_card_count('a', 2)
    window.project_changed()
    state.set_card_count('a', 3)
    window._autosave_if_idle()
    assert window.writes == []
    assert window._autosave_timer.isActive()
    state.set_card_count('a', 1)
    window.project_changed()
    assert not window._project_dirty
    assert not window._autosave_timer.isActive()


def test_poll_detects_settings_and_layout_without_widget_refresh(window):
    state = window._active_session['state']
    state.backside_offset = '1.5'
    state.manual_layout = {'version': 1, 'placements': []}
    window._project_watch_timer.start(10)
    QtTest.QTest.qWait(50)
    assert window._project_dirty
    window.save_active_project(state)
    assert not window._project_dirty
    assert not window._autosave_timer.isActive()
    assert window.writes[0][1]['backside_offset'] == '1.5'
    assert window.writes[0][1]['manual_layout'] == state.manual_layout


def test_failed_autosave_keeps_dirty_and_retries_without_modal(window, monkeypatch):
    state = window._active_session['state']
    state.set_card_count('a', 2)
    window.project_changed()
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(main_window.project_library, 'save_project', fail)
    window._autosave_managed_session()
    assert window._project_dirty
    assert window._editor_page.text().endswith('*')
    assert window._autosave_timer.interval() == 10000
    assert window.warnings == []
    assert 'Save failed' in window.statusBar().currentMessage()
    assert not window._leave_active_session()
    assert window._active_session is not None
    event = QtGui.QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()


def test_new_draft_autosaves_recovery_without_prompting_for_a_name(window, monkeypatch):
    state = window._active_session['state']
    window._set_active_editor(Editor(), dict(state=state, managed=False, is_draft=True,
        display_name='Unsaved Draft', project_id=None, project_path=None))
    monkeypatch.setattr(main_window.QInputDialog, 'getText', lambda *args: pytest.fail('Unexpected prompt'))
    recovery_writes = []
    monkeypatch.setattr(main_window.project_library, 'save_draft_project',
                        lambda value: recovery_writes.append(value.to_persisted_dict()))
    state.set_card_count('a', 2)
    window.project_changed()
    window._autosave_managed_session()
    assert window._editor_page.text() == 'Unsaved Draft*'
    assert window.writes == []
    assert recovery_writes[0]['card_entries'][0]['count'] == 2
    assert not window._autosave_timer.isActive()


def test_busy_work_defers_autosave_and_close_flushes_changes(window):
    state = window._active_session['state']
    state.set_card_count('a', 2)
    window.project_changed()
    window.setEnabled(False)
    window._autosave_managed_session()
    assert window.writes == []
    window.setEnabled(True)
    event = QtGui.QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()
    assert len(window.writes) == 1
    assert not window._project_dirty


def test_switching_projects_cancels_pending_save(window):
    old = window._active_session['state']
    old.set_card_count('a', 2)
    window.project_changed()
    assert window._leave_active_session()
    assert len(window.writes) == 1
    assert not window._autosave_timer.isActive()
    window._set_active_editor(Editor(), dict(state=ProjectState(), managed=True, project_id='other',
        display_name='Other', project_path='other.json'))
    window._autosave_if_idle()
    assert len(window.writes) == 1
    assert window._editor_page.text() == 'Other'


def test_first_save_names_draft_and_enables_autosave(window, monkeypatch):
    state = window._active_session['state']
    window._set_active_editor(Editor(), dict(state=state, managed=False, is_draft=True,
        display_name='Unsaved Draft', project_id=None, project_path=None))
    monkeypatch.setattr(main_window.QInputDialog, 'getText', lambda *args: ('My deck', True))
    monkeypatch.setattr(main_window.project_library, 'materialize_draft_project', lambda *args, **kwargs:
        dict(id='named', path='named.json', display_name='My deck'))
    window.save_active_project(state)
    assert window._editor_page.text() == 'My deck'
    assert not window._project_dirty
    state.set_card_count('a', 3)
    window.project_changed()
    assert window._editor_page.text() == 'My deck*'
    assert window._autosave_timer.isActive()


def test_card_print_flags_survive_autosave_observation(window):
    import editor_widgets
    from PyQt6 import QtCore
    state = window._active_session['state']
    card = SimpleNamespace(_card_name='a')
    editor_widgets.CardWidget.toggle_oversized(card, state, QtCore.Qt.CheckState.Checked)
    editor_widgets.CardWidget.toggle_short_edge(card, state, QtCore.Qt.CheckState.Checked)
    window.project_changed()
    assert window._project_dirty
    window._autosave_managed_session()
    entry = window.writes[0][1]['card_entries'][0]
    assert entry['oversized']
    assert entry['backside_short_edge']
    assert state.oversized['a']


def test_modal_dialog_defers_autosave(window, monkeypatch):
    state = window._active_session['state']
    state.set_card_count('a', 2)
    window.project_changed()
    monkeypatch.setattr(main_window.QApplication, 'activeModalWidget', lambda: object())
    window._autosave_if_idle()
    assert window.writes == []
    assert window._project_dirty
    assert window._autosave_timer.isActive()
