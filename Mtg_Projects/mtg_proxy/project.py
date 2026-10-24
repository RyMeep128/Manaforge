"""Compatibility alias for mtg_print.legacy_project."""
import sys
from mtg_print import legacy_project as _shared

sys.modules[__name__] = _shared
