"""Interaction layer over the print artwork; never used by PDF rendering."""
import json
from PyQt6 import QtCore, QtGui, QtWidgets
from services import layout_service

MIME = 'application/x-print-proxy-copy'


class PreviewOverlay(QtWidgets.QWidget):
    def __init__(self, grid, preview, page):
        super().__init__(grid)
        self.preview, self.page = preview, page
        self.items = [p for p in preview._placements if p['page'] == page]
        self.occupied = {slot: item for item in self.items for slot in layout_service.cells(item)}
        self.hovered = None
        self.drop_destination = None
        self.drop_valid = False
        self.press_position = None
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground)
        grid.installEventFilter(self)
        self.setGeometry(grid.rect())
        self.show()

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Type.Resize:
            self.setGeometry(obj.rect())
        return False

    def slot(self, position):
        return (self.page, int(position.y() * self.preview._rows / max(1, self.height())),
                int(position.x() * self.preview._columns / max(1, self.width())))

    def item_at(self, slot):
        return self.occupied.get(slot)

    def rectangle(self, row, column, span=1):
        width = self.width() / max(1, self.preview._columns)
        height = self.height() / max(1, self.preview._rows)
        return QtCore.QRectF(column * width, row * height, span * width, height)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        for row in range(self.preview._rows):
            for column in range(self.preview._columns):
                slot = (self.page, row, column)
                if self.item_at(slot):
                    continue
                rect = self.rectangle(row, column).adjusted(3, 3, -3, -3)
                painter.fillRect(rect, QtGui.QColor('#eef3f8'))
                painter.setPen(QtGui.QPen(QtGui.QColor('#93a4b8'), 1, QtCore.Qt.PenStyle.DashLine))
                painter.drawRoundedRect(rect, 5, 5)
                # Draw the plus as strokes so it stays crisp at every zoom/font.
                arm = min(rect.width(), rect.height()) * .18
                center = rect.center()
                painter.setPen(QtGui.QPen(QtGui.QColor('#47617e'), max(3, arm * .15),
                    QtCore.Qt.PenStyle.SolidLine, QtCore.Qt.PenCapStyle.RoundCap))
                painter.drawLine(center + QtCore.QPointF(-arm, 0), center + QtCore.QPointF(arm, 0))
                painter.drawLine(center + QtCore.QPointF(0, -arm), center + QtCore.QPointF(0, arm))
        for item in self.items:
            selected = item['copy_id'] == self.preview._selected_copy
            hovered = self.hovered is not None and self.hovered in layout_service.cells(item)
            if selected or hovered:
                rect = self.rectangle(item['row'], item['column'], item['span']).adjusted(3, 3, -3, -3)
                painter.fillRect(rect, QtGui.QColor(70, 165, 255, 45 if hovered else 20))
                painter.setPen(QtGui.QPen(QtGui.QColor('#128cff' if hovered else '#005fc7'), 4 if hovered else 3))
                painter.drawRoundedRect(rect, 4, 4)
        if self.hovered and self.item_at(self.hovered) is None:
            _, row, column = self.hovered
            painter.setPen(QtGui.QPen(QtGui.QColor('#128cff'), 4))
            painter.drawRect(self.rectangle(row, column).adjusted(3, 3, -3, -3))
        if self.drop_destination is not None:
            _, row, column = self.drop_destination
            rect = self.rectangle(row, column, self.preview._drag_span).adjusted(3, 3, -3, -3)
            color = QtGui.QColor('#16894b' if self.drop_valid else '#d52d39')
            painter.setPen(QtGui.QPen(color, 5))
            color.setAlpha(65)
            painter.fillRect(rect, color)
            painter.drawRect(rect)

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        self.press_position = event.position().toPoint()
        item = self.item_at(self.slot(event.position()))
        self.preview._selected_copy = item['copy_id'] if item else None
        self.preview.update_overlays()

    def mouseMoveEvent(self, event):
        self.hovered = self.slot(event.position())
        item = self.item_at(self.hovered)
        self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor if item else QtCore.Qt.CursorShape.PointingHandCursor)
        self.setToolTip(item['name'] if item else 'Add a card here')
        self.update()
        if self.press_position is None or not event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            return
        if (event.position().toPoint() - self.press_position).manhattanLength() < QtWidgets.QApplication.startDragDistance():
            return
        source_slot = self.slot(self.press_position)
        source = self.item_at(source_slot)
        self.press_position = None
        if source is None:
            return
        self.preview._drag_span = source['span']
        self.preview._drag_active = True
        drag = QtGui.QDrag(self)
        mime = QtCore.QMimeData()
        mime.setData(MIME, json.dumps({'copy_id': source['copy_id'],
            'offset': source_slot[2] - source['column'], 'preview': id(self.preview)}).encode())
        drag.setMimeData(mime)
        rect = self.rectangle(source['row'], source['column'], source['span']).toRect()
        drag.setPixmap(self.parentWidget().grab(rect))
        drag.setHotSpot(event.position().toPoint() - rect.topLeft())
        self.preview._drag_timer.start()
        try:
            drag.exec(QtCore.Qt.DropAction.MoveAction)
        finally:
            self.preview._drag_active = False
            self.preview._drag_timer.stop()
            self.preview.update_overlays()

    def mouseReleaseEvent(self, event):
        if self.press_position is not None and event.button() == QtCore.Qt.MouseButton.LeftButton:
            slot = self.slot(event.position())
            if slot == self.slot(self.press_position) and self.item_at(slot) is None:
                self.preview.add_at_slot(slot)
        self.press_position = None

    def leaveEvent(self, event):
        self.hovered = None
        self.update()

    def dragEnterEvent(self, event):
        self.dragMoveEvent(event)

    def dragMoveEvent(self, event):
        try:
            payload = json.loads(bytes(event.mimeData().data(MIME)))
            if payload['preview'] != id(self.preview):
                raise ValueError('Foreign preview')
            page, row, column = self.slot(event.position())
            self.drop_destination = (page, row, column - payload['offset'])
            self.drop_valid = layout_service.move(self.preview._placements, payload['copy_id'],
                self.drop_destination, self.preview._columns, self.preview._rows) is not None
            # Accept the drag even over invalid slots to continue receiving movement.
            event.acceptProposedAction()
        except (ValueError, KeyError, TypeError):
            self.drop_destination = None
            event.ignore()
        self.update()

    def dragLeaveEvent(self, event):
        self.drop_destination = None
        self.update()

    def dropEvent(self, event):
        self.dragMoveEvent(event)
        if self.drop_destination is not None and self.drop_valid:
            payload = json.loads(bytes(event.mimeData().data(MIME)))
            result = layout_service.move(self.preview._placements, payload['copy_id'],
                self.drop_destination, self.preview._columns, self.preview._rows)
            if result is not None and result != self.preview._placements:
                self.preview.commit_layout(result)
                QtCore.QTimer.singleShot(0, self.preview.refresh_after_edit)
                event.acceptProposedAction()
        else:
            event.ignore()
        self.drop_destination = None
        self.update()


class DragPageButton(QtWidgets.QPushButton):
    def __init__(self, text, callback, preview):
        super().__init__(text)
        self.preview = preview
        self.setAcceptDrops(True)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(650)
        self.timer.timeout.connect(callback)
        self.clicked.connect(callback)

    def dragEnterEvent(self, event):
        if self.preview._drag_active and event.mimeData().hasFormat(MIME):
            self.timer.start()
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.timer.stop()

    def dropEvent(self, event):
        self.timer.stop()
        event.ignore()
