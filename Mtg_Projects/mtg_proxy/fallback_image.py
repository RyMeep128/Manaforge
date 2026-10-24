"""Compatibility alias for the shared printing fallback_image module."""
import sys
from mtg_print import fallback_image as _shared

sys.modules[__name__] = _shared
