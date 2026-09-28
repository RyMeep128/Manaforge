"""Compatibility alias for mtg_print.high_res."""
import sys
from mtg_print import high_res as _shared

sys.modules[__name__] = _shared
