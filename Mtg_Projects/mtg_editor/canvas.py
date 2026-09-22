"""Image-first deck canvas. Only visible cards request and paint artwork."""
import json
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_ui.cards import rounded_card, drag_ghost
from mtg_ui.theme import COLORS
from .organization import grouped_entries
from mtg_core.categorization import is_manual


class CardCanvas(W.QAbstractScrollArea):
    selectionChanged = C.pyqtSignal()
    quantityRequested = C.pyqtSignal(str, int)
    artworkRequested = C.pyqtSignal(str)
    detailsRequested = C.pyqtSignal(str)
    menuRequested = C.pyqtSignal(str, object)
    quickTagRequested = C.pyqtSignal(object)
    moveRequested = C.pyqtSignal(object, str, object)
    preferencesChanged = C.pyqtSignal()
    addRequested = C.pyqtSignal()

    def __init__(self, document, thumbnails, parent=None, search=False):
        super().__init__(parent)
        self.document, self.thumbnails = document, thumbnails
        self.search_mode = search
        self.mode, self.grouping, self.sort, self.query = 'Grid', 'Type', 'Name', ''
        self.card_width = 180
        self.selected = set()
        self.filtered_ids = None
        self.collapsed = set()
        self.items, self.headers = [], []
        self.hovered = None
        self.anchor = None
        self.press_position = None
        self.detail_entry = None
        self.detail_timer = C.QTimer(self)
        self.detail_timer.setSingleShot(True)
        self.detail_timer.timeout.connect(self.open_details)
        self.drop_target = None
        self.setFrameShape(W.QFrame.Shape.NoFrame)
        self.setFocusPolicy(C.Qt.FocusPolicy.StrongFocus)
        self.viewport().setMouseTracking(True)
        self.setAcceptDrops(not search)
        # Use a useful pixel step for card-sized content and native wheel handling.
        self.verticalScrollBar().setSingleStep(48)
        self.verticalScrollBar().valueChanged.connect(self.scrolled)
        self.thumbnails.updated.connect(self.viewport().update)
        self.hover_timer = C.QTimer(self)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.setInterval(450)
        self.hover_timer.timeout.connect(self.show_preview)
        self.preview = W.QLabel(None, C.Qt.WindowType.ToolTip)
        self.preview.setStyleSheet('background:#171b22;border:2px solid #2f9e72;padding:4px;')
        self.auto_scroll = C.QTimer(self)
        self.auto_scroll.setInterval(35)
        self.auto_scroll.timeout.connect(self.scroll_drag)
        self.drag_y = 0

    def refresh(self):
        self.selected.intersection_update(e.entry_id for e in self.document.deck.entries)
        self.relayout()

    def relayout(self):
        self.items, self.headers = [], []
        width = max(150, self.viewport().width())
        cw = min(self.card_width, width - 32)
        if self.search_mode and width >= 270:
            cw = min(cw, (width-48)//2)
        ch = int(cw * 1.4)
        groups = [('Search', 'Results', self.document.deck.entries)] if self.search_mode else grouped_entries(
            self.document.deck, self.grouping, self.sort, self.query,
            show_empty_categories=self.document.editor_preferences.get('show_empty_categories', False),
            entry_ids=self.filtered_ids)
        y, x = 12, 16
        columns = max(1, (width - 16) // (cw + 16))
        row_bottom = y
        for group_index, (key, title, entries) in enumerate(groups):
            if self.mode == 'Stacks' and not self.search_mode:
                if group_index % columns == 0:
                    y, x = row_bottom + (16 if group_index else 0), 16
                else:
                    x += cw + 16
                header = C.QRect(x, y, cw, 38)
                bottom = y + 50
                if key not in self.collapsed:
                    for n, entry in enumerate(entries):
                        rect = C.QRect(x, y + 44 + n * 34, cw, ch)
                        self.items.append((entry, rect, key))
                        bottom = rect.bottom() + 40
                row_bottom = max(row_bottom, bottom)
            else:
                header = C.QRect(16, y, width - 32, 38)
                y += 0 if self.search_mode else 46
                if key not in self.collapsed:
                    for n, entry in enumerate(entries):
                        rect = C.QRect(16 + (n % columns) * (cw + 16), y + (n // columns) * (ch + 40), cw, ch)
                        self.items.append((entry, rect, key))
                    y += max(1, (len(entries) + columns - 1) // columns) * (ch + 40) if entries else 40
                y += 12
                row_bottom = y
            if not self.search_mode:
                self.headers.append((key, title, sum(e.quantity for e in entries), header))
        self.verticalScrollBar().setRange(0, max(0, row_bottom + 16 - self.viewport().height()))
        self.verticalScrollBar().setPageStep(self.viewport().height())
        self.viewport().update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.relayout()

    def scrolled(self):
        self.detail_timer.stop()
        self.preview.hide()
        self.viewport().update()

    def hit(self, position):
        point = position + C.QPoint(0, self.verticalScrollBar().value())
        return next(((e, r, k) for e, r, k in reversed(self.items) if r.contains(point)), None)

    def header_at(self, position):
        point = position + C.QPoint(0, self.verticalScrollBar().value())
        return next((h for h in self.headers if h[3].contains(point)), None)

    def paintEvent(self, event):
        p = G.QPainter(self.viewport())
        p.fillRect(self.viewport().rect(), G.QColor(COLORS['canvas']))
        offset = self.verticalScrollBar().value()
        p.translate(0, -offset)
        visible = C.QRect(0, offset, self.viewport().width(), self.viewport().height())
        near = visible.adjusted(0, -60, 0, 60)
        nearby = [e for e, r, _ in self.items if r.intersects(near)]
        self.thumbnails.set_visible(id(self), [(e.card_id, e.image_asset_id) for e in nearby])
        for entry in nearby:
            self.thumbnails.get(entry.card_id, entry.image_asset_id)
        for key, title, count, rect in self.headers:
            if not rect.intersects(visible):
                continue
            p.fillRect(rect, G.QColor(COLORS['surface']))
            p.setPen(G.QColor(COLORS['accent'] if key == 'Commander' else COLORS['text']))
            center = rect.topLeft() + C.QPoint(12, 19)
            offsets = [(0, -4), (5, 0), (0, 4)] if key in self.collapsed else [(-4, -2), (4, -2), (0, 3)]
            p.setBrush(p.pen().color())
            p.drawPolygon(G.QPolygon([center+C.QPoint(*point) for point in offsets]))
            p.drawText(rect.adjusted(25, 0, -5, 0), C.Qt.AlignmentFlag.AlignVCenter, f'{title}   {count}')
        for entry, rect, key in self.items:
            if not rect.adjusted(0, 0, 0, 32).intersects(visible):
                continue
            pixmap = self.thumbnails.get(entry.card_id, entry.image_asset_id)
            rounded_card(p, rect, pixmap, entry.entry_id in self.selected, entry.entry_id == self.hovered)
            badge = C.QRect(rect.x()+4, rect.bottom()-28, 32, 24)
            p.fillRect(badge, G.QColor('#20352f'))
            p.setPen(G.QColor('white'))
            p.drawText(badge, C.Qt.AlignmentFlag.AlignCenter, str(entry.quantity))
            if not self.search_mode and (entry.category_ids or entry.extras.get('auto_categories')):
                source = 'Manual' if is_manual(entry) else 'Auto'
                source_rect = C.QRect(rect.x()+40, rect.bottom()-28, 54, 24)
                p.fillRect(source_rect, G.QColor('#69458a' if source == 'Manual' else '#20352f'))
                p.drawText(source_rect, C.Qt.AlignmentFlag.AlignCenter, source)
            if entry.entry_id == self.hovered or entry.entry_id in self.selected:
                control = self.control_rect(rect)
                p.fillRect(control, G.QColor('#20352f'))
                p.drawText(control, C.Qt.AlignmentFlag.AlignCenter, '+ Add' if self.search_mode else '−     +')
            if self.mode != 'Stacks' or not any(r.y() > rect.y() and r.x() == rect.x() and k == key for _, r, k in self.items):
                label = ('Oversized · ' if entry.extras.get('oversized') else '') + ('Owned · ' if entry.do_not_print else '') + entry.name
                p.setPen(G.QColor(COLORS['text_secondary']))
                p.drawText(C.QRect(rect.x(), rect.bottom()+4, rect.width(), 28), C.Qt.AlignmentFlag.AlignCenter,
                           p.fontMetrics().elidedText(label, C.Qt.TextElideMode.ElideRight, rect.width()))
        if self.drop_target:
            key, valid = self.drop_target
            rect = next(h[3] for h in self.headers if h[0] == key)
            p.setPen(G.QPen(G.QColor(COLORS['accent'] if valid else COLORS['danger']), 3))
            p.setBrush(C.Qt.BrushStyle.NoBrush)
            p.drawRect(rect)
        if not self.document.deck.entries or (not self.items and not self.headers):
            middle = visible.center()
            for dx in (-55, 0, 55):
                p.setPen(G.QPen(G.QColor(COLORS['border_strong']), 2))
                p.setBrush(G.QColor(COLORS['surface']))
                p.drawRoundedRect(C.QRect(middle.x()+dx-40, middle.y()-145, 80, 112), 8, 8)
            p.setPen(G.QColor(COLORS['text_secondary']))
            p.drawText(visible, C.Qt.AlignmentFlag.AlignCenter,
                       '+ Add Cards\nBuild your deck with local card search' if not self.search_mode else 'Search your local catalog')
        p.end()

    def control_rect(self, rect):
        # Narrow cards need a separate row so controls do not cover the badges.
        bottom_offset = 57 if rect.width() < 164 else 29
        return C.QRect(rect.right()-65, rect.top()+3 if self.mode == 'Stacks' else rect.bottom()-bottom_offset, 60, 25)

    def mousePressEvent(self, event):
        self.detail_timer.stop()
        self.detail_entry = None
        self.setFocus()
        self.hover_timer.stop()
        self.preview.hide()
        if event.button() != C.Qt.MouseButton.LeftButton:
            return
        header = self.header_at(event.position().toPoint())
        if header:
            key = header[0]
            self.collapsed.symmetric_difference_update({key})
            self.preferencesChanged.emit()
            self.relayout()
            return
        item = self.hit(event.position().toPoint())
        if item is None:
            self.selected.clear()
            self.selectionChanged.emit()
            if not self.document.deck.entries:
                self.addRequested.emit()
            self.viewport().update()
            return
        entry, rect, _ = item
        point = event.position().toPoint() + C.QPoint(0, self.verticalScrollBar().value())
        if self.control_rect(rect).contains(point):
            self.quantityRequested.emit(entry.entry_id, 1 if self.search_mode or point.x() > rect.right()-35 else -1)
            return
        mods = event.modifiers()
        visible_ids = [e.entry_id for e, _, _ in self.items]
        if mods & C.Qt.KeyboardModifier.ShiftModifier and self.anchor in visible_ids:
            a, b = sorted((visible_ids.index(self.anchor), visible_ids.index(entry.entry_id)))
            self.selected.update(visible_ids[a:b+1])
        elif mods & C.Qt.KeyboardModifier.ControlModifier:
            self.selected.symmetric_difference_update({entry.entry_id})
        elif entry.entry_id not in self.selected:
            self.selected = {entry.entry_id}
        self.anchor = entry.entry_id
        self.press_position = event.position().toPoint()
        if not self.search_mode and not mods:
            self.detail_entry = entry.entry_id
        self.selectionChanged.emit()
        self.viewport().update()

    def mouseMoveEvent(self, event):
        item = self.hit(event.position().toPoint())
        hovered = item[0].entry_id if item else None
        if hovered != self.hovered:
            self.hovered = hovered
            self.preview.hide()
            self.hover_timer.start()
            self.viewport().update()
        if (not self.search_mode and event.buttons() & C.Qt.MouseButton.LeftButton and self.press_position is not None
                and (event.position().toPoint()-self.press_position).manhattanLength() >= W.QApplication.startDragDistance()):
            self.press_position = None
            self.detail_entry = None
            self.hover_timer.stop()
            drag = G.QDrag(self)
            mime = C.QMimeData()
            mime.setData('application/x-manaforge-entries', json.dumps(sorted(self.selected)).encode())
            drag.setMimeData(mime)
            if item:
                pix = self.thumbnails.get(item[0].card_id, item[0].image_asset_id)
                if pix and not pix.isNull():
                    drag.setPixmap(drag_ghost(pix))
            drag.exec(C.Qt.DropAction.MoveAction)
            self.auto_scroll.stop()
            self.drop_target = None
            self.viewport().update()

    def mouseReleaseEvent(self, event):
        if event.button() == C.Qt.MouseButton.LeftButton and self.press_position is not None and self.detail_entry:
            self.detail_timer.start(W.QApplication.doubleClickInterval())
        self.press_position = None

    def open_details(self):
        if self.detail_entry and self.isVisible():
            self.hover_timer.stop()
            self.preview.hide()
            self.detailsRequested.emit(self.detail_entry)

    def mouseDoubleClickEvent(self, event):
        self.detail_timer.stop()
        self.detail_entry = None
        self.press_position = None
        if event.button() != C.Qt.MouseButton.LeftButton:
            return
        item = self.hit(event.position().toPoint())
        if item:
            if self.search_mode:
                self.quantityRequested.emit(item[0].entry_id, 1)
            else:
                self.artworkRequested.emit(item[0].entry_id)

    def leaveEvent(self, event):
        self.hover_timer.stop()
        self.preview.hide()
        self.hovered = None
        self.viewport().update()

    def show_preview(self):
        if not self.isVisible() or W.QApplication.activePopupWidget() is not None:
            return
        entry = next((e for e in self.document.deck.entries if e.entry_id == self.hovered), None)
        if entry is None or W.QApplication.mouseButtons() != C.Qt.MouseButton.NoButton:
            return
        pixmap = self.thumbnails.get(entry.card_id, entry.image_asset_id)
        if pixmap is None or pixmap.isNull():
            return
        self.preview.setPixmap(pixmap.scaled(300, 420, C.Qt.AspectRatioMode.KeepAspectRatio, C.Qt.TransformationMode.SmoothTransformation))
        self.preview.adjustSize()
        screen = W.QApplication.screenAt(G.QCursor.pos()) or W.QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        point = G.QCursor.pos() + C.QPoint(24, 12)
        point.setX(min(point.x(), bounds.right()-self.preview.width()))
        point.setY(min(point.y(), bounds.bottom()-self.preview.height()))
        self.preview.move(point)
        self.preview.show()

    def contextMenuEvent(self, event):
        if not self.search_mode and not event.modifiers() & C.Qt.KeyboardModifier.ShiftModifier:
            event.accept()
            return
        self.hover_timer.stop()
        self.preview.hide()
        item = self.hit(event.pos())
        if item:
            if item[0].entry_id not in self.selected:
                self.selected = {item[0].entry_id}
            self.selectionChanged.emit()
            self.menuRequested.emit(item[0].entry_id, event.globalPos())
            self.viewport().update()

    def keyPressEvent(self, event):
        self.detail_timer.stop()
        if event.key() == C.Qt.Key.Key_T and not event.modifiers() and self.selected and not self.search_mode:
            if not event.isAutoRepeat():
                self.quickTagRequested.emit(G.QCursor.pos())
        elif event.matches(G.QKeySequence.StandardKey.SelectAll):
            self.selected = {e.entry_id for e, _, _ in self.items}
            self.selectionChanged.emit()
            self.viewport().update()
        elif event.key() == C.Qt.Key.Key_Delete and self.selected:
            self.quantityRequested.emit('', 0)
        else:
            super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.source() is self:
            event.acceptProposedAction()

    def destination(self, point):
        header = self.header_at(point)
        item = self.hit(point)
        key = header[0] if header else item[2] if item else None
        return key, item[0].entry_id if item else None

    def dragMoveEvent(self, event):
        key, before = self.destination(event.position().toPoint())
        valid = key is not None and (self.grouping in ('Section', 'Category') or
                (self.sort == 'Import Order' and all(k == key for e, _, k in self.items if e.entry_id in self.selected)))
        self.drop_target = (key, valid) if key else None
        self.drag_y = event.position().toPoint().y()
        self.auto_scroll.start()
        if valid:
            event.acceptProposedAction()
        else:
            event.ignore()
        self.viewport().update()

    def scroll_drag(self):
        delta = -18 if self.drag_y < 45 else 18 if self.drag_y > self.viewport().height()-45 else 0
        self.verticalScrollBar().setValue(self.verticalScrollBar().value()+delta)

    def dragLeaveEvent(self, event):
        self.auto_scroll.stop()
        self.drop_target = None
        self.viewport().update()

    def dropEvent(self, event):
        self.auto_scroll.stop()
        if self.drop_target and self.drop_target[1] and event.source() is self:
            key, before = self.destination(event.position().toPoint())
            self.moveRequested.emit(set(self.selected), key, before if self.sort == 'Import Order' else None)
            event.acceptProposedAction()
        self.drop_target = None
        self.viewport().update()
