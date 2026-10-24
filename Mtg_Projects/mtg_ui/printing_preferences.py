"""Shared editor for Core-owned global printing defaults."""
from PyQt6 import QtWidgets as W
from mtg_core.diagnostics import get_logger
from mtg_core.printing_preferences import PrintingPreferences, PAPER_SIZES, DUPLEX


class PrintingPreferencesDialog(W.QDialog):
    def __init__(self, parent, card_service):
        super().__init__(parent)
        self.card_service = card_service
        preferences = card_service.get_printing_preferences() or PrintingPreferences()
        self.setWindowTitle('Global printing defaults')
        layout = W.QVBoxLayout(self)
        note = W.QLabel('New print projects use these shared defaults. Existing projects keep '
                       'their saved settings. Offsets use millimetres: positive X moves backs '
                       'right; positive Y moves backs up.')
        note.setWordWrap(True)
        layout.addWidget(note)
        form = W.QFormLayout()
        self.controls = {}
        for key, label, choices in (
                ('pagesize', 'Paper size', PAPER_SIZES),
                ('orient', 'Orientation', ('Portrait', 'Landscape')),
                ('printer_duplex', 'Duplex preference', DUPLEX)):
            control = W.QComboBox()
            control.addItems(choices)
            control.setCurrentText(getattr(preferences, key))
            self.controls[key] = control
            form.addRow(label, control)
        for key, label in (('backside_offset', 'Horizontal back offset (mm)'),
                           ('backside_vertical_offset', 'Vertical back offset (mm)')):
            control = W.QLineEdit(str(getattr(preferences, key)))
            self.controls[key] = control
            form.addRow(label, control)
        for key, label in (
                ('backside_enabled', 'Enable backs'),
                ('backside_pages_at_end', 'Put back pages at the end'),
                ('backside_separate_file', 'Save backs in a separate file'),
                ('backside_reverse_page_order', 'Reverse back page order')):
            control = W.QCheckBox(label)
            control.setChecked(getattr(preferences, key))
            self.controls[key] = control
            form.addRow(control)
        layout.addLayout(form)
        buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Save |
                                     W.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        settings = {}
        for key, control in self.controls.items():
            if isinstance(control, W.QCheckBox):
                settings[key] = control.isChecked()
            elif isinstance(control, W.QComboBox):
                settings[key] = control.currentText()
            else:
                settings[key] = control.text().strip()
        try:
            self.card_service.set_printing_preferences(PrintingPreferences(**settings))
        except Exception as exc:
            get_logger(__name__).exception('Global printing defaults could not be saved')
            W.QMessageBox.warning(self, 'Could not save printing defaults', str(exc))
            return
        self.accept()


def edit_printing_preferences(parent, card_service):
    """Read current defaults on every open; Cancel performs no writes."""
    dialog = None
    try:
        dialog = PrintingPreferencesDialog(parent, card_service)
        return dialog.exec() == W.QDialog.DialogCode.Accepted
    except Exception as exc:
        get_logger(__name__).exception('Global printing defaults could not be opened')
        W.QMessageBox.warning(parent, 'Could not open printing defaults', str(exc))
        return False
    finally:
        if dialog is not None:
            dialog.deleteLater()
