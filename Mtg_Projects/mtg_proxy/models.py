"""Compatibility alias for the shared printing models module."""
import sys
from mtg_print import models as _shared

sys.modules[__name__] = _shared
