"""Shared, offline What’s New presentation and per-version acknowledgment."""
import logging
from PyQt6 import QtCore as C, QtWidgets as W
from mtg_proxy.constants import APP_VERSION
from mtg_print.update_service import is_newer_version, UpdateCheckError
from .release_notes import GROUPS, load_notes


class WhatsNewDialog(W.QDialog):
    def __init__(self, notes, parent=None):
        super().__init__(parent)
        self.setWindowTitle('What’s New in Manaforge')
        self.resize(590, 520)
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        def label(text, role=None):
            widget = W.QLabel(text)
            widget.setTextFormat(C.Qt.TextFormat.PlainText)
            widget.setWordWrap(True)
            if role:
                widget.setProperty('role', role)
            return widget

        layout.addWidget(label('What’s New in Manaforge', 'title'))
        layout.addWidget(label(f'Version {APP_VERSION}', 'success'))
        layout.addWidget(label(notes['summary'] or
            'You’re ready to build. Update highlights will appear here when available.', 'subtitle'))
        scroll = W.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFocusPolicy(C.Qt.FocusPolicy.StrongFocus)
        scroll.setAccessibleName('Update highlights')
        content = W.QWidget()
        body = W.QVBoxLayout(content)
        body.setContentsMargins(0, 0, 10, 0)
        body.setSpacing(12)
        if len(notes['versions']) > 1:
            body.addWidget(label('Highlights from your skipped updates, together in one place.', 'muted'))
        for key, title in GROUPS:
            if not notes['groups'][key]:
                continue
            group = W.QGroupBox(title)
            items = W.QVBoxLayout(group)
            items.setSpacing(10)
            for text in notes['groups'][key]:
                items.addWidget(label('•  ' + text))
            body.addWidget(group)
        if not any(notes['groups'].values()):
            body.addWidget(label('There are no update highlights available for this version yet.', 'muted'))
        body.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        buttons = W.QDialogButtonBox()
        start = buttons.addButton('Start Building', W.QDialogButtonBox.ButtonRole.AcceptRole)
        start.setProperty('buttonRole', 'primary')
        start.setDefault(True)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        start.setFocus()


class WhatsNew(C.QObject):
    def __init__(self, app):
        super().__init__(app)
        self.settings = C.QSettings('Manaforge', 'ApplicationUpdates')
        self.started = False
        self.dialog = None

    def startup(self, parent=None, previous=None):
        """Called after a usable window exists, or after update verification succeeds."""
        if self.started:
            return
        self.started = True
        try:
            last = self.settings.value('whatsNew/lastSuccessfulVersion', '') or previous
            acknowledged = self.settings.value('whatsNew/acknowledgedVersion', '')
            self.settings.setValue('whatsNew/lastSuccessfulVersion', APP_VERSION)
            self.settings.sync()
            if not last:
                # Establish a quiet baseline for fresh installs and older settings.
                self.settings.setValue('whatsNew/baselineVersion', APP_VERSION)
                self.settings.sync()
                return
            if not is_newer_version(APP_VERSION, last) and acknowledged == APP_VERSION:
                return
            baseline = acknowledged or self.settings.value('whatsNew/baselineVersion', '') or last
            self.settings.setValue('whatsNew/baselineVersion', baseline)
            self.settings.sync()
            if not is_newer_version(APP_VERSION, baseline):
                return
            notes = load_notes(APP_VERSION, baseline)
            if any(notes['groups'].values()):
                self.show(parent, notes=notes, automatic=True)
        except (OSError, TypeError, ValueError, UpdateCheckError):
            logging.getLogger(__name__).exception('Could not load update highlights')

    def show(self, parent=None, *, notes=None, automatic=False):
        if self.dialog is not None:
            self.dialog.raise_()
            self.dialog.activateWindow()
            return
        self.dialog = WhatsNewDialog(notes or load_notes(APP_VERSION), parent)
        self.dialog.setAttribute(C.Qt.WidgetAttribute.WA_DeleteOnClose)

        def dismissed(_result):
            self.dialog = None
            if automatic:
                # Escape and the window close button also acknowledge the highlights.
                self.settings.setValue('whatsNew/acknowledgedVersion', APP_VERSION)
                self.settings.sync()

        self.dialog.finished.connect(dismissed)
        self.dialog.open()


def whats_new():
    app = W.QApplication.instance()
    if not hasattr(app, '_whats_new'):
        app._whats_new = WhatsNew(app)
    return app._whats_new
