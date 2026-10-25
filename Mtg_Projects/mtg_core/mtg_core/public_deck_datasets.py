"""Names shared by public dataset collectors, source settings, and evidence UI."""

DATASET_LABELS = {
    "playgroup": "Playgroup.gg",
    "deckstats": "Deckstats",
    "mtggoldfish": "MTGGoldfish",
    "preconstructed": "Preconstructed decks",
    "metagame": "Metagame decks (cEDH)",
}
STATISTICAL_SOURCES = ("archidekt", "moxfield", *DATASET_LABELS)
SOURCE_LABELS = {
    "archidekt": "Archidekt", "edhrec": "EDHREC", "moxfield": "Moxfield",
    **DATASET_LABELS,
}
