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
        explanation = W.QLabel('Uses local Oracle Tags and front-face types only. First role is the primary category. '
                              'Manual categories are preserved. Missing tags may produce type-only results.')
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
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
        layout.addWidget(W.QLabel(f'{len(self.rows)} entries can be categorized. Uncheck any you want to leave unchanged.'))
        buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Apply | W.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(W.QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_proposals(self):
        return {entry_id: self.proposals[entry_id] for row, entry_id in self.rows
                if self.table.item(row, 0).checkState() == QtCore.Qt.CheckState.Checked}
