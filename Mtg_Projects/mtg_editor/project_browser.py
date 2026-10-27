"""Visual deck/project browser shared by the editor and Print Studio."""
from mtg_ui.loading import LoadingThread
from datetime import datetime
from pathlib import Path
from .card_drop import CardSearchEdit
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_core.project_catalog import project_catalog, managed_deck_path, rename_deck
from mtg_core.diagnostics import get_logger


class CatalogWorker(LoadingThread):
    def __init__(self, deck_root, project_root, parent):
        super().__init__(parent)
        self.roots = deck_root, project_root
        self.result = [], []

    def run(self):
        try:
            self.result = project_catalog(*self.roots)
        except Exception as exc:
            get_logger(__name__).exception('Project catalog failed deck_root=%s project_root=%s', *self.roots)
            self.result = [], [str(exc)]


class ProjectList(W.QListWidget):
    """Keep row-based access for existing modal-browser integrations."""
    def rowCount(self):
        return self.count()

    def isRowHidden(self, row):
        item = self.item(row)
        return item.isHidden() if item is not None else False

    def selectRow(self, row):
        self.setCurrentRow(row)


class ProjectTileDelegate(W.QStyledItemDelegate):
    def __init__(self, browser):
        super().__init__(browser)
        self.browser = browser

    def sizeHint(self, option, index):
        return C.QSize(220, 282)

    def paint(self, painter, option, index):
        row = index.data(C.Qt.ItemDataRole.UserRole)
        rect = option.rect.adjusted(3, 3, -3, -3)
        selected = bool(option.state & W.QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & W.QStyle.StateFlag.State_MouseOver)
        painter.save()
        painter.setRenderHint(G.QPainter.RenderHint.Antialiasing)
        painter.setPen(G.QColor('#8ab4f8' if selected else '#566273' if hovered else '#303743'))
        painter.setBrush(G.QColor('#252e3b' if selected else '#1d222b' if hovered else '#171b22'))
        painter.drawRoundedRect(rect, 9, 9)
        image_rect = C.QRect(rect.center().x()-55, rect.top()+12, 110, 154)
        cover = row.get('cover', (None, None))
        pixmap = self.browser.thumbnails.get(*cover) if any(cover) else None
        if pixmap is not None and not pixmap.isNull():
            scaled = pixmap.scaled(image_rect.size(), C.Qt.AspectRatioMode.KeepAspectRatio,
                                   C.Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(image_rect.center().x()-scaled.width()//2,
                               image_rect.center().y()-scaled.height()//2, scaled)
        else:
            painter.setPen(G.QColor('#465467'))
            painter.setBrush(G.QColor('#232c38'))
            painter.drawRoundedRect(image_rect, 6, 6)
            painter.setPen(G.QColor('#9faec1'))
            painter.drawText(image_rect, C.Qt.AlignmentFlag.AlignCenter, 'Manaforge')
        text_rect = C.QRect(rect.left()+10, rect.top()+178, rect.width()-20, 24)
        font = G.QFont(option.font)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(G.QColor('#edf1f7'))
        painter.drawText(text_rect, C.Qt.AlignmentFlag.AlignCenter,
                         G.QFontMetrics(font).elidedText(row['name'], C.Qt.TextElideMode.ElideRight, text_rect.width()))
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(G.QColor('#aab6c7'))
        details = f"{row['kind']} · {row.get('format') or 'Custom'}\n{row.get('card_count', 0)} cards\nUpdated {datetime.fromtimestamp(row['modified']):%Y-%m-%d %H:%M}"
        painter.drawText(C.QRect(rect.left()+8, rect.top()+207, rect.width()-16, 62),
                         C.Qt.AlignmentFlag.AlignCenter, details)
        if option.state & W.QStyle.StateFlag.State_HasFocus:
            painter.setPen(G.QPen(G.QColor('#8ab4f8'), 1, C.Qt.PenStyle.DotLine))
            painter.setBrush(C.Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(3, 3, -3, -3), 7, 7)
        painter.restore()


class ProjectDashboard(W.QWidget):
    openRequested = C.pyqtSignal(object)
    newRequested = C.pyqtSignal()
    resumeRequested = C.pyqtSignal()
    deckRenamed = C.pyqtSignal(object, str)
    deckDeleted = C.pyqtSignal(object)
    settled = C.pyqtSignal()

    def __init__(self, deck_root, project_root, thumbnails, parent=None):
        super().__init__(parent)
        self.roots = deck_root, project_root
        self.thumbnails = thumbnails
        self.worker = None
        self.rows, self.errors = [], []
        self.stopping = False
        self.setMinimumWidth(300)
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        title = W.QLabel('Your decks')
        title.setProperty('role', 'title')
        layout.addWidget(title)
        self.subtitle = W.QLabel('Pick up where you left off or start a new deck.')
        subtitle = self.subtitle
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        actions = W.QHBoxLayout()
        self.resume_button = W.QPushButton('Resume deck')
        self.resume_button.clicked.connect(self.resumeRequested.emit)
        self.resume_button.hide()
        new_button = W.QPushButton('+ New deck')
        new_button.setProperty('buttonRole', 'primary')
        new_button.clicked.connect(self.newRequested.emit)
        open_button = W.QPushButton('Open file…')
        open_button.clicked.connect(self.browse)
        self.refresh_button = W.QPushButton('Refresh')
        self.refresh_button.clicked.connect(self.refresh)
        for button in (new_button, open_button, self.resume_button, self.refresh_button):
            button.setAutoDefault(False)
            actions.addWidget(button)
        self.tabs = W.QTabBar()
        self.tabs.addTab('Decks')
        self.tabs.addTab('Print projects')
        self.tabs.setAccessibleName('Project library tabs')
        self.tabs.setExpanding(False)
        actions.addWidget(self.tabs)
        actions.addStretch()
        layout.addLayout(actions)
        filters = W.QHBoxLayout()
        self.filter = CardSearchEdit()
        self.filter.setPlaceholderText('Search by name, type, or format')
        self.filter.setAccessibleName('Search projects')
        self.find_shortcut = G.QShortcut(G.QKeySequence('Ctrl+F'), self)
        self.find_shortcut.setContext(C.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.find_shortcut.activated.connect(self.filter.setFocus)
        self.sort = W.QComboBox()
        self.sort.addItems(['Updated: newest first', 'Name: A–Z'])
        self.sort.setAccessibleName('Sort projects')
        filters.addWidget(self.filter, 1)
        filters.addWidget(self.sort)
        layout.addLayout(filters)
        self.list = ProjectList()
        self.list.setAccessibleName('Decks')
        self.list.setViewMode(W.QListView.ViewMode.IconMode)
        self.list.setResizeMode(W.QListView.ResizeMode.Adjust)
        self.list.setMovement(W.QListView.Movement.Static)
        self.list.setSelectionMode(W.QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list.setSpacing(8)
        self.list.setGridSize(C.QSize(228, 290))
        self.list.setMouseTracking(True)
        self.list.setItemDelegate(ProjectTileDelegate(self))
        self.list.setContextMenuPolicy(C.Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self.deck_context_menu)
        self.list.itemActivated.connect(self.open_selected)
        self.list.itemSelectionChanged.connect(self.selection_changed)
        self.list.verticalScrollBar().valueChanged.connect(self.update_visible)
        self.list.viewport().installEventFilter(self)
        layout.addWidget(self.list, 1)
        self.empty = W.QLabel('Loading projects…')
        self.empty.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)
        self.status = W.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.error_details = W.QPlainTextEdit()
        self.error_details.setReadOnly(True)
        self.error_details.setMaximumHeight(80)
        self.error_details.hide()
        layout.addWidget(self.error_details)
        self.open_button = W.QPushButton('Open selected')
        self.open_button.setAutoDefault(False)
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_selected)
        layout.addWidget(self.open_button)
        self.filter.textChanged.connect(self.filter_rows)
        self.filter.returnPressed.connect(self.open_selected)
        self.sort.currentIndexChanged.connect(self.filter_rows)
        self.tabs.currentChanged.connect(self.filter_rows)
        self.thumbnails.updated.connect(self.list.viewport().update)
        self.refresh()

    def refresh(self):
        if self.worker is not None or self.stopping:
            return
        self.refresh_button.setEnabled(False)
        self.status.setText('Loading projects…')
        self.worker = CatalogWorker(*self.roots, self)
        self.worker.finished.connect(self.loaded)
        self.worker.start()

    def loaded(self):
        self.rows, self.errors = self.worker.result
        self.worker.deleteLater()
        self.worker = None
        self.refresh_button.setEnabled(True)
        if not self.stopping:
            self.error_details.setPlainText('\n'.join(self.errors))
            self.error_details.setVisible(bool(self.errors))
            self.filter_rows()
        self.settled.emit()

    def filter_rows(self, *_):
        selected = self.list.currentItem()
        selected_path = selected.data(C.Qt.ItemDataRole.UserRole)['path'] if selected else None
        query = self.filter.text().strip().casefold()
        print_projects = self.tabs.currentIndex() == 1
        kind = 'Print project' if print_projects else 'Deck'
        label = 'print projects' if print_projects else 'decks'
        self.subtitle.setText('Open a print project as a separate editable deck.' if print_projects else
                              'Pick up where you left off or start a new deck.')
        self.list.setAccessibleName('Print projects' if print_projects else 'Decks')
        self.open_button.setText('Open selected as deck' if print_projects else 'Open selected')
        rows = [row for row in self.rows if row['kind'] == kind]
        rows.sort(key=(lambda row: (row['name'].casefold(), row['path'])) if self.sort.currentIndex()
                  else (lambda row: (-row['modified'], row['name'].casefold(), row['path'])))
        self.list.clear()
        visible = []
        for row in rows:
            item = W.QListWidgetItem(row['name'])
            item.setData(C.Qt.ItemDataRole.UserRole, row)
            item.setToolTip(f"{row['name']}\n{row['path']}")
            self.list.addItem(item)
            matches = query in ' '.join(str(row.get(key, '')) for key in ('name', 'kind', 'format')).casefold()
            item.setHidden(not matches)
            if matches:
                visible.append(item)
                if row['path'] == selected_path:
                    self.list.setCurrentItem(item)
        if self.list.currentItem() is None and visible:
            self.list.setCurrentItem(visible[0])
        self.empty.setVisible(not visible)
        self.empty.setText(f'No matching {label}. Try another search.' if rows else
                           'No print projects yet. Open a project file to edit it as a deck.' if print_projects else
                           'No decks yet. Start a new deck or open a deck file.')
        self.status.setText(f'{len(visible)} of {len(rows)} {label}' +
                            (f' · {len(self.errors)} unavailable files (details below)' if self.errors else ''))
        self.selection_changed()
        C.QTimer.singleShot(0, self.update_visible)

    def selection_changed(self):
        item = self.list.currentItem()
        self.open_button.setEnabled(item is not None and not item.isHidden())

    def open_selected(self, *_):
        item = self.list.currentItem()
        if item is not None and not item.isHidden() and not self.stopping:
            self.openRequested.emit(Path(item.data(C.Qt.ItemDataRole.UserRole)['path']))

    def deck_context_menu(self, position):
        item = self.list.itemAt(position)
        if item is None or self.worker is not None or self.stopping:
            return
        row = item.data(C.Qt.ItemDataRole.UserRole)
        if row['kind'] != 'Deck':
            return
        self.list.setCurrentItem(item)
        menu = W.QMenu(self)
        rename = menu.addAction('Rename...')
        delete = menu.addAction('Delete...')
        action = menu.exec(self.list.viewport().mapToGlobal(position))
        if action == rename:
            self.rename_selected_deck(row)
        elif action == delete:
            self.delete_selected_deck(row)

    def rename_selected_deck(self, row):
        name, accepted = W.QInputDialog.getText(self, 'Rename deck', 'Deck name:', text=row['name'])
        if not accepted or name.strip() == row['name']:
            return
        try:
            name = rename_deck(row['path'], self.roots[0], name)
        except (OSError, ValueError, TypeError) as exc:
            W.QMessageBox.warning(self, 'Could not rename deck', str(exc))
            return
        self.deckRenamed.emit(Path(row['path']), name)
        self.refresh()

    def delete_selected_deck(self, row):
        answer = W.QMessageBox.question(self, 'Delete deck',
            f'Move "{row["name"]}" to the Recycle Bin?',
            W.QMessageBox.StandardButton.Yes | W.QMessageBox.StandardButton.No,
            W.QMessageBox.StandardButton.No)
        if answer != W.QMessageBox.StandardButton.Yes:
            return
        try:
            path = managed_deck_path(row['path'], self.roots[0])
            result = C.QFile.moveToTrash(str(path))
            if not (result[0] if isinstance(result, tuple) else result):
                raise OSError('The deck could not be moved to the Recycle Bin.')
        except (OSError, ValueError) as exc:
            W.QMessageBox.warning(self, 'Could not delete deck', str(exc))
            return
        self.deckDeleted.emit(path)
        self.refresh()

    def browse(self):
        print_projects = self.tabs.currentIndex() == 1
        path, _ = W.QFileDialog.getOpenFileName(
            self, 'Open print project as deck' if print_projects else 'Open deck',
            str(self.roots[1 if print_projects else 0]), 'JSON projects (*.json)')
        if path:
            self.openRequested.emit(Path(path))

    def eventFilter(self, watched, event):
        if event.type() in (C.QEvent.Type.Resize, C.QEvent.Type.Show):
            C.QTimer.singleShot(0, self.update_visible)
        return super().eventFilter(watched, event)

    def hideEvent(self, event):
        self.thumbnails.set_visible(id(self), [])
        super().hideEvent(event)

    def update_visible(self, *_):
        keys = []
        if self.isVisible() and not self.stopping:
            viewport = self.list.viewport().rect()
            for index in range(self.list.count()):
                item = self.list.item(index)
                if self.list.visualItemRect(item).intersects(viewport):
                    key = item.data(C.Qt.ItemDataRole.UserRole).get('cover', (None, None))
                    if any(key):
                        keys.append(key)
        self.thumbnails.set_visible(id(self), keys)

    def stop(self):
        self.stopping = True
        self.thumbnails.set_visible(id(self), [])


class ProjectBrowser(W.QDialog):
    """Modal wrapper used by Print Studio; keeps path/new_deck results."""
    def __init__(self, deck_root, project_root, parent=None):
        super().__init__(parent)
        from mtg_core import get_default_card_service
        from .card_views import Thumbnails
        self.setWindowTitle('Decks and print projects')
        self.resize(900, 640)
        self.path, self.new_deck, self.closing = None, False, False
        self.thumbnails = Thumbnails(get_default_card_service(), self)
        layout = W.QVBoxLayout(self)
        self.browser = ProjectDashboard(deck_root, project_root, self.thumbnails, self)
        layout.addWidget(self.browser)
        self.filter = self.browser.filter
        self.table = self.browser.list
        close = W.QPushButton('Close')
        close.setAutoDefault(False)
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        self.browser.openRequested.connect(self.select_path)
        self.browser.newRequested.connect(self.create)
        self.browser.settled.connect(self.finish_close)
        self.finish_timer = C.QTimer(self)
        self.finish_timer.setInterval(100)
        self.finish_timer.timeout.connect(self.finish_close)
        self._result = W.QDialog.DialogCode.Rejected

    @property
    def worker(self):
        return self.browser.worker

    def open_selected(self):
        self.browser.open_selected()

    def select_path(self, path):
        self.path = path
        self.accept()

    def create(self):
        self.new_deck = True
        self.accept()

    def done(self, result):
        self.closing = True
        self._result = result
        self.browser.stop()
        self.thumbnails.stopping = True
        self.thumbnails.pending.clear()
        self.finish_timer.start()
        self.finish_close()

    def finish_close(self):
        if self.closing and self.browser.worker is None and self.thumbnails.worker is None:
            self.finish_timer.stop()
            self.thumbnails.stop()
            super().done(self._result)

    def closeEvent(self, event):
        self.reject()
        event.ignore()
