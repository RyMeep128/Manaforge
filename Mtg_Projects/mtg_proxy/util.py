"""Compatibility alias for mtg_print.util."""
import sys
from mtg_print import util as _shared

sys.modules[__name__] = _shared
