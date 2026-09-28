"""Convert shared decks into compatible print-project payloads."""
from copy import deepcopy
from mtg_core.decks import DeckDocument


def project_payload(document, base=None):
    adapter = DeckDocument.from_dict(document.to_dict())
    if base is not None:
        adapter.print_settings['proxy_project'] = deepcopy(base)
    # Stable unique filenames also distinguish two entries of the same printing.
    for entry in adapter.deck.entries:
        # New catalog entries use card-sized images. Legacy/custom sources retain
        # their explicit metadata or the printer's filename compatibility rule.
        if entry.pre_cropped is None:
            entry.pre_cropped = bool(entry.card_id
                and not entry.art_override and not entry.extras.get('proxy_front_name'))
        entry.extras.setdefault('proxy_front_name', f'{entry.entry_id}.png')
    payload = adapter.apply_to_legacy_proxy()
    by_id = {e.entry_id: e for e in adapter.deck.entries}
    for raw in payload['card_entries']:
        entry = by_id[raw['entry_id']]
        raw['oversized'] = entry.oversized if entry.oversized is not None else raw.get('oversized', False)
        for key in ('backside_name', 'backside_short_edge'):
            if key in entry.extras:
                raw[key] = entry.extras[key]
    payload['oversized_enabled'] = payload.get('oversized_enabled', False) or any(r.get('oversized') for r in payload['card_entries'])
    # Embed deck metadata without recursively embedding the entire print project.
    embedded = adapter.to_dict()
    embedded['print_settings'] = {}
    payload['deck_document'] = embedded
    return payload
