"""A deliberately narrow sharing projection of the existing Deck model."""
import json

from mtg_core.decks import Deck
from . import LibraryError

MAX_BODY = 1024 * 1024
DECK_FIELDS = ('deck_id', 'name', 'format', 'description', 'tags', 'commander_entry_ids')
ENTRY_FIELDS = ('entry_id', 'name', 'quantity', 'section', 'sort_order', 'card_id',
                'oracle_id', 'set_code', 'collector_number', 'category_ids', 'tags', 'notes')


def text(value, limit=256, *, empty=False):
    if not isinstance(value, str) or len(value) > limit or ('\x00' in value):
        raise LibraryError(400, 'Invalid text field.')
    if not empty and not value.strip():
        raise LibraryError(400, 'A required text field is empty.')
    return value


def strings(value, limit=100):
    if not isinstance(value, list) or len(value) > limit:
        raise LibraryError(400, 'Invalid list field.')
    return [text(item) for item in value]


def shared_deck(value):
    """Drop private status, file paths, image URLs, overrides and unknown extras.

    Clients resolve artwork using printing/oracle identifiers in their own cache.
    Never feed untrusted extras into desktop image loaders or project settings.
    """
    if not isinstance(value, dict):
        raise LibraryError(400, 'Expected a deck object.')
    try:
        encoded = json.dumps(value, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, RecursionError):
        raise LibraryError(400, 'Invalid deck JSON.') from None
    if len(encoded) > MAX_BODY:
        raise LibraryError(413, 'Deck exceeds the 1 MiB limit.')
    result = {}
    for key in DECK_FIELDS:
        if key in value:
            if key in ('tags', 'commander_entry_ids'):
                result[key] = strings(value[key])
            else:
                result[key] = text(value[key], 16000 if key == 'description' else 256,
                                   empty=key == 'description')
    text(result.get('name'))
    entries = value.get('entries', [])
    categories = value.get('categories', [])
    if not isinstance(entries, list) or len(entries) > 2000:
        raise LibraryError(400, 'Decks may contain at most 2000 entries.')
    if not isinstance(categories, list) or len(categories) > 100:
        raise LibraryError(400, 'Decks may contain at most 100 categories.')
    result['entries'] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise LibraryError(400, 'Invalid card entry.')
        clean = {}
        for key in ENTRY_FIELDS:
            if key not in entry:
                continue
            item = entry[key]
            if key in ('quantity', 'sort_order'):
                if type(item) is not int or not 0 <= item <= 10000:
                    raise LibraryError(400, 'Invalid card quantity or order.')
                clean[key] = item
            elif key in ('category_ids', 'tags'):
                clean[key] = strings(item)
            elif item is not None:
                clean[key] = text(item, 4000 if key == 'notes' else 256, empty=key == 'notes')
        text(clean.get('entry_id'))
        text(clean.get('name'))
        result['entries'].append(clean)
    result['categories'] = []
    for category in categories:
        if not isinstance(category, dict):
            raise LibraryError(400, 'Invalid category.')
        order = category.get('sort_order', 0)
        if type(order) is not int or not 0 <= order <= 10000:
            raise LibraryError(400, 'Invalid category order.')
        result['categories'].append({'category_id': text(category.get('category_id')),
                                     'name': text(category.get('name')), 'sort_order': order})
    ids = [item['entry_id'] for item in result['entries']]
    category_ids = [item['category_id'] for item in result['categories']]
    if len(ids) != len(set(ids)) or len(category_ids) != len(set(category_ids)):
        raise LibraryError(400, 'Duplicate entry or category identifiers.')
    if not set(result.get('commander_entry_ids', [])) <= set(ids):
        raise LibraryError(400, 'Commander references an unknown entry.')
    if any(not set(item.get('category_ids', [])) <= set(category_ids) for item in result['entries']):
        raise LibraryError(400, 'Card references an unknown category.')
    # Normalize through the application model, then project again to omit its local defaults.
    model = Deck.from_dict(result).to_dict()
    return {**{key: model[key] for key in DECK_FIELDS},
            'categories': model['categories'],
            'entries': [{key: item[key] for key in ENTRY_FIELDS if key in item}
                        for item in model['entries']]}


def colors(value):
    values = strings(value, 5)
    if len(set(values)) != len(values) or any(item not in 'WUBRG' or len(item) != 1 for item in values):
        raise LibraryError(400, 'Color identity must contain unique W/U/B/R/G symbols.')
    return ''.join(item for item in 'WUBRG' if item in values)
