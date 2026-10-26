"""Image-first deck canvas. Only visible cards request and paint artwork."""
import json
import math
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_ui.cards import rounded_card, drag_ghost
from mtg_ui.theme import COLORS
from .organization import grouped_entries
from .card_views import Thumbnails
from .card_chrome import (marker_color, corner_colors, draw_quantity_corner,
                          quantity_control_rect, draw_quantity_controls)


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
    discoverRequested = C.pyqtSignal(object)

    def __init__(self, document, thumbnails, parent=None, search=False):
        super().__init__(parent)
        self.document, self.thumbnails = document, thumbnails
        self.search_mode = search
        self.mode, self.grouping, self.sort, self.query = 'Grid', 'Type', 'Name', ''
        self.card_width = 180
        self.fit_height = False
        self.faces = {}
        self.flip_animations = {}
        self.expanded_stacks = set()
        self.discovery_drop = False
        self.minimum_search_card_width = None
        self.card_aspect_ratio = 1.4
        self.selected = set()
        self.in_deck_ids = set()
        self.filtered_ids = None
        self.collapsed = set()
        self.items, self.headers = [], []
        self.hovered = None
        self.stack_expansion = {}
        self.stack_animation_start = {}
        self.stack_animation_target = {}
        self.stack_animation = C.QVariantAnimation(self)
        self.stack_animation.setDuration(720)
        self.stack_animation.setStartValue(0.0)
        self.stack_animation.setEndValue(1.0)
        self.stack_animation.setEasingCurve(C.QEasingCurve.Type.OutCubic)
        self.stack_animation.valueChanged.connect(self.animate_stack_frame)
        self.context_target = None
        self.context_resume_timer = C.QTimer(self)
        self.context_resume_timer.setSingleShot(True)
        self.context_resume_timer.timeout.connect(self.resume_context_hover)
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
        self.setAcceptDrops(True)
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
        self.prune_flips()
        self.items, self.headers = [], []
        width = max(1 if self.minimum_search_card_width is not None else 150, self.viewport().width())
        cw = min(self.card_width, width - 32)
        if self.search_mode and self.minimum_search_card_width is None and width >= 270:
            cw = min(cw, (width-48)//2)
        elif self.search_mode and self.minimum_search_card_width is not None:
            cw = min(max(self.minimum_search_card_width, self.card_width), max(1, width - 32))
        if self.fit_height:
            cw = min(cw, max(1, int((self.viewport().height() - 60) / self.card_aspect_ratio)))
        cw = max(1, cw)
        ch = int(cw * self.card_aspect_ratio)
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
                    expanded_offset = 0
                    for n, entry in enumerate(entries):
                        rect = C.QRect(x, y + 44 + n * (ch + 36 if key in self.expanded_stacks else 34) + expanded_offset, cw, ch)
                        self.items.append((entry, rect, key))
                        bottom = rect.bottom() + 40
                        expanded_offset += round((0 if key in self.expanded_stacks else max(0, ch + 6 - 34)) *
                                                 self.stack_expansion.get(entry.entry_id, 0.0))
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

    def animate_stack(self):
        # Retarget from the current positions when moving between cards quickly.
        self.stack_animation.stop()
        self.stack_animation_start = dict(self.stack_expansion)
        self.stack_animation_target = {self.hovered: 1.0} if self.hovered else {}
        self.stack_animation.start()

    def pin_context_target(self, entry_id):
        self.context_resume_timer.stop()
        self.context_target = entry_id
        self.hovered = entry_id
        self.hover_timer.stop()
        self.detail_timer.stop()
        self.preview.hide()
        self.stack_animation.stop()
        self.viewport().update()

    def release_context_target(self):
        # Popups may enter a nested event loop or take over the mouse grab.
        self.context_resume_timer.start(0)

    def resume_context_hover(self):
        if W.QApplication.activePopupWidget() is not None or W.QApplication.mouseButtons() & C.Qt.MouseButton.RightButton:
            self.context_resume_timer.start(50)
            return
        self.context_target = None
        point = self.viewport().mapFromGlobal(G.QCursor.pos())
        item = self.hit(point) if self.viewport().rect().contains(point) else None
        self.hovered = item[0].entry_id if item else None
        if self.mode == 'Stacks' and not self.search_mode:
            self.animate_stack()
        else:
            self.viewport().update()

    def animate_stack_frame(self, progress):
        start, target = self.stack_animation_start, self.stack_animation_target
        self.stack_expansion = {
            key: start.get(key, 0.0) + (target.get(key, 0.0) - start.get(key, 0.0)) * progress
            for key in start.keys() | target.keys()
        }
        self.stack_expansion = {key: value for key, value in self.stack_expansion.items() if value > .0001}
        self.relayout()

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
        self.prune_flips()
        p = G.QPainter(self.viewport())
        p.fillRect(self.viewport().rect(), G.QColor(COLORS['canvas']))
        offset = self.verticalScrollBar().value()
        p.translate(0, -offset)
        visible = C.QRect(0, offset, self.viewport().width(), self.viewport().height())
        near = visible.adjusted(0, -60, 0, 60)
        nearby = [e for e, r, _ in self.items if r.intersects(near)]
        visible_keys = [self.image_key(e) for e in nearby]
        if self.mode == 'Stacks' and not self.search_mode:
            visible_keys.extend(self.image_key(e, high_resolution=True) for e in nearby if e.entry_id == self.hovered)
        for entry in nearby:
            state = self.flip_animations.get(entry.entry_id)
            if state:
                options, asset = self.face_image_options(entry, state['target'])
                visible_keys.append(Thumbnails.key(entry.card_id, asset, **options))
        self.thumbnails.set_visible(id(self), visible_keys)
        for entry in nearby:
            self.card_image(entry)
        category_colors = {category.category_id: marker_color('role:' + category.category_id)
                           for category in self.document.deck.categories}
        for key, title, count, rect in self.headers:
            if not rect.intersects(visible):
                continue
            p.fillRect(rect, G.QColor(COLORS['surface']))
            p.setPen(G.QColor(COLORS['accent'] if key == 'Commander' else COLORS['text']))
            center = rect.topLeft() + C.QPoint(12, 19)
            offsets = [(0, -4), (5, 0), (0, 4)] if key in self.collapsed else [(-4, -2), (4, -2), (0, 3)]
            p.setBrush(p.pen().color())
            p.drawPolygon(G.QPolygon([center+C.QPoint(*point) for point in offsets]))
            text_rect = rect.adjusted(25, 0, -34 if self.mode == 'Stacks' else -5, 0)
            count_width = p.fontMetrics().horizontalAdvance(str(count)) + 12
            count_rect = C.QRect(text_rect.right()-count_width, text_rect.top(), count_width, text_rect.height())
            text_rect.setRight(count_rect.left()-4)
            p.drawText(text_rect, C.Qt.AlignmentFlag.AlignVCenter,
                       p.fontMetrics().elidedText(title, C.Qt.TextElideMode.ElideRight, max(0, text_rect.width())))
            p.drawText(count_rect, C.Qt.AlignmentFlag.AlignVCenter | C.Qt.AlignmentFlag.AlignRight, str(count))
            if self.mode == 'Stacks':
                p.drawText(self.expand_rect(rect), C.Qt.AlignmentFlag.AlignCenter,
                           '-' if key in self.expanded_stacks else '+')
            if self.grouping == 'Category' and key in category_colors:
                p.fillRect(C.QRect(rect.right()-7, rect.top()+10, 4, 18), G.QColor(category_colors[key]))
        for entry, rect, key in self.items:
            if not rect.adjusted(0, 0, 0, 32).intersects(visible):
                continue
            pixmap = self.card_image(entry)
            if self.mode == 'Stacks' and not self.search_mode and entry.entry_id == self.hovered:
                pixmap = self.card_image(entry, high_resolution=True)
            in_deck = self.search_mode and entry.entry_id in self.in_deck_ids
            state = self.flip_animations.get(entry.entry_id)
            if state:
                self.paint_flip(p, rect, pixmap, entry.entry_id in self.selected or in_deck,
                                entry.entry_id == self.hovered, state['progress'])
            else:
                rounded_card(p, rect, pixmap, entry.entry_id in self.selected or in_deck, entry.entry_id == self.hovered)
            primary, tags = corner_colors(entry, category_colors)
            draw_quantity_corner(p, rect, entry.quantity, primary, tags)
            if self.face_count(entry) > 1:
                self.draw_flip(p, self.flip_rect(rect))
            if entry.entry_id == self.hovered or entry.entry_id in self.selected:
                control = self.control_rect(rect)
                draw_quantity_controls(p, control, self.quantity_buttons(rect), can_decrease=entry.quantity > 0)
            if self.mode != 'Stacks' or key in self.expanded_stacks or not any(r.y() > rect.y() and r.x() == rect.x() and k == key for _, r, k in self.items):
                label = ('Oversized · ' if entry.oversized else '') + ('Owned · ' if entry.do_not_print else '') + self.shown_facts(entry).get('name', entry.name)
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
        if self.discovery_drop:
            p.resetTransform()
            p.setPen(G.QPen(G.QColor(COLORS['accent']), 4))
            p.setBrush(C.Qt.BrushStyle.NoBrush)
            p.drawRect(self.viewport().rect().adjusted(2, 2, -2, -2))
        p.end()

    @staticmethod
    def face_count(entry):
        return len((entry.extras.get('facts') or {}).get('card_faces') or [])

    def shown_facts(self, entry):
        facts = entry.extras.get('facts') or {}
        faces = facts.get('card_faces') or []
        return faces[self.faces.get(entry.entry_id, 0) % len(faces)] if faces else facts

    def image_options(self, entry, high_resolution=False):
        face = self.faces.get(entry.entry_id, 0) % max(1, self.face_count(entry))
        return self.face_image_options(entry, face, high_resolution)

    @staticmethod
    def face_image_options(entry, face, high_resolution=False):
        asset = entry.backside_asset_id if face else entry.image_asset_id
        options = {}
        if face:
            options['face'] = face
        if high_resolution:
            options['high_resolution'] = True
        return options, asset

    def image_key(self, entry, high_resolution=False):
        options, asset = self.image_options(entry, high_resolution)
        return Thumbnails.key(entry.card_id, asset, **options)

    def card_image(self, entry, high_resolution=False):
        options, asset = self.image_options(entry, high_resolution)
        return self.thumbnails.get(entry.card_id, asset, **options)

    @staticmethod
    def flip_rect(rect):
        control = quantity_control_rect(rect)
        return C.QRect(control.left(), control.bottom()+5, control.width(), control.width())

    @staticmethod
    def draw_flip(painter, rect):
        painter.save()
        painter.setRenderHint(G.QPainter.RenderHint.Antialiasing)
        painter.translate(rect.x(), rect.y())
        painter.scale(rect.width()/32, rect.height()/32)
        painter.setPen(G.QPen(G.QColor('#453f36'), 1.2))
        painter.setBrush(G.QColor(237, 229, 210, 235))
        painter.drawEllipse(C.QRectF(1, 1, 30, 30))
        painter.setPen(G.QPen(G.QColor('#39362f'), 2.5,
                             C.Qt.PenStyle.SolidLine, C.Qt.PenCapStyle.RoundCap))
        painter.setBrush(C.Qt.BrushStyle.NoBrush)
        upper = G.QPainterPath(C.QPointF(7, 16))
        upper.cubicTo(7, 9, 17, 7, 23, 11)
        lower = G.QPainterPath(C.QPointF(25, 16))
        lower.cubicTo(25, 23, 15, 25, 9, 21)
        painter.drawPath(upper)
        painter.drawPath(lower)
        painter.setPen(C.Qt.PenStyle.NoPen)
        painter.setBrush(G.QColor('#39362f'))
        painter.drawPolygon(G.QPolygonF([C.QPointF(24, 7), C.QPointF(24, 15), C.QPointF(17, 13)]))
        painter.drawPolygon(G.QPolygonF([C.QPointF(8, 25), C.QPointF(8, 17), C.QPointF(15, 19)]))
        painter.restore()

    @staticmethod
    def expand_rect(rect):
        return C.QRect(rect.right()-32, rect.top(), 28, rect.height())

    def toggle_stack(self, entry):
        key = next((k for e, _, k in self.items if e.entry_id == entry.entry_id), None)
        if key is not None:
            self.expanded_stacks.symmetric_difference_update({key})
            self.collapsed.discard(key)
            self.relayout()

    def flip_entry(self, entry):
        count = self.face_count(entry)
        key = entry.entry_id
        if count <= 1 or key in self.flip_animations:
            return
        target = (self.faces.get(key, 0)+1) % count
        options, asset = self.face_image_options(entry, target)
        self.thumbnails.get(entry.card_id, asset, **options)
        animation = C.QVariantAnimation(self)
        animation.setDuration(420)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(C.QEasingCurve.Type.InOutSine)
        self.flip_animations[key] = dict(animation=animation, progress=0.0, target=target,
                                         document=self.document, deck_id=self.document.deck.deck_id, entry=entry)
        animation.valueChanged.connect(lambda value: self.animate_flip_frame(key, value))
        animation.finished.connect(lambda: self.finish_flip(key))
        self.hover_timer.stop()
        self.preview.hide()
        animation.start()

    def animate_flip_frame(self, key, progress):
        self.prune_flips()
        state = self.flip_animations.get(key)
        if state is None:
            return
        state['progress'] = float(progress)
        if progress >= 0.5:
            self.faces[key] = state['target']
        self.viewport().update()

    def finish_flip(self, key):
        state = self.flip_animations.pop(key, None)
        if state:
            self.faces[key] = state['target']
            state['animation'].stop()
            state['animation'].deleteLater()
        self.viewport().update()

    def prune_flips(self):
        if not self.flip_animations:
            return
        entries = {e.entry_id: e for e in self.document.deck.entries}
        for key, state in list(self.flip_animations.items()):
            if (state['document'] is not self.document or state['deck_id'] != self.document.deck.deck_id
                    or entries.get(key) is not state['entry']):
                self.flip_animations.pop(key)
                state['animation'].stop()
                state['animation'].deleteLater()
                self.faces.pop(key, None)

    @staticmethod
    def paint_flip(painter, rect, pixmap, selected, hovered, progress):
        # Turn toward edge-on, exchange faces, then turn the new face forward.
        angle = 180 * progress if progress < 0.5 else -180 * (1-progress)
        if abs(abs(angle)-90) < 0.2:
            angle = 89.8 if angle > 0 else -89.8
        painter.save()
        transform = G.QTransform()
        transform.translate(rect.center().x(), rect.center().y())
        transform.rotate(angle, C.Qt.Axis.YAxis)
        painter.setWorldTransform(transform, True)
        local = C.QRect(-(rect.width()//2), -(rect.height()//2), rect.width(), rect.height())
        rounded_card(painter, local, pixmap, selected, hovered)
        path = G.QPainterPath()
        path.addRoundedRect(C.QRectF(local), 9, 9)
        painter.setClipPath(path)
        shading = G.QLinearGradient(C.QPointF(local.topLeft()), C.QPointF(local.topRight()))
        strength = int(105 * math.sin(math.pi * progress))
        shading.setColorAt(0, G.QColor(0, 0, 0, strength))
        shading.setColorAt(1, G.QColor(255, 255, 255, strength//3))
        painter.fillRect(local, shading)
        painter.restore()

    def control_rect(self, rect):
        return quantity_control_rect(rect)

    def hideEvent(self, event):
        for key in list(self.flip_animations):
            self.finish_flip(key)
        self.context_resume_timer.stop()
        self.context_target = None
        self.hover_timer.stop()
        self.detail_timer.stop()
        self.preview.hide()
        self.thumbnails.set_visible(id(self), [])
        super().hideEvent(event)

    def quantity_buttons(self, rect):
        control = self.control_rect(rect)
        half = control.height() // 2
        return [(1, C.QRect(control.x(), control.y(), control.width(), half)),
                (-1, C.QRect(control.x(), control.y()+half, control.width(), control.height()-half))]

    def activate_quantity(self, item, position):
        if item is None:
            return False
        entry, rect, _ = item
        point = position + C.QPoint(0, self.verticalScrollBar().value())
        if self.face_count(entry) > 1 and self.flip_rect(rect).contains(point):
            return True
        for delta, button in self.quantity_buttons(rect):
            if button.contains(point):
                self.press_position = None
                self.detail_entry = None
                if self.search_mode and delta < 0 and entry.quantity <= 0:
                    return True
                self.quantityRequested.emit(entry.entry_id, delta)
                return True
        return False

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
            point = event.position().toPoint() + C.QPoint(0, self.verticalScrollBar().value())
            if self.mode == 'Stacks' and self.expand_rect(header[3]).contains(point):
                self.expanded_stacks.symmetric_difference_update({key})
                self.collapsed.discard(key)
                self.relayout()
                return
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
        if self.face_count(entry) > 1 and self.flip_rect(rect).contains(point):
            self.press_position = None
            self.flip_entry(entry)
            return
        if self.activate_quantity(item, event.position().toPoint()):
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
        if self.context_target is not None:
            return
        item = self.hit(event.position().toPoint())
        hovered = item[0].entry_id if item else None
        if hovered != self.hovered:
            self.hovered = hovered
            facts = self.shown_facts(item[0]) if item else {}
            self.setToolTip('\n'.join(str(facts.get(k) or '') for k in ('name', 'mana_cost', 'type_line', 'oracle_text')) + ('\nF: flip card; D: discover similar cards; E: expand stack' if item else ''))
            self.preview.hide()
            if self.mode == 'Stacks' and not self.search_mode:
                self.hover_timer.stop()
                self.animate_stack()
            else:
                self.hover_timer.start()
                self.viewport().update()
        if (event.buttons() & C.Qt.MouseButton.LeftButton and self.press_position is not None
                and (event.position().toPoint()-self.press_position).manhattanLength() >= W.QApplication.startDragDistance()):
            self.press_position = None
            self.detail_entry = None
            self.hover_timer.stop()
            drag = G.QDrag(self)
            mime = C.QMimeData()
            mime.setData('application/x-manaforge-entries', json.dumps(sorted(self.selected)).encode())
            drag.setMimeData(mime)
            if item:
                pix = self.card_image(item[0])
                if pix and not pix.isNull():
                    drag.setPixmap(drag_ghost(pix))
            actions = C.Qt.DropAction.CopyAction if self.search_mode else C.Qt.DropAction.MoveAction | C.Qt.DropAction.CopyAction
            drag.exec(actions)
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
        if self.activate_quantity(item, event.position().toPoint()):
            return
        if item:
            if self.search_mode:
                self.quantityRequested.emit(item[0].entry_id, 1)
            else:
                self.artworkRequested.emit(item[0].entry_id)

    def leaveEvent(self, event):
        self.hover_timer.stop()
        self.preview.hide()
        if self.context_target is not None:
            return
        self.hovered = None
        if self.mode == 'Stacks' and not self.search_mode:
            self.animate_stack()
        else:
            self.viewport().update()

    def show_preview(self):
        if self.mode == 'Stacks' and not self.search_mode:
            return
        if not self.isVisible() or W.QApplication.activePopupWidget() is not None:
            return
        entry = next((e for e in self.document.deck.entries if e.entry_id == self.hovered), None)
        if entry is None or W.QApplication.mouseButtons() != C.Qt.MouseButton.NoButton:
            return
        pixmap = self.card_image(entry)
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
        if event.key() == C.Qt.Key.Key_Escape and self.preview.isVisible():
            self.hover_timer.stop()
            self.preview.hide()
            event.accept()
        elif event.key() == C.Qt.Key.Key_T and not event.modifiers() and self.selected and not self.search_mode:
            if not event.isAutoRepeat():
                self.quickTagRequested.emit(G.QCursor.pos())
        elif event.key() in (C.Qt.Key.Key_F, C.Qt.Key.Key_D, C.Qt.Key.Key_E) and not event.modifiers() and self.selected:
            entry = next((e for e, _, _ in self.items if e.entry_id in self.selected), None)
            if entry and event.key() == C.Qt.Key.Key_F:
                self.flip_entry(entry)
            elif entry and event.key() == C.Qt.Key.Key_D:
                self.discoverRequested.emit(entry)
            elif entry and self.mode == 'Stacks':
                key = next(k for e, _, k in self.items if e.entry_id == entry.entry_id)
                self.expanded_stacks.symmetric_difference_update({key})
                self.relayout()
        elif event.matches(G.QKeySequence.StandardKey.SelectAll):
            self.selected = {e.entry_id for e, _, _ in self.items}
            self.selectionChanged.emit()
            self.viewport().update()
        elif (event.key() in (C.Qt.Key.Key_Delete, C.Qt.Key.Key_Backspace)
              and not event.modifiers() and self.selected and not self.search_mode):
            self.quantityRequested.emit('', 0)
        else:
            super().keyPressEvent(event)

    def discovery_source(self, event):
        source = event.source()
        return self.search_mode and isinstance(source, CardCanvas) and event.mimeData().hasFormat('application/x-manaforge-entries')

    def dragEnterEvent(self, event):
        if self.discovery_source(event):
            event.setDropAction(C.Qt.DropAction.CopyAction)
            event.accept()
            self.discovery_drop = True
            self.viewport().update()
        elif event.source() is self:
            event.acceptProposedAction()

    def destination(self, point):
        header = self.header_at(point)
        item = self.hit(point)
        key = header[0] if header else item[2] if item else None
        return key, item[0].entry_id if item else None

    def dragMoveEvent(self, event):
        if self.discovery_source(event):
            event.setDropAction(C.Qt.DropAction.CopyAction)
            event.accept()
            return
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
        self.discovery_drop = False
        self.auto_scroll.stop()
        self.drop_target = None
        self.viewport().update()

    def dropEvent(self, event):
        self.discovery_drop = False
        self.auto_scroll.stop()
        if self.discovery_source(event):
            source = event.source()
            entry = next((e for e in source.document.deck.entries if e.entry_id == source.anchor), None)
            if entry:
                event.setDropAction(C.Qt.DropAction.CopyAction)
                event.accept()
                self.discoverRequested.emit(entry)
            self.viewport().update()
            return
        if self.drop_target and self.drop_target[1] and event.source() is self:
            key, before = self.destination(event.position().toPoint())
            self.moveRequested.emit(set(self.selected), key, before if self.sort == 'Import Order' else None)
            event.acceptProposedAction()
        self.drop_target = None
        self.viewport().update()
