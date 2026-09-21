"""Deck organization commands and deterministic visual groups."""
SECTIONS = {'mainboard': 'Mainboard', 'commander': 'Commander', 'sideboard': 'Sideboard',
            'considering': 'Considering', 'excluded': 'Excluded'}
GROUPS = ['Type', 'Mana Value', 'Color', 'Category', 'Section']
SORTS = ['Name', 'Mana Value', 'Quantity', 'Import Order']


def card_facts(payload):
    face = (payload.get('card_faces') or [{}])[0]
    return {key: payload.get(key, face.get(key)) for key in
            ('type_line', 'cmc', 'colors', 'oracle_text', 'keywords', 'layout', 'card_faces')}


def group_key(entry, grouping):
    if entry.section == 'commander':
        return 'Commander'
    facts = entry.extras.get('facts', {})
    if grouping == 'Category':
        return entry.category_ids[0] if entry.category_ids else 'Uncategorized'
    if grouping == 'Section':
        return SECTIONS.get(entry.section, entry.section.title())
    if grouping == 'Mana Value':
        value = facts.get('cmc')
        return 'Unknown' if value is None else f'MV {value:g}'
    if grouping == 'Color':
        colors = facts.get('colors')
        if colors is None:
            return 'Unknown'
        return {'W': 'White', 'U': 'Blue', 'B': 'Black', 'R': 'Red', 'G': 'Green'}.get(
            ''.join(colors), 'Multicolor' if colors else 'Colorless')
    line = facts.get('type_line') or ''
    return next((t for t in ('Land', 'Creature', 'Planeswalker', 'Battle', 'Instant',
                            'Sorcery', 'Artifact', 'Enchantment') if t in line), 'Other')


def grouped_entries(deck, grouping='Type', sort='Name', query=''):
    categories = {c.category_id: c for c in deck.categories}
    groups = {}
    for entry in deck.entries:
        if query.casefold() not in (entry.name + ' ' + ' '.join(entry.tags)).casefold():
            continue
        groups.setdefault(group_key(entry, grouping), []).append(entry)
    if grouping == 'Section':
        for label in SECTIONS.values():
            groups.setdefault(label, [])
    if grouping == 'Category':
        for key in categories:
            groups.setdefault(key, [])
        groups.setdefault('Uncategorized', [])
    def order(key):
        if key == 'Commander':
            return (-1, 0, '')
        if grouping == 'Category':
            return (0, categories[key].sort_order if key in categories else 100000, key)
        if grouping == 'Mana Value' and key.startswith('MV '):
            return (0, float(key[3:]), '')
        if grouping == 'Type':
            order = ['Creature', 'Planeswalker', 'Battle', 'Instant', 'Sorcery', 'Artifact', 'Enchantment', 'Land', 'Other']
            return (0, order.index(key) if key in order else len(order), key)
        return (0, 0, key)
    def entry_order(e):
        if sort == 'Quantity':
            return (-e.quantity, e.name.casefold(), e.entry_id)
        if sort == 'Mana Value':
            return (e.extras.get('facts', {}).get('cmc') or 0, e.name.casefold(), e.entry_id)
        if sort == 'Import Order':
            return (e.sort_order, e.name.casefold(), e.entry_id)
        return (e.name.casefold(), e.sort_order, e.entry_id)
    return [(key, categories[key].name if key in categories else key,
             sorted(groups[key], key=entry_order)) for key in sorted(groups, key=order)]


def assign(document, ids, field, value):
    for entry in document.deck.entries:
        if entry.entry_id not in ids:
            continue
        if field == 'category':
            entry.extras['auto_categories'] = {'manual': True}
            entry.category_ids = ([value] + [c for c in entry.category_ids if c != value]) if value else []
        elif field in ('oversized',):
            entry.extras[field] = value
        else:
            setattr(entry, field, value.copy() if isinstance(value, list) else value)
    document.deck.commander_entry_ids = [e.entry_id for e in document.deck.entries if e.section == 'commander']


def remove_category(document, category_id):
    document.deck.categories = [c for c in document.deck.categories if c.category_id != category_id]
    for entry in document.deck.entries:
        if category_id in entry.category_ids:
            entry.extras['auto_categories'] = {'manual': True}
        entry.category_ids = [c for c in entry.category_ids if c != category_id]


def move_entries(document, ids, grouping, target, before_id=None):
    if before_id in ids and all(group_key(e, grouping) == target for e in document.deck.entries if e.entry_id in ids):
        return
    if grouping == 'Section':
        section = next((s for s, name in SECTIONS.items() if name == target), None)
        if section is None:
            raise ValueError('Unknown section')
        assign(document, ids, 'section', section)
    elif grouping == 'Category':
        if target == 'Commander':
            assign(document, ids, 'section', 'commander')
        else:
            if target != 'Uncategorized' and target not in {c.category_id for c in document.deck.categories}:
                raise ValueError('Unknown category')
            assign(document, ids, 'category', None if target == 'Uncategorized' else target)
            for entry in document.deck.entries:
                if entry.entry_id in ids and entry.section == 'commander':
                    entry.section = 'mainboard'
            document.deck.commander_entry_ids = [e.entry_id for e in document.deck.entries if e.section == 'commander']
    ordered = sorted(document.deck.entries, key=lambda e: e.sort_order)
    moving = [e for e in ordered if e.entry_id in ids]
    remaining = [e for e in ordered if e.entry_id not in ids]
    position = next((i for i, e in enumerate(remaining) if e.entry_id == before_id), len(remaining))
    ordered = remaining[:position] + moving + remaining[position:]
    for index, entry in enumerate(ordered):
        entry.sort_order = index
