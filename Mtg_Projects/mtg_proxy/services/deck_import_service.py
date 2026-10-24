"""Compatibility alias for mtg_print.services.deck_import_service."""
import sys
from mtg_print.services import deck_import_service as _shared

sys.modules[__name__] = _shared
