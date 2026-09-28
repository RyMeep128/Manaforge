"""Internal artwork operations for CardService."""
from __future__ import annotations

from mtg_core.preferences import ArtworkPreferenceRules, choose_print


class ArtworkOperations:
    """Operation group sharing the facade dependencies; not instantiated alone."""

    def get_artwork_favorite(self, oracle_id: str) -> str | None:
        return self.database.get_artwork_favorite(oracle_id)

    def set_artwork_favorite(self, oracle_id: str,
                             card_id: str | None) -> None:
        self.database.set_artwork_favorite(oracle_id, card_id)

    def get_artwork_preferences(self) -> ArtworkPreferenceRules:
        return ArtworkPreferenceRules.from_dict(
            self.database.get_artwork_preference_profile())

    def set_artwork_preferences(self, rules) -> ArtworkPreferenceRules:
        normalized = (rules if isinstance(rules, ArtworkPreferenceRules)
                      else ArtworkPreferenceRules.from_dict(rules))
        self.database.set_artwork_preference_profile(normalized.to_dict())
        return normalized

    def choose_preferred_print(self, oracle_id: str, *,
                               explicit_card_id: str | None = None) -> dict | None:
        return choose_print(
            self.get_prints(oracle_id), explicit_card_id=explicit_card_id,
            favorite_card_id=self.get_artwork_favorite(oracle_id),
            rules=self.get_artwork_preferences())
