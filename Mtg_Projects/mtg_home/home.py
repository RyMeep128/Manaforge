"""Responsive, keyboard-accessible homepage using Manaforge's visual tokens."""
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_ui.theme import COLORS
from mtg_proxy.constants import APP_VERSION
from .modules import MODULES


class ModuleTile(W.QAbstractButton):
    def __init__(self, module, parent=None):
        super().__init__(parent)
        self.module = module
        self.setEnabled(module.available)
        self.setMinimumSize(280, 195)
        self.setSizePolicy(W.QSizePolicy.Policy.Expanding, W.QSizePolicy.Policy.Fixed)
        self.setFixedHeight(205)
        self.setFocusPolicy(C.Qt.FocusPolicy.StrongFocus)
        self.setCursor(C.Qt.CursorShape.PointingHandCursor if module.available else C.Qt.CursorShape.ArrowCursor)
        self.setAccessibleName(module.title)
        self.setAccessibleDescription(module.description + (' Available.' if module.available else ' Coming soon.'))

    def sizeHint(self):
        return C.QSize(440, 205)

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (C.Qt.Key.Key_Return, C.Qt.Key.Key_Enter):
            self.click()
            event.accept()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        p = G.QPainter(self)
        p.setRenderHint(G.QPainter.RenderHint.Antialiasing)
        enabled = self.isEnabled()
        highlighted = enabled and (self.underMouse() or self.hasFocus())
        p.setPen(G.QPen(G.QColor(COLORS['accent'] if highlighted else COLORS['border']), 2 if highlighted else 1))
        p.setBrush(G.QColor(COLORS['surface_hover'] if highlighted else COLORS['surface']))
        p.drawRoundedRect(C.QRectF(self.rect()).adjusted(2, 2, -2, -2), 15, 15)
        p.save()
        p.translate(26, 26)
        p.setPen(G.QPen(G.QColor('#72d6ad' if enabled else COLORS['text_muted']), 2))
        p.setBrush(C.Qt.BrushStyle.NoBrush)
        self.paint_icon(p)
        p.restore()
        font = self.font()
        font.setPointSize(15)
        font.setBold(True)
        p.setFont(font)
        p.setPen(G.QColor(COLORS['text'] if enabled else COLORS['text_muted']))
        p.drawText(C.QRect(78, 23, self.width()-102, 38), C.Qt.AlignmentFlag.AlignVCenter, self.module.title)
        font.setPointSize(10)
        font.setBold(False)
        p.setFont(font)
        p.setPen(G.QColor(COLORS['text_secondary'] if enabled else COLORS['text_muted']))
        p.drawText(C.QRect(26, 83, self.width()-52, 58), C.Qt.TextFlag.TextWordWrap, self.module.description)
        p.setPen(G.QColor('#72d6ad' if enabled else COLORS['text_muted']))
        p.drawText(C.QRect(26, self.height()-47, self.width()-52, 25), C.Qt.AlignmentFlag.AlignVCenter,
                   'Open  →' if enabled else 'Coming soon')
        p.end()

    def paint_icon(self, p):
        if self.module.icon == 'cards':
            for offset in (0, 5, 10):
                p.drawRoundedRect(C.QRectF(offset, 10-offset/2, 24, 30), 3, 3)
        elif self.module.icon == 'book':
            path = G.QPainterPath(C.QPointF(18, 8))
            for point in ((2, 3), (2, 31), (18, 36), (34, 31), (34, 3), (18, 8), (18, 36)):
                path.lineTo(*point)
            p.drawPath(path)
        elif self.module.icon == 'printer':
            p.drawRoundedRect(C.QRectF(1, 13, 34, 22), 4, 4)
            p.drawRect(C.QRectF(8, 1, 20, 15))
            p.drawRect(C.QRectF(8, 26, 20, 15))
            p.drawLine(12, 31, 24, 31)
            p.drawLine(12, 36, 24, 36)
        else:
            for points in (((4, 2), (29, 32)), ((32, 2), (7, 32)), ((0, 28), (11, 37)), ((25, 37), (36, 28))):
                p.drawLine(*points[0], *points[1])


class HomeWindow(W.QMainWindow):
    moduleRequested = C.pyqtSignal(str)
    settingsRequested = C.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Manaforge')
        bounds = W.QApplication.primaryScreen().availableGeometry()
        self.resize(min(1100, bounds.width()-30), min(800, bounds.height()-30))
        self.setMinimumSize(420, 420)
        scroll = W.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(W.QFrame.Shape.NoFrame)
        self.setCentralWidget(scroll)
        wrapper = W.QWidget()
        outer = W.QVBoxLayout(wrapper)
        outer.setContentsMargins(30, 28, 30, 28)
        outer.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
        content = W.QWidget()
        content.setMaximumWidth(1020)
        layout = W.QVBoxLayout(content)
        layout.setSpacing(16)
        kicker = W.QLabel('BUILD  ·  LEARN  ·  PRINT  ·  PLAY')
        kicker.setStyleSheet('color:#72d6ad;font-size:10pt;font-weight:600;')
        layout.addWidget(kicker)
        brand = W.QLabel('Manaforge')
        brand.setStyleSheet('font-size:34pt;font-weight:700;')
        layout.addWidget(brand)
        subtitle = W.QLabel('Your decks. Your table. One workspace.')
        subtitle.setProperty('role', 'subtitle')
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        layout.addSpacing(12)
        self.grid = W.QGridLayout()
        self.grid.setSpacing(18)
        self.tiles = {}
        for module in MODULES:
            tile = ModuleTile(module)
            tile.clicked.connect(lambda checked=False, key=module.key: self.moduleRequested.emit(key))
            self.tiles[module.key] = tile
        layout.addLayout(self.grid)
        footer = W.QHBoxLayout()
        version = W.QLabel('Manaforge  ' + APP_VERSION)
        version.setProperty('role', 'muted')
        footer.addWidget(version, 1)
        settings = W.QToolButton()
        settings.setText('Settings')
        settings.setPopupMode(W.QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = W.QMenu(settings)
        menu.addAction('Global printing defaults', lambda: self.settingsRequested.emit('printing'))
        menu.addAction('Artwork preferences', lambda: self.settingsRequested.emit('artwork'))
        menu.addAction('Data Management', lambda: self.settingsRequested.emit('data'))
        settings.setMenu(menu)
        footer.addWidget(settings)
        layout.addLayout(footer)
        outer.addWidget(content)
        scroll.setWidget(wrapper)
        self.takeCentralWidget()
        self.home_page = scroll
        self.pages = W.QStackedWidget()
        self.pages.addWidget(scroll)
        self.setCentralWidget(self.pages)
        self.workspaces = {}
        self.current_workspace = 'home'
        self.shutdown_guard = None
        navigation = self.addToolBar('Manaforge')
        navigation.setMovable(False)
        self.navigation = {}
        group = G.QActionGroup(self)
        group.setExclusive(True)
        for key, title, enabled in [('home', 'Home', True)] + [
                (module.key, module.title, module.available) for module in MODULES]:
            action = navigation.addAction(title)
            action.setCheckable(True)
            action.setEnabled(enabled)
            group.addAction(action)
            self.navigation[key] = action
            action.triggered.connect(lambda checked=False, target=key: self.moduleRequested.emit(target))
        self.navigation['home'].setChecked(True)
        self.navigation['home'].setShortcut('Ctrl+Shift+H')
        from mtg_ui.keyboard import add_shortcuts_help
        add_shortcuts_help(self)
        self._columns = None
        self.reflow()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'grid'):
            self.reflow()

    def reflow(self):
        columns = 2 if self.width() >= 760 else 1
        if columns == self._columns:
            return
        while self.grid.count():
            self.grid.takeAt(0)
        for index, tile in enumerate(self.tiles.values()):
            self.grid.addWidget(tile, index // columns, index % columns)
        for column in range(2):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        self._columns = columns

    def add_workspace(self, key, widget):
        widget.setProperty('manaforgeEmbedded', True)
        scroll = W.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(W.QFrame.Shape.NoFrame)
        widget.setParent(scroll)
        widget.setWindowFlags(C.Qt.WindowType.Widget)
        scroll.setWidget(widget)
        self.pages.addWidget(scroll)
        self.workspaces[key] = (scroll, widget)
        widget.windowTitleChanged.connect(lambda title: self.update_workspace_title(key, title))

    def show_workspace(self, key):
        self.current_workspace = key
        if key == 'home':
            self.pages.setCurrentWidget(self.home_page)
            self.setWindowTitle('Manaforge')
        else:
            scroll, widget = self.workspaces[key]
            self.pages.setCurrentWidget(scroll)
            widget.show()
            self.update_workspace_title(key, widget.windowTitle())
        self.navigation[key].setChecked(True)

    def update_workspace_title(self, key, title):
        if key in self.workspaces and self.pages.currentWidget() is self.workspaces[key][0]:
            self.setWindowTitle('Manaforge — ' + title)

    def closeEvent(self, event):
        if self.shutdown_guard is not None and not self.shutdown_guard():
            event.ignore()
            return
        super().closeEvent(event)
