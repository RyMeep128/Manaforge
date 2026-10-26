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


def search_commanders(service, filters, store, *, metadata=None, should_cancel=None):
    """Page through broad catalog candidates; eligibility is never guessed.

    Theme associations are filtered by exact cohort. Pair evidence stays labeled
    as a pair even when displaying either member's artwork.
    """
    from .discovery_themes import theme_catalog
    check_cancelled(should_cancel)
    theme = filters.get('theme')
    metadata = metadata or {}
    try:
        snapshot = store.snapshot(theme, should_cancel=should_cancel)
        rankings = store.rankings(should_cancel=should_cancel) if hasattr(store, 'rankings') else {}
    except (OSError, ValueError, sqlite3.DatabaseError) as exc:
        check_cancelled(should_cancel)
        snapshot = dict(themes=[], members=[], status=f"EDHREC theme data unavailable: {exc}. Local search remains available.")
        rankings = {}
    catalog = theme_catalog(snapshot['themes'], metadata)
    from .discovery_themes import oracle_tag_theme
    catalog.extend(oracle_tag_theme(t['oracle_tag']) for t in filters.get('custom_themes', [])
                   if t.get('origin') == 'custom' and t.get('oracle_tag'))
    option = next((item for item in catalog if item['slug'] == theme), None)
    cached_theme = bool(theme and option and option['origin'] == 'edhrec')
    snapshot.update(themes=catalog, cards=metadata.get('cards', 0), ranked=bool(rankings))
    associations = {}
    for row in snapshot.pop('members'):
        associations.setdefault(row['oracle_id'], []).append(row)
    if theme and not option:
        return dict(snapshot, results=[], more=False, status='This theme is unavailable. Clear it to browse local commanders.')
    if cached_theme and not associations:
        return dict(snapshot, results=[], more=False)
    top = filters.get('browse') == 'top' and bool(rankings) and not theme

    # This is only a broad SQL prefilter. Actual eligibility and pairing use
    # commander.py, including front-face and special commander-text rules.
    terms = ['(t:legendary or o:"can be your commander")']
    for field, operator in (("name", "name"), ("type", "t"), ("text", "o")):
        value = filters.get(field, "").strip()
        if value:
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            terms.append(f'{operator}:"{escaped}"')
    if option and not cached_theme and option.get('query'):
        terms.append('(' + option['query'] + ')')
        snapshot['status'] = 'Local card mechanics / type search; no EDHREC commander association is claimed.'
    if filters.get('identity') is not None:
        terms.append(('id<=' if filters.get('partner_card_id') else 'id=') + (filters['identity'] or 'C'))
    query = " ".join(terms)
    partner = None
    if filters.get("partner_card_id"):
        partner = service.get_card(card_id=filters["partner_card_id"])
        if not partner:
            return dict(snapshot, results=[], more=False,
                        status="Current commander's local rules data is unavailable; cannot verify compatible partners.")
    limit = max(50, int(filters.get("limit", 50)))
    results, offset = [], 0
    # Theme membership is an exact Oracle-ID prefilter, applied before the SQL
    # printing selection. Larger pages avoid repeating the catalog sort while
    # retaining pagination for catalogs that exceed a single page.
    batch_size = 10000 if theme or partner or filters.get("capability") else 1000
    while True:
        check_cancelled(should_cancel)
        batch = service.search_cards(query, dict(scryfall_syntax=True, allow_remote=False,
                                    limit=batch_size, offset=offset, should_cancel=should_cancel,
                                    oracle_ids=list(associations) if cached_theme else list(rankings) if top else None))
        for result in batch:
            check_cancelled(should_cancel)
            payload = result.payload or {}
            if payload.get("layout") in {"art_series", "token", "double_faced_token", "emblem"}:
                continue
            if not result.oracle_id or result.oracle_id.startswith("proxy-oracle-"):
                continue
            if not (eligible(payload) is True or background(payload)):
                continue
            if filters.get("legal_only", True):
                format_name = filters.get('deck_format') or 'commander'
                allowed = ('legal', 'restricted') if format_name == 'vintage' else ('legal',)
                if (payload.get('legalities') or {}).get(format_name) not in allowed:
                    continue
                deck_identity = filters.get('deck_identity')
                if (deck_identity is not None and (payload.get('color_identity') is None
                        or not set(payload['color_identity']) <= set(deck_identity))):
                    continue
            identity = filters.get("identity")
            if identity is not None:
                if payload.get('color_identity') is None or (partner and partner.get('color_identity') is None):
                    continue
                combined = set(payload['color_identity']) | (set(partner['color_identity']) if partner else set())
                if combined != set(identity):
                    continue
            if option and option.get('companion') and not cached_theme:
                from .companions import companion_restriction
                from .decks import DeckEntry
                entry = DeckEntry(result.card_id, result.name)
                entries, payloads = [entry], {entry.entry_id: payload}
                if partner:
                    paired = DeckEntry('existing-partner', partner.get('name') or 'Current commander')
                    entries.append(paired)
                    payloads[paired.entry_id] = partner
                bad, unknown, _ = companion_restriction(option.get('companion_name', option['name']),
                                                        entries, payloads)
                combined = set(payload.get('color_identity') or []) | (set(partner.get('color_identity') or []) if partner else set())
                if (bad or unknown or option.get('companion_legal') == 'banned'
                        or not set(option.get('companion_identity') or []) <= combined):
                    continue
            if not capability_matches(payload, filters.get("capability", "")):
                continue
            if partner and (partner.get("oracle_id") == result.oracle_id or compatible(partner, payload) is not True):
                continue
            evidence = associations.get(result.oracle_id, [])
            if cached_theme and partner:
                pair = commander_key([partner.get("oracle_id") or "", result.oracle_id])
                evidence = [row for row in evidence if row["commander_key"] == pair]
            if cached_theme and not evidence:
                continue
            results.append(dict(card=result, associations=evidence, popularity=rankings.get(result.oracle_id)))
        offset += len(batch)
        # Theme results need the complete matching pool before ordering by the
        # source's cohort count; local browsing can stop at the display bound.
        if len(batch) < batch_size or (not theme and not top and len(results) > limit):
            break
    if cached_theme:
        results.sort(key=lambda row: (-max(a["num_decks"] for a in row["associations"]), row["card"].name.casefold()))
    elif top:
        results.sort(key=lambda row: (-row['popularity'], row['card'].name.casefold()))
    check_cancelled(should_cancel)
    return dict(snapshot, results=results[:limit], more=len(results) > limit)
