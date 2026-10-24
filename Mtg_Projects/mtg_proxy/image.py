"""Compatibility alias for mtg_print.image."""
import sys
from mtg_print import image as _shared

sys.modules[__name__] = _shared
