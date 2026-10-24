"""Suppress hover tooltips across application windows and dynamically built menus."""
from PyQt6 import QtCore, QtWidgets


class _TooltipFilter(QtCore.QObject):
    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Type.ToolTip:
            return True
        return False


def disable_hover_tooltips():
    app = QtWidgets.QApplication.instance()
    if app is not None and not hasattr(app, '_hover_tooltip_filter'):
        app._hover_tooltip_filter = _TooltipFilter(app)
        app.installEventFilter(app._hover_tooltip_filter)
        QtWidgets.QToolTip.hideText()
