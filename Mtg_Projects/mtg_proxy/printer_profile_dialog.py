"""Printer profile library UI. Changes to profiles never rewrite projects."""
from PyQt6 import QtWidgets
from services import printer_profiles as profiles


class PrinterProfileDialog(QtWidgets.QDialog):
    def __init__(self, parent, state):
        super().__init__(parent)
        self.setWindowTitle('Printer profiles')
        self.resize(480, 460)
        self.state = state
        self.applied = False
        self.relocated = 0
        self.profiles = profiles.load()
        self.names = QtWidgets.QComboBox()
        self.details = QtWidgets.QLabel()
        self.details.setWordWrap(True)
        self.duplex = QtWidgets.QComboBox()
        self.duplex.addItems(profiles.DUPLEX)
        self.duplex.setCurrentText(state.printer_duplex)
        layout = QtWidgets.QVBoxLayout(self)
        note = QtWidgets.QLabel('Save the current project’s paper and backside settings as a reusable profile. Applying a profile copies its settings into this project.')
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addWidget(self.names)
        layout.addWidget(self.details)
        layout.addWidget(QtWidgets.QLabel('Duplex preference for saved profile'))
        layout.addWidget(self.duplex)
        for label, callback in [('Save current settings as…', self.save_current),
                                ('Delete selected profile', self.delete_selected),
                                ('Apply selected profile', self.apply_selected),
                                ('Close', self.reject)]:
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(callback)
            layout.addWidget(button)
        self.names.currentTextChanged.connect(self.show_details)
        self.reload()

    def reload(self, selected=''):
        self.names.clear()
        self.names.addItems(sorted(self.profiles, key=str.casefold))
        if selected:
            self.names.setCurrentText(selected)
        self.show_details()

    def show_details(self):
        settings = self.profiles.get(self.names.currentText())
        self.details.setText(profiles.summary(settings) if settings else 'No saved profiles yet.')

    def save_current(self):
        name, ok = QtWidgets.QInputDialog.getText(self, 'Save printer profile', 'Profile name:')
        name = name.strip()
        if not ok or not name:
            return
        existing = next((key for key in self.profiles if key.casefold() == name.casefold()), None)
        if existing:
            if QtWidgets.QMessageBox.question(self, 'Replace profile?', f'Replace “{existing}” with the current settings?') != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            name = existing
        updated = dict(self.profiles)
        updated[name] = profiles.capture(self.state, self.duplex.currentText())
        self.write(updated, name)

    def write(self, updated, selected=''):
        try:
            profiles.save_all(updated)
        except (OSError, ValueError, TypeError) as exc:
            QtWidgets.QMessageBox.warning(self, 'Could not save printer profiles', str(exc))
            return
        self.profiles = updated
        self.reload(selected)

    def delete_selected(self):
        name = self.names.currentText()
        if name and QtWidgets.QMessageBox.question(self, 'Delete profile?', f'Delete “{name}”? Saved projects keep their settings.') == QtWidgets.QMessageBox.StandardButton.Yes:
            updated = dict(self.profiles)
            del updated[name]
            self.write(updated)

    def apply_selected(self):
        settings = self.profiles.get(self.names.currentText())
        if settings is None:
            return
        changes = '\n'.join(f'{key.replace("_", " ")}: {getattr(self.state, key)} → {settings[key]}'
                            for key in profiles.FIELDS if getattr(self.state, key) != settings[key])
        if QtWidgets.QMessageBox.question(self, 'Apply printer profile?', changes or 'These settings already match the project.') != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        try:
            self.relocated = profiles.apply(self.state, settings)
        except (ValueError, TypeError) as exc:
            QtWidgets.QMessageBox.warning(self, 'Could not apply profile', str(exc))
            return
        self.applied = True
        self.accept()
