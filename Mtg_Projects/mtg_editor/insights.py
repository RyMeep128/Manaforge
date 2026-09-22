"""Read-only composition view over a deck snapshot and local card metadata."""
from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.deck_insights import deck_insights
from .organization import SECTIONS


class InsightsDialog(W.QDialog):
    def __init__(self, document, records, parent=None):
        super().__init__(parent)
        self.document, self.records = document, records
        self.setWindowTitle('Deck insights')
        self.resize(700, 650)
        layout = W.QVBoxLayout(self)
        self.scope = W.QComboBox()
        self.scope.addItem('Mainboard + commanders', ('mainboard', 'commander'))
        self.scope.addItem('Mainboard only', ('mainboard',))
        self.scope.addItem('All sections', tuple(SECTIONS))
        layout.addWidget(self.scope)
        self.summary = W.QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.tabs = W.QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.tables = {}
        for key, title in [('curve', 'Mana curve'), ('colors', 'Colors'), ('pips', 'Mana symbols'),
                           ('types', 'Types'), ('roles', 'Roles / tags')]:
            table = W.QTableWidget(0, 2)
            table.setHorizontalHeaderLabels([title, 'Copies'])
            table.horizontalHeader().setSectionResizeMode(0, W.QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionResizeMode(1, W.QHeaderView.ResizeMode.ResizeToContents)
            table.verticalHeader().hide()
            table.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
            self.tables[key] = table
            self.tabs.addTab(table, title)
        self.note = W.QLabel('Snapshot when opened; reopen after editing. Counts use card quantities and include owned/do-not-print cards. '
            'Average mana value and curve exclude lands. DFCs use the front face. '
            'Multi-type and multicolor cards count in each matching row; hybrid symbols '
            'count toward each color. Roles use your categories and tags, not global tags.')
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.warning = W.QLabel()
        self.warning.setWordWrap(True)
        layout.addWidget(self.warning)
        buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        self.scope.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        result = deck_insights(self.document, self.records, self.scope.currentData())
        self.result = result
        avg = result['average_mana_value']
        average = f'{avg:.2f}' if avg is not None else 'Unknown'
        self.summary.setText(f"{result['total']} cards · {result['lands']} lands · "
            f"{result['nonlands']} nonlands\nAverage mana value: {average} "
            f"({result['known_mana_value']} nonland copies with known mana value)")
        names = dict(W='White', U='Blue', B='Black', R='Red', G='Green', C='Colorless')
        for key, table in self.tables.items():
            rows = result[key]
            table.setRowCount(len(rows))
            for row, (name, count) in enumerate(rows.items()):
                label = f'{name:g}' if isinstance(name, (int, float)) else names.get(name, name) if key in ('colors', 'pips') else name
                table.setItem(row, 0, W.QTableWidgetItem(label))
                table.setItem(row, 1, W.QTableWidgetItem(str(count)))
                if key == 'curve':
                    bar = W.QProgressBar()
                    bar.setRange(0, max(rows.values(), default=1))
                    bar.setValue(count)
                    bar.setFormat(str(count))
                    table.setCellWidget(row, 1, bar)
        missing = ', '.join(f'{count} missing {field}' for field, count in result['unknown'].items())
        self.warning.setText('Incomplete local card data: ' + missing if missing else 'Local card data is complete for these counts.')
