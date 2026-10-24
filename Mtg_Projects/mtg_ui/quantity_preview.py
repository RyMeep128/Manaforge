"""Card preview with the same corner count and vertical controls as deck tiles."""
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from .card_chrome import draw_quantity_corner, draw_quantity_controls, quantity_control_rect


class QuantityPreview(W.QLabel):
    quantityRequested = C.pyqtSignal(int)

    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.quantity = 0
        self.quantity_active = False

    def card_rect(self):
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            return C.QRect()
        size = pixmap.deviceIndependentSize().toSize()
        rect = C.QRect(C.QPoint(), size)
        rect.moveCenter(self.contentsRect().center())
        return rect

    def paintEvent(self, event):
        super().paintEvent(event)
        rect = self.card_rect()
        if not self.quantity_active or rect.isEmpty():
            return
        painter = G.QPainter(self)
        draw_quantity_corner(painter, rect, self.quantity, '#52606b')
        control = quantity_control_rect(rect)
        half = control.height() // 2
        buttons = [(1, C.QRect(control.x(), control.y(), control.width(), half)),
                   (-1, C.QRect(control.x(), control.y()+half, control.width(), control.height()-half))]
        draw_quantity_controls(painter, control, buttons, can_decrease=self.quantity > 0)
        painter.end()

    def mousePressEvent(self, event):
        rect = self.card_rect()
        if self.quantity_active and not rect.isEmpty() and event.button() == C.Qt.MouseButton.LeftButton:
            control = quantity_control_rect(rect)
            if control.contains(event.position().toPoint()):
                delta = 1 if event.position().y() < control.y()+control.height()//2 else -1
                if delta > 0 or self.quantity > 0:
                    self.quantityRequested.emit(delta)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.mousePressEvent(event)
