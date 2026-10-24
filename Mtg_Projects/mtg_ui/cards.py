from PyQt6 import QtCore, QtGui
from .theme import COLORS


def rounded_card(painter, rect, pixmap, selected=False, hovered=False):
    painter.save()
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
    path = QtGui.QPainterPath()
    path.addRoundedRect(QtCore.QRectF(rect), 9, 9)
    painter.setClipPath(path)
    painter.fillRect(rect, QtGui.QColor(COLORS['surface_raised']))
    if pixmap is not None and not pixmap.isNull():
        size = pixmap.size().scaled(rect.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        target = QtCore.QRect(QtCore.QPoint(), size)
        target.moveCenter(rect.center())
        painter.drawPixmap(target, pixmap)
    else:
        painter.setPen(QtGui.QColor(COLORS['text_secondary']))
        painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter,
                         'Loading artwork…' if pixmap is None else 'Image unavailable\nRight-click to retry')
    painter.setClipping(False)
    if selected or hovered:
        selection_outline(painter, rect.adjusted(2, 2, -2, -2), '#55dfaa' if selected else COLORS['accent'], radius=8)
    painter.restore()


def drag_ghost(pixmap, size=140):
    return pixmap.scaledToWidth(size, QtCore.Qt.TransformationMode.SmoothTransformation)


def selection_outline(painter, rect, color, width=3, radius=4, fill=None):
    painter.save()
    if fill is not None:
        painter.fillRect(rect, fill)
    painter.setPen(QtGui.QPen(QtGui.QColor(color), width))
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QtCore.QRectF(rect), radius, radius)
    painter.restore()
