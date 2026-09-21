"""Preview imports before applying; resolve on a cancellable worker thread."""
from PyQt6 import QtCore as C, QtWidgets as W
from threading import Event
from mtg_core.decklists import resolve_decklist, resolve_entries, read_decklist_file, export_decklist
from mtg_core.deck_sources import fetch_public_deck


class ImportWorker(C.QThread):
    progress = C.pyqtSignal(int, int)

    def __init__(self, text, service, remote, parent=None, *, public_url=''):
        super().__init__(parent)
        self.text, self.service, self.remote = text, service, remote
        self.result, self.error = None, ''
        self.cancelled = Event()
        self.public_url = public_url

    def run(self):
        try:
            if self.public_url:
                entries = fetch_public_deck(self.public_url, cancelled=self.cancelled.is_set)
                self.result = resolve_entries(entries, self.service, allow_remote=self.remote,
                    progress=self.progress.emit, cancelled=self.cancelled.is_set)
            else:
                self.result = resolve_decklist(self.text, self.service, allow_remote=self.remote,
                    progress=self.progress.emit, cancelled=self.cancelled.is_set)
        except Exception as exc:
            self.error = str(exc)


class ImportDecklist(W.QDialog):
    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service, self.worker, self.result = service, None, None
        self.setWindowTitle('Import decklist')
        self.resize(700, 650)
        layout = W.QVBoxLayout(self)
        note = W.QLabel('Paste a decklist, load a text/CSV file, or import a public deck URL. Sections and exact printings are preserved. '
                       'Import adds to this deck; review unresolved lines before applying.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.input_mode = W.QComboBox()
        self.input_mode.addItems(['Text / CSV', 'Public deck URL'])
        layout.addWidget(self.input_mode)
        self.url = W.QLineEdit()
        self.url.setPlaceholderText('Public Archidekt, Moxfield, or Blueprint MTG deck URL')
        self.url.hide()
        layout.addWidget(self.url)
        self.url_note = W.QLabel('Review downloads public deck data. The option below controls additional card lookups.')
        self.url_note.setWordWrap(True)
        self.url_note.hide()
        layout.addWidget(self.url_note)
        self.source = W.QPlainTextEdit()
        self.source.setPlaceholderText('Commander\n1 Your commander\nDeck\n1 Sol Ring (cmm) 410\nSideboard\n1 Opt')
        layout.addWidget(self.source, 1)
        row = W.QHBoxLayout()
        self.file_button = W.QPushButton('Load file…')
        self.file_button.clicked.connect(self.load_file)
        row.addWidget(self.file_button)
        self.remote = W.QCheckBox('Fetch missing cards online')
        row.addWidget(self.remote)
        self.resolve_button = W.QPushButton('Review import')
        self.resolve_button.clicked.connect(self.resolve)
        row.addWidget(self.resolve_button)
        layout.addLayout(row)
        self.progress = W.QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.preview = W.QTableWidget(0, 4)
        self.preview.setHorizontalHeaderLabels(['Card', 'Quantity', 'Section', 'Printing'])
        self.preview.horizontalHeader().setSectionResizeMode(0, W.QHeaderView.ResizeMode.Stretch)
        self.preview.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.preview, 1)
        self.messages = W.QPlainTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setMaximumHeight(100)
        layout.addWidget(self.messages)
        self.buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Apply | W.QDialogButtonBox.StandardButton.Cancel)
        self.apply_button = self.buttons.button(W.QDialogButtonBox.StandardButton.Apply)
        self.apply_button.setText('Import reviewed cards')
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.source.textChanged.connect(self.invalidate)
        self.remote.toggled.connect(self.invalidate)
        self.url.textChanged.connect(self.invalidate)
        self.input_mode.currentIndexChanged.connect(self.change_mode)

    def change_mode(self, index):
        self.invalidate()
        self.source.setVisible(index == 0)
        self.file_button.setVisible(index == 0)
        self.url.setVisible(index == 1)
        self.url_note.setVisible(index == 1)

    def invalidate(self):
        self.result = None
        self.apply_button.setEnabled(False)
        self.preview.setRowCount(0)
        self.messages.clear()

    def load_file(self):
        path, _ = W.QFileDialog.getOpenFileName(self, 'Import decklist', '', 'Decklists (*.txt *.csv *.dec *.dek);;All files (*)')
        if path:
            try:
                self.source.setPlainText(read_decklist_file(path))
            except OSError as exc:
                W.QMessageBox.warning(self, 'Could not read decklist', str(exc))

    def resolve(self):
        public_url = self.url.text().strip() if self.input_mode.currentIndex() == 1 else ''
        source = self.source.toPlainText().strip() if self.input_mode.currentIndex() == 0 else public_url
        if self.worker is not None or not source:
            return
        self.invalidate()
        for widget in (self.source, self.file_button, self.remote, self.resolve_button, self.url, self.input_mode):
            widget.setEnabled(False)
        self.progress.setRange(0, 0)
        self.worker = ImportWorker(source, self.service, self.remote.isChecked(), self, public_url=public_url)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.resolved)
        self.worker.start()

    def update_progress(self, done, total):
        self.progress.setRange(0, total)
        self.progress.setValue(done)

    def resolved(self):
        worker, self.worker = self.worker, None
        self.result = worker.result
        cancelled = worker.cancelled.is_set()
        worker.deleteLater()
        if cancelled:
            self.result = None
            super().reject()
            return
        for widget in (self.source, self.file_button, self.remote, self.resolve_button, self.url, self.input_mode):
            widget.setEnabled(True)
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        if worker.error:
            self.messages.setPlainText(worker.error)
            return
        entries, _, warnings = self.result
        self.preview.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            for col, value in enumerate((entry.name, str(entry.quantity), entry.section,
                                         f'{entry.set_code or ""} {entry.collector_number or ""}')):
                self.preview.setItem(row, col, W.QTableWidgetItem(value))
        self.messages.setPlainText(f'{sum(e.quantity for e in entries)} cards ready; {len(warnings)} unresolved lines.\n'
                                  + '\n'.join(warnings))
        self.apply_button.setEnabled(bool(entries))

    def reject(self):
        if self.worker is not None:
            self.worker.cancelled.set()
            self.messages.setPlainText('Cancelling after the current lookup finishes…')
        else:
            super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)


class ExportDecklist(W.QDialog):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Export decklist')
        self.resize(600, 500)
        layout = W.QVBoxLayout(self)
        self.printings = W.QCheckBox('Include set / collector number')
        self.sections = W.QCheckBox('Include sections')
        self.printings.setChecked(True)
        self.sections.setChecked(True)
        layout.addWidget(self.printings)
        layout.addWidget(self.sections)
        self.preview = W.QPlainTextEdit()
        self.preview.setReadOnly(True)
        layout.addWidget(self.preview)
        def refresh():
            self.preview.setPlainText(export_decklist(document, include_printings=self.printings.isChecked(),
                                                     include_sections=self.sections.isChecked()))
        self.printings.toggled.connect(refresh)
        self.sections.toggled.connect(refresh)
        refresh()
        row = W.QHBoxLayout()
        for label, action in [('Copy', lambda: W.QApplication.clipboard().setText(self.preview.toPlainText())),
                              ('Save text file…', self.save_file), ('Close', self.accept)]:
            button = W.QPushButton(label)
            button.clicked.connect(action)
            row.addWidget(button)
        layout.addLayout(row)

    def save_file(self):
        path, _ = W.QFileDialog.getSaveFileName(self, 'Export decklist', 'deck.txt', 'Text decklist (*.txt)')
        if path:
            try:
                from pathlib import Path
                Path(path).write_text(self.preview.toPlainText(), encoding='utf-8')
            except OSError as exc:
                W.QMessageBox.warning(self, 'Could not export decklist', str(exc))
