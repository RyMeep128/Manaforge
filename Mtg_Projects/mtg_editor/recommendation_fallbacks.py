"""Local type candidates; all downstream browsing uses the shared pipeline."""
import uuid

from mtg_core.card_metadata import card_facts
from mtg_core.card_pool import deck_query, in_card_pool, pool_context
from mtg_core.decks import DeckEntry
from mtg_core.search.cancellation import check_cancelled


def fallback_rows(service, document, *, seen, query='', include_present=False, should_cancel=None):
    import sqlite3
    if not callable(getattr(service, 'search_cards', None)):
        return
    excluded = set() if include_present else {e.oracle_id for e in document.deck.entries}
    names = set() if include_present else {e.name.casefold() for e in document.deck.entries}
    for kind in ('Instant', 'Sorcery', 'Creature', 'Artifact', 'Enchantment', 'Planeswalker', 'Land'):
        check_cancelled(should_cancel)
        term = f't:{kind}' + (f' ({query})' if query.strip() else '')
        if not pool_context(document)[0]:
            term += ' legal:commander'
        try:
            matches = service.search_cards(deck_query(term, document), dict(
                scryfall_syntax=True, allow_remote=False, popularity=True, limit=500,
                should_cancel=should_cancel))
        except (OSError, ValueError, sqlite3.DatabaseError):
            continue
        for result in matches:
            check_cancelled(should_cancel)
            payload = result.payload or {}
            oid = result.oracle_id
            rank = payload.get('edhrec_rank')
            if (not oid or oid in seen or oid in excluded or result.name.casefold() in names
                    or not in_card_pool(payload, document)
                    or not isinstance(rank, int) or isinstance(rank, bool) or rank <= 0):
                continue
            seen.add(oid)
            entry = DeckEntry(str(uuid.uuid4()), result.name, card_id=result.card_id,
                              oracle_id=oid, extras={'facts': card_facts(payload)})
            value = 1 / (1 + rank / 1000)
            yield dict(oracle_id=oid, entry=entry, fallback=True, score=value,
                       public_score=value, local_score=0, source_evidence={}, association={},
                       sources_present=['popular'], commander_names=[])
