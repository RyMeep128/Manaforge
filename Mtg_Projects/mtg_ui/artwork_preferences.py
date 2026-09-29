"""Shared artwork preference editor, independent of print-project UI."""
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QLabel, QLineEdit,
    QMessageBox, QSpinBox, QVBoxLayout,
)
from mtg_core.diagnostics import get_logger


class ArtworkPreferencesDialog(QDialog):
    def __init__(self, parent, card_service):
        super().__init__(parent)
        self._card_service = card_service
        rules = card_service.get_artwork_preferences()
        self.setWindowTitle('Artwork Preferences')
        self.resize(520, 560)
        self.language = QLineEdit(rules.language)
        self.sets = QLineEdit(', '.join(rules.preferred_sets))
        self.year = QSpinBox()
        self.year.setRange(0, 2200)
        self.year.setSpecialValueText('Any year')
        self.year.setValue(rules.preferred_year or 0)
        self.artists = QLineEdit(', '.join(rules.preferred_artists))
        self.frames = QLineEdit(', '.join(rules.preferred_frames))
        self.borders = QLineEdit(', '.join(rules.preferred_borders))
        self.sources = QLineEdit(', '.join(rules.preferred_sources))
        self.minimum_dpi = QSpinBox()
        self.minimum_dpi.setRange(0, 2400)
        self.minimum_dpi.setSingleStep(50)
        self.minimum_dpi.setValue(rules.minimum_dpi)
        self.avoid_promos = QCheckBox('Avoid promotional printings')
        self.avoid_textless = QCheckBox('Avoid textless printings')
        self.avoid_ub = QCheckBox('Avoid Universes Beyond printings')
        self.avoid_foil = QCheckBox('Avoid foil-only treatments')
        self.avoid_promos.setChecked(rules.avoid_promos)
        self.avoid_textless.setChecked(rules.avoid_textless)
        self.avoid_ub.setChecked(rules.avoid_universes_beyond)
        self.avoid_foil.setChecked(rules.avoid_foil_only)
        layout = QVBoxLayout()
        intro = QLabel(
            'These preferences are shared by Manaforge apps. Lists use commas; '
            'earlier values have higher priority.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        for label, widget in (
            ('Language code', self.language), ('Preferred sets', self.sets),
            ('Preferred year', self.year), ('Preferred artists', self.artists),
            ('Preferred frames', self.frames), ('Preferred borders', self.borders),
            ('Preferred sources', self.sources), ('Minimum DPI', self.minimum_dpi)):
            layout.addWidget(QLabel(label))
            layout.addWidget(widget)
        for checkbox in (self.avoid_promos, self.avoid_textless,
                         self.avoid_ub, self.avoid_foil):
            layout.addWidget(checkbox)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setLayout(layout)

    @staticmethod
    def _list(text):
        return tuple(item.strip() for item in text.split(',') if item.strip())

    def rules(self):
        from mtg_core import ArtworkPreferenceRules
        return ArtworkPreferenceRules(
            language=self.language.text().strip() or 'en',
            preferred_sets=self._list(self.sets.text()),
            preferred_year=self.year.value() or None,
            preferred_artists=self._list(self.artists.text()),
            preferred_frames=self._list(self.frames.text()),
            preferred_borders=self._list(self.borders.text()),
            preferred_sources=self._list(self.sources.text()),
            minimum_dpi=self.minimum_dpi.value(),
            avoid_promos=self.avoid_promos.isChecked(),
            avoid_textless=self.avoid_textless.isChecked(),
            avoid_universes_beyond=self.avoid_ub.isChecked(),
            avoid_foil_only=self.avoid_foil.isChecked())

    def save(self):
        return self._card_service.set_artwork_preferences(self.rules())


def edit_artwork_preferences(parent, card_service):
    """Reload shared rules when opened; only Save persists changes."""
    dialog = None
    try:
        dialog = ArtworkPreferencesDialog(parent, card_service)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.save()
    except Exception as exc:
        get_logger(__name__).exception("Artwork preferences could not be opened or saved")
        QMessageBox.critical(parent, "Artwork Preferences", str(exc))
    finally:
        if dialog is not None:
            dialog.deleteLater()
    return None
