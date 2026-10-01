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
        normalized = ArtworkPreferenceRules.from_dict(
            rules.to_dict() if isinstance(rules, ArtworkPreferenceRules) else rules)
        self.database.set_artwork_preference_profile(normalized.to_dict())
        return normalized

    def choose_preferred_print(self, oracle_id: str, *,
                               explicit_card_id: str | None = None) -> dict | None:
        return choose_print(
            self.get_prints(oracle_id), explicit_card_id=explicit_card_id,
            favorite_card_id=self.get_artwork_favorite(oracle_id),
            rules=self.get_artwork_preferences())

    def iter_preferred_prints(self, oracle_ids):
        """Resolve recommendations in small batches, preserving input order.

        Read preferences once per request; stop loading batches as soon as the
        caller has enough cards. Favorites and print selection use the same rules
        as individual artwork requests.
        """
        identities = list(oracle_ids)
        rules = self.get_artwork_preferences()
        for offset in range(0, len(identities), 100):
            batch = identities[offset:offset + 100]
            prints, favorites = self.database.artwork_candidates(batch)
            for oracle_id in batch:
                yield choose_print(prints.get(oracle_id, []),
                                   favorite_card_id=favorites.get(oracle_id), rules=rules)
