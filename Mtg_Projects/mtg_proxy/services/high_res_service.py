"""Compatibility alias for mtg_print.services.high_res_service."""
import sys
from mtg_print.services import high_res_service as _shared

sys.modules[__name__] = _shared
