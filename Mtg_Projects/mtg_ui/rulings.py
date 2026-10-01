"""Shared offline rulings viewer with explicit background updates."""
from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.diagnostics import get_logger
from mtg_core.search import card_rules_text


def add_card_reference_action(menu, service, *, name, oracle_id=None, card_id=None, parent=None):
    """Bind the clicked card's identity, independently of other selected cards."""
    action = menu.addAction('View Oracle text and rulings…')
    action.setEnabled(bool(oracle_id or card_id))
    action.triggered.connect(lambda: RulingsDialog(
        service, name=name, oracle_id=oracle_id, card_id=card_id, parent=parent).exec())
    return action


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
        result = {'card_id': self.card_id, 'oracle_id': self.oracle_id, 'payload': None,
                  'snapshot': None}
        try:
            if self.refresh:
                result['snapshot'] = self.service.refresh_rulings(
                    card_id=self.card_id, oracle_id=self.oracle_id)
            else:
                payload = self.service.get_card(card_id=self.card_id) if self.card_id else None
                if payload and self.oracle_id and payload.get('oracle_id') != self.oracle_id:
                    payload = None
                    result['card_id'] = None
                if not payload and self.oracle_id:
                    payload = self.service.get_card(oracle_id=self.oracle_id)
                # A stale or mismatched printing must not replace the requested card.
                if payload and self.oracle_id and payload.get('oracle_id') != self.oracle_id:
                    payload = None
                    result['card_id'] = None
                if payload:
                    result.update(payload=payload, card_id=payload.get('id'),
                                  oracle_id=payload.get('oracle_id') or self.oracle_id)
                if result['oracle_id']:
                    result['snapshot'] = self.service.get_rulings(result['oracle_id'])
            self.signals.ready.emit(result, '')
        except Exception as exc:
            get_logger(__name__).exception('Rulings load failed oracle_id=%s refresh=%s',
                                           self.oracle_id, self.refresh)
            self.signals.ready.emit(result, str(exc))


class RulingsDialog(W.QDialog):
    def __init__(self, service, *, name, oracle_id, card_id=None, parent=None):
        super().__init__(parent)
        self.setAttribute(C.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.service, self.oracle_id, self.card_id = service, oracle_id, card_id
        self._closed = False
        self.setWindowTitle(f'{name} — Card reference')
        self.resize(650, 520)
        layout = W.QVBoxLayout(self)
        self.metadata = W.QLabel('Rulings cache format 1 · Loading cached rulings…')
        self.metadata.setWordWrap(True)
        layout.addWidget(self.metadata)
        self.text = W.QTextBrowser()
        self.text.setPlainText('Loading cached rulings…')
        self.oracle_text = W.QTextBrowser()
        self.oracle_text.setPlainText('Loading local Oracle text…')
        tabs = W.QTabWidget()
        tabs.addTab(self.oracle_text, 'Oracle text')
        tabs.addTab(self.text, 'Rulings')
        layout.addWidget(tabs, 1)
        self.status = W.QLabel('')
        self.status.setWordWrap(True)
        self.status.setTextFormat(C.Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        buttons = W.QHBoxLayout()
        self.refresh = W.QPushButton('Refresh rulings from Scryfall')
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
    def loaded(self, result, error):
        if self._closed:
            return
        self.card_id, self.oracle_id = result['card_id'], result['oracle_id']
        if result['payload'] is not None:
            payload = result['payload']
            text = card_rules_text(payload) or 'Oracle text unavailable in the local catalog.'
            keywords = payload.get('keywords') or []
            if keywords:
                text += '\n\nKeywords: ' + ', '.join(str(keyword) for keyword in keywords)
            self.oracle_text.setPlainText(text)
        elif self.oracle_text.toPlainText() == 'Loading local Oracle text…':
            self.oracle_text.setPlainText('Oracle text unavailable in the local catalog.')
        self.refresh.setEnabled(bool(self.card_id and self.oracle_id))
        if error:
            self.status.setText('Could not load rulings. Existing cached rulings were preserved. ' + error)
            if self.text.toPlainText() == 'Loading cached rulings…':
                self.text.setPlainText('Cached rulings could not be read.')
                self.metadata.setText('Rulings cache format 1 · Cache unavailable')
            return
        snapshot = result['snapshot']
        if not self.oracle_id:
            self.metadata.setText('Card identity unavailable')
            self.text.setPlainText('This card has no local Oracle identity. Import its Scryfall record to view rulings.')
            self.status.setText('No network request was made.')
            return
        self.status.setText('Source: Scryfall. Wizards rulings and Scryfall notes are labelled separately.'
                            if self.card_id else 'A Scryfall printing is required to download rulings.')
        if snapshot is None:
            self.metadata.setText('Rulings cache format 1 · Not downloaded')
            message = 'No rulings have been downloaded for this card.'
            if self.card_id:
                message += ' Use Refresh rulings from Scryfall to cache them for offline reading.'
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
