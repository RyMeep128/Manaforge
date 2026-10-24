from copy import deepcopy

import pytest

from mtg_core.decks import DeckDocument, DeckEntry
from mtg_core.recommendation_scoring import DEFAULT_WEIGHTS, context, score, settings


def test_context_respects_manual_roles_distinct_themes_and_dismissals():
    doc = DeckDocument()
    doc.editor_preferences["guidance"] = dict(
        theme_minimum=2, targets=dict(ramp=10), dismissed=["shortage:lands"]
    )
    doc.deck.entries = [
        DeckEntry(
            "a",
            "A",
            quantity=5,
            oracle_id="a",
            extras={
                "facts": {"type_line": "Artifact", "cmc": 5},
                "auto_categories": {"manual": True},
            },
        ),
        DeckEntry(
            "b",
            "B",
            oracle_id="b",
            extras={"facts": {"type_line": "Artifact", "cmc": 5}},
        ),
    ]
    proposals = {
        e.entry_id: [
            dict(name="Ramp", reason="fixture"),
            dict(name="Tokens", reason="fixture"),
        ]
        for e in doc.deck.entries
    }
    before = deepcopy(doc.to_dict())
    result = context(doc, proposals)
    assert result["gaps"]["ramp"] == 0.9
    assert "lands" not in result["gaps"]
    assert result["themes"] == []
    assert result["archetypes"] == ["Artifact"]
    assert result["average"] == 5 and result["known"] == 6
    assert doc.to_dict() == before


def test_scoring_exposes_contributions_and_weights_can_disable_every_bonus():
    entry = DeckEntry(
        "x", "Candidate", extras={"facts": {"type_line": "Artifact", "cmc": 2}}
    )
    row = dict(
        entry=entry,
        roles=[dict(name="Ramp"), dict(name="Tokens")],
        statistical_score=0.5,
        baseline=0.1,
        association=dict(value=0.5, seeds=4),
    )
    ctx = dict(
        gaps=dict(ramp=0.5),
        themes=["Tokens"],
        archetypes=["Artifact"],
        average=4,
        known=10,
    )
    result = score(row, ctx, DEFAULT_WEIGHTS)
    assert result["score"] == pytest.approx(0.5 + 0.1 + 0.125 + 0.15 + 0.15 + 0.15)
    assert result["score"] == sum(result["contributions"].values())
    assert score(row, ctx, dict.fromkeys(DEFAULT_WEIGHTS, 0))["score"] == 0
    assert "score" not in row
    ctx["known"] = 4
    assert score(row, ctx, DEFAULT_WEIGHTS)["components"]["curve"] == 0
    doc = DeckDocument()
    doc.editor_preferences["recommendations"] = dict(
        weights=dict(curve=float("nan"), roles=9)
    )
    assert settings(doc)["weights"]["curve"] == DEFAULT_WEIGHTS["curve"]
    assert settings(doc)["weights"]["roles"] == 2
