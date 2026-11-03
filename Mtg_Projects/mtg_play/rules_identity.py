"""Audited engine spelling aliases; never artwork or printing substitutions."""

import unicodedata
import json
from pathlib import Path
import sqlite3


def name_key(name):
    return unicodedata.normalize("NFKC", name).replace("’", "'").casefold()


def identity_hint_key(name):
    """Triage suggestions only. Never use this lossy key to resolve a game card."""
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", name).casefold()
        if not unicodedata.combining(c) and c.isalnum()
    )


ALIASES = {
    "mj\u00f6lnir, hammer of thor": {
        "engine_name": "Mjolnir, Hammer of Thor",
        "oracle_id": "7f9a8845-d760-44a7-a4c9-8a20dba4e14a",
        "source": "Mage.Sets/src/mage/sets/MarvelSuperHeroes.java; MjolnirHammerOfThor.java",
    },
}


def engine_rule_name(name, oracle_id=None):
    alias = ALIASES.get(name_key(name))
    if alias and (oracle_id is None or oracle_id == alias["oracle_id"]):
        return alias["engine_name"]
    return name


def configured_catalog(data_root):
    state = Path(data_root) / "mtg_core/installation.sqlite3"
    if state.is_file():
        with sqlite3.connect(
            state.resolve().as_uri() + "?mode=ro", uri=True
        ) as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key='catalog_path'"
            ).fetchone()
            if row and json.loads(row[0]):
                return Path(json.loads(row[0]))
    return Path(data_root) / "mtg_core/card_data.sqlite3"


def canonical_cards(oracle_ids, catalog=None):
    ids = sorted({value for value in oracle_ids if isinstance(value, str) and value})
    if not ids:
        return {}
    if catalog is None:
        from mtg_core.paths import data_root

        catalog = configured_catalog(data_root())
    path = Path(catalog).resolve()
    if not path.is_file():
        return {}
    result = {}
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        connection.execute("BEGIN")
        for offset in range(0, len(ids), 900):
            batch = ids[offset : offset + 900]
            query = (
                "SELECT oracle_id,name,layout FROM cards_oracle WHERE oracle_id IN ("
                + ",".join("?" for _ in batch)
                + ")"
            )
            for identity, name, layout in connection.execute(query, batch):
                result[identity] = dict(name=name, layout=layout)
    return result


def canonicalize_requests(requests, cards):
    result = []
    for original in requests:
        row = dict(original)
        card = cards.get(row.get("oracle_id"))
        if card:
            if row.get("name") != card["name"]:
                row["source_name"] = row.get("name")
                row["identity_status"] = "saved_name_differs_from_canonical_oracle"
            row.update(name=card["name"], layout=card["layout"])
        result.append(row)
    return result
