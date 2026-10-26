"""Card discovery drop target shared by search and recommendation panels."""
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from .canvas import CardCanvas


class CardSearchEdit(W.QLineEdit):
    """Keep text editing while opening discovery for cards dropped on searches."""

    def card_editor(self, event):
        if not (isinstance(event.source(), CardCanvas)
                and event.mimeData().hasFormat('application/x-manaforge-entries')):
            return None
        widget = event.source()
        while widget is not None:
            editor = getattr(widget, 'editor', widget)
            if callable(getattr(editor, 'discover_card', None)):
                return editor
            widget = widget.parentWidget()
        return None

    def dragEnterEvent(self, event):
        if self.card_editor(event) is not None:
            event.setDropAction(C.Qt.DropAction.CopyAction)
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self.card_editor(event) is not None:
            event.setDropAction(C.Qt.DropAction.CopyAction)
            event.accept()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        editor = self.card_editor(event)
        if editor is None:
            super().dropEvent(event)
            return
        source = event.source()
        entry = next((e for e in source.document.deck.entries if e.entry_id == source.anchor), None)
        if entry is not None:
            event.setDropAction(C.Qt.DropAction.CopyAction)
            event.accept()
            editor.discover_card(entry)


class CardDropPanel(W.QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.drop_editor = editor
        self.card_drag = False
        self.setAcceptDrops(True)

    def accepts_card(self, event):
        return isinstance(event.source(), CardCanvas) and event.mimeData().hasFormat('application/x-manaforge-entries')

    def dragEnterEvent(self, event):
        if self.accepts_card(event):
            self.card_drag = True
            event.setDropAction(C.Qt.DropAction.CopyAction)
            event.accept()
            self.update()

    def dragMoveEvent(self, event):
        if self.accepts_card(event):
            event.setDropAction(C.Qt.DropAction.CopyAction)
            event.accept()

    def dragLeaveEvent(self, event):
        self.card_drag = False
        self.update()

    def dropEvent(self, event):
        self.card_drag = False
        self.update()
        if self.accepts_card(event):
            source = event.source()
            entry = next((e for e in source.document.deck.entries if e.entry_id == source.anchor), None)
            if entry:
                event.setDropAction(C.Qt.DropAction.CopyAction)
                event.accept()
                self.drop_editor.discover_card(entry)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.card_drag:
            painter = G.QPainter(self)
            painter.setPen(G.QPen(G.QColor('#2f9e72'), 4))
            painter.drawRect(self.rect().adjusted(2, 2, -2, -2))
