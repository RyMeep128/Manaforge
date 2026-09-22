"""Small, cursor-centered marking menu for primary roles and secondary tags."""
import math
import uuid
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_core.decks import DeckCategory
from mtg_core.categorization import ROLE_TAGS
from .organization import assign

COMMON = ('Ramp', 'Draw', 'Removal', 'Protection', 'Board Wipes', 'Win Conditions')


class HoldTagGesture(C.QObject):
    """Shared right-button gesture for canvas and table viewports."""
    def __init__(self, view, select, actions, radial):
        super().__init__(view)
        self.select, self.actions, self.radial = select, actions, radial
        self.pending = None
        self.timer = C.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.open_radial)
        view.installEventFilter(self)
        view.viewport().installEventFilter(self)
        view.verticalScrollBar().valueChanged.connect(self.cancel)
        view.horizontalScrollBar().valueChanged.connect(self.cancel)

    def cancel(self, *_):
        self.timer.stop()
        self.pending = None

    def open_radial(self):
        pending = self.pending
        self.cancel()
        if pending:
            self.radial(pending[1], hold=True)

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == C.QEvent.Type.ContextMenu and event.reason() == G.QContextMenuEvent.Reason.Mouse:
            return True
        if kind == C.QEvent.Type.MouseButtonPress and event.button() == C.Qt.MouseButton.RightButton:
            self.cancel()
            entry_id = self.select(event.globalPosition().toPoint())
            if entry_id:
                self.pending = (entry_id, event.globalPosition().toPoint())
                if not event.modifiers() & C.Qt.KeyboardModifier.ShiftModifier:
                    self.timer.start()
            return True
        if kind == C.QEvent.Type.MouseButtonRelease and event.button() == C.Qt.MouseButton.RightButton:
            pending = self.pending
            self.cancel()
            if pending:
                self.actions(*pending)
            return True
        if kind == C.QEvent.Type.MouseMove and self.pending:
            if (event.globalPosition().toPoint() - self.pending[1]).manhattanLength() >= W.QApplication.startDragDistance():
                self.cancel()
        if kind in (C.QEvent.Type.FocusOut, C.QEvent.Type.Hide, C.QEvent.Type.Wheel):
            self.cancel()
        if kind == C.QEvent.Type.KeyPress and event.key() == C.Qt.Key.Key_Escape:
            self.cancel()
        return False


def apply_quick_role(document, ids, name, tags=False):
    entries = [e for e in document.deck.entries if e.entry_id in ids]
    if not entries:
        return
    if tags:
        # Mixed selections converge: add to all unless all already have the tag.
        remove = all(name in e.tags for e in entries)
        for entry in entries:
            if remove:
                entry.tags = [t for t in entry.tags if t != name]
            elif name not in entry.tags:
                entry.tags.append(name)
        return
    if not name:
        assign(document, ids, 'category', None)
        return
    category = next((c for c in document.deck.categories if c.name.casefold() == name.casefold()), None)
    if category is None:
        category = DeckCategory(str(uuid.uuid4()), name,
                                max((c.sort_order for c in document.deck.categories), default=-1) + 1)
        document.deck.categories.append(category)
    assign(document, ids, 'category', category.category_id)


class QuickTagMenu(W.QWidget):
    chosen = C.pyqtSignal(str, bool)

    def __init__(self, document, ids, parent=None, *, hold=False):
        super().__init__(parent, C.Qt.WindowType.Popup | C.Qt.WindowType.FramelessWindowHint)
        self.document, self.ids = document, set(ids)
        self.tags = False
        self.active = None
        self.hold = hold
        self.setFixedSize(440, 440)
        self.setMouseTracking(True)
        self.setFocusPolicy(C.Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('Quick tagging: primary category. Tab switches to secondary tags.')

    def popup(self, position):
        self.press_origin = C.QPoint(position)
        screen = W.QApplication.screenAt(position) or W.QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        origin = position - C.QPoint(220, 220)
        origin.setX(max(bounds.left(), min(origin.x(), bounds.right() - self.width() + 1)))
        origin.setY(max(bounds.top(), min(origin.y(), bounds.bottom() - self.height() + 1)))
        self.move(origin)
        self.show()
        self.setFocus()

    def sector(self, position):
        dx, dy = position.x() - 220, position.y() - 220
        if not 68 <= math.hypot(dx, dy) <= 214:
            return None
        return int(((math.atan2(dy, dx) + math.pi / 2 + math.pi / 8) % (2 * math.pi)) / (math.pi / 4))

    def label(self, index):
        if index == 6:
            return 'More…'
        if index == 7:
            return 'Primary mode' if self.tags else 'Tags mode'
        name = COMMON[index]
        if self.tags:
            entries = [e for e in self.document.deck.entries if e.entry_id in self.ids]
            return ('− ' if entries and all(name in e.tags for e in entries) else '+ ') + name
        return name

    def paintEvent(self, event):
        p = G.QPainter(self)
        p.setRenderHint(G.QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), G.QColor('#171b22'))
        accent = '#9865c9' if self.tags else '#2f9e72'
        for i in range(8):
            p.setPen(G.QPen(G.QColor('#171b22'), 3))
            p.setBrush(G.QColor(accent if i == self.active else '#29333e'))
            p.drawPie(C.QRectF(6, 6, 428, 428), int((67.5-i*45)*16), 45*16)
            angle = -math.pi / 2 + i * math.pi / 4
            rect = C.QRectF(220+math.cos(angle)*145-58, 220+math.sin(angle)*145-28, 116, 56)
            p.setPen(G.QColor('white'))
            p.drawText(rect, C.Qt.AlignmentFlag.AlignCenter | C.Qt.TextFlag.TextWordWrap, self.label(i))
        p.setPen(G.QPen(G.QColor(accent), 3))
        p.setBrush(G.QColor('#171b22'))
        p.drawEllipse(C.QPointF(220, 220), 68, 68)
        p.setPen(G.QColor('white'))
        font = p.font()
        font.setPointSize(8)
        p.setFont(font)
        title = 'SECONDARY TAGS\nAdd / remove' if self.tags else 'PRIMARY\nReplace category'
        p.drawText(C.QRectF(155, 174, 130, 92), C.Qt.AlignmentFlag.AlignCenter,
                   f'{title}\n{len(self.ids)} selected\nTab: switch\nEsc: cancel')
        p.end()

    def mouseMoveEvent(self, event):
        self.active = self.sector(event.position())
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() in (C.Qt.MouseButton.LeftButton, C.Qt.MouseButton.RightButton):
            index = self.sector(event.position())
            unmoved = (event.globalPosition().toPoint() - self.press_origin).manhattanLength() < W.QApplication.startDragDistance()
            if self.hold and (index is None or unmoved):
                self.close()
            else:
                self.activate(index)
            self.hold = False

    def contextMenuEvent(self, event):
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == C.Qt.Key.Key_Escape:
            self.close()
        elif event.key() == C.Qt.Key.Key_Tab and not event.isAutoRepeat():
            self.switch_mode()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == C.Qt.Key.Key_T and not event.isAutoRepeat():
            index = self.sector(self.mapFromGlobal(G.QCursor.pos()))
            if index is None:
                self.close()
            else:
                self.activate(index)

    def switch_mode(self):
        self.tags = not self.tags
        self.setAccessibleName('Quick tagging: ' + ('secondary tags' if self.tags else 'primary category'))
        self.update()

    def activate(self, index):
        if index is None:
            return  # Button-opened menus remain available for a subsequent click.
        if index == 7:
            self.switch_mode()
        elif index == 6:
            self.more()
        else:
            self.choose(COMMON[index])

    def choose(self, name):
        self.chosen.emit(name, self.tags)
        self.close()

    def more(self):
        menu = W.QMenu(self)
        names = {c.name for c in self.document.deck.categories} | {name for name, _ in ROLE_TAGS} | {'Lands'}
        if self.tags:
            names.update(t for e in self.document.deck.entries for t in e.tags)
        for name in sorted(names.difference(COMMON), key=str.casefold):
            menu.addAction(name, lambda checked=False, n=name: self.choose(n))
        menu.addAction('New tag…' if self.tags else 'New category…', self.new_name)
        if not self.tags:
            menu.addAction('Uncategorized', lambda: self.choose(''))
        menu.exec(G.QCursor.pos())

    def new_name(self):
        name, ok = W.QInputDialog.getText(self, 'New tag' if self.tags else 'New category', 'Name:')
        if ok and name.strip():
            self.choose(name.strip())
