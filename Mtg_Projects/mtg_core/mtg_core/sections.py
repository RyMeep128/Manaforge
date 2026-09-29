"""Stable deck-section values, independent of display labels.

Do not coerce loaded sections through this enum: unknown extension sections
must remain valid and round-trip unchanged.
"""

from enum import StrEnum


class DeckSection(StrEnum):
    MAINBOARD = "mainboard"
    COMMANDER = "commander"
    SIDEBOARD = "sideboard"
    CONSIDERING = "considering"
    EXCLUDED = "excluded"
