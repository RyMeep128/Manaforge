"""Compact grouped deck rows sharing the editor model, selection, and commands."""
import re

from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_ui.card_chrome import marker_color
from .organization import grouped_entries
from .tasks import Task


class TextRows(W.QAbstractScrollArea):
    def __init__(self, editor, host):
        super().__init__(host)
        self.editor, self.host = editor, host
        self.items, self.headers = [], []
        self.hovered = self.anchor = None
        self.collapsed = set()
        self.setFocusPolicy(C.Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(C.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAccessibleName('Grouped text deck list')
        self.verticalScrollBar().valueChanged.connect(self.viewport().update)
        self.detail_timer = C.QTimer(self)
        self.detail_timer.setSingleShot(True)
        self.detail_timer.timeout.connect(self.open_details)
        self.detail_entry = None

    def refresh(self):
        grid = self.editor.grid
        ids = {entry.entry_id for entry in self.editor.model.document.deck.entries}
        if self.anchor not in ids:
            self.anchor = None
        groups = grouped_entries(self.editor.model.document.deck, grid.grouping, grid.sort,
                                 grid.query, entry_ids=grid.filtered_ids)
        width = max(1, self.viewport().width())
        columns = max(1, min(4, width // 320))
        gap = 16
        column_width = max(1, (width - gap*(columns-1)) // columns)
        heights = [8] * columns
        self.items, self.headers = [], []
        for key, title, entries in groups:
            if not entries:
                continue
            commander = key == 'Commander'
            column = min(range(columns), key=lambda index: heights[index])
            x, y = column*(column_width+gap), heights[column]
            if commander:
                x, y = 0, max(heights)
            row_width = width if commander else column_width
            self.headers.append((key, title, sum(entry.quantity for entry in entries), C.QRect(x, y, row_width, 30)))
            y += 32
            if key not in self.collapsed:
                for entry in entries:
                    self.items.append((entry, C.QRect(x, y, row_width, 26)))
                    y += 26
            if commander:
                heights = [y+16] * columns
            else:
                heights[column] = y+16
        self.verticalScrollBar().setRange(0, max(0, max(heights)-self.viewport().height()))
        self.verticalScrollBar().setPageStep(self.viewport().height())
        self.viewport().update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh()

    def paintEvent(self, event):
        painter = G.QPainter(self.viewport())
        painter.fillRect(self.viewport().rect(), G.QColor('#101419'))
        painter.setRenderHint(G.QPainter.RenderHint.Antialiasing)
        offset = self.verticalScrollBar().value()
        painter.translate(0, -offset)
        visible = C.QRect(0, offset, self.viewport().width(), self.viewport().height())
        category_ids = {category.category_id for category in self.editor.document.deck.categories}
        for key, title, count, rect in self.headers:
            if not rect.intersects(visible):
                continue
            color = '#27b78a' if key == 'Commander' else marker_color('role:' + key) if key in category_ids else '#b5bdc9'
            painter.fillRect(C.QRect(rect.x(), rect.y()+6, 3, 18), G.QColor(color))
            painter.setPen(G.QColor(color))
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)
            text = ('▸ ' if key in self.collapsed else '▾ ') + f'{title} ({count})'
            painter.drawText(rect.adjusted(10, 0, -4, 0), C.Qt.AlignmentFlag.AlignVCenter,
                             painter.fontMetrics().elidedText(text, C.Qt.TextElideMode.ElideRight, rect.width()-16))
            font.setBold(False)
            painter.setFont(font)
        for entry, rect in self.items:
            if not rect.intersects(visible):
                continue
            selected = entry.entry_id in self.editor.grid.selected
            hovered = entry.entry_id == self.hovered
            if selected or hovered:
                painter.fillRect(rect, G.QColor('#24493f' if selected else '#222c35'))
            painter.setPen(G.QColor('#e4e8ed'))
            painter.drawText(C.QRect(rect.x()+17, rect.y(), 27, rect.height()),
                             C.Qt.AlignmentFlag.AlignCenter, str(entry.quantity))
            tokens = re.findall(r'\{([^}]+)\}', self.host.mana_cost(entry))
            cost_width = min(len(tokens)*21, max(0, rect.width()-160))
            name_rect = rect.adjusted(64, 0, -cost_width-32, 0)
            painter.drawText(name_rect, C.Qt.AlignmentFlag.AlignVCenter,
                             painter.fontMetrics().elidedText(entry.name, C.Qt.TextElideMode.ElideRight, max(0, name_rect.width())))
            self.paint_mana(painter, tokens, C.QRect(rect.right()-cost_width-28, rect.y(), cost_width, rect.height()))
            painter.setPen(G.QColor('#aab6c3'))
            painter.drawText(self.menu_rect(rect), C.Qt.AlignmentFlag.AlignCenter, '⋯')
            if hovered:
                for delta, button in self.quantity_buttons(rect):
                    painter.drawText(button, C.Qt.AlignmentFlag.AlignCenter, '+' if delta > 0 else '−')

    @staticmethod
    def paint_mana(painter, tokens, rect):
        colors = {'W': '#eee4c4', 'U': '#80b8d8', 'B': '#a29a9a', 'R': '#de927b', 'G': '#91ba9b'}
        painter.save()
        painter.setClipRect(rect)
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        step = min(21, rect.width() // max(1, len(tokens)))
        diameter = max(1, min(18, step-2))
        for index, token in enumerate(tokens):
            circle = C.QRect(rect.x()+index*step, rect.y()+(rect.height()-diameter)//2, diameter, diameter)
            painter.setPen(C.Qt.PenStyle.NoPen)
            painter.setBrush(G.QColor(colors.get(token, '#c4c6c9')))
            painter.drawEllipse(circle)
            painter.setPen(G.QColor('#15191d'))
            painter.drawText(circle, C.Qt.AlignmentFlag.AlignCenter, token)
        painter.restore()

    @staticmethod
    def menu_rect(rect):
        return C.QRect(rect.right()-24, rect.y(), 24, rect.height())

    @staticmethod
    def quantity_buttons(rect):
        return [(-1, C.QRect(rect.x(), rect.y(), 17, rect.height())),
                (1, C.QRect(rect.x()+44, rect.y(), 18, rect.height()))]

    def point(self, event):
        return event.position().toPoint() + C.QPoint(0, self.verticalScrollBar().value())

    def mouseMoveEvent(self, event):
        item = next((item for item in self.items if item[1].contains(self.point(event))), None)
        self.hovered = item[0].entry_id if item else None
        if item:
            self.host.preview_entry(item[0])
        self.viewport().update()

    def leaveEvent(self, event):
        self.hovered = None
        self.viewport().update()
        super().leaveEvent(event)

    def select(self, entry, modifiers):
        selected = self.editor.grid.selected
        ids = [item[0].entry_id for item in self.items]
        if modifiers & C.Qt.KeyboardModifier.ShiftModifier and self.anchor in ids:
            first, last = sorted((ids.index(self.anchor), ids.index(entry.entry_id)))
            selected.update(ids[first:last+1])
        elif modifiers & C.Qt.KeyboardModifier.ControlModifier:
            selected.symmetric_difference_update({entry.entry_id})
        else:
            self.editor.grid.selected = {entry.entry_id}
        self.anchor = entry.entry_id
        self.editor.selection_changed()
        self.host.preview_entry(entry)
        self.viewport().update()

    def mousePressEvent(self, event):
        self.detail_timer.stop()
        self.setFocus()
        point = self.point(event)
        if event.button() == C.Qt.MouseButton.LeftButton:
            for key, _, _, rect in self.headers:
                if rect.contains(point):
                    self.collapsed.symmetric_difference_update({key})
                    self.host.save_preferences()
                    self.refresh()
                    return
        item = next((item for item in self.items if item[1].contains(point)), None)
        if item is None:
            return
        entry, rect = item
        if event.button() == C.Qt.MouseButton.RightButton:
            if entry.entry_id not in self.editor.grid.selected:
                self.select(entry, C.Qt.KeyboardModifier.NoModifier)
            self.editor.card_menu(entry.entry_id, event.globalPosition().toPoint())
            return
        if event.button() != C.Qt.MouseButton.LeftButton:
            return
        if self.menu_rect(rect).contains(point):
            if entry.entry_id not in self.editor.grid.selected:
                self.select(entry, C.Qt.KeyboardModifier.NoModifier)
            self.editor.card_menu(entry.entry_id, event.globalPosition().toPoint())
            return
        for delta, button in self.quantity_buttons(rect):
            if button.contains(point):
                self.editor.change_quantity(entry.entry_id, delta)
                return
        self.select(entry, event.modifiers())
        if not event.modifiers():
            self.detail_entry = entry.entry_id
            self.detail_timer.start(W.QApplication.doubleClickInterval())

    def mouseDoubleClickEvent(self, event):
        self.detail_timer.stop()
        point = self.point(event)
        item = next((item for item in self.items if item[1].contains(point)), None)
        if item and event.button() == C.Qt.MouseButton.LeftButton:
            entry, rect = item
            if not self.menu_rect(rect).contains(point) and not any(button.contains(point) for _, button in self.quantity_buttons(rect)):
                self.editor.card_details(entry.entry_id)

    def open_details(self):
        if self.isVisible() and self.detail_entry:
            self.editor.card_details(self.detail_entry)

    def keyPressEvent(self, event):
        key = event.key()
        if key == C.Qt.Key.Key_A and event.modifiers() & C.Qt.KeyboardModifier.ControlModifier:
            self.editor.grid.selected = {entry.entry_id for entry, _ in self.items}
            self.editor.selection_changed()
            self.viewport().update()
        elif key in (C.Qt.Key.Key_Up, C.Qt.Key.Key_Down, C.Qt.Key.Key_Home, C.Qt.Key.Key_End) and self.items:
            ids = [entry.entry_id for entry, _ in self.items]
            index = ids.index(self.anchor) if self.anchor in ids else -1
            index = (0 if key == C.Qt.Key.Key_Home else len(ids)-1 if key == C.Qt.Key.Key_End
                     else max(0, min(len(ids)-1, index + (1 if key == C.Qt.Key.Key_Down else -1))))
            entry, rect = self.items[index]
            self.select(entry, event.modifiers())
            bar = self.verticalScrollBar()
            if rect.top() < bar.value():
                bar.setValue(rect.top())
            elif rect.bottom() > bar.value()+self.viewport().height():
                bar.setValue(rect.bottom()-self.viewport().height())
        elif key in (C.Qt.Key.Key_Return, C.Qt.Key.Key_Enter) and self.anchor:
            self.editor.card_details(self.anchor)
        elif key in (C.Qt.Key.Key_Menu, C.Qt.Key.Key_F10) and self.anchor:
            self.editor.card_menu(self.anchor, G.QCursor.pos())
        elif key in (C.Qt.Key.Key_Delete, C.Qt.Key.Key_Backspace):
            self.editor.remove_selected()
        elif key in (C.Qt.Key.Key_Plus, C.Qt.Key.Key_Equal, C.Qt.Key.Key_Minus) and self.editor.grid.selected:
            self.editor.change_quantity(next(iter(self.editor.grid.selected)), -1 if key == C.Qt.Key.Key_Minus else 1)
        elif key == C.Qt.Key.Key_T and self.editor.grid.selected:
            if not event.isAutoRepeat():
                self.editor.quick_tag(G.QCursor.pos())
        else:
            super().keyPressEvent(event)

    def hideEvent(self, event):
        self.detail_timer.stop()
        super().hideEvent(event)


class TextDeckView(W.QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.worker = None
        self.stopping = False
        self.costs = {}
        self.preview_id = None
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        self.preview_toggle = W.QCheckBox('Card preview')
        self.preview_toggle.setChecked(True)
        self.preview_toggle.toggled.connect(self.toggle_preview)
        layout.addWidget(self.preview_toggle)
        body = W.QHBoxLayout()
        self.preview = W.QLabel('Hover or select a card')
        self.preview.setAlignment(C.Qt.AlignmentFlag.AlignTop | C.Qt.AlignmentFlag.AlignHCenter)
        self.preview.setFixedWidth(240)
        self.preview.setSizePolicy(W.QSizePolicy.Policy.Fixed, W.QSizePolicy.Policy.Ignored)
        self.preview.setWordWrap(True)
        body.addWidget(self.preview)
        self.rows = TextRows(editor, self)
        body.addWidget(self.rows, 1)
        layout.addLayout(body, 1)
        editor.thumbnails.updated.connect(self.update_preview)

    def save_preferences(self):
        self.editor.document.editor_preferences.update(
            text_preview=self.preview_toggle.isChecked(), text_collapsed=sorted(self.rows.collapsed))
        self.editor.changed()

    def toggle_preview(self):
        self.preview.setVisible(self.preview_toggle.isChecked() and self.width() >= 900)
        self.update_preview()
        self.save_preferences()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.preview.setVisible(self.preview_toggle.isChecked() and self.width() >= 900)
        self.update_preview()

    def refresh(self):
        self.rows.refresh()
        self.update_preview()
        self.load_costs()

    def mana_cost(self, entry):
        facts = entry.extras.get('facts') or {}
        return facts.get('mana_cost') or (facts.get('card_faces') or [{}])[0].get('mana_cost') or self.costs.get(entry.card_id, '')

    def load_costs(self):
        if not self.isVisible() or self.worker is not None or self.stopping or not hasattr(self.editor.service, 'get_card'):
            return
        ids = list(dict.fromkeys(entry.card_id for entry in self.editor.document.deck.entries
                               if entry.card_id and entry.card_id not in self.costs
                               and 'mana_cost' not in (entry.extras.get('facts') or {})))[:50]
        if not ids:
            return
        service = self.editor.service
        def load():
            costs = {}
            for card_id in ids:
                payload = service.get_card(card_id=card_id) or {}
                costs[card_id] = payload.get('mana_cost') or (payload.get('card_faces') or [{}])[0].get('mana_cost') or ''
            return costs
        self.worker = Task(load, self, operation='text view mana costs')
        def completed(costs, error):
            self.costs.update(costs if not error else dict.fromkeys(ids, ''))
            self.rows.viewport().update()
        def finished():
            self.worker.deleteLater()
            self.worker = None
            self.load_costs()
        self.worker.completed.connect(completed)
        self.worker.finished.connect(finished)
        self.worker.start()

    def preview_entry(self, entry):
        self.preview_id = entry.entry_id
        self.update_preview()

    def update_preview(self):
        if not self.isVisible() or self.preview.isHidden():
            self.editor.thumbnails.set_visible(id(self), [])
            return
        entry = next((entry for entry in self.editor.document.deck.entries if entry.entry_id == self.preview_id), None)
        if entry is None:
            entry = next((entry for entry in self.editor.document.deck.entries if entry.entry_id in self.editor.grid.selected), None)
        if entry is None:
            self.preview.clear()
            self.preview.setText('Hover or select a card')
            self.editor.thumbnails.set_visible(id(self), [])
            return
        self.preview_id = entry.entry_id
        self.editor.thumbnails.set_visible(id(self), [(entry.card_id, entry.image_asset_id, 600)])
        pixmap = self.editor.thumbnails.get(entry.card_id, entry.image_asset_id, high_resolution=True)
        if pixmap is not None and not pixmap.isNull():
            self.preview.setPixmap(pixmap.scaled(240, max(1, min(336, self.preview.height())), C.Qt.AspectRatioMode.KeepAspectRatio,
                                                 C.Qt.TransformationMode.SmoothTransformation))
        else:
            self.preview.setText(entry.name + '\nLoading artwork...')

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def hideEvent(self, event):
        self.editor.thumbnails.set_visible(id(self), [])
        super().hideEvent(event)
