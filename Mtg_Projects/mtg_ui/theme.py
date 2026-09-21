"""Shared visual tokens and application-wide Qt styling."""

COLORS = {
    "canvas": "#101318",
    "surface": "#171b22",
    "surface_raised": "#1d222b",
    "surface_hover": "#242b36",
    "surface_selected": "#20352f",
    "border": "#303743",
    "border_strong": "#414b5a",
    "text": "#f2f4f7",
    "text_secondary": "#b5bdc9",
    "text_muted": "#7f8998",
    "accent": "#2f9e72",
    "accent_hover": "#38b985",
    "danger": "#d45b63",
    "warning": "#d5a44a",
}


def application_stylesheet() -> str:
    c = COLORS
    return f"""
    QWidget {{
        color: {c['text']};
        background-color: {c['canvas']};
        font-size: 10pt;
    }}
    QMainWindow, QDialog {{ background-color: {c['canvas']}; }}
    QLabel {{ background: transparent; }}
    QLabel[role="title"] {{ font-size: 18pt; font-weight: 650; }}
    QLabel[role="subtitle"] {{ color: {c['text_secondary']}; }}
    QLabel[role="muted"] {{ color: {c['text_muted']}; }}
    QLabel[role="success"] {{ color: #72d6ad; }}
    QLabel[role="warning"] {{ color: #efc36d; }}
    QFrame[role="toolbar"], QWidget[role="toolbar"] {{
        background-color: {c['surface']};
        border-bottom: 1px solid {c['border']};
    }}
    QFrame[role="panel"], QWidget[role="panel"], QGroupBox {{
        background-color: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 8px;
    }}
    QGroupBox {{ margin-top: 12px; padding: 14px 10px 10px; font-weight: 600; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 5px; }}
    QPushButton, QToolButton {{
        min-height: 32px;
        padding: 0 12px;
        border: 1px solid {c['border_strong']};
        border-radius: 6px;
        background-color: {c['surface_raised']};
        color: {c['text']};
        font-weight: 550;
    }}
    QPushButton:hover, QToolButton:hover {{ background-color: {c['surface_hover']}; border-color: #596576; }}
    QPushButton:pressed, QToolButton:pressed {{ background-color: #12161c; }}
    QPushButton:disabled, QToolButton:disabled {{ color: #626b78; border-color: #29303a; background: #151920; }}
    QPushButton[buttonRole="primary"], QToolButton[buttonRole="primary"] {{
        background-color: {c['accent']}; border-color: {c['accent']}; color: white;
    }}
    QPushButton[buttonRole="primary"]:hover, QToolButton[buttonRole="primary"]:hover {{
        background-color: {c['accent_hover']}; border-color: {c['accent_hover']};
    }}
    QPushButton[buttonRole="danger"] {{ color: #ffb8bd; border-color: #6f3b42; }}
    QPushButton[buttonRole="ghost"], QToolButton[buttonRole="ghost"] {{ background: transparent; border-color: transparent; }}
    QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        min-height: 32px;
        padding: 0 9px;
        background-color: #12161c;
        border: 1px solid {c['border']};
        border-radius: 6px;
        selection-background-color: {c['accent']};
    }}
    QTextEdit {{ padding: 9px; }}
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {c['accent']}; }}
    QComboBox::drop-down {{ border: 0; width: 24px; }}
    QComboBox QAbstractItemView, QMenu {{
        background: {c['surface_raised']}; border: 1px solid {c['border_strong']}; padding: 5px;
        selection-background-color: {c['surface_selected']};
    }}
    QMenu::item {{ padding: 7px 24px 7px 10px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {c['surface_hover']}; }}
    QTabWidget::pane {{ border: 0; background: {c['canvas']}; }}
    QTabBar {{ background: {c['surface']}; }}
    QTabBar::tab {{
        min-width: 84px; padding: 11px 16px; color: {c['text_secondary']};
        background: transparent; border: 0; border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:hover {{ color: {c['text']}; }}
    QTabBar::tab:selected {{ color: {c['text']}; border-bottom-color: {c['accent']}; }}
    QScrollArea, QListWidget {{ background: {c['canvas']}; border: 0; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: #3a424e; border-radius: 4px; min-height: 36px; }}
    QScrollBar::handle:vertical:hover {{ background: #505b6a; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QToolTip {{ background: #272d37; color: {c['text']}; border: 1px solid {c['border_strong']}; padding: 5px; }}
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{ width: 17px; height: 17px; }}
    QCheckBox::indicator:unchecked {{ border: 1px solid #596576; border-radius: 4px; background: #12161c; }}
    QCheckBox::indicator:checked {{ border: 1px solid {c['accent']}; border-radius: 4px; background: {c['accent']}; }}
    QSplitter::handle {{ background: {c['border']}; width: 1px; }}
    """


def set_role(widget, role: str):
    widget.setProperty("role", role)
    return widget


def set_button_role(widget, role: str):
    widget.setProperty("buttonRole", role)
    return widget
