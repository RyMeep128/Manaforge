"""A local hand sampler with deck-local notes and optional inclusion settings."""
from PyQt6 import QtCore as C, QtWidgets as W

from mtg_core.playtest import HandSampler


class PlaytestDialog(W.QDialog):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.entries = {e.entry_id: e for e in document.deck.entries}
        self.setWindowTitle('Opening-hand playtest')
        self.resize(740, 680)
        layout = W.QVBoxLayout(self)
        note = W.QLabel('Sample actual deck quantities. Mulligans redraw seven (or all cards in a smaller deck); '
                       'select cards to put on the bottom before keeping. This sampler does not enforce game rules.')
        note.setWordWrap(True)
        layout.addWidget(note)
        settings = document.editor_preferences.get('playtest', {})
        included = settings.get('sections', ['mainboard'])
        controls = W.QGridLayout()
        self.sections = {}
        for i, (key, label) in enumerate((('mainboard', 'Mainboard'), ('commander', 'Commanders'),
                ('sideboard', 'Sideboard'), ('considering', 'Considering'), ('excluded', 'Excluded'))):
            box = W.QCheckBox(label)
            box.setChecked(key in included)
            controls.addWidget(box, i // 3, i % 3)
            self.sections[key] = box
        self.include_owned = W.QCheckBox('Include do-not-print cards')
        self.include_owned.setChecked(settings.get('include_do_not_print', True))
        controls.addWidget(self.include_owned, 1, 2)
        self.free = W.QCheckBox('First mulligan is free')
        self.free.setChecked(settings.get('free_mulligan', document.deck.format.casefold() == 'commander'))
        controls.addWidget(self.free, 2, 0, 1, 3)
        layout.addLayout(controls)
        reset_note = W.QLabel('Changing inclusion or mulligan settings starts a new sample.')
        layout.addWidget(reset_note)
        self.summary = W.QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.hand = W.QListWidget()
        self.hand.setSelectionMode(W.QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.hand, 1)
        self.message = W.QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        actions = W.QHBoxLayout()
        self.restart_button = W.QPushButton('New sample')
        self.mulligan_button = W.QPushButton('Mulligan')
        self.keep_button = W.QPushButton('Keep hand')
        self.draw_button = W.QPushButton('Draw a card')
        for button, action in ((self.restart_button, self.restart), (self.mulligan_button, self.mulligan),
                               (self.keep_button, self.keep), (self.draw_button, self.draw)):
            button.clicked.connect(action)
            actions.addWidget(button)
        layout.addLayout(actions)
        layout.addWidget(W.QLabel('Playtest notes (saved with this deck):'))
        self.notes = W.QPlainTextEdit(document.deck.playtest_notes)
        self.notes.setMaximumHeight(120)
        layout.addWidget(self.notes)
        buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Save | W.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(W.QDialogButtonBox.StandardButton.Save).setText('Save notes/settings')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for box in (*self.sections.values(), self.include_owned, self.free):
            box.toggled.connect(self.restart)
        self.restart()

    def settings(self):
        return {'sections': [key for key, box in self.sections.items() if box.isChecked()],
                'include_do_not_print': self.include_owned.isChecked(), 'free_mulligan': self.free.isChecked()}

    def restart(self):
        settings = self.settings()
        self.sampler = HandSampler(self.document.deck, sections=settings['sections'],
            include_do_not_print=settings['include_do_not_print'], free_mulligans=int(settings['free_mulligan']))
        self.refresh()

    def mulligan(self):
        self.sampler.mulligan()
        self.refresh()

    def keep(self):
        selected = [item.data(C.Qt.ItemDataRole.UserRole) for item in self.hand.selectedItems()]
        try:
            self.sampler.keep(selected)
        except ValueError as exc:
            self.message.setText(str(exc))
            return
        self.refresh()

    def draw(self):
        self.sampler.draw()
        self.refresh()

    def refresh(self):
        sampler = self.sampler
        self.hand.clear()
        for card in sampler.hand:
            entry = self.entries[card.entry_id]
            printing = ' / '.join(str(value) for value in (entry.set_code, entry.collector_number) if value)
            item = W.QListWidgetItem(entry.name + (f' [{printing}]' if printing else ''))
            item.setData(C.Qt.ItemDataRole.UserRole, card)
            facts = entry.extras.get('facts', {})
            item.setToolTip('\n'.join(str(facts.get(key) or '') for key in ('mana_cost', 'type_line', 'oracle_text')))
            self.hand.addItem(item)
        self.summary.setText(f'{len(sampler.cards)} included copies | {len(sampler.hand)} in hand | '
                             f'{len(sampler.library)} in library | {sampler.mulligans} mulligans')
        self.message.setText('No cards match these inclusion settings.' if not sampler.cards else
            ('Hand kept. Library empty.' if not sampler.library else 'Hand kept. Draw a card or start a new sample.')
            if sampler.kept else f'Select {sampler.bottom_count} cards to put on the bottom, then Keep hand.')
        self.mulligan_button.setEnabled(sampler.can_mulligan)
        self.keep_button.setEnabled(bool(sampler.cards) and not sampler.kept)
        self.draw_button.setEnabled(sampler.kept and bool(sampler.library))
