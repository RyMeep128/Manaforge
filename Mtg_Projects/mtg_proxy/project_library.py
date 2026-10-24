"""Compatibility alias for the shared printing library module."""
import sys
from mtg_print import library as _shared

sys.modules[__name__] = _shared
