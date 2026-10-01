"""Shared offline rulings viewer with explicit background updates."""
from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.diagnostics import get_logger


class _Signals(C.QObject):
    ready = C.pyqtSignal(object, str)


class _Load(C.QRunnable):
    def __init__(self, service, card_id, oracle_id, refresh, callback):
        super().__init__()
        self.service, self.card_id, self.oracle_id = service, card_id, oracle_id
        self.refresh = refresh
        self.signals = _Signals()
        self.signals.ready.connect(callback, C.Qt.ConnectionType.QueuedConnection)

    def run(self):
        try:
            if self.refresh:
                result = self.service.refresh_rulings(card_id=self.card_id, oracle_id=self.oracle_id)
            else:
                result = self.service.get_rulings(self.oracle_id)
            self.signals.ready.emit(result, '')
        except Exception as exc:
            get_logger(__name__).exception('Rulings load failed oracle_id=%s refresh=%s',
                                           self.oracle_id, self.refresh)
            self.signals.ready.emit(None, str(exc))


class RulingsDialog(W.QDialog):
    def __init__(self, service, *, name, oracle_id, card_id=None, parent=None):
        super().__init__(parent)
        self.setAttribute(C.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.service, self.oracle_id, self.card_id = service, oracle_id, card_id
        self._closed = False
        self.setWindowTitle(f'{name} — Card rulings')
        self.resize(650, 520)
        layout = W.QVBoxLayout(self)
        self.metadata = W.QLabel('Rulings cache format 1 · Loading cached rulings…')
        self.metadata.setWordWrap(True)
        layout.addWidget(self.metadata)
        self.text = W.QTextBrowser()
        self.text.setPlainText('Loading cached rulings…')
        layout.addWidget(self.text, 1)
        self.status = W.QLabel('')
        self.status.setWordWrap(True)
        self.status.setTextFormat(C.Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        buttons = W.QHBoxLayout()
        self.refresh = W.QPushButton('Refresh from Scryfall')
        self.refresh.clicked.connect(lambda: self.load(refresh=True))
        buttons.addWidget(self.refresh)
        close = W.QPushButton('Close')
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.load()

    def load(self, *, refresh=False):
        self.refresh.setEnabled(False)
        self.status.setText('Downloading rulings…' if refresh else 'Reading local cache…')
        C.QThreadPool.globalInstance().start(
            _Load(self.service, self.card_id, self.oracle_id, refresh, self.loaded))

    @C.pyqtSlot(object, str)
    def loaded(self, snapshot, error):
        if self._closed:
            return
        self.refresh.setEnabled(bool(self.card_id))
        if error:
            self.status.setText('Could not load rulings. Existing cached rulings were preserved. ' + error)
            if self.text.toPlainText() == 'Loading cached rulings…':
                self.text.setPlainText('Cached rulings could not be read.')
                self.metadata.setText('Rulings cache format 1 · Cache unavailable')
            return
        self.status.setText('Source: Scryfall. Wizards rulings and Scryfall notes are labelled separately.'
                            if self.card_id else 'A Scryfall printing is required to download rulings.')
        if snapshot is None:
            self.metadata.setText('Rulings cache format 1 · Not downloaded')
            message = 'No rulings have been downloaded for this card.'
            if self.card_id:
                message += ' Use Refresh from Scryfall to cache them for offline reading.'
            self.text.setPlainText(message)
            return
        self.metadata.setText('Rulings cache format 1 · Last downloaded (UTC): ' + snapshot['fetched_at'])
        paragraphs = []
        for row in snapshot['rulings']:
            source = 'Wizards of the Coast' if row['source'] == 'wotc' else 'Scryfall note'
            paragraphs.append(f"{row['published_at']} · {source}\n\n{row['comment']}")
        self.text.setPlainText('\n\n────\n\n'.join(paragraphs) or
                               'Scryfall returned no rulings for this card at the last download.')

    def done(self, result):
        self._closed = True
        super().done(result)
