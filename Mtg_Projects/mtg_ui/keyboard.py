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


def add_shortcuts_help(window):
    menu = window.menuBar().addMenu('Help')
    menu.addAction('Keyboard Shortcuts', lambda: W.QMessageBox.information(
        window, 'Keyboard Shortcuts', SHORTCUTS))
