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
            pending = self.pending is not None
            self.cancel()
            if pending:
                return True
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
        self.rings = []
        self.paths = {}
        self.page = 0
        self.page_size = 1
        self.setFixedSize(280, 280)
        self.setAttribute(C.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFocusPolicy(C.Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('Quick organization: Primary Role or Additional Tags')
        self.setToolTip('Move and release to assign. Tab: switch mode. Center or Esc: cancel. Arrow keys and Enter: select.')
        self.update_mode()
        if parent is not None:
            parent.window().installEventFilter(self)

    def eventFilter(self, watched, event):
        if self.isVisible() and event.type() in (C.QEvent.Type.Resize, C.QEvent.Type.Move):
            self.layout_menu()
            self.update()
        return super().eventFilter(watched, event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if hasattr(self, "press_origin") and event.type() in (
                C.QEvent.Type.FontChange, C.QEvent.Type.StyleChange,
                getattr(C.QEvent.Type, "DevicePixelRatioChange", C.QEvent.Type.FontChange)):
            self.layout_menu()
            self.update()

    @property
    def options(self):
        return self.models[self.tags][0]

    def update_mode(self):
        self.active = None
        self.models = {mode: radial_choices(self.document, mode) for mode in (False, True)}
        selected = [e for e in self.document.deck.entries if e.entry_id in self.ids]
        self.shared_tags = set.intersection(*({t.casefold() for t in e.tags} for e in selected)) if selected else set()
        self.page = 0
        self.setAccessibleDescription('Additional Tags' if self.tags else 'Primary Role')
        if hasattr(self, 'press_origin'):
            self.layout_menu()
        self.update()

    def geometry_values(self):
        center = C.QPointF(self.width() / 2, self.height() / 2)
        outer = min(center.x(), center.y()) - 8
        return center, outer, self.rings[0][2] if self.rings else min(52, outer * .36)

    def popup(self, position):
        self.snapshot = self.document.to_dict()
        self.press_origin = C.QPoint(position)
        self.update_mode()
        self.show()
        self.setFocus()

    def layout_menu(self):
        """Cache measured annular sectors; mouse motion only performs hit testing.

        Qt screen/widget coordinates and font metrics are logical pixels, so no
        manual device-pixel conversion is needed on mixed-DPI desktops.
        """
        screen = W.QApplication.screenAt(self.press_origin) or W.QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        if self.parentWidget() is not None:
            window = self.parentWidget().window()
            client = C.QRect(window.mapToGlobal(C.QPoint()), window.size())
            intersection = bounds.intersected(client)
            if not intersection.isEmpty():
                bounds = intersection
        metrics = self.fontMetrics()
        height = metrics.height() + 12
        # Keep equal-sized menus for equal choice counts. Long names are elided
        # when painted instead of enlarging every wedge in the menu.
        base_thickness = max(88, metrics.height() * 5) + 12
        limit = max(1, (min(bounds.width(), bounds.height()) - 16) / 2 - 8)

        def candidate(count, ring_count):
            # Reserve enough tangential room at the inner edge of every label.
            counts = [count // ring_count + (r < count % ring_count) for r in range(ring_count)]
            inner = max(48, height * max(counts) / (2 * math.pi))
            rings = []
            offset = 0
            for n in counts:
                # Give crowded menus visibly more room, even with short names.
                thickness = base_thickness + max(0, n - 6) * 7
                # A rotated label rectangle must fit inside its wedge.
                needed = height / (2 * math.tan(math.pi / n)) if n > 2 else 0
                inner = max(inner, needed + 8)
                rings.append((offset, n, inner, inner + thickness))
                offset += n
                inner += thickness
            return inner, rings

        count = len(self.options)
        candidates = [candidate(max(1, count), n) for n in range(1, min(max(1, count), 8) + 1)]
        radius, rings = min(candidates, key=lambda item: item[0])
        self.page_size = max(1, count)
        if radius > limit:
            # Paging is a last resort when the choices exceed available space.
            self.page_size = 1
            for capacity in range(1, count + 1):
                if candidate(capacity, 1)[0] <= limit:
                    self.page_size = capacity
                else:
                    break
            self.page = min(self.page, max(0, (count - 1) // self.page_size))
            visible = min(self.page_size, max(1, count - self.page * self.page_size))
            radius, rings = candidate(visible, 1)
            if radius > limit:
                radius = limit
                inner = min(48, radius * .36)
                rings = [(0, visible, inner, radius)]
        self.rings = [(start + self.page * self.page_size, n, lo, hi) for start, n, lo, hi in rings] if count else []
        side = max(1, math.ceil(2 * (radius + 8)))
        self.setFixedSize(side, side)
        center, _, _ = self.geometry_values()
        origin = self.press_origin - center.toPoint()
        origin.setX(max(bounds.left(), min(origin.x(), bounds.right() - side + 1)))
        origin.setY(max(bounds.top(), min(origin.y(), bounds.bottom() - side + 1)))
        self.move(origin)
        self.paths = {}
        for start, n, lo, hi in self.rings:
            circle = C.QRectF(center.x()-hi, center.y()-hi, hi*2, hi*2)
            cutout = G.QPainterPath()
            cutout.addEllipse(C.QRectF(center.x()-lo, center.y()-lo, lo*2, lo*2))
            for i in range(n):
                path = G.QPainterPath()
                path.moveTo(center)
                path.arcTo(circle, 90-180/n-i*360/n, 360/n)
                path.closeSubpath()
                self.paths[start+i] = path.subtracted(cutout)
        self.active = None

    def sector(self, position):
        center, _, _ = self.geometry_values()
        dx, dy = position.x() - center.x(), position.y() - center.y()
        distance = math.hypot(dx, dy)
        for start, count, inner, outer in self.rings:
            if inner <= distance <= outer:
                step = 2 * math.pi / count
                return start + int(((math.atan2(dy, dx) + math.pi / 2 + step / 2) % (2 * math.pi)) / step) % count
        return None

    def change_page(self, delta):
        pages = max(1, math.ceil(len(self.options) / self.page_size))
        self.page = (self.page + delta) % pages
        self.layout_menu()
        self.update()

    def wheelEvent(self, event):
        self.change_page(1 if event.angleDelta().y() < 0 else -1)
        event.accept()

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
        inner = self.rings[0][2] if self.rings else inner
        for start, ring_count, lo, hi in self.rings:
            for i in range(ring_count):
                index = start + i
                path = self.paths[index]
                p.setPen(G.QPen(G.QColor('#171b22'), 3))
                p.setBrush(G.QColor(accent if index == self.active else '#29333e'))
                p.drawPath(path)
                angle = -math.pi / 2 + i * 2 * math.pi / ring_count
                radius = (lo + hi) / 2
                label_width = max(1, hi - lo - 16)
                p.save()
                p.setClipPath(path)
                p.translate(center.x()+math.cos(angle)*radius, center.y()+math.sin(angle)*radius)
                rotation = math.degrees(angle) + (180 if math.cos(angle) < 0 else 0)
                p.rotate(rotation)
                rect = C.QRectF(-label_width/2, -p.fontMetrics().height()/2, label_width, p.fontMetrics().height())
                p.setPen(G.QColor('white'))
                label = p.fontMetrics().elidedText(self.label(index), C.Qt.TextElideMode.ElideRight, int(label_width))
                p.drawText(rect, C.Qt.AlignmentFlag.AlignCenter, label)
                p.restore()
        p.setPen(G.QPen(G.QColor(accent), 2))
        p.setBrush(G.QColor('#171b22'))
        p.drawEllipse(center, inner, inner)
        p.setPen(G.QColor('white'))
        title = 'Tags' if self.tags else 'Primary role'
        text = f'{title}\n{len(self.ids)} selected' if count else 'No active tags\nMore settings'
        if len(self.options) > self.page_size:
            text += f'\n{self.page + 1}/{math.ceil(len(self.options) / self.page_size)}\nWheel/PgDn'
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
        elif event.key() in (C.Qt.Key.Key_PageDown, C.Qt.Key.Key_PageUp):
            self.change_page(1 if event.key() == C.Qt.Key.Key_PageDown else -1)
        elif event.key() == C.Qt.Key.Key_Tab and not event.isAutoRepeat():
            self.switch_mode()
        elif event.key() in (C.Qt.Key.Key_Left, C.Qt.Key.Key_Up, C.Qt.Key.Key_Right, C.Qt.Key.Key_Down) and self.options:
            delta = -1 if event.key() in (C.Qt.Key.Key_Left, C.Qt.Key.Key_Up) else 1
            self.active = ((self.active if self.active is not None else -delta) + delta) % len(self.options)
            if self.active // self.page_size != self.page:
                index = self.active
                self.page = index // self.page_size
                self.layout_menu()
                self.active = index
            self.update()
        elif event.key() in (C.Qt.Key.Key_Return, C.Qt.Key.Key_Enter):
            self.activate(self.active)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == C.Qt.Key.Key_T and not event.isAutoRepeat():
            index = self.sector(self.mapFromGlobal(G.QCursor.pos()))
            unmoved = (G.QCursor.pos() - self.press_origin).manhattanLength() < W.QApplication.startDragDistance()
            if index is None or unmoved:
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
