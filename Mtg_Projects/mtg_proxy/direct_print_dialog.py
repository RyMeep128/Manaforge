from PyQt6 import QtWidgets


class DirectPrintOptionsDialog(QtWidgets.QDialog):
    """Choose which generated sides enter the native printer dialog."""

    def __init__(self, parent, *, backs_enabled):
        super().__init__(parent)
        self.setWindowTitle('Direct printing')
        self.resize(440, 220)
        intro = QtWidgets.QLabel(
            'Choose the sheet sides to render. The next window selects the printer, '
            'page range, copies, and printer-specific options. Nothing prints until '
            'you confirm that system dialog.')
        intro.setWordWrap(True)
        self.side = QtWidgets.QComboBox()
        self.side.addItem('Fronts and backs', 'both')
        self.side.addItem('Fronts only', 'front')
        self.side.addItem('Backs only', 'back')
        if not backs_enabled:
            self.side.setCurrentIndex(1)
            self.side.model().item(0).setEnabled(False)
            self.side.model().item(2).setEnabled(False)
        form = QtWidgets.QFormLayout()
        form.addRow('Print', self.side)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel |
            QtWidgets.QDialogButtonBox.StandardButton.Ok)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(
            'Continue to printer...')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addStretch()
        layout.addWidget(buttons)

    def page_side(self):
        return self.side.currentData()
