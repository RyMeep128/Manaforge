"""Review and atomically append a basic-land plan using the editor history."""
from copy import deepcopy
import uuid

from PyQt6 import QtWidgets as W
from mtg_core.basic_lands import BASICS, available_slots, basic_distribution
from mtg_core.categorization import apply_categories, classify
from mtg_core.decks import DeckEntry
from .organization import card_facts


class BasicLandsDialog(W.QDialog):
    def __init__(self, document, parent):
        super().__init__(parent)
        self.document = deepcopy(document)
        self.setWindowTitle('Auto Add Basic Lands')
        layout = W.QVBoxLayout(self)
        note = W.QLabel('Choose additional basic-land slots. Existing cards stay in place. '
                        'This pip-based starting point does not optimize your mana base or subtract existing sources. '
                        'Uses mainboard and commander costs; double-faced cards use the front face. '
                        'Hybrid pips count once for each color; phyrexian and monocolor hybrid pips count as one colored pip. '
                        'Generic, snow and variable symbols are ignored. Edit counts before adding.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.slots = W.QSpinBox()
        self.slots.setRange(0, available_slots(document))
        self.slots.setValue(min(20, self.slots.maximum()))
        form = W.QFormLayout()
        form.addRow('Additional basic lands', self.slots)
        self.counts = {}
        from mtg_core.card_pool import pool_context
        _, identity, _ = pool_context(document)
        for color, name in BASICS.items():
            spin = W.QSpinBox()
            spin.setRange(0, self.slots.maximum())
            spin.setEnabled(color == 'C' or identity is None or color in identity)
            spin.valueChanged.connect(self.review)
            self.counts[name] = spin
            form.addRow(name, spin)
        layout.addLayout(form)
        self.notice = W.QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Cancel)
        self.apply = buttons.addButton('Auto Add Basic Lands', W.QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.slots.valueChanged.connect(self.recommend)
        self.recommend()

    def recommend(self):
        counts, self.pips = basic_distribution(self.document, self.slots.value())
        from PyQt6.QtCore import QSignalBlocker
        for name, spin in self.counts.items():
            with QSignalBlocker(spin):
                spin.setValue(counts.get(name, 0))
        self.review()

    def review(self):
        from mtg_core.deck_insights import deck_insights
        total = sum(spin.value() for spin in self.counts.values())
        unknown = deck_insights(self.document)['unknown'].get('mana cost', 0)
        self.notice.setText(f'{total} / {self.slots.value()} additional lands. '
                            + 'Pips: ' + ', '.join(f'{c}: {n:g}' for c, n in getattr(self, 'pips', {}).items())
                            + (f' · {unknown} copies have unknown mana costs.' if unknown else '')
                            + ' With no colored pips, the plan splits known commander colors evenly or uses Wastes.')
        self.apply.setEnabled(total == self.slots.value() and total > 0)


def add_basic_lands(editor):
    if editor.task is not None or editor.closing:
        return
    snapshot = deepcopy(editor.document)
    dialog = BasicLandsDialog(snapshot, editor)
    if dialog.exec() != W.QDialog.DialogCode.Accepted:
        return
    counts = {name: spin.value() for name, spin in dialog.counts.items() if spin.value()}
    def resolve():
        payloads = {}
        for name in counts:
            payload = editor.service.get_card(exact_name=name)
            if not payload and hasattr(editor.service, 'fetch_missing_card'):
                payload = editor.service.fetch_missing_card(exact_name=name)
            if not payload or not payload.get('id') or 'Basic' not in (payload.get('type_line') or ''):
                raise ValueError(f'Basic land unavailable in the catalog: {name}. No cards were added.')
            from mtg_core.card_pool import in_card_pool
            if not in_card_pool(payload, snapshot):
                raise ValueError(f'{name} is not marked legal for this deck in the local catalog. '
                                 'Review the plan or enable Include illegal cards. No cards were added.')
            payloads[name] = payload
        return payloads
    def apply(payloads):
        if editor.document.to_dict() != snapshot.to_dict():
            editor.statusBar().showMessage('Deck changed while resolving lands. Review a new plan; no lands were added.')
            return
        if sum(counts.values()) > available_slots(editor.document):
            raise ValueError('Not enough deck slots remain. No lands were added.')
        def command(document):
            proposals = {}
            for name, quantity in counts.items():
                existing = next((e for e in document.deck.entries if e.section == 'mainboard'
                                 and e.name.casefold() == name.casefold()
                                 and ('Basic' in ((e.extras.get('facts') or {}).get('type_line') or '')
                                      or e.oracle_id == payloads[name].get('oracle_id')
                                      and e.oracle_id is not None)), None)
                if existing:
                    existing.quantity += quantity
                    continue
                payload = payloads[name]
                entry = DeckEntry(str(uuid.uuid4()), name, quantity=quantity,
                                  card_id=payload['id'], oracle_id=payload.get('oracle_id'),
                                  set_code=payload.get('set'), collector_number=payload.get('collector_number'),
                                  pre_cropped=True, extras={'facts': card_facts(payload)},
                                  sort_order=max((e.sort_order for e in document.deck.entries), default=-1)+1)
                document.deck.entries.append(entry)
                proposals[entry.entry_id] = classify(payload)
            apply_categories(document, proposals)
        editor.edit(command)
        editor.statusBar().showMessage(f'Added {sum(counts.values())} basic lands. Undo is available.')
    editor.run_task(resolve, apply)
