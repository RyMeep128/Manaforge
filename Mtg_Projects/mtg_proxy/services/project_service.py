"""Compatibility alias for mtg_print.services.project_service."""
import sys
from mtg_print.services import project_service as _shared

sys.modules[__name__] = _shared
