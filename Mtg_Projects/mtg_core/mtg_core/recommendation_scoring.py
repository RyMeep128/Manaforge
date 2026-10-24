"""Explicit, adjustable deck-context bonuses over public/local statistical scores."""

from collections import Counter
import math

from .deck_insights import deck_insights
from .guidance import GROUPS, GuidanceSettings, guidance
from .sections import DeckSection


DEFAULT_WEIGHTS = dict(
    statistics=1.0,
    cooccurrence=0.25,
    roles=0.25,
    themes=0.15,
    archetype=0.15,
    curve=0.15,
)


def settings(document):
    raw = document.editor_preferences.get("recommendations", {})
    if raw.get("version", 1) != 1:
        raise ValueError("Unsupported recommendation settings version")
    weights = {}
    for key, default in DEFAULT_WEIGHTS.items():
        value = float(raw.get("weights", {}).get(key, default))
        weights[key] = min(2, max(0, value)) if math.isfinite(value) else default
    return dict(
        version=1,
        weights=weights,
        dismissed=list(raw.get("dismissed", [])),
        local_enabled=bool(raw.get("local_enabled", True)),
    )


def context(document, proposals, records=None):
    rules = GuidanceSettings.from_document(document)
    result = guidance(document, proposals, rules)
    gaps = {
        key: max(0, target - result["counts"][key]) / target
        for key, target in rules.targets.items()
        if target > 0 and f"shortage:{key}" not in rules.dismissed
    }
    themes = [
        row["id"][6:] for row in result["suggestions"] if row["id"].startswith("theme:")
    ]
    composition = deck_insights(document, records)
    # Archetypes describe dominant card types, not inferred competitive labels.
    types = Counter()
    seen = set()
    for entry in document.deck.entries:
        if entry.quantity <= 0 or entry.section not in (
            DeckSection.MAINBOARD,
            DeckSection.COMMANDER,
        ):
            continue
        identity = entry.oracle_id or entry.name.casefold()
        if identity in seen:
            continue
        seen.add(identity)
        facts = (records or {}).get(entry.card_id) or entry.extras.get("facts", {})
        line = facts.get("type_line") or ""
        for kind in ("Artifact", "Enchantment", "Creature", "Instant", "Sorcery"):
            if kind in line.split("—")[0].split():
                types[kind] += 1
    archetypes = [
        kind
        for kind, count in types.items()
        if count >= rules.theme_minimum and count >= len(seen) * 0.25
    ]
    return dict(
        gaps=gaps,
        themes=themes,
        archetypes=archetypes,
        average=composition["average_mana_value"],
        known=composition["known_mana_value"],
    )


def score(row, deck_context, weights):
    facts = row["entry"].extras.get("facts", {})
    line = facts.get("type_line") or ""
    role_names = {item["name"].casefold() for item in row["roles"]}
    gaps = {
        key: value
        for key, value in deck_context["gaps"].items()
        if (key == "lands" and "Land" in line.split("—")[0].split())
        or (key != "lands" and role_names & GROUPS[key])
    }
    themes = [name for name in deck_context["themes"] if name.casefold() in role_names]
    archetypes = [
        kind
        for kind in deck_context["archetypes"]
        if kind in line.split("—")[0].split()
    ]
    mv = facts.get("cmc")
    average = deck_context["average"]
    curve = (
        isinstance(mv, (int, float))
        and not isinstance(mv, bool)
        and math.isfinite(mv)
        and 0 <= mv <= 3
        and "Land" not in line
        and deck_context["known"] >= 5
        and average is not None
        and average > 3.5
    )
    association = row.get("association", {})
    components = dict(
        statistics=row["statistical_score"],
        cooccurrence=max(
            0,
            association.get("value", 0)
            - association.get("baseline", row.get("baseline", 0)),
        ),
        roles=max(gaps.values(), default=0),
        themes=float(bool(themes)),
        archetype=float(bool(archetypes)),
        curve=float(bool(curve)),
    )
    contributions = {key: value * weights[key] for key, value in components.items()}
    reasons = []
    if gaps:
        reasons.append(
            "Role deficits: "
            + ", ".join(f"{key} {value:.0%}" for key, value in gaps.items())
        )
    if themes:
        reasons.append("Theme matches: " + ", ".join(themes))
    if archetypes:
        reasons.append("Type-based archetype matches: " + ", ".join(archetypes))
    if curve:
        reasons.append(
            f"Known nonland average {average:.2f} exceeds 3.5; candidate mana value {mv:g} is at most 3"
        )
    if association.get("seeds"):
        reasons.append(
            f"Mean conditional inclusion {association['value']:.1%} across {association['seeds']} known deck cards; subtract global baseline"
        )
    return dict(
        row,
        score=sum(contributions.values()),
        components=components,
        contributions=contributions,
        context_reasons=reasons,
    )
