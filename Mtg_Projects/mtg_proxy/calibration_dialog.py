import os
import subprocess

from PyQt6 import QtWidgets

from constants import cwd
from services import calibration_service, printer_profiles


class PrinterCalibrationDialog(QtWidgets.QDialog):
    def __init__(self, parent, state):
        super().__init__(parent)
        self.state = state
        self.applied = False
        self.setWindowTitle('Printer calibration')
        self.resize(560, 430)

        intro = QtWidgets.QLabel(
            '<b>1.</b> Save and print the test PDF at Actual size / 100%.<br>'
            '<b>2.</b> Hold the sheet to a light and measure where the back marks land '
            'relative to the front marks.<br><b>3.</b> Enter the correction needed to move '
            'the back marks onto the front marks, then generate another sheet to verify.<br>'
            '<b>4.</b> Cut a test rectangle on its solid line to verify the 63 x 88 mm '
            'finished card size. The nine-card grid tests alignment across the full sheet.')
        intro.setWordWrap(True)
        setup = QtWidgets.QLabel(
            f'<b>Current setup:</b> {state.pagesize}, {state.orient}, '
            f'{state.printer_duplex} duplex. Change these in Print Settings before '
            'opening calibration if needed.')
        setup.setWordWrap(True)
        self.horizontal = self._offset_spin(float(state.backside_offset))
        self.vertical = self._offset_spin(float(state.backside_vertical_offset))
        self.profile_name = QtWidgets.QLineEdit()
        self.profile_name.setPlaceholderText('Optional profile name')
        self.status = QtWidgets.QLabel('Positive X moves backs right; positive Y moves backs up.')
        self.status.setWordWrap(True)

        form = QtWidgets.QFormLayout()
        form.addRow('Horizontal correction', self.horizontal)
        form.addRow('Vertical correction', self.vertical)
        form.addRow('Save into profile', self.profile_name)

        save_pdf = QtWidgets.QPushButton('Save calibration PDF…')
        save_pdf.clicked.connect(self.save_pdf)
        apply_button = QtWidgets.QPushButton('Apply corrections')
        apply_button.clicked.connect(self.apply_corrections)
        profile_button = QtWidgets.QPushButton('Apply and save profile')
        profile_button.clicked.connect(self.apply_and_save_profile)
        close_button = QtWidgets.QPushButton('Close')
        close_button.clicked.connect(self.accept)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(save_pdf)
        buttons.addStretch()
        buttons.addWidget(apply_button)
        buttons.addWidget(profile_button)
        buttons.addWidget(close_button)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(setup)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addStretch()
        layout.addLayout(buttons)

    @staticmethod
    def _offset_spin(value):
        spin = QtWidgets.QDoubleSpinBox()
        spin.setDecimals(2)
        spin.setRange(-7.62, 7.62)
        spin.setSingleStep(0.1)
        spin.setSuffix(' mm')
        spin.setValue(value)
        return spin

    def save_pdf(self):
        path = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Save calibration PDF', os.path.join(cwd, 'Manaforge Calibration.pdf'),
            'PDF Files (*.pdf)')[0]
        if not path:
            return
        if not path.casefold().endswith('.pdf'):
            path += '.pdf'
        try:
            calibration_service.generate_calibration_pdf(
                self.state, path, horizontal_mm=self.horizontal.value(),
                vertical_mm=self.vertical.value())
        except (OSError, ValueError, TypeError) as exc:
            QtWidgets.QMessageBox.warning(self, 'Calibration PDF Failed', str(exc))
            return
        self.status.setText(f'Calibration PDF saved to {path}')
        try:
            subprocess.Popen([path], shell=True)
        except OSError:
            pass

    def apply_corrections(self):
        self.state.backside_offset = str(self.horizontal.value())
        self.state.backside_vertical_offset = str(self.vertical.value())
        self.applied = True
        self.status.setText('Corrections applied to the current project.')

    def apply_and_save_profile(self):
        name = self.profile_name.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(
                self, 'Profile Name Required', 'Enter a profile name first.')
            return
        self.apply_corrections()
        try:
            saved = printer_profiles.load()
            existing = next((key for key in saved if key.casefold() == name.casefold()), None)
            if existing:
                answer = QtWidgets.QMessageBox.question(
                    self, 'Replace profile"', f'Replace “{existing}” with these settings"')
                if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                    return
                name = existing
            saved[name] = printer_profiles.capture(self.state, self.state.printer_duplex)
            printer_profiles.save_all(saved)
        except (OSError, ValueError, TypeError) as exc:
            QtWidgets.QMessageBox.warning(self, 'Could Not Save Profile', str(exc))
            return
        self.status.setText(f'Corrections applied and saved to profile “{name}”.')
