"""Shared card facts and search-result conversion, independent of UI widgets."""
from copy import deepcopy


def card_facts(payload):
    """Keep the same metadata for imports, discovery, and card inspection."""
    face = (payload.get('card_faces') or [{}])[0]
    return deepcopy({key: payload.get(key, face.get(key)) for key in
        ('released_at', 'type_line', 'mana_cost', 'cmc', 'colors', 'oracle_text', 'keywords', 'layout', 'card_faces',
         'color_identity', 'power', 'toughness', 'rarity', 'artist', 'legalities',
         'finishes', 'frame_effects', 'promo', 'textless', 'full_art', 'border_color', 'oracle_tags')})


def search_entry(result):
    """Convert a catalog result to a discovery candidate with category evidence."""
    from .decks import DeckEntry
    from .categorization import classify
    payload = getattr(result, 'payload', {}) or {}
    proposals = payload['_category_evidence'] if '_category_evidence' in payload else classify(payload)
    return DeckEntry(result.card_id, result.name, card_id=result.card_id, oracle_id=result.oracle_id,
        set_code=result.set_code, collector_number=result.collector_number, pre_cropped=True,
        extras={'facts': card_facts(payload), 'category_suggestion': deepcopy(proposals)})
