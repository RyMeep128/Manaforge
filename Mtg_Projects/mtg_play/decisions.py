"""Reusable engine decision controls; every submission is an explicit click."""

from PyQt6 import QtCore as C, QtWidgets as W


FAMILIES = {
    "boolean",
    "selection",
    "target",
    "ability",
    "options",
    "number",
    "mana",
    "amounts",
    "piles",
}


def opening_hand_request(view):
    request = view.decision
    if request is None or request.player_id != view.viewer_id:
        return False
    prompt = request.prompt.lower()
    if request.family == "boolean":
        return "mulligan" in prompt or "keep your hand" in prompt
    if request.family != "target" or "bottom" not in prompt:
        return False
    hand = {
        obj.object_id
        for obj in view.objects
        if obj.zone == "hand"
        and obj.owner_id == view.viewer_id
        and not obj.hidden
        and not obj.face_down
    }
    return bool(request.options) and all(
        option.object_id in hand for option in request.options
    )


def pass_label(view):
    kinds = {action.kind for action in view.actions}
    if view.step == "DECLARE_ATTACKERS" or "declare_attacker" in kinds:
        return "Finish attackers"
    if view.step == "DECLARE_BLOCKERS" or "declare_blocker" in kinds:
        return "Finish blockers"
    if view.decision is not None and view.decision.family == "mana":
        return "Finish payment"
    return "Pass priority"


class DecisionPanel(W.QWidget):
    command = C.pyqtSignal(object, str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = W.QVBoxLayout(self)
        self.rows.setContentsMargins(8, 8, 8, 8)
        self.view = None

    def clear(self):
        self.view = None
        self.setEnabled(False)
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                widget = item.widget()
                widget.setEnabled(False)
                widget.hide()
                if isinstance(widget, W.QPushButton):
                    widget.clicked.disconnect()
                    widget.setText("")
                elif isinstance(widget, W.QLabel):
                    widget.clear()
                widget.deleteLater()

    def button(self, text, method, args=()):
        button = W.QPushButton(text)
        button.play_method, button.play_args = method, args
        view = self.view
        button.clicked.connect(
            lambda checked=False: self.command.emit(view, method, args)
        )
        self.rows.addWidget(button)
        return button

    def present(self, view):
        self.clear()
        self.view = view
        request = view.decision
        if request is None:
            text = (
                "Waiting for the other player…" if not view.result else "Game complete"
            )
            self.rows.addWidget(W.QLabel(text))
            return
        title = W.QLabel(request.prompt or "Make your choice")
        title.setWordWrap(True)
        title.setTextFormat(C.Qt.TextFormat.PlainText)
        title.setProperty("role", "subtitle")
        self.rows.addWidget(title)
        if request.family not in FAMILIES:
            error = W.QLabel(
                "This decision is not supported by this Play preview. Close the game to recover."
            )
            error.setWordWrap(True)
            self.rows.addWidget(error)
            return
        self.setEnabled(True)
        names = {
            obj.object_id: obj.characteristics.name
            for obj in view.objects
            if not obj.hidden and not obj.face_down and obj.characteristics
        }
        names.update({player.player_id: player.name for player in view.players})
        for option in request.options:
            text = (
                names.get(option.object_id)
                or names.get(option.player_id)
                or option.label
            )
            if opening_hand_request(view) and request.family == "boolean":
                affirmative = option.label.lower() in {"yes", "true"}
                negative = option.label.lower() in {"no", "false"}
                prompt = request.prompt.lower()
                unambiguous = ("mulligan" in prompt) != ("keep your hand" in prompt)
                if (affirmative or negative) and unambiguous:
                    mulligan_question = "mulligan" in request.prompt.lower()
                    text = "Mulligan" if affirmative == mulligan_question else "Keep"
            text = ("Selected · " if option.selected else "") + (text or "Choose")
            button = self.button(text, "choose", (option.option_id,))
            if opening_hand_request(view) and request.family == "boolean":
                button.setMinimumHeight(44)
                if text == "Keep":
                    button.setProperty("buttonRole", "primary")
        for action in view.actions:
            if action.object_id is None:
                label = action.label
                if action.kind == "pass":
                    label = pass_label(view)
                button = self.button(label, "perform", (action.action_id,))
                if action.kind == "pass":
                    button.setMinimumHeight(44)
                    button.setProperty("buttonRole", "primary")
                    button.setAccessibleDescription(
                        "Submit this engine-offered action once. The game determines what happens next."
                    )
        if request.family == "target":
            selected = sum(option.selected for option in request.options)
            self.rows.addWidget(
                W.QLabel(f"{selected} selected · Select again to deselect")
            )
        if request.family == "mana":
            note = W.QLabel(
                "Select a mana source on the table. Available abilities and payment are checked by the game."
            )
            note.setWordWrap(True)
            self.rows.addWidget(note)
        if request.family == "number":
            if request.minimum is None or request.maximum is None:
                self.rows.addWidget(
                    W.QLabel(
                        "This number request has no supported range. Close the game to recover."
                    )
                )
                self.setEnabled(False)
                return
            number = W.QSpinBox()
            number.setRange(request.minimum, request.maximum)
            number.setAccessibleName(request.prompt or "Choose a number")
            self.rows.addWidget(number)
            confirm = self.button("Confirm number", "choose_number")
            confirm.clicked.disconnect()
            confirm.clicked.connect(
                lambda: self.command.emit(view, "choose_number", (number.value(),))
            )
        if request.family == "amounts":
            amounts = []
            for constraint in request.amounts:
                label = W.QLabel(constraint.label)
                label.setTextFormat(C.Qt.TextFormat.PlainText)
                label.setWordWrap(True)
                self.rows.addWidget(label)
                amount = W.QSpinBox()
                amount.setRange(constraint.minimum, constraint.maximum)
                amount.setValue(
                    constraint.default
                    if constraint.default is not None
                    else constraint.minimum
                )
                amount.setAccessibleName(constraint.label)
                self.rows.addWidget(amount)
                amounts.append(amount)
            total = W.QLabel()
            self.rows.addWidget(total)
            confirm = self.button("Confirm amounts", "choose_amounts")
            confirm.clicked.disconnect()
            confirm.clicked.connect(
                lambda: self.command.emit(
                    view,
                    "choose_amounts",
                    (tuple(amount.value() for amount in amounts),),
                )
            )

            def update_total():
                value = sum(amount.value() for amount in amounts)
                total.setText(
                    f"Total: {value} · Required: {request.minimum}–{request.maximum}"
                )
                confirm.setEnabled(
                    request.minimum is not None
                    and request.maximum is not None
                    and request.minimum <= value <= request.maximum
                )

            for amount in amounts:
                amount.valueChanged.connect(update_total)
            update_total()
        if request.can_finish:
            self.button("Finish selection", "finish_selection")
        if request.cancellable:
            self.button("Cancel", "cancel")
        self.rows.addStretch()
