"""Homepage rules workspace reusing the shared browser and card reference."""
from mtg_ui.loading import LoadingRunnable
from PyQt6 import QtCore as C, QtWidgets as W
from mtg_ui.rules_reference import RulesBrowser
from mtg_core.diagnostics import get_logger


class _Signals(C.QObject):
    ready = C.pyqtSignal(object, str)


class _FindCard(LoadingRunnable):
    def __init__(self, service, name, callback):
        super().__init__()
        self.service, self.name = service, name
        self.signals = _Signals()
        self.signals.ready.connect(callback, C.Qt.ConnectionType.QueuedConnection)

    def run(self):
        try:
            self.signals.ready.emit(self.service.get_card(exact_name=self.name), '')
        except Exception as exc:
            get_logger(__name__).exception('Homepage card reference lookup failed')
            self.signals.ready.emit(None, str(exc))


class RulesWorkspace(RulesBrowser):
    def __init__(self, service, home):
        super().__init__(service)
        self._home = home
        self.setWindowTitle('Rules & Rulings — Manaforge')
        self.card_panel = W.QWidget()
        row = W.QHBoxLayout(self.card_panel)
        row.setContentsMargins(0, 0, 0, 0)
        back = W.QPushButton('Home')
        back.clicked.connect(home)
        self.footer_actions.insertWidget(0, back)
        back.setAutoDefault(False)
        row.addWidget(W.QLabel('Card rulings'))
        self.card_name = W.QLineEdit()
        self.card_name.setPlaceholderText('Exact card name for Oracle text and rulings')
        self.card_name.setClearButtonEnabled(True)
        self.card_name.returnPressed.connect(self.find_card)
        row.addWidget(self.card_name, 1)
        self.card_button = W.QPushButton('Find card')
        self.card_button.setAutoDefault(False)
        self.card_button.clicked.connect(self.find_card)
        row.addWidget(self.card_button)
        self.card_toggle = W.QPushButton('Card rulings')
        self.card_toggle.setAutoDefault(False)
        self.card_toggle.setCheckable(True)
        self.card_toggle.toggled.connect(self.card_panel.setVisible)
        self.search_tools.addWidget(self.card_toggle)
        self.layout().insertWidget(2, self.card_panel)
        self.card_panel.hide()

    def keyPressEvent(self, event):
        if event.key() == C.Qt.Key.Key_Escape and self.card_toggle.isChecked():
            self.card_toggle.setChecked(False)
            event.accept()
        else:
            super().keyPressEvent(event)

    def reject(self):
        if self.property('manaforgeEmbedded') and not self.property('manaforgeQuitting'):
            self._home()
            return
        super().reject()

    def find_card(self):
        name = self.card_name.text().strip()
        if not name or not self.card_button.isEnabled():
            return
        self.card_button.setEnabled(False)
        self.status.setText('Looking up the card in your local catalog…')
        C.QThreadPool.globalInstance().start(_FindCard(self.service, name, self.card_found))

    @C.pyqtSlot(object, str)
    def card_found(self, payload, error):
        if self._closed:
            return
        self.card_button.setEnabled(True)
        if error:
            self.status.setText('Could not find the card. ' + error)
        elif not payload:
            self.status.setText('No local card with that exact name. Download its card data through Core or use Deck Editor search.')
        else:
            from mtg_ui.rulings import RulingsDialog
            self.status.setText('Card found in your local catalog.')
            RulingsDialog(self.service, name=payload.get('name', self.card_name.text()),
                          oracle_id=payload.get('oracle_id'), card_id=payload.get('id'), parent=self).exec()
