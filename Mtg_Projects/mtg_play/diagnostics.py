"""Sanitized compatibility categories; preserve the original diagnostic code."""


def diagnostic_category(code):
    if code == "CARD_NOT_SUPPORTED":
        return "card_missing_from_pinned_engine"
    if code in {"PRINTING_NOT_RESOLVED", "ORACLE_ID_NOT_RESOLVED", "MISSING_CARD_NAME",
                "AMBIGUOUS_INSTANCE_PRINTING", "MISSING_RESOLUTION"}:
        return "identity_or_printing_resolution"
    if code in {"INVALID_QUANTITY", "DUPLICATE_ENTRY_ID", "UNSUPPORTED_SECTION",
                "COMMANDER_FORMAT_REQUIRED", "MISSING_COMMANDER_ENTRY", "EMPTY_MAINBOARD",
                "UNSUPPORTED_GAME_SETUP", "INVALID_SEATS", "INVALID_SEAT_IDENTITIES"}:
        return "unsupported_deck_configuration"
    if "DECISION_UNSUPPORTED" in code or code in {"UNSUPPORTED_DECISION", "UNSUPPORTED_PROMPT", "SCENARIO_TARGET_UNSUPPORTED"}:
        return "unsupported_game_decision"
    if code.startswith(("PINNED_METADATA_", "METADATA_")) or code in {
        "DUPLICATE_OBJECT_REFERENCES", "HIDDEN_IDENTITY_EXPOSED", "COPY_SOURCE_NOT_VISIBLE",
        "OPPONENT_HAND_EXPOSED", "OPPONENT_DECISION_EXPOSED"}:
        return "adapter_translation_failure"
    return "unexpected_engine_or_harness_behavior"
