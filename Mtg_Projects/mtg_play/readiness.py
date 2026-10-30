"""Local deck checks, kept separate from authoritative XMage validation."""

from dataclasses import dataclass
from typing import Literal

from mtg_core.commander import check_commander
from .decks import deck_document_issues


@dataclass(frozen=True)
class DeckReadiness:
    format: str
    state: Literal["available", "review", "blocked"]
    messages: tuple[str, ...]
    codes: tuple[str, ...] = ()

    @property
    def can_start(self):
        return self.state != "blocked"

    @property
    def summary(self):
        return {
            "available": "Local checks complete. Engine validation happens at start.",
            "review": "Review needed. Some local checks could not be verified.",
            "blocked": "Not eligible for this format. Review in Deck Editor.",
        }[self.state]


STRUCTURAL_MESSAGES = {
    "INVALID_QUANTITY": "Card quantities must be nonnegative whole numbers.",
    "DUPLICATE_ENTRY_ID": "The saved deck has duplicate entry identities.",
    "UNSUPPORTED_SECTION": "The deck contains a section unsupported by Play.",
    "COMMANDER_FORMAT_REQUIRED": "This deck has commanders selected. Choose Commander format.",
    "MISSING_COMMANDER_ENTRY": "A selected commander is missing from the deck.",
    "MISSING_CARD_NAME": "A card is missing its name and Oracle identity.",
    "EMPTY_MAINBOARD": "The deck has no playable mainboard cards.",
}

COMMANDER_MESSAGES = {
    "size": "The main deck plus commanders must contain 100 cards.",
    "commanders": "Choose a commander or a supported commander pair.",
    "commander_quantity": "Each commander must have quantity one.",
    "eligibility": "Commander eligibility needs review.",
    "pairing": "The selected commander pairing needs review.",
    "commander_identity": "Commander color identity is incomplete or needs a saved color choice.",
    "identity": "Card color identity needs review against the commanders.",
    "land_types": "Basic land types are outside the commanders' color identity.",
    "legality": "Card legality needs review in the local Commander data.",
    "singleton": "Card copy limits need review for Commander.",
    "quantity": "A card quantity is invalid for Commander.",
    "stale": "Some local card data is older than the Core checker's freshness limit.",
    "undated": "Some local card data has no reliable cache date.",
    "companion_selection": "The saved companion selection needs review.",
    "companion_ability": "The companion ability could not be verified.",
    "companion_restriction": "Companion deck restrictions need review.",
}


def local_readiness(document, format, records=None):
    if format not in {"freeform", "commander"}:
        return DeckReadiness(
            format,
            "blocked",
            ("Choose a supported offline format.",),
            ("UNSUPPORTED_GAME_SETUP",),
        )
    try:
        structural = deck_document_issues(document, commander=format == "commander")
    except (TypeError, ValueError, AttributeError):
        return DeckReadiness(
            format,
            "blocked",
            ("Saved deck details need review in Deck Editor.",),
            ("INVALID_DECK_DOCUMENT",),
        )
    if structural:
        codes = tuple(dict.fromkeys(issue.code for issue in structural))
        return DeckReadiness(
            format,
            "blocked",
            tuple(
                (
                    "Unsupported deck sections: "
                    + ", ".join(
                        sorted(
                            {
                                str(entry.section)
                                for entry in document.deck.entries
                                if entry.section
                                not in {
                                    "mainboard",
                                    "sideboard",
                                    "commander",
                                    "considering",
                                    "excluded",
                                    "display_commander",
                                }
                            }
                        )
                    )
                    + ". Review this deck in Deck Editor."
                    if code == "UNSUPPORTED_SECTION"
                    else STRUCTURAL_MESSAGES.get(
                        code, "Review the deck configuration in Deck Editor."
                    )
                )
                for code in codes
            )[:6],
            codes,
        )
    if format == "freeform":
        # Freeform is not Standard/Modern/etc.; do not impose constructed rules.
        return DeckReadiness(format, "available", ())
    try:
        report = check_commander(document, records or {})
    except (TypeError, ValueError, KeyError, AttributeError):
        return DeckReadiness(
            format,
            "review",
            (
                "Local card details could not be checked. Engine validation is still required.",
            ),
            ("LOCAL_CARD_DATA_UNAVAILABLE",),
        )
    state = (
        "blocked"
        if any(issue.severity == "Error" for issue in report.issues)
        else (
            "review"
            if any(issue.severity == "Unknown" for issue in report.issues)
            else "available"
        )
    )
    ordered = sorted(report.issues, key=lambda issue: issue.severity != "Error")
    codes = tuple(dict.fromkeys(issue.code for issue in ordered))
    # Show useful categories, not opponents' private card names or entry IDs.
    messages = tuple(
        dict.fromkeys(
            COMMANDER_MESSAGES.get(code, "Review the Commander deck configuration.")
            for code in codes
        )
    )[:6]
    return DeckReadiness(format, state, messages, codes)
