"""Compatibility alias for mtg_ui.print_dialogs."""
import sys
from mtg_ui import print_dialogs as _shared

sys.modules[__name__] = _shared
