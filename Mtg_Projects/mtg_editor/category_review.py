"""Review deterministic role assignments before changing an existing deck."""
from PyQt6 import QtCore, QtWidgets as W
from mtg_core.categorization import is_manual


class CategoryReview(W.QDialog):
    def __init__(self, document, proposals, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Auto Categorize')
        self.resize(850, 520)
        self.proposals = proposals
        self.rows = []
        layout = W.QVBoxLayout(self)
        explanation = W.QLabel('Uses local Oracle Tags, Oracle text, keywords, and card types. First role is primary. '
                              'Manual categories are preserved. Rule matches are explained below; no AI is used.')
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.reconsider = W.QCheckBox('Reconsider manual assignments (replace my primary categories)')
        layout.addWidget(self.reconsider)
        self.table = W.QTableWidget(len(document.deck.entries), 3)
        self.table.setHorizontalHeaderLabels(['Card', 'Categories', 'Why / source'])
        self.table.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(W.QHeaderView.ResizeMode.Stretch)
        for row, entry in enumerate(document.deck.entries):
            evidence = proposals.get(entry.entry_id, [])
            protected = is_manual(entry)
            item = W.QTableWidgetItem(entry.name)
            enabled = bool(evidence) and not protected
            if enabled:
                item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(QtCore.Qt.CheckState.Checked)
                self.rows.append((row, entry.entry_id))
            self.table.setItem(row, 0, item)
            self.table.setItem(row, 1, W.QTableWidgetItem('Manual — unchanged' if protected else
                ', '.join(m['name'] for m in evidence) or 'Uncategorized — unchanged'))
            self.table.setItem(row, 2, W.QTableWidgetItem('Manual assignment' if protected else
                '; '.join(m['reason'] for m in evidence) or 'No supported local data'))
            for column in (1, 2):
                self.table.item(row, column).setToolTip(self.table.item(row, column).text())
        layout.addWidget(self.table, 1)
        def toggle_manual(checked):
            for row, entry in enumerate(document.deck.entries):
                if not is_manual(entry) or not proposals.get(entry.entry_id):
                    continue
                item = self.table.item(row, 0)
                if checked:
                    item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(QtCore.Qt.CheckState.Checked)
                    self.rows.append((row, entry.entry_id))
                else:
                    item.setCheckState(QtCore.Qt.CheckState.Unchecked)
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                    self.rows.remove((row, entry.entry_id))
                self.table.item(row, 1).setText(', '.join(m['name'] for m in proposals[entry.entry_id])
                                              if checked else 'Manual — unchanged')
                self.table.item(row, 2).setText('; '.join(m['reason'] for m in proposals[entry.entry_id])
                                              if checked else 'Manual assignment')
        self.reconsider.toggled.connect(toggle_manual)
        layout.addWidget(W.QLabel(f'{len(self.rows)} entries can be categorized. Uncheck any you want to leave unchanged.'))
        buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Apply | W.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(W.QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_proposals(self):
        return {entry_id: self.proposals[entry_id] for row, entry_id in self.rows
                if self.table.item(row, 0).checkState() == QtCore.Qt.CheckState.Checked}
