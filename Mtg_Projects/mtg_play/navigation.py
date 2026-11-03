"""Engine-free Play navigation and local, code-drawn decorative artwork."""

from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_ui.theme import COLORS


class PlayPages(W.QStackedWidget):
    """Hidden battlefield minimum sizes must not enlarge the landing window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout().setSizeConstraint(W.QLayout.SizeConstraint.SetNoConstraint)
        self.currentChanged.connect(self.updateGeometry)

    def sizeHint(self):
        page = self.currentWidget()
        return page.sizeHint() if page else C.QSize(800, 560)

    def minimumSizeHint(self):
        page = self.currentWidget()
        return page.minimumSizeHint() if page else C.QSize(0, 0)


class CardFan(W.QWidget):
    """Original decorative card backs; no printing lookup, file I/O, or cache."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.setSizePolicy(
            W.QSizePolicy.Policy.Expanding, W.QSizePolicy.Policy.Expanding
        )
        self.setAttribute(C.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = G.QPainter(self)
        painter.setRenderHint(G.QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        scale = min(self.width() / 380, self.height() / 220)
        painter.scale(scale, scale)
        for x, angle, color in (
            (-70, -17, COLORS["border"]),
            (70, 17, COLORS["border"]),
            (0, 0, COLORS["accent"]),
        ):
            painter.save()
            painter.translate(x, 0)
            painter.rotate(angle)
            gradient = G.QLinearGradient(-55, -82, 55, 82)
            gradient.setColorAt(0, G.QColor(COLORS["surface_hover"]))
            gradient.setColorAt(1, G.QColor(COLORS["surface"]))
            painter.setBrush(G.QBrush(gradient))
            painter.setPen(G.QPen(G.QColor(color), 2))
            painter.drawRoundedRect(C.QRectF(-55, -82, 110, 164), 9, 9)
            painter.setBrush(C.Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(C.QRectF(-45, -72, 90, 144), 5, 5)
            path = G.QPainterPath(C.QPointF(0, -37))
            for point in ((25, 0), (0, 37), (-25, 0), (0, -37)):
                path.lineTo(*point)
            painter.drawPath(path)
            painter.drawEllipse(C.QPointF(0, 0), 12, 12)
            painter.restore()
        painter.end()


class PlayLanding(W.QScrollArea):
    playRequested = C.pyqtSignal()
    offlineRequested = C.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wide = None
        self.setWidgetResizable(True)
        self.setFrameShape(W.QFrame.Shape.NoFrame)
        content = W.QWidget()
        self.setWidget(content)
        self.grid = W.QGridLayout(content)
        self.grid.setContentsMargins(0, 12, 0, 12)
        self.grid.setSpacing(24)
        self.hero = W.QFrame()
        self.hero.setProperty("role", "panel")
        hero = W.QVBoxLayout(self.hero)
        hero.setContentsMargins(28, 24, 28, 28)
        hero.setSpacing(16)
        hero.addWidget(CardFan(), 1)
        title = W.QLabel("Bring your decks to the table.")
        title.setWordWrap(True)
        font = title.font()
        font.setPointSize(24)
        font.setBold(True)
        title.setFont(font)
        hero.addWidget(title)
        description = W.QLabel(
            "Choose your deck, face an AI opponent, and find your next play."
        )
        description.setWordWrap(True)
        description.setProperty("role", "subtitle")
        hero.addWidget(description)
        buttons = W.QHBoxLayout()
        buttons.setSpacing(12)
        self.play_button = W.QPushButton("Play")
        self.play_button.setProperty("buttonRole", "primary")
        self.play_button.setMinimumHeight(48)
        self.play_button.clicked.connect(lambda: self.playRequested.emit())
        self.offline_button = W.QPushButton("Play Offline")
        self.offline_button.setMinimumHeight(48)
        self.offline_button.clicked.connect(lambda: self.offlineRequested.emit())
        buttons.addWidget(self.play_button)
        buttons.addWidget(self.offline_button)
        hero.addLayout(buttons)
        self.friends = W.QFrame()
        self.friends.setProperty("role", "panel")
        friends = W.QVBoxLayout(self.friends)
        friends.setContentsMargins(24, 28, 24, 28)
        friends.setSpacing(16)
        heading = W.QLabel("Play with friends")
        heading.setProperty("role", "title")
        heading.setWordWrap(True)
        friends.addWidget(heading)
        soon = W.QLabel("Coming soon")
        soon.setProperty("role", "muted")
        friends.addWidget(soon)
        description = W.QLabel(
            "Host your own table or join a friend's match when multiplayer arrives."
        )
        description.setWordWrap(True)
        friends.addWidget(description)
        self.host_button = W.QPushButton("Host Match")
        self.join_button = W.QPushButton("Join Match")
        for button in (self.host_button, self.join_button):
            button.setEnabled(False)
            button.setMinimumHeight(44)
            button.setToolTip("Coming soon with multiplayer.")
            button.setAccessibleDescription(
                "Unavailable. Coming soon with multiplayer."
            )
            friends.addWidget(button)
        friends.addStretch()
        self._wide = None
        self._arrange()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "friends"):
            self._arrange()

    def _arrange(self):
        wide = self.viewport().width() >= 760
        if wide == self._wide:
            return
        self._wide = wide
        self.grid.removeWidget(self.hero)
        self.grid.removeWidget(self.friends)
        self.grid.addWidget(self.hero, 0, 0)
        self.grid.addWidget(self.friends, 0 if wide else 1, 1 if wide else 0)
        self.grid.setColumnStretch(0, 3)
        self.grid.setColumnStretch(1, 2 if wide else 0)


class ModeSelection(W.QWidget):
    offlineRequested = C.pyqtSignal()
    backRequested = C.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(0, 24, 0, 24)
        layout.setSpacing(20)
        title = W.QLabel("How would you like to play?")
        title.setProperty("role", "title")
        title.setWordWrap(True)
        layout.addWidget(title)
        description = W.QLabel("Play against an AI opponent using your saved decks.")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.offline_button = W.QPushButton("Play Offline")
        self.offline_button.setProperty("buttonRole", "primary")
        self.offline_button.setMinimumHeight(52)
        self.offline_button.clicked.connect(lambda: self.offlineRequested.emit())
        layout.addWidget(self.offline_button)
        note = W.QLabel("Matches with friends are coming soon.")
        note.setProperty("role", "muted")
        layout.addWidget(note)
        layout.addStretch()
        back = W.QPushButton("Back to Play")
        back.clicked.connect(lambda: self.backRequested.emit())
        layout.addWidget(back, 0, C.Qt.AlignmentFlag.AlignLeft)
