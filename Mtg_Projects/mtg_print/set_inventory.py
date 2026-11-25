"""Deterministic collection inventories, intentionally independent of pack collation."""

from collections import Counter
from dataclasses import asdict, dataclass, field

from mtg_core.card_identity import normalized_card_name
from mtg_core.preferences import rank_prints

RARITIES = ("common", "uncommon", "rare", "mythic", "special", "bonus", "other")
PRESETS = {"Set Cube": (4, 2, 1, 1, 1, 1, 1), "One of Each": (1,) * 7}


@dataclass
class InventorySettings:
    preset: str = "Set Cube"
    quantities: dict = field(
        default_factory=lambda: dict(zip(RARITIES, PRESETS["Set Cube"]))
    )
    basic_lands: bool = False
    tokens: bool = False
    alternate_printings: bool = False
    available_only: bool = False
    related_codes: list = field(default_factory=list)
    overrides: dict = field(default_factory=dict)

    def apply_preset(self, name):
        self.preset = name
        if name in PRESETS:
            self.quantities = dict(zip(RARITIES, PRESETS[name]))

    def to_dict(self):
        return asdict(self)


def eligible_cards(payloads, settings, *, rules=None, favorites=None):
    groups = {}
    for card in payloads:
        if not card.get("id") or not card.get("name") or card.get("digital"):
            continue
        if card.get("games") and "paper" not in card["games"]:
            continue
        token = (
            card.get("layout") in ("token", "double_faced_token", "emblem")
            or card.get("set_type") == "token"
        )
        if token and not settings.tokens:
            continue
        if (
            "Basic" in card.get("type_line", "")
            and "Land" in card.get("type_line", "")
            and not settings.basic_lands
        ):
            continue
        identity = (
            (card.get("set"), str(card["collector_number"]))
            if settings.alternate_printings and card.get("collector_number")
            else (
                card["id"]
                if settings.alternate_printings
                else (card.get("oracle_id") or normalized_card_name(card["name"]))
            )
        )
        groups.setdefault(identity, []).append(card)
    result = []
    for identity, cards in groups.items():
        # Prefer an ordinary treatment; preferences choose between equivalent prints
        # within this set, without silently adding cards from other sets.
        ordinary = [
            c
            for c in cards
            if not (
                c.get("promo")
                or c.get("variation")
                or c.get("full_art")
                or c.get("frame_effects")
                or c.get("border_color") == "borderless"
            )
        ]
        favorite = (favorites or {}).get(cards[0].get("oracle_id"))
        preferred = [c for c in cards if c["id"] == favorite]
        candidates = (
            cards if settings.alternate_printings else (preferred or ordinary or cards)
        )
        result.append(
            rank_prints(candidates, rules=rules, favorite_card_id=favorite)[0]
        )
    return sorted(
        result, key=lambda c: (RARITIES.index(rarity(c)), c["name"].casefold(), c["id"])
    )


def rarity(card):
    value = card.get("rarity") or "other"
    return value if value in RARITIES else "other"


def inventory(cards, settings):
    return [
        (
            card,
            max(
                0,
                int(
                    settings.overrides.get(
                        card["id"], settings.quantities.get(rarity(card), 0)
                    )
                ),
            ),
        )
        for card in cards
    ]


def totals(cards, settings):
    selected = [(card, count) for card, count in inventory(cards, settings) if count]
    return len(selected), sum(count for _, count in selected)


def rarity_counts(cards):
    return Counter(rarity(card) for card in cards)
