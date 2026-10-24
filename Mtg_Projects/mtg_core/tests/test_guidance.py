from copy import deepcopy

from mtg_core.decks import DeckCategory, DeckDocument, DeckEntry, DeckHistory
from mtg_core.guidance import GuidanceSettings, guidance


def test_guidance_respects_manual_roles_counts_unions_and_scope():
    doc = DeckDocument()
    doc.deck.categories = [DeckCategory("ramp", "Ramp")]
    doc.deck.entries = [
        DeckEntry("manual", "Manual", quantity=2, category_ids=["ramp"]),
        DeckEntry("empty", "No role", extras={"auto_categories": {"manual": True}}),
        DeckEntry("both", "Multiple interaction roles", quantity=3, do_not_print=True),
        DeckEntry("side", "Side", quantity=20, section="sideboard"),
    ]
    proposals = {
        key: [
            dict(name="Removal", reason="Local Oracle Tags: removal"),
            dict(name="Counterspells", reason="Local Oracle Tags: counterspell"),
        ]
        for key in ("manual", "empty", "both", "side")
    }
    before = deepcopy(doc.to_dict())
    result = guidance(doc, proposals)
    assert result["counts"]["ramp"] == 2
    assert result["counts"]["interaction"] == 3
    assert result["total"] == 6
    assert doc.to_dict() == before


def test_theme_requires_distinct_cards_and_dismissals_are_reversible():
    doc = DeckDocument()
    doc.deck.entries = [
        DeckEntry("a", "Same", quantity=20, oracle_id="same"),
        DeckEntry("b", "Same", oracle_id="same"),
    ]
    proposals = {
        e.entry_id: [dict(name="Tokens", reason="Local Oracle Tags: token-generator")]
        for e in doc.deck.entries
    }
    settings = GuidanceSettings(theme_minimum=2)
    assert not any(
        s["id"].startswith("theme:")
        for s in guidance(doc, proposals, settings)["suggestions"]
    )
    doc.deck.entries[1].oracle_id = "different"
    assert any(
        s["id"] == "theme:Tokens"
        for s in guidance(doc, proposals, settings)["suggestions"]
    )
    settings.dismissed = ["theme:Tokens", "shortage:lands"]
    history = DeckHistory(doc)
    history.execute(lambda d: d.editor_preferences.update(guidance=settings.to_dict()))
    restored = DeckDocument.from_dict(doc.to_dict())
    assert not any(
        s["id"] in settings.dismissed
        for s in guidance(restored, proposals)["suggestions"]
    )
    assert history.undo() and "guidance" not in doc.editor_preferences
    assert history.redo() and doc.editor_preferences["guidance"]["dismissed"]


def test_land_type_is_counted_despite_empty_manual_roles():
    doc = DeckDocument()
    doc.deck.entries = [
        DeckEntry(
            "land",
            "Land",
            quantity=4,
            extras={
                "auto_categories": {"manual": True},
                "facts": {"type_line": "Basic Land — Forest"},
            },
        )
    ]
    result = guidance(doc, {})
    assert result["counts"]["lands"] == 4
    settings = GuidanceSettings(targets=dict(lands=0, ramp=0, draw=0, interaction=0))
    assert guidance(doc, {}, settings)["suggestions"] == []
