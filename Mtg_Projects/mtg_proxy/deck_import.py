"""Compatibility alias for mtg_print.deck_import."""
import sys
from mtg_print import deck_import as _shared

sys.modules[__name__] = _shared
