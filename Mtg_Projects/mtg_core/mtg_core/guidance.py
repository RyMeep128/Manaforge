"""Explainable composition heuristics; never mutate roles or assert legality."""

from collections import Counter
from dataclasses import dataclass, field

from .categorization import is_manual
from .sections import DeckSection


GROUPS = {
    "lands": {"lands"},
    "ramp": {"ramp"},
    "draw": {"draw", "card advantage"},
    "interaction": {"interaction", "removal", "counterspells", "board wipes"},
}
THEMES = ("Tokens", "Lifegain", "Graveyard", "Sacrifice / Aristocrats")


@dataclass
class GuidanceSettings:
    targets: dict[str, int] = field(
        default_factory=lambda: dict(lands=36, ramp=10, draw=10, interaction=10)
    )
    theme_minimum: int = 10
    dismissed: list[str] = field(default_factory=list)

    @classmethod
    def from_document(cls, document):
        commander = document.deck.format.casefold() == "commander" or bool(
            document.deck.commander_entry_ids
        )
        defaults = (
            dict(lands=36, ramp=10, draw=10, interaction=10)
            if commander
            else dict(lands=24, ramp=6, draw=6, interaction=6)
        )
        raw = document.editor_preferences.get("guidance", {})
        if raw.get("version", 1) != 1:
            raise ValueError("Unsupported deck guidance settings version")
        targets = {
            key: max(0, min(1000, int(raw.get("targets", {}).get(key, value))))
            for key, value in defaults.items()
        }
        return cls(
            targets,
            max(1, int(raw.get("theme_minimum", 10))),
            list(raw.get("dismissed", [])),
        )

    def to_dict(self):
        return dict(
            version=1,
            targets=dict(self.targets),
            theme_minimum=self.theme_minimum,
            dismissed=sorted(set(self.dismissed)),
        )


def guidance(document, proposals, settings=None):
    """Proposals come from CardService.analyze_entries (local tags and text).

    Manual categories, including explicitly empty choices, suppress inference.
    Interaction/draw unions count each copy once; themes require distinct cards.
    """
    settings = settings or GuidanceSettings.from_document(document)
    categories = {c.category_id: c.name for c in document.deck.categories}
    counts = Counter({key: 0 for key in GROUPS})
    evidence = {key: [] for key in GROUPS}
    themes = {name: set() for name in THEMES}
    total = unknown = 0
    for entry in document.deck.entries:
        if (
            entry.section not in (DeckSection.MAINBOARD, DeckSection.COMMANDER)
            or entry.quantity <= 0
        ):
            continue
        total += entry.quantity
        assigned = [
            categories[c] for c in entry.category_ids if c in categories
        ] + entry.tags
        inferred = [] if is_manual(entry) else proposals.get(entry.entry_id, [])
        names = {name.casefold() for name in assigned} | {
            item["name"].casefold() for item in inferred
        }
        # Lands are physical card types, independent of a manually chosen role.
        facts = entry.extras.get("facts") or {}
        faces = facts.get("card_faces") or []
        line = (faces[0] if faces else facts).get("type_line") or ""
        is_land = "Land" in line.split("—")[0].split()
        is_land |= any(
            item["name"] == "Lands" for item in proposals.get(entry.entry_id, [])
        )
        if not line and not proposals.get(entry.entry_id):
            unknown += entry.quantity
        for key, roles in GROUPS.items():
            matched = is_land if key == "lands" else bool(names & roles)
            if matched:
                counts[key] += entry.quantity
                reasons = [
                    f"Deck role: {name}"
                    for name in assigned
                    if name.casefold() in roles
                ]
                reasons += [
                    item["reason"]
                    for item in inferred
                    if item["name"].casefold() in roles
                ]
                if key == "lands":
                    reasons = ["Front-face Land type"]
                evidence[key].append(
                    dict(
                        entry_id=entry.entry_id,
                        name=entry.name,
                        quantity=entry.quantity,
                        reasons=reasons,
                    )
                )
        for theme in THEMES:
            if theme.casefold() in names:
                themes[theme].add(entry.oracle_id or entry.name.casefold())
    suggestions = []
    for key, target in settings.targets.items():
        if key in counts and counts[key] < target:
            suggestions.append(
                dict(
                    id=f"shortage:{key}",
                    title=f"Consider more {key}",
                    reason=f"{counts[key]} copies counted against your target of {target}; gap {target - counts[key]}. "
                    "This is a composition heuristic, not a deckbuilding or rules requirement.",
                )
            )
    for theme, identities in themes.items():
        if len(identities) >= settings.theme_minimum:
            suggestions.append(
                dict(
                    id=f"theme:{theme}",
                    title=f"Possible theme: {theme}",
                    reason=f"{len(identities)} distinct cards match; your threshold is {settings.theme_minimum}. "
                    "Review roles/categories to assign a theme yourself; no categories were changed.",
                )
            )
    return dict(
        total=total,
        counts=dict(counts),
        evidence=evidence,
        unknown=unknown,
        suggestions=[s for s in suggestions if s["id"] not in settings.dismissed],
    )
