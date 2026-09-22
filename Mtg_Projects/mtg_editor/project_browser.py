"""Shared deck/project browser, available from both Editor and Proxy."""
from datetime import datetime
from pathlib import Path
from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.project_catalog import project_catalog


class CatalogWorker(C.QThread):
    def __init__(self, deck_root, project_root, parent):
        super().__init__(parent)
        self.roots = deck_root, project_root
        self.result = [], []

    def run(self):
        try:
            self.result = project_catalog(*self.roots)
        except Exception as exc:
            self.result = [], [str(exc)]


class ProjectBrowser(W.QDialog):
    def __init__(self, deck_root, project_root, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Decks and print projects')
        self.resize(760, 520)
        self.path, self.new_deck, self.closing = None, False, False
        layout = W.QVBoxLayout(self)
        self.filter = W.QLineEdit()
        self.filter.setPlaceholderText('Filter by name or project type')
        layout.addWidget(self.filter)
        self.table = W.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['Name', 'Type', 'Updated'])
        self.table.horizontalHeader().setSectionResizeMode(0, W.QHeaderView.ResizeMode.Stretch)
        for column in (1, 2):
            self.table.horizontalHeader().setSectionResizeMode(column, W.QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(W.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(W.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)
        self.status = W.QLabel('Loading projects…')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = W.QHBoxLayout()
        for label, action in [('New deck', self.create), ('Open file…', self.browse), ('Open selected', self.open_selected), ('Close', self.reject)]:
            button = W.QPushButton(label)
            button.clicked.connect(action)
            row.addWidget(button)
        layout.addLayout(row)
        self.table.cellDoubleClicked.connect(self.open_selected)
        self.filter.textChanged.connect(self.filter_rows)
        self.worker = CatalogWorker(deck_root, project_root, self)
        self.worker.finished.connect(self.loaded)
        self.worker.start()

    def loaded(self):
        rows, errors = self.worker.result
        self.worker.deleteLater()
        self.worker = None
        if self.closing:
            super().reject()
            return
        self.table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            values = (item['name'], item['kind'], datetime.fromtimestamp(item['modified']).strftime('%Y-%m-%d %H:%M'))
            for col, text in enumerate(values):
                cell = W.QTableWidgetItem(text)
                cell.setToolTip(item['path'])
                cell.setData(C.Qt.ItemDataRole.UserRole, item['path'])
                self.table.setItem(row, col, cell)
        self.status.setText(f'{len(rows)} projects. Print projects open as separate editable decks.' +
                            (f' {len(errors)} unavailable files; hover for details.' if errors else ''))
        self.status.setToolTip('\n'.join(errors))
        self.filter_rows()

    def filter_rows(self, *_):
        query = self.filter.text().casefold()
        for row in range(self.table.rowCount()):
            text = ' '.join(self.table.item(row, c).text() for c in (0, 1)).casefold()
            self.table.setRowHidden(row, query not in text)

    def open_selected(self, *_):
        row = self.table.currentRow()
        if self.worker is None and row >= 0 and not self.table.isRowHidden(row):
            self.path = Path(self.table.item(row, 0).data(C.Qt.ItemDataRole.UserRole))
            self.accept()

    def create(self):
        if self.worker is None:
            self.new_deck = True
            self.accept()

    def browse(self):
        if self.worker is None:
            path, _ = W.QFileDialog.getOpenFileName(self, 'Open deck or project', '', 'JSON projects (*.json)')
            if path:
                self.path = Path(path)
                self.accept()

    def reject(self):
        if self.worker is not None:
            self.closing = True
        else:
            super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            self.closing = True
            event.ignore()
        else:
            super().closeEvent(event)
