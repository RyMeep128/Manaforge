"""Card identity matching shared by discovery membership, counts, and removal."""


def normalized_card_name(name):
    return ' '.join(name.split()).casefold()


def matches_card(entry, candidate):
    """Use printing/Oracle IDs, falling back to names for legacy metadata only."""
    return bool((candidate.card_id and entry.card_id == candidate.card_id)
        or (candidate.oracle_id and entry.oracle_id == candidate.oracle_id)
        or ((not candidate.oracle_id or not entry.oracle_id)
            and normalized_card_name(entry.name) == normalized_card_name(candidate.name)))


def matching_entries(entries, candidate):
    return [entry for entry in entries if entry.quantity > 0 and matches_card(entry, candidate)]
