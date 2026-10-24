"""Compatibility alias for mtg_ui.print_tasks."""
import sys
from mtg_ui import print_tasks as _shared

sys.modules[__name__] = _shared
