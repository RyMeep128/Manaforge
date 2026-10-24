"""Lightweight deck-card corner cues and quantity controls; no document writes."""
from functools import lru_cache
from hashlib import blake2s
from PyQt6 import QtCore as C, QtGui as G


@lru_cache(maxsize=1024)
def marker_color(identity):
    # Stable across sessions and category renames; never use randomized hash().
    digest = blake2s(identity.encode('utf-8'), digest_size=4).digest()
    hue = int.from_bytes(digest, 'big') % 360
    return G.QColor.fromHsv(hue, 140 + digest[1] % 60, 100 + digest[2] % 35).name()


def corner_colors(entry, category_colors):
    primary = category_colors.get(entry.category_ids[0]) if entry.category_ids else None
    tags = list(dict.fromkeys(tag.strip().casefold() for tag in entry.tags if tag.strip()))
    if primary is None and tags:
        primary = marker_color('tag:' + tags.pop(0))
    return primary or '#52606b', [marker_color('tag:' + tag) for tag in tags[:3]]


def draw_quantity_corner(painter, rect, quantity, primary, tags=()):
    painter.save()
    painter.setRenderHint(G.QPainter.RenderHint.Antialiasing)
    font = painter.font()
    font.setPointSize(9 if rect.width() >= 160 else 8)
    font.setBold(True)
    painter.setFont(font)
    amount = str(quantity)
    side = max(32, min(rect.width()-8, painter.fontMetrics().horizontalAdvance(amount)+29))
    rounded = G.QPainterPath()
    rounded.addRoundedRect(C.QRectF(rect), 9, 9)
    painter.setClipPath(rounded)
    triangle = G.QPolygon([rect.topLeft(), rect.topLeft()+C.QPoint(side, 0),
                           rect.topLeft()+C.QPoint(0, side)])
    painter.setBrush(G.QColor(primary))
    painter.setPen(G.QPen(G.QColor(255, 255, 255, 100), 1))
    painter.drawPolygon(triangle)
    if tags:
        path = G.QPainterPath()
        path.addPolygon(G.QPolygonF(triangle))
        painter.setClipPath(path, C.Qt.ClipOperation.IntersectClip)
        width = max(5, side // len(tags))
        for index, color in enumerate(tags):
            painter.fillRect(C.QRect(rect.x()+index*width, rect.y(), width, 4), G.QColor(color))
    painter.setPen(G.QColor('white'))
    painter.drawText(C.QRect(rect.x()+2, rect.y()+3, side-22, 18), C.Qt.AlignmentFlag.AlignCenter, amount)
    painter.restore()


def quantity_control_rect(rect):
    width = max(26, min(36, round(rect.width() * .14)))
    row = max(27, min(36, round(rect.width() * .15)))
    return C.QRect(rect.right()-width-4, rect.top()+max(38, round(rect.height()*.16)), width, row*2)


def draw_quantity_controls(painter, control, buttons):
    painter.save()
    painter.setRenderHint(G.QPainter.RenderHint.Antialiasing)
    painter.setBrush(G.QColor(235, 242, 248, 65))
    painter.setPen(G.QPen(G.QColor(255, 255, 255, 150), 1))
    painter.drawRoundedRect(C.QRectF(control), 5, 5)
    painter.drawLine(control.left(), control.center().y(), control.right(), control.center().y())
    font = painter.font()
    font.setPointSize(14)
    font.setBold(True)
    painter.setFont(font)
    for delta, button in buttons:
        label = '+' if delta > 0 else '−'
        painter.setPen(G.QColor(0, 0, 0, 225))
        painter.drawText(button.translated(1, 1), C.Qt.AlignmentFlag.AlignCenter, label)
        painter.setPen(G.QColor('white'))
        painter.drawText(button, C.Qt.AlignmentFlag.AlignCenter, label)
    painter.restore()
