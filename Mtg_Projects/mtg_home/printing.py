"""Isolate legacy printer imports while hosting its existing UI in Manaforge."""
from pathlib import Path
import sys
from PyQt6 import QtWidgets as W


def create_print_workspace(parent):
    # Legacy printer modules still use sibling imports. Keep that bridge here.
    proxy = Path(__file__).resolve().parents[1] / 'mtg_proxy'
    if str(proxy) not in sys.path:
        sys.path.insert(0, str(proxy))
    import image
    from main_window import AppShellWindow, PrintApplicationContext
    app = W.QApplication.instance()
    context = PrintApplicationContext(parent)
    try:
        image.init()
        app._manaforge_print_context = context
        workspace = AppShellWindow(context, embedded=True)
        context.set_window(workspace)
        workspace._manaforge_context = context
        return workspace
    except Exception:
        if getattr(app, '_manaforge_print_context', None) is context:
            del app._manaforge_print_context
        context.deleteLater()
        raise
