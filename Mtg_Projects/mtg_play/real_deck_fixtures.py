"""Public synthetic Commander lists; no user data, network or deck substitutions.

Fixture version 1. Names resolve against the pinned engine, never a web service.
Only explicit selected printings claim a printing; other entries are name-only.
"""
from mtg_core.decks import Deck, DeckDocument, DeckEntry

COMMON = """Sol Ring|Arcane Signet|Commander's Sphere|Mind Stone|Fellwar Stone|
Wayfarer's Bauble|Swiftfoot Boots|Lightning Greaves|Solemn Simulacrum|
Burnished Hart|Thought Vessel|Mind's Eye""".replace("\n", "").split("|")

ELEMENTALS = """Risen Reef|Coiling Oracle|Mulldrifter|Cloudkin Seer|Omnath, Locus of the Roil|
Avenger of Zendikar|Zendikar's Roil|Spitebellows|Ingot Chewer|Foundation Breaker|
Leafkin Druid|Creeping Trailblazer|Smokebraider|Flamekin Harbinger|Incandescent Soulstoke|
Thunderkin Awakener|Fertilid|Woodland Bellower|Eternal Witness|Reclamation Sage|
Clone|Sakashima's Student|Clever Impersonator|Quasiduplicate|Rite of Replication|
Twinflame|Heat Shimmer|Cackling Counterpart|Cultivate|Kodama's Reach|Rampant Growth|
Farseek|Nature's Lore|Explosive Vegetation|Counterspell|Negate|Beast Within|
Chaos Warp|Blasphemous Act|Decimate|Harmonize|Fact or Fiction|Brainstorm|
Ponder|Preordain|Temur Ascendancy|Garruk's Uprising|Guardian Project|
Warstorm Surge|Impact Tremors""".replace("\n", "").split("|")

TOKENS = """Soul Warden|Soul's Attendant|Essence Warden|Suture Priest|Mentor of the Meek|
Welcoming Vampire|Llanowar Elves|Elvish Mystic|Avacyn's Pilgrim|Birds of Paradise|
Sakura-Tribe Elder|Wood Elves|Farhaven Elf|Eternal Witness|Reclamation Sage|
Trostani, Selesnya's Voice|Emmara, Soul of the Accord|Tendershoot Dryad|
Avenger of Zendikar|Scute Swarm|Hornet Queen|Myr Battlesphere|Advent of the Wurm|
Call of the Conclave|Raise the Alarm|Secure the Wastes|March of the Multitudes|
Selesnya Charm|Rootborn Defenses|Growing Ranks|Parallel Lives|Intangible Virtue|
Beastmaster Ascension|Cathars' Crusade|Mirari's Wake|Aura Shards|Skullclamp|
Cultivate|Kodama's Reach|Rampant Growth|Swords to Plowshares|Path to Exile|
Beast Within|Generous Gift|Return to Nature|Wrath of God|Hour of Reckoning|
Harmonize|Shamanic Revelation|Overrun""".replace("\n", "").split("|")


def commander_decks():
    result = []
    for title, commander, spells, basics in (
        ("Temur Elementals", "Animar, Soul of Elements", ELEMENTALS,
         (("Forest", 13), ("Island", 12), ("Mountain", 12))),
        ("Selesnya Tokens", "Rhys the Redeemed", TOKENS,
         (("Forest", 19), ("Plains", 18))),
    ):
        names = COMMON + spells
        entries = [DeckEntry(f"spell-{i}", name, 1) for i, name in enumerate(names)]
        entries += [DeckEntry(name.lower(), name, count) for name, count in basics]
        entries.append(DeckEntry("commander", commander, 1, section="commander"))
        document = DeckDocument(deck=Deck(name=title, entries=entries))
        document.deck.commander_entry_ids = ["commander"]
        # Explicit physical selection in each list exercises strict resolution.
        land = next(entry for entry in entries if entry.name == "Forest")
        land.set_code, land.collector_number, land.card_id = "M10", "248", "fixture-forest-M10-248"
        if sum(e.quantity for e in entries) != 100 or len(set(names)) != 62:
            raise ValueError("Invalid versioned Commander fixture")
        result.append(document)
    return tuple(result)
