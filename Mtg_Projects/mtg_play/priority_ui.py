"""Cancelable UI scheduling around the pure priority policy and public session API."""

from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from .priority import PriorityController, STEPS, opportunity, turn_boundary


class PriorityControls(W.QWidget):
    def __init__(self, session, seat, parent=None, *, settings=None):
        super().__init__(parent)
        self.session, self.seat_id = session, seat
        self.policy = PriorityController()
        self.settings = settings or C.QSettings("Manaforge", "PlayPriority")
        state = self.policy.seat(seat)
        state.automatic = self.settings.value(f"{seat}/automatic", True, type=bool)
        state.full_control = self.settings.value(
            f"{seat}/full_control", False, type=bool
        )
        self.view = None
        self.timer = C.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(180)
        self.timer.timeout.connect(self._automatic_pass)
        rows = W.QVBoxLayout(self)
        rows.setContentsMargins(0, 0, 0, 0)
        top = W.QHBoxLayout()
        self.indicator = W.QLabel("Automatic priority")
        self.indicator.setTextFormat(C.Qt.TextFormat.PlainText)
        top.addWidget(self.indicator, 1)
        self.until = W.QPushButton("Pass Until Response")
        self.until.setToolTip(
            "Pass uninteresting priority this turn. Stops at decisions, playable actions and turn boundaries."
        )
        self.until.clicked.connect(self.pass_until_response)
        top.addWidget(self.until)
        self.menu_button = W.QToolButton()
        self.menu_button.setText("Priority controls")
        self.menu_button.setPopupMode(W.QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = W.QMenu(self.menu_button)
        self.automatic = menu.addAction("Automatic priority")
        self.automatic.setCheckable(True)
        self.automatic.setChecked(state.automatic)
        self.automatic.toggled.connect(self._automatic_changed)
        self.full = menu.addAction("Full Control")
        self.full.setCheckable(True)
        self.full.setChecked(state.full_control)
        self.full.toggled.connect(self._full_changed)
        menu.addAction("Hold next priority", self.hold_next)
        self.recurring = menu.addAction("Make new stops recurring")
        self.recurring.setCheckable(True)
        menu.addAction("Configure shortcuts...", self.configure_shortcuts)
        menu.aboutToShow.connect(self.timer.stop)
        menu.aboutToHide.connect(lambda: C.QTimer.singleShot(0, self._reconsider))
        self.menu_button.setMenu(menu)
        top.addWidget(self.menu_button)
        rows.addLayout(top)
        timeline = W.QHBoxLayout()
        self.scope = W.QComboBox()
        self.scope.addItems(["Your turn", "Other turns"])
        self.scope.currentIndexChanged.connect(self._render)
        timeline.addWidget(self.scope)
        self.phase_buttons = {}
        scroll = W.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(W.QFrame.Shape.NoFrame)
        scroll.setVerticalScrollBarPolicy(C.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = W.QWidget()
        phases = W.QHBoxLayout(content)
        phases.setContentsMargins(0, 0, 0, 0)
        phases.setSpacing(2)
        for step, label in STEPS:
            button = W.QPushButton(label)
            button.setCheckable(True)
            button.setToolTip(
                "Click to schedule/remove a stop at the next engine-granted priority in this step."
            )
            button.clicked.connect(lambda checked=False, value=step: self._stop(value))
            self.phase_buttons[step] = button
            phases.addWidget(button)
        scroll.setWidget(content)
        scroll.setFixedHeight(42)
        timeline.addWidget(scroll, 1)
        rows.addLayout(timeline)
        self.shortcuts = []
        self._install_shortcuts()
        W.QApplication.instance().installEventFilter(self)
        session.interactionPending.connect(self.suspend)
        session.viewCleared.connect(self.suspend)
        session.stopped.connect(self.reset)
        session.commandFinished.connect(self._result)

    def suspend(self):
        self.timer.stop()
        self.view = None
        self.until.setEnabled(False)

    def reset(self):
        self.suspend()
        self.policy.reset()
        self._render()

    def observe(self, view):
        if view.viewer_id != self.seat_id:
            return
        self.view = view
        action = self.policy.observe(view)
        self._render()
        self.timer.stop()
        if action:
            self.timer.start()

    def _automatic_pass(self):
        view = self.view
        if (
            view is None
            or self.session.closing
            or self.session.needs_recovery
            or not self.session.active
        ):
            return
        if (
            self.session.busy
            or W.QApplication.activeModalWidget() is not None
            or W.QApplication.activePopupWidget() is not None
        ):
            # Polling a snapshot or reading a menu must not consume the scheduled pass.
            # Re-evaluate the current preferences and frame when the UI is available.
            self.timer.start()
            return
        action = self.policy.observe(view)
        if action is None:
            return
        self.policy.claimed(view)
        self.session.submit(view, "perform", action.action_id)

    def manual(self, view, method, args):
        self.timer.stop()
        if self.session.submit(view, method, *args):
            self.policy.manual_submitted(view)

    def _result(self, result):
        self.policy.command_result(self.seat_id, result)
        self._render()

    def _automatic_changed(self, checked):
        self.policy.seat(self.seat_id).automatic = checked
        self.settings.setValue(f"{self.seat_id}/automatic", checked)
        self._reconsider()

    def _full_changed(self, checked):
        self.policy.seat(self.seat_id).full_control = checked
        self.settings.setValue(f"{self.seat_id}/full_control", checked)
        self._reconsider()

    def _reconsider(self):
        self.timer.stop()
        if self.view:
            self.observe(self.view)
        else:
            self._render()

    def hold_next(self):
        self.policy.seat(self.seat_id).temporary = True
        self._reconsider()

    def pass_until_response(self):
        state = self.policy.seat(self.seat_id)
        if state.until_turn:
            state.until_turn = None
            # Cancel must cancel even the already scheduled default automatic pass.
            state.temporary = True
        elif self.view and opportunity(self.view) and not turn_boundary(self.view):
            state.until_turn = self.policy.turn(self.view)
        self._reconsider()

    def _stop(self, step):
        self.policy.stop(
            self.seat_id,
            "own" if self.scope.currentIndex() == 0 else "other",
            step,
            self.recurring.isChecked(),
        )
        self._reconsider()

    def _render(self, *args):
        state = self.policy.seat(self.seat_id)
        mode = (
            "Full Control"
            if state.full_control
            else "Hold next priority"
            if state.temporary
            else "Pass Until Response"
            if state.until_turn
            else "Automatic"
            if state.automatic
            else "Manual"
        )
        self.indicator.setText(
            mode
            + " | "
            + state.reason
            + (f" | {len(state.stops)} stops" if state.stops else "")
        )
        self.until.setText(
            "Cancel passing" if state.until_turn else "Pass Until Response"
        )
        self.until.setEnabled(
            bool(
                state.until_turn
                or self.view
                and opportunity(self.view)
                and not turn_boundary(self.view)
                and not state.full_control
            )
        )
        scope = "own" if self.scope.currentIndex() == 0 else "other"
        for step, button in self.phase_buttons.items():
            button.setChecked(any(item[:2] == (scope, step) for item in state.stops))
            font = button.font()
            font.setBold(bool(self.view and self.view.step == step))
            button.setFont(font)

    def _keyboard_allowed(self):
        focus = W.QApplication.focusWidget()
        return (
            self.session.active
            and not self.session.closing
            and not self.session.needs_recovery
            and self.isVisible()
            and not W.QApplication.activeModalWidget()
            and W.QApplication.activeWindow() is self.window()
            and not isinstance(
                focus,
                (
                    W.QLineEdit,
                    W.QTextEdit,
                    W.QPlainTextEdit,
                    W.QAbstractSpinBox,
                    W.QComboBox,
                ),
            )
        )

    def _key_action(self, name):
        if not self._keyboard_allowed():
            return
        if name == "hold":
            self.hold_next()
        elif name == "full":
            self.full.setChecked(not self.full.isChecked())
        elif name == "until":
            self.pass_until_response()
        elif name == "pass":
            view = self.view
            action = opportunity(view) if view else None
            # End Turn requires its dedicated explicit button, never Space/Enter.
            if action and not turn_boundary(view):
                self.manual(view, "perform", (action.action_id,))

    def _install_shortcuts(self):
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self.shortcuts = []
        self.bindings = {
            name: self.settings.value(f"shortcuts/{name}", default)
            for name, default in {
                "pass": "Space",
                "until": "Return",
                "hold": "Ctrl",
                "full": "Ctrl+Shift",
            }.items()
        }
        for name, binding in self.bindings.items():
            if binding in {"Ctrl", "Ctrl+Shift"}:
                continue
            shortcut = G.QShortcut(G.QKeySequence(binding), self.parentWidget())
            shortcut.setAutoRepeat(False)
            shortcut.activated.connect(lambda value=name: self._key_action(value))
            self.shortcuts.append(shortcut)
        self.menu_button.setToolTip(
            "; ".join(f"{name}: {binding}" for name, binding in self.bindings.items())
        )

    def eventFilter(self, obj, event):
        if (
            event.type() == C.QEvent.Type.KeyPress
            and not event.isAutoRepeat()
            and self._keyboard_allowed()
        ):
            binding = None
            if event.key() == C.Qt.Key.Key_Control:
                binding = (
                    "Ctrl+Shift"
                    if event.modifiers() & C.Qt.KeyboardModifier.ShiftModifier
                    else "Ctrl"
                )
            elif (
                event.key() == C.Qt.Key.Key_Shift
                and event.modifiers() & C.Qt.KeyboardModifier.ControlModifier
            ):
                binding = "Ctrl+Shift"
                self.policy.seat(self.seat_id).temporary = False
            for name, value in self.bindings.items():
                if binding and value == binding:
                    self._key_action(name)
                    return True
        return super().eventFilter(obj, event)

    def configure_shortcuts(self):
        dialog = W.QDialog(self)
        dialog.setWindowTitle("Priority shortcuts")
        layout = W.QFormLayout(dialog)
        fields = {}
        for name, value in self.bindings.items():
            fields[name] = W.QLineEdit(value)
            layout.addRow(name.title(), fields[name])
        buttons = W.QDialogButtonBox(
            W.QDialogButtonBox.StandardButton.Save
            | W.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() != W.QDialog.DialogCode.Accepted:
            return
        values = {name: field.text().strip() for name, field in fields.items()}
        if len(set(values.values())) != len(values) or any(
            not value
            or value not in {"Ctrl", "Ctrl+Shift"}
            and G.QKeySequence(value).isEmpty()
            for value in values.values()
        ):
            W.QMessageBox.information(
                self, "Priority shortcuts", "Choose distinct, valid key combinations."
            )
            return
        for name, value in values.items():
            self.settings.setValue(f"shortcuts/{name}", value)
        self._install_shortcuts()
