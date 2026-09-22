"""Select commanders and review local deck checks without blocking house rules."""
from copy import deepcopy
from datetime import datetime, timezone
from PyQt6 import QtWidgets as W
from mtg_core.commander import check_commander, set_commanders, RULE_VERSION
from mtg_core.legality import check_constructed


class CommanderDialog(W.QDialog):
    def __init__(self, document, records, parent=None):
        super().__init__(parent)
        self.document, self.records = document, records
        self.is_commander = document.deck.format in ('Commander', 'Custom')
        self.setWindowTitle('Commander selection and deck checks' if self.is_commander else f'{document.deck.format} deck checks')
        self.resize(860, 600)
        layout = W.QVBoxLayout(self)
        note = W.QLabel('Checks use dated local Oracle/legality data. Owned / do-not-print cards still count. '
                       'A companion must be one card in the sideboard; Commander excludes other sideboard cards. '
                       'The report previews these selections; Apply saves them. House rules are not enforced.')
        note.setWordWrap(True)
        layout.addWidget(note)
        form = W.QFormLayout()
        self.selectors = []
        self.color_choices = []
        current = [e.entry_id for e in document.deck.entries if e.section == 'commander']
        for i, label in enumerate(('Commander', 'Partner / Background')):
            combo = W.QComboBox()
            combo.addItem('None', None)
            for entry in sorted(document.deck.entries, key=lambda e: e.name.casefold()):
                combo.addItem(f'{entry.name} ({entry.set_code or "?"} {entry.collector_number or ""}) · {entry.quantity}', entry.entry_id)
            if i < len(current):
                combo.setCurrentIndex(combo.findData(current[i]))
            form.addRow(label, combo)
            combo.setVisible(self.is_commander)
            form.labelForField(combo).setVisible(self.is_commander)
            self.selectors.append(combo)
            color = W.QComboBox()
            color.addItem('No pregame color chosen', None)
            for code, name in zip('WUBRG', ('White', 'Blue', 'Black', 'Red', 'Green')):
                color.addItem(name, code)
            if i < len(current):
                color.setCurrentIndex(max(0, color.findData(document.deck.extras.get('commander_colors', {}).get(current[i]))))
            form.addRow('Pregame color (if required)', color)
            color.setVisible(self.is_commander)
            form.labelForField(color).setVisible(self.is_commander)
            self.color_choices.append(color)
        self.companion = W.QComboBox()
        self.companion.addItem('No companion', None)
        for entry in document.deck.entries:
            if entry.section == 'sideboard':
                self.companion.addItem(entry.name, entry.entry_id)
        saved_companion = document.deck.extras.get('companion_entry_id')
        if saved_companion and self.companion.findData(saved_companion) < 0:
            self.companion.addItem('Saved companion missing or outside sideboard — choose another', saved_companion)
        self.companion.setCurrentIndex(max(0, self.companion.findData(saved_companion)))
        form.addRow('Companion (from sideboard)', self.companion)
        layout.addLayout(form)
        self.summary = W.QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = W.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(['Status', 'Finding'])
        self.table.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, W.QHeaderView.ResizeMode.Stretch)
        self.table.setWordWrap(True)
        layout.addWidget(self.table, 1)
        self.source = W.QLabel()
        self.source.setWordWrap(True)
        layout.addWidget(self.source)
        self.rules = W.QLabel('<a href="https://magic.wizards.com/en/rules">Official Commander rules</a>')
        self.rules.setOpenExternalLinks(True)
        layout.addWidget(self.rules)
        self.buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Apply | W.QDialogButtonBox.StandardButton.Close)
        self.apply_button = self.buttons.button(W.QDialogButtonBox.StandardButton.Apply)
        self.apply_button.setText('Apply selections')
        self.apply_button.clicked.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        for selector in self.selectors:
            selector.currentIndexChanged.connect(self.refresh)
        for selector in self.color_choices + [self.companion]:
            selector.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def selected_ids(self):
        return [c.currentData() for c in self.selectors if c.currentData() is not None]

    def apply_selections(self, document):
        if self.is_commander:
            set_commanders(document, self.selected_ids())
            document.deck.extras['commander_colors'] = {selector.currentData(): color.currentData()
                for selector, color in zip(self.selectors, self.color_choices)
                if selector.currentData() and color.currentData()}
        document.deck.extras['companion_entry_id'] = self.companion.currentData()

    def refresh(self, *_):
        ids = self.selected_ids()
        if len(set(ids)) != len(ids):
            self.apply_button.setEnabled(False)
            self.summary.setText('Choose two different cards, or set the second selection to None.')
            self.table.setRowCount(0)
            return
        self.apply_button.setEnabled(True)
        preview = deepcopy(self.document)
        self.apply_selections(preview)
        report = check_commander(preview, self.records) if self.is_commander else check_constructed(preview, self.records)
        target = '/ 100' if self.is_commander else '(minimum 60)'
        current_ids = [e.entry_id for e in self.document.deck.entries if e.section == 'commander']
        changed = ((self.is_commander and set(ids) != set(current_ids)) or
                   preview.deck.extras.get('companion_entry_id') != self.document.deck.extras.get('companion_entry_id') or
                   preview.deck.extras.get('commander_colors', {}) != self.document.deck.extras.get('commander_colors', {}))
        self.summary.setText(f'{report.total} {target} cards — {report.summary}' +
                             ('\nPreview contains unsaved selection changes. Apply to update the deck.' if changed else ''))
        self.table.setRowCount(len(report.issues))
        for row, issue in enumerate(report.issues):
            self.table.setItem(row, 0, W.QTableWidgetItem(issue.severity))
            item = W.QTableWidgetItem(issue.message)
            item.setToolTip(issue.message)
            self.table.setItem(row, 1, item)
        self.table.resizeRowsToContents()
        cached = datetime.fromtimestamp(report.oldest_cache, timezone.utc).strftime('%Y-%m-%d %H:%M UTC') if report.oldest_cache else 'unknown'
        self.source.setText(f'Checker {RULE_VERSION}. Oldest known card cache: {cached}. '
                            'Cache dates show local retrieval times, not a ban-list publication date. '
                            'Refresh card data in Core and reopen this check to use newer data.')
