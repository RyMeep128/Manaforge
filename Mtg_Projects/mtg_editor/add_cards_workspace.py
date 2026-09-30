"""Persistent full-width host for the same Search and Recommendations widgets.

Moving the tab widget between hosts deliberately preserves its controller,
cache, result objects and selection. There is still only one active session.
"""

from PyQt6 import QtCore as C, QtWidgets as W

from .commander_discovery import CommanderDiscovery


class AddCardsWorkspace(W.QWidget):
    def __init__(self, editor, controls):
        super().__init__(editor)
        self.editor, self.controls = editor, controls
        self.expanded = False
        self.quick_index = self.full_index = 0
        self.quick_visible = False
        self.quick_scroll = [0, 0]
        self.full_scroll = [0, 0]
        self.discovery = CommanderDiscovery(editor)
        self.discovery.hide()
        self.content_layout = W.QVBoxLayout(self)
        navigation = W.QHBoxLayout()
        back = W.QPushButton("Back to Deck")
        back.clicked.connect(self.back)
        navigation.addWidget(back)
        title = W.QLabel("Add Cards")
        title.setProperty("role", "title")
        navigation.addWidget(title)
        self.undo_button = W.QPushButton("Undo")
        self.undo_button.clicked.connect(editor.undo)
        navigation.addWidget(self.undo_button)
        self.redo_button = W.QPushButton("Redo")
        self.redo_button.clicked.connect(editor.redo)
        navigation.addWidget(self.redo_button)
        navigation.addStretch()
        navigation.addWidget(W.QLabel("Card size"))
        self.zoom = W.QSlider(C.Qt.Orientation.Horizontal)
        self.zoom.setRange(150, 260)
        self.zoom.setValue(190)
        self.zoom.setMaximumWidth(180)
        self.zoom.valueChanged.connect(self.resize_cards)
        navigation.addWidget(self.zoom)
        self.content_layout.addLayout(navigation)

    def open(self):
        if self.expanded:
            return
        editor = self.editor
        tabs = editor.add_card_tabs
        self.quick_index = tabs.currentIndex()
        self.quick_visible = not editor.search_panel.isHidden()
        self.quick_scroll = self.scroll_positions()
        self.expanded = True
        with C.QSignalBlocker(tabs):
            self.content_layout.addWidget(tabs, 1)
            tabs.setTabText(0, "Search")
            tabs.addTab(self.discovery, "Commanders")
            tabs.setCurrentIndex(self.full_index)
        editor.search_panel.hide()
        self.controls.hide()
        editor.recommendation_panel.set_expanded(True)
        editor.query.setMinimumHeight(38)
        editor.workspace_stack.setCurrentWidget(self)
        tabs.show()
        self.resize_cards()
        editor.add_card_tab_changed(tabs.currentIndex())
        C.QTimer.singleShot(0, lambda: self.restore_scroll(True))

    def back(self):
        if not self.expanded:
            return
        editor = self.editor
        tabs = editor.add_card_tabs
        self.full_index = tabs.currentIndex()
        self.full_scroll = self.scroll_positions()
        self.expanded = False
        with C.QSignalBlocker(tabs):
            tabs.removeTab(tabs.indexOf(self.discovery))
            self.discovery.hide()
            editor.search_panel.layout().addWidget(tabs, 1)
            tabs.setTabText(0, "Syntax Search")
            tabs.setCurrentIndex(self.quick_index)
        editor.recommendation_panel.set_expanded(False)
        editor.results.card_width = 130
        editor.recommendation_panel.canvas.card_width = 150
        editor.query.setMinimumHeight(0)
        editor.workspace_stack.setCurrentWidget(editor.splitter)
        self.controls.show()
        editor.search_panel.setVisible(self.quick_visible)
        tabs.show()
        editor.results.refresh()
        editor.recommendation_panel.canvas.refresh()
        if self.quick_visible:
            editor.add_card_tab_changed(tabs.currentIndex())
        else:
            editor.cancel_search()
        C.QTimer.singleShot(0, lambda: self.restore_scroll(False))

    def scroll_positions(self):
        return [canvas.verticalScrollBar().value()
                for canvas in (self.editor.results, self.editor.recommendation_panel.canvas)]

    def restore_scroll(self, expanded):
        if expanded != self.expanded:
            return
        positions = self.full_scroll if expanded else self.quick_scroll
        for canvas, position in zip((self.editor.results, self.editor.recommendation_panel.canvas), positions):
            canvas.verticalScrollBar().setValue(position)

    def resize_cards(self, *_):
        if not self.expanded:
            return
        for canvas in (self.editor.results, self.editor.recommendation_panel.canvas, self.discovery.canvas):
            canvas.card_width = self.zoom.value()
            canvas.refresh()
