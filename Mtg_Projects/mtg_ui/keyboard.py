"""Shared, compact reference for the existing workspace bindings."""
from PyQt6 import QtWidgets as W


SHORTCUTS = '''Deck Editor
Ctrl+N / Ctrl+O / Ctrl+S — New / Open / Save deck
Ctrl+Z — Undo; Ctrl+Y or Ctrl+Shift+Z — Redo
Ctrl+F — Deck filter; Ctrl+K — Quick Add
Ctrl+A — Select visible cards when a card view has focus
Delete / Backspace — Remove selected deck cards when a card view has focus
T — Quick tagging when selected deck cards have focus

Search and discovery
Enter — Submit search or activate a focused button
Tab / Shift+Tab — Move between controls
Arrow keys — Navigate native lists, menus, and autocomplete suggestions
Esc — Dismiss the current popup or preview first; otherwise return from
Add Cards, Recommendations, or Discover Deck Ideas to the deck, or close Quick Add

Print Studio
Ctrl+N / Ctrl+O — New / Open project
Ctrl+S — Save project; Ctrl+F — Focus card search
Ctrl+A — Select cards when the card grid has focus
Ctrl+Z / Ctrl+Y — Undo / Redo print layout
Esc — Close printing settings

Across Manaforge
Ctrl+Shift+H — Home (in the unified app)
Esc — Cancel native dialogs and menus; ordinary deck and Home views stay open
Text fields retain their native editing and selection shortcuts.'''


def help_workspace(parent=None):
    from .feedback import FeedbackDialog, pending_reports

    page = W.QWidget(parent)
    page.setWindowTitle('Help')
    layout = W.QVBoxLayout(page)
    title = W.QLabel('Help')
    title.setProperty('role', 'title')
    layout.addWidget(title)
    actions = W.QHBoxLayout()
    send = W.QPushButton('Send Feedback')
    send.clicked.connect(lambda: FeedbackDialog(page).exec())
    actions.addWidget(send)
    pending = W.QPushButton('Pending Feedback')
    pending.clicked.connect(lambda: pending_reports(page))
    actions.addWidget(pending)
    from .whats_new import whats_new
    highlights = W.QPushButton('What’s New')
    highlights.clicked.connect(lambda: whats_new().show(page))
    actions.addWidget(highlights)
    actions.addStretch()
    layout.addLayout(actions)
    shortcuts = W.QTextBrowser()
    shortcuts.setPlainText(SHORTCUTS)
    layout.addWidget(shortcuts, 1)
    return page


def add_shortcuts_help(window):
    from .feedback import FeedbackDialog, pending_reports
    menu = window.menuBar().addMenu('Help')
    from .whats_new import whats_new
    menu.addAction('What’s New', lambda: whats_new().show(window))
    menu.addAction('Send Feedback', lambda: FeedbackDialog(window).exec())
    menu.addAction('Pending Feedback', lambda: pending_reports(window))
    menu.addAction('Keyboard Shortcuts', lambda: W.QMessageBox.information(
        window, 'Keyboard Shortcuts', SHORTCUTS))
