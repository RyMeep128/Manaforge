"""Resolve printer boundaries without assuming a dedicated QApplication/window."""
from PyQt6.QtWidgets import QApplication


def print_application():
    app = QApplication.instance()
    return getattr(app, '_manaforge_print_context', app)


def print_workspace(widget):
    parent = widget
    while parent is not None:
        if parent.property('printWorkspace'):
            return parent
        parent = parent.parentWidget()
    return widget.window()
