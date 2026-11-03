"""UI scheduling and persistence coverage for CI; no engine is simulated here."""

from dataclasses import replace
import pytest
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W, sip
from mtg_play.priority_ui import PriorityControls
from mtg_play.tests.test_priority import priority_view


class Session(C.QObject):
    interactionPending = C.pyqtSignal()
    viewCleared = C.pyqtSignal()
    stopped = C.pyqtSignal()
    commandFinished = C.pyqtSignal(object)
    active = True
    closing = busy = needs_recovery = False

    def __init__(self):
        super().__init__()
        self.calls = []

    def submit(self, view, method, *args):
        self.calls.append((view, method, args))
        self.interactionPending.emit()
        return True


@pytest.fixture
def controls(tmp_path):
    app = W.QApplication.instance() or W.QApplication([])
    parent = W.QWidget()
    session = Session()
    settings = C.QSettings(str(tmp_path / "priority.ini"), C.QSettings.Format.IniFormat)
    controls = PriorityControls(session, "one", parent, settings=settings)
    yield controls, session, settings
    controls.reset()
    parent.deleteLater()
    app.processEvents()


def test_registered_hold_cancels_scheduled_pass(controls):
    ui, session, _ = controls
    ui.observe(priority_view())
    assert ui.timer.isActive()
    ui.hold_next()
    ui._automatic_pass()
    assert not session.calls and not ui.timer.isActive()


def test_application_filter_is_harmless_after_parent_native_deletion(tmp_path):
    app = W.QApplication.instance() or W.QApplication([])
    parent = W.QWidget()
    session = Session()
    settings = C.QSettings(
        str(tmp_path / "deleted-priority.ini"), C.QSettings.Format.IniFormat
    )
    ui = PriorityControls(session, "one", parent, settings=settings)
    parent.deleteLater()
    app.sendPostedEvents(None, C.QEvent.Type.DeferredDelete)
    assert sip.isdeleted(ui)
    assert ui.eventFilter(app, C.QEvent(C.QEvent.Type.User)) is False
    key = G.QKeyEvent(
        C.QEvent.Type.KeyPress,
        C.Qt.Key.Key_Control,
        C.Qt.KeyboardModifier.ControlModifier,
    )
    assert ui.eventFilter(app, key) is False
    assert not session.calls


def test_duplicate_timer_and_stale_view_never_submit_twice(controls):
    ui, session, _ = controls
    view = priority_view()
    ui.observe(view)
    ui._automatic_pass()
    assert session.calls == [(view, "perform", ("pass",))]
    ui.observe(view)
    ui._automatic_pass()
    assert len(session.calls) == 1


def test_cancel_until_response_cancels_default_automatic_pass_too(controls):
    ui, session, _ = controls
    ui.observe(priority_view())
    ui.pass_until_response()
    assert ui.until.text() == "Cancel passing"
    ui.pass_until_response()
    ui._automatic_pass()
    assert not session.calls


def test_shortcuts_never_advance_the_explicit_turn_boundary(controls, monkeypatch):
    ui, session, _ = controls
    monkeypatch.setattr(ui, "_keyboard_allowed", lambda: True)
    ui.observe(replace(priority_view(), step="POSTCOMBAT_MAIN"))
    ui._key_action("pass")
    ui._key_action("until")
    ui._automatic_pass()
    assert not session.calls


def test_preferences_persist_but_temporary_state_does_not(controls):
    ui, _, settings = controls
    ui.observe(priority_view())
    ui.full.setChecked(True)
    ui.automatic.setChecked(False)
    ui.hold_next()
    ui.policy.stop("one", "own", "DRAW")
    ui.reset()
    assert settings.value("one/full_control", type=bool)
    assert not settings.value("one/automatic", type=bool)
    state = ui.policy.seat("one")
    assert state.full_control and not state.automatic
    assert not state.temporary and not state.stops


def test_pending_close_and_failed_session_prevent_queued_pass(controls):
    ui, session, _ = controls
    for flag in ("closing", "busy", "needs_recovery"):
        ui.observe(priority_view())
        setattr(session, flag, True)
        ui._automatic_pass()
        assert not session.calls
        setattr(session, flag, False)
    ui.suspend()
    ui._automatic_pass()
    assert not session.calls
