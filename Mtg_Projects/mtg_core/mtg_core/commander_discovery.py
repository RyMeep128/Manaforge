"""Local commander browsing using the catalog search and existing rules."""

import sqlite3

from .commander import abilities, compatible, eligible, front
from .edhrec import commander_key
from .search.cancellation import check_cancelled


def background(payload):
    return {"Legendary", "Enchantment", "Background"} <= set((front(payload).get("type_line") or "").split())


def capability_matches(payload, capability):
    known = abilities(payload)
    if capability == "background":
        return background(payload)
    if capability == "partner":
        return any(a == "partner" or a.startswith("partner ") for a in known)
    return not capability or capability in known


def search_commanders(service, filters, store, *, should_cancel=None):
    """Page through broad catalog candidates; eligibility is never guessed.

    Theme associations are filtered by exact cohort. Pair evidence stays labeled
    as a pair even when displaying either member's artwork.
    """
    check_cancelled(should_cancel)
    try:
        snapshot = store.snapshot(filters.get("theme"), should_cancel=should_cancel)
    except (OSError, ValueError, sqlite3.DatabaseError) as exc:
        check_cancelled(should_cancel)
        snapshot = dict(themes=[], members=[], status=f"EDHREC theme data unavailable: {exc}. Local search remains available.")
    theme = filters.get("theme")
    associations = {}
    for row in snapshot.pop("members"):
        associations.setdefault(row["oracle_id"], []).append(row)
    if theme and not associations:
        return dict(snapshot, results=[], more=False)

    # This is only a broad SQL prefilter. Actual eligibility and pairing use
    # commander.py, including front-face and special commander-text rules.
    terms = ['(t:legendary or o:"can be your commander")']
    for field, operator in (("name", "name"), ("type", "t"), ("text", "o")):
        value = filters.get(field, "").strip()
        if value:
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            terms.append(f'{operator}:"{escaped}"')
    colors = filters.get("colors")
    if colors is not None:
        terms.append("id=" + ("".join(c for c in "WUBRG" if c in colors) or "c"))
    count = filters.get("color_count")
    if count is not None:
        terms.append(f"id={int(count)}")
    query = " ".join(terms)
    partner = None
    if filters.get("partner_card_id"):
        partner = service.get_card(card_id=filters["partner_card_id"])
        if not partner:
            return dict(snapshot, results=[], more=False,
                        status="Current commander's local rules data is unavailable; cannot verify compatible partners.")
    limit = min(2000, max(100, int(filters.get("limit", 200))))
    results, offset = [], 0
    while True:
        check_cancelled(should_cancel)
        batch = service.search_cards(query, dict(scryfall_syntax=True, allow_remote=False,
                                    limit=500, offset=offset, should_cancel=should_cancel))
        for result in batch:
            check_cancelled(should_cancel)
            payload = result.payload or {}
            if payload.get("layout") in {"art_series", "token", "double_faced_token", "emblem"}:
                continue
            if not result.oracle_id or result.oracle_id.startswith("proxy-oracle-"):
                continue
            if not (eligible(payload) is True or background(payload)):
                continue
            if filters.get("legal_only", True) and (payload.get("legalities") or {}).get("commander") != "legal":
                continue
            if not capability_matches(payload, filters.get("capability", "")):
                continue
            if partner and (partner.get("oracle_id") == result.oracle_id or compatible(partner, payload) is not True):
                continue
            evidence = associations.get(result.oracle_id, [])
            if theme and partner:
                pair = commander_key([partner.get("oracle_id") or "", result.oracle_id])
                evidence = [row for row in evidence if row["commander_key"] == pair]
            if theme and not evidence:
                continue
            # Identity-less records must not pass a colorless query.
            identity = payload.get("color_identity")
            if (colors is not None or count is not None) and identity is None:
                continue
            results.append(dict(card=result, associations=evidence))
        offset += len(batch)
        # Theme results need the complete matching pool before ordering by the
        # source's cohort count; local browsing can stop at the display bound.
        if len(batch) < 500 or (not theme and len(results) > limit):
            break
    if theme:
        results.sort(key=lambda row: (-max(a["num_decks"] for a in row["associations"]), row["card"].name.casefold()))
    check_cancelled(should_cancel)
    return dict(snapshot, results=results[:limit], more=len(results) > limit)
