"""Small, cursor-centered marking menu for primary roles and secondary tags."""
import math
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from .tag_model import apply_choice, radial_choices, preferences

class HoldTagGesture(C.QObject):
    """Shared right-button gesture for canvas and table viewports."""
    def __init__(self, view, select, actions, radial, delay=None):
        super().__init__(view)
        self.view = view
        self.delay = delay
        self.select, self.actions, self.radial = select, actions, radial
        self.pending = None
        self.timer = C.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.open_radial)
        view.installEventFilter(self)
        view.viewport().installEventFilter(self)
        view.verticalScrollBar().valueChanged.connect(self.cancel)
        view.horizontalScrollBar().valueChanged.connect(self.cancel)

    def cancel(self, *_):
        self.timer.stop()
        if self.pending and hasattr(self.view, 'release_context_target'):
            self.view.release_context_target()
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
                if hasattr(self.view, 'pin_context_target'):
                    self.view.pin_context_target(entry_id)
                if not event.modifiers() & C.Qt.KeyboardModifier.ShiftModifier:
                    if self.delay:
                        self.timer.setInterval(self.delay())
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
    """Shared marking-menu command: replace primary role or toggle extra tags."""
    apply_choice(document, ids, name, tags, toggle=tags)


class QuickTagMenu(W.QWidget):
    chosen = C.pyqtSignal(str, bool)
    closed = C.pyqtSignal()

    def __init__(self, document, ids, parent=None, *, hold=False, tags=None):
        super().__init__(parent, C.Qt.WindowType.Popup | C.Qt.WindowType.FramelessWindowHint)
        self.document, self.ids = document, set(ids)
        self.tags = preferences(document).get('initial_mode') == 'tags' if tags is None else tags
        self.active = None
        self.hold = hold
        self.models = {mode: radial_choices(document, mode) for mode in (False, True)}
        selected = [e for e in document.deck.entries if e.entry_id in self.ids]
        self.shared_tags = set.intersection(*({t.casefold() for t in e.tags} for e in selected)) if selected else set()
        self.setFixedSize(380, 380)
        self.setAttribute(C.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFocusPolicy(C.Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('Quick organization: Primary Role or Additional Tags')
        self.setToolTip('Move and release to assign. Tab: switch mode. Center or Esc: cancel. Arrow keys and Enter: select.')
        self.update_mode()

    @property
    def options(self):
        return self.models[self.tags][0]

    def update_mode(self):
        self.active = None
        self.setAccessibleDescription('Additional Tags' if self.tags else 'Primary Role')
        self.update()

    def geometry_values(self):
        center = C.QPointF(self.width() / 2, self.height() / 2)
        outer = min(center.x(), center.y()) - 8
        return center, outer, min(52, outer * .36)

    def popup(self, position):
        self.snapshot = self.document.to_dict()
        self.press_origin = C.QPoint(position)
        screen = W.QApplication.screenAt(position) or W.QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        side = min(380, bounds.width() - 16, bounds.height() - 16)
        self.setFixedSize(side, side)
        center, _, _ = self.geometry_values()
        origin = position - center.toPoint()
        origin.setX(max(bounds.left(), min(origin.x(), bounds.right() - self.width() + 1)))
        origin.setY(max(bounds.top(), min(origin.y(), bounds.bottom() - self.height() + 1)))
        self.move(origin)
        self.show()
        self.setFocus()

    def sector(self, position):
        center, outer, inner = self.geometry_values()
        dx, dy = position.x() - center.x(), position.y() - center.y()
        count = len(self.options)
        if not count or not inner <= math.hypot(dx, dy) <= outer:
            return None
        step = 2 * math.pi / count
        return int(((math.atan2(dy, dx) + math.pi / 2 + step / 2) % (2 * math.pi)) / step) % count

    def label(self, index):
        choice = self.options[index]
        if not self.tags:
            return choice.name
        remove = choice.name.casefold() in self.shared_tags
        return ('− ' if remove else '+ ') + choice.name

    def paintEvent(self, event):
        p = G.QPainter(self)
        p.setRenderHint(G.QPainter.RenderHint.Antialiasing)
        center, outer, inner = self.geometry_values()
        accent = '#9865c9' if self.tags else '#2f9e72'
        count = len(self.options)
        circle = C.QRectF(center.x()-outer, center.y()-outer, outer*2, outer*2)
        for i in range(count):
            step = 360 / count
            p.setPen(G.QPen(G.QColor('#171b22'), 3))
            p.setBrush(G.QColor(accent if i == self.active else '#29333e'))
            p.drawPie(circle, round((90-step/2-i*step)*16), round(step*16))
            angle = -math.pi / 2 + i * 2 * math.pi / count
            radius = (inner + outer) / 2
            label_width = outer - inner - 16
            label_height = max(14, min(38, 2 * radius * math.sin(math.pi / max(2, count)) - 5))
            p.save()
            p.translate(center.x()+math.cos(angle)*radius, center.y()+math.sin(angle)*radius)
            rotation = math.degrees(angle)
            if math.cos(angle) < 0:
                rotation += 180
            p.rotate(rotation)
            rect = C.QRectF(-label_width/2, -label_height/2, label_width, label_height)
            p.setPen(G.QColor('white'))
            label = p.fontMetrics().elidedText(self.label(i), C.Qt.TextElideMode.ElideRight, max(20, int(label_width)))
            p.drawText(rect, C.Qt.AlignmentFlag.AlignCenter, label)
            p.restore()
        p.setPen(G.QPen(G.QColor(accent), 2))
        p.setBrush(G.QColor('#171b22'))
        p.drawEllipse(center, inner, inner)
        p.setPen(G.QColor('white'))
        title = 'Tags' if self.tags else 'Primary role'
        text = f'{title}\n{len(self.ids)} selected' if count else 'No active tags\nMore settings'
        p.drawText(C.QRectF(center.x()-inner, center.y()-inner, inner*2, inner*2), C.Qt.AlignmentFlag.AlignCenter, text)
        p.end()

    def mouseMoveEvent(self, event):
        self.active = self.sector(event.position())
        self.setToolTip(self.label(self.active) if self.active is not None else 'Center: cancel · Tab: switch mode · Esc: close')
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() not in (C.Qt.MouseButton.LeftButton, C.Qt.MouseButton.RightButton):
            return
        index = self.sector(event.position())
        unmoved = (event.globalPosition().toPoint() - self.press_origin).manhattanLength() < W.QApplication.startDragDistance()
        if index is None or (self.hold and unmoved):
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
        elif event.key() in (C.Qt.Key.Key_Left, C.Qt.Key.Key_Up, C.Qt.Key.Key_Right, C.Qt.Key.Key_Down) and self.options:
            delta = -1 if event.key() in (C.Qt.Key.Key_Left, C.Qt.Key.Key_Up) else 1
            self.active = ((self.active if self.active is not None else -delta) + delta) % len(self.options)
            self.update()
        elif event.key() in (C.Qt.Key.Key_Return, C.Qt.Key.Key_Enter):
            self.activate(self.active)
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
        self.update_mode()

    def activate(self, index):
        if index is not None and 0 <= index < len(self.options):
            self.choose(self.options[index].name)

    def choose(self, name):
        if self.document.to_dict() == self.snapshot and self.ids <= {e.entry_id for e in self.document.deck.entries}:
            self.chosen.emit(name, self.tags)
        self.close()

    def hideEvent(self, event):
        self.closed.emit()
        super().hideEvent(event)
