"""Deck editing operations; callers own undo transactions and UI refreshes."""
from copy import deepcopy
import uuid

from .categorization import apply_categories
from .sections import DeckSection


def remove_entries(document, entry_ids):
    """Remove entries and their commander references in one operation."""
    ids = set(entry_ids)
    document.deck.entries = [e for e in document.deck.entries if e.entry_id not in ids]
    document.deck.commander_entry_ids = [key for key in document.deck.commander_entry_ids if key not in ids]
    if document.deck.extras.get('companion_entry_id') in ids:
        document.deck.extras.pop('companion_entry_id', None)


def apply_quantity(document, entry_id, quantity):
    """Set a copy count, clamping at zero and removing empty entries."""
    entry = next((e for e in document.deck.entries if e.entry_id == entry_id), None)
    if entry is None:
        return
    entry.quantity = max(0, int(quantity))
    if entry.quantity == 0:
        remove_entries(document, {entry_id})


def change_quantities(document, entry_ids, delta):
    """Adjust only the requested entries, including each selected card once."""
    ids = set(entry_ids)
    for entry in list(document.deck.entries):
        if entry.entry_id in ids:
            apply_quantity(document, entry.entry_id, entry.quantity + delta)


def add_card(document, candidate):
    """Add one mainboard copy using discovery's printing and artwork policy."""
    existing = next((e for e in document.deck.entries if ((candidate.card_id and e.card_id == candidate.card_id)
        or (not candidate.card_id and not e.card_id and e.name.casefold() == candidate.name.casefold()))
        and e.section == DeckSection.MAINBOARD and not e.art_override), None)
    if existing:
        apply_quantity(document, existing.entry_id, existing.quantity + 1)
        return
    entry = deepcopy(candidate)
    entry.quantity = 1
    entry.entry_id = str(uuid.uuid4())
    entry.sort_order = max((e.sort_order for e in document.deck.entries), default=-1) + 1
    document.deck.entries.append(entry)
    apply_categories(document, {entry.entry_id: entry.extras.pop('category_suggestion', [])})


def change_candidate_quantity(document, candidate, delta=1):
    """Discovery +/- is one copy per activation, independent of editor selection."""
    if delta > 0:
        add_card(document, candidate)
        return
    if delta >= 0:
        return
    matches = [entry for entry in document.deck.entries
               if entry.quantity > 0 and entry.section in (DeckSection.MAINBOARD, DeckSection.COMMANDER)
               and ((candidate.card_id and entry.card_id == candidate.card_id)
                    or (candidate.oracle_id and entry.oracle_id == candidate.oracle_id)
                    or (entry.name.casefold() == candidate.name.casefold()
                        and (not candidate.oracle_id or not entry.oracle_id)))]
    if matches:
        target = min(matches, key=lambda entry: (entry.section == DeckSection.COMMANDER,
                                                 entry.card_id != candidate.card_id, entry.sort_order))
        apply_quantity(document, target.entry_id, target.quantity - 1)
