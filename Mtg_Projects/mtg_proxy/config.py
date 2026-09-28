"""Compatibility alias for the shared printing config module."""
import sys
from mtg_print import config as _shared

sys.modules[__name__] = _shared
