"""Compatibility import for the shared application-release service."""
import sys
from mtg_print import update_service

sys.modules[__name__] = update_service
