"""Small gallery/dialog widgets using Manaforge's existing visual conventions."""
from PyQt6 import QtCore as C, QtWidgets as W

COLOR_NAMES = {'W': 'White', 'U': 'Blue', 'B': 'Black', 'R': 'Red', 'G': 'Green', 'C': 'Colorless'}
COLOR_SWATCHES = {'W': '#eee4c4', 'U': '#80bddd', 'B': '#b5a6bc',
                  'R': '#e99b87', 'G': '#91c4a2', 'C': '#b7bdc5'}


def plain_label(text='', role=None):
    label = W.QLabel(text)
    label.setTextFormat(C.Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if role:
        label.setProperty('role', role)
    return label


class ColorChoices(W.QWidget):
    """Named color toggles; wire values stay out of the user-facing form."""
    changed = C.pyqtSignal()

    def __init__(self, parent=None, *, allow_any=True):
        super().__init__(parent)
        self.allow_any = allow_any
        self.buttons = {}
        row = W.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        for color, name in COLOR_NAMES.items():
            button = W.QToolButton()
            button.setText(name)
            button.setCheckable(True)
            button.setAccessibleName(name + ' color identity')
            button.setStyleSheet('QToolButton { padding: 0 7px; border-bottom: 3px solid '
                                + COLOR_SWATCHES[color] + '; } QToolButton:checked { background: #20352f; '
                                'border: 2px solid #38b985; border-bottom: 3px solid ' + COLOR_SWATCHES[color] + '; }')
            button.clicked.connect(lambda checked, key=color: self.choose(key, checked))
            self.buttons[color] = button
            row.addWidget(button)
        row.addStretch()
        self.setText('' if allow_any else 'C')

    def choose(self, color, checked):
        if checked:
            for key, button in self.buttons.items():
                if (color == 'C' and key != 'C') or (color != 'C' and key == 'C'):
                    button.setChecked(False)
        if not self.allow_any and not any(button.isChecked() for button in self.buttons.values()):
            self.buttons['C'].setChecked(True)
        self.changed.emit()

    def text(self):
        return ''.join(key for key, button in self.buttons.items() if button.isChecked())

    def setText(self, value):
        if not value and not self.allow_any:
            value = 'C'
        for key, button in self.buttons.items():
            button.setChecked(key in value)

    def clear(self):
        self.setText('' if self.allow_any else 'C')


class SignInDialog(W.QDialog):
    submitted = C.pyqtSignal()

    def __init__(self, parent=None, connection=None):
        super().__init__(parent)
        self.busy = False
        self.setWindowTitle('Sign in' if connection else 'Join a library')
        self.setWindowModality(C.Qt.WindowModality.WindowModal)
        self.setMinimumWidth(420)
        self.resize(470, 420)
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(plain_label('Sign in to your library' if connection else 'Join a deck library', 'title'))
        layout.addWidget(plain_label('Use the address shared by your library host.', 'subtitle'))
        self.mode = W.QTabBar()
        self.mode.addTab('Sign in')
        self.mode.addTab('Create account')
        self.mode.setExpanding(False)
        layout.addWidget(self.mode)
        form = W.QFormLayout()
        form.setSpacing(10)
        self.url = W.QLineEdit(connection['url'] if connection else '')
        self.url.setPlaceholderText('https://your-library.example')
        self.url.setReadOnly(bool(connection))
        form.addRow('Library address', self.url)
        self.username = W.QLineEdit()
        self.username.setMaxLength(64)
        self.username.setPlaceholderText('Your username')
        form.addRow('Username', self.username)
        self.password = W.QLineEdit()
        self.password.setMaxLength(256)
        self.password.setEchoMode(W.QLineEdit.EchoMode.Password)
        form.addRow('Password', self.password)
        self.invitation = W.QLineEdit()
        self.invitation.setMaxLength(200)
        self.invitation.setEchoMode(W.QLineEdit.EchoMode.Password)
        self.invitation.setPlaceholderText('Invitation from the library administrator')
        form.addRow('Invitation', self.invitation)
        self.invitation_label = form.labelForField(self.invitation)
        layout.addLayout(form)
        self.advanced_button = W.QToolButton()
        self.advanced_button.setText('Advanced connection options')
        self.advanced_button.setCheckable(True)
        layout.addWidget(self.advanced_button, 0, C.Qt.AlignmentFlag.AlignLeft)
        self.lan = W.QCheckBox('Allow HTTP on a trusted local network')
        self.lan.setChecked(bool(connection and connection['allow_lan']))
        self.lan.setEnabled(not connection)
        self.lan.hide()
        self.advanced_button.toggled.connect(self.lan.setVisible)
        layout.addWidget(self.lan)
        self.remember_supported = True
        self.remember = W.QCheckBox('Stay signed in on this computer')
        self.remember.setToolTip('Stay signed in for up to two years using Windows-protected storage. Your password is never saved.')
        layout.addWidget(self.remember)
        self.error = plain_label('', 'warning')
        self.error.hide()
        layout.addWidget(self.error)
        self.progress = W.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumHeight(4)
        self.progress.hide()
        layout.addWidget(self.progress)
        layout.addStretch()
        layout.addWidget(plain_label('Your password is never saved.', 'muted'))
        footer = W.QHBoxLayout()
        footer.addStretch()
        self.cancel_button = W.QPushButton('Cancel')
        self.cancel_button.clicked.connect(self.reject)
        self.submit_button = W.QPushButton('Sign in')
        self.submit_button.setProperty('buttonRole', 'primary')
        self.submit_button.setDefault(True)
        self.submit_button.clicked.connect(self.submit)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.submit_button)
        layout.addLayout(footer)
        self.mode.currentChanged.connect(self.change_mode)
        self.change_mode()

    def change_mode(self, *_):
        creating = self.mode.currentIndex() == 1
        self.invitation.setVisible(creating)
        self.invitation_label.setVisible(creating)
        self.submit_button.setText('Create account & join' if creating else 'Sign in')
        self.password.setPlaceholderText('At least 12 characters' if creating else 'Your password')
        self.error.hide()

    def submit(self):
        if self.busy:
            return
        required = [self.url, self.username, self.password]
        if self.mode.currentIndex() == 1:
            required.append(self.invitation)
        for field in required:
            if not field.text().strip():
                self.set_error('Complete the highlighted field to continue.', clear_password=False)
                field.setFocus()
                return
        if self.mode.currentIndex() == 1 and len(self.password.text()) < 12:
            self.set_error('Choose a password with at least 12 characters.', clear_password=False)
            return
        self.submitted.emit()

    def set_busy(self, busy):
        self.busy = busy
        for widget in (self.mode, self.url, self.username, self.password, self.invitation,
                       self.submit_button, self.cancel_button, self.advanced_button):
            widget.setEnabled(not busy)
        self.lan.setEnabled(not busy and not self.url.isReadOnly())
        self.remember.setEnabled(not busy and self.remember_supported)
        self.progress.setVisible(busy)
        if busy:
            self.error.hide()

    def set_error(self, message, *, clear_password=True):
        self.set_busy(False)
        if clear_password:
            self.password.clear()
        self.error.setText(message)
        self.error.show()
        self.password.setFocus()

    def reject(self):
        if not self.busy:
            self.password.clear()
            self.invitation.clear()
            super().reject()


class DeckPreviewDialog(W.QDialog):
    """A focused read-only deck preview, opened from a gallery card or review."""
    def __init__(self, workspace):
        super().__init__(workspace)
        self.workspace = workspace
        self.scope = 'browse'
        self.row = None
        self.setWindowTitle('Deck preview')
        self.setWindowModality(C.Qt.WindowModality.WindowModal)
        self.resize(860, 680)
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        self.title = plain_label('', 'title')
        self.metadata = plain_label('', 'subtitle')
        self.hint = plain_label('', 'warning')
        layout.addWidget(self.title)
        layout.addWidget(self.metadata)
        layout.addWidget(self.hint)
        self.description = plain_label()
        layout.addWidget(self.description)
        self.tabs = W.QTabWidget()
        self.cards = W.QTreeWidget()
        self.cards.setHeaderLabels(['Qty', 'Card', 'Printing', 'Categories'])
        self.cards.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.cards.setRootIsDecorated(True)
        self.cards.header().setSectionResizeMode(0, W.QHeaderView.ResizeMode.ResizeToContents)
        self.cards.header().setSectionResizeMode(1, W.QHeaderView.ResizeMode.Stretch)
        self.cards.setColumnWidth(2, 130)
        self.cards.setColumnWidth(3, 150)
        self.tabs.addTab(self.cards, 'Decklist')
        self.notes = W.QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setAccessibleName('Shared deck details')
        self.tabs.addTab(self.notes, 'Details')
        layout.addWidget(self.tabs, 1)
        self.footer = W.QHBoxLayout()
        self.more_button = W.QToolButton()
        self.more_button.setText('More')
        self.more_button.setPopupMode(W.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_menu = W.QMenu(self.more_button)
        self.more_button.setMenu(self.more_menu)
        self.footer.addWidget(self.more_button)
        self.footer.addStretch()
        self.close_button = W.QPushButton('Close')
        self.close_button.clicked.connect(self.reject)
        self.footer.addWidget(self.close_button)
        layout.addLayout(self.footer)

    def set_publication(self, row, *, scope='browse', hint=''):
        self.scope, self.row = scope, row
        deck = row['deck']
        self.title.setText(deck['name'])
        count = sum(entry['quantity'] for entry in deck['entries'])
        colors = ', '.join(COLOR_NAMES[color] for color in row['color_identity']) or 'Colorless'
        self.metadata.setText(f"{row['owner']} · {deck['format']} · {count} cards · {colors}")
        self.hint.setText(hint)
        self.hint.setVisible(bool(hint))
        self.description.setText(deck['description'])
        self.description.setVisible(bool(deck['description']))
        self.notes.setPlainText(self.workspace.publication_text(row))
        self.cards.clear()
        categories = {item['category_id']: item['name'] for item in deck['categories']}
        groups = {}
        for entry in deck['entries']:
            section = 'Commanders' if entry['entry_id'] in deck['commander_entry_ids'] else entry['section'].replace('_', ' ').title()
            if section not in groups:
                groups[section] = W.QTreeWidgetItem([section])
                self.cards.addTopLevelItem(groups[section])
                groups[section].setFirstColumnSpanned(True)
                groups[section].setExpanded(True)
            printing = ' '.join(filter(None, (entry.get('set_code'), entry.get('collector_number'))))
            child = W.QTreeWidgetItem([str(entry['quantity']), entry['name'], printing,
                                      ', '.join(categories[key] for key in entry['category_ids'])])
            child.setToolTip(1, entry.get('notes', ''))
            groups[section].addChild(child)
        self.tabs.setCurrentIndex(0)

    def show_for(self, parent=None):
        if not self.isVisible() and self.parentWidget() is not (parent or self.workspace):
            self.setParent(parent or self.workspace, C.Qt.WindowType.Dialog)
        if self.isVisible():
            self.raise_()
        else:
            self.open()

    def reject(self):
        if not self.workspace._job:
            super().reject()
