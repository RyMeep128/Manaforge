"""Application-facing global printing preferences; reads are never cached."""
from mtg_core.printing_preferences import PrintingPreferences


class PreferenceOperations:
    def get_printing_preferences(self) -> PrintingPreferences | None:
        return self.database.get_printing_preferences()

    def set_printing_preferences(self, preferences) -> PrintingPreferences:
        normalized = (preferences if isinstance(preferences, PrintingPreferences)
                      else PrintingPreferences.from_dict(preferences))
        self.database.set_printing_preferences(normalized)
        return normalized
