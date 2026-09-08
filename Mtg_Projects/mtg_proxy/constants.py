import os
import sys

from reportlab.lib.pagesizes import LETTER, A5, A4, A3, LEGAL

APP_VERSION = "0.1.6-alpha.1"

if getattr(sys, "frozen", False):
    app_dir = os.path.dirname(os.path.abspath(sys.executable))
else:
    app_dir = os.path.dirname(os.path.abspath(__file__))

products_root = os.path.dirname(app_dir)
workspace_root = os.path.dirname(products_root)

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    resource_dir = sys._MEIPASS
else:
    resource_dir = app_dir


def _default_data_dir() -> str:
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA")
        if not root:
            root = os.path.join(os.path.expanduser("~"), "AppData", "Local")
        return os.path.join(root, "PrintProxyPrep")
    root = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(root, "PrintProxyPrep")


data_dir = os.path.abspath(os.environ.get("PRINT_PROXY_PREP_DATA_DIR") or _default_data_dir())
os.makedirs(data_dir, exist_ok=True)

# Backwards-compatible name used by older modules for mutable app data.
cwd = data_dir

page_sizes = {"Letter": LETTER, "A5": A5, "A4": A4, "A3": A3, "Legal": LEGAL}

card_size_with_bleed_inch = (2.72, 3.7)
card_size_without_bleed_inch = (2.48, 3.46)
card_ratio = card_size_without_bleed_inch[0] / card_size_without_bleed_inch[1]

low_dpi_warning_threshold = 300
