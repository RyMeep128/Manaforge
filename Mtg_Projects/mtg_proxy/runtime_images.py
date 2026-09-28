"""Compatibility alias for mtg_print.runtime_images."""
import sys
from mtg_print import runtime_images as _shared

sys.modules[__name__] = _shared
