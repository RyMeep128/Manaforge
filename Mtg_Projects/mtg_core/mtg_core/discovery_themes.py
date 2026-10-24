"""Local theme browsing rules; never claim these are EDHREC card associations."""
import re

# Query mechanics and roles, never card-name lists or invented source statistics.
LOCAL_THEMES = (
    ('tokens', 'Tokens', 'Themes', 'o:"create" o:"token"', ('Tokens',)),
    ('plus-1-plus-1-counters', '+1/+1 Counters', 'Themes', 'o:"+1/+1 counter"', ('Counters',)),
    ('combo', 'Combo', 'Themes', 'otag:combo', ()),
    ('artifacts', 'Artifacts', 'Themes', 't:artifact', ('Artifact',)),
    ('aggro', 'Aggro', 'Themes', 't:creature mv<=3', ()),
    ('spellslinger', 'Spellslinger', 'Themes', '(t:instant or t:sorcery or o:"instant or sorcery")', ('Spellslinger',)),
    ('reanimator', 'Reanimator', 'Themes', 'o:"graveyard" o:"battlefield"', ('Recursion',)),
    ('lifegain', 'Lifegain', 'Themes', '(o:"gain life" or o:"gain" o:"life" or keyword:lifelink)', ('Lifegain',)),
    ('aristocrats', 'Aristocrats', 'Themes', '(o:"sacrifice" or o:"dies")', ('Sacrifice / Aristocrats',)),
    ('enchantress', 'Enchantress', 'Themes', '(t:enchantment or o:"enchantment")', ('Enchantment',)),
    ('blink', 'Blink', 'Themes', 'o:"exile" o:"return"', ('Blink',)),
    ('landfall', 'Landfall', 'Themes', '(keyword:landfall or o:"land" o:"enters")', ()),
    ('voltron', 'Voltron', 'Themes', '(t:equipment or t:aura or o:"equipped creature")', ('Equipment',)),
    ('vehicles', 'Vehicles', 'Themes', '(t:vehicle or o:"vehicle")', ('Vehicle',)),
)


def slug(value):
    return re.sub(r'[^a-z0-9]+', '-', value.casefold()).strip('-')


def plural(value):
    irregular = {'elf': 'elves', 'dwarf': 'dwarves', 'wolf': 'wolves', 'mouse': 'mice', 'ox': 'oxen', 'merfolk': 'merfolk', 'fish': 'fish', 'sheep': 'sheep',
                 'deer': 'deer', 'elk': 'elk', 'moose': 'moose', 'eldrazi': 'eldrazi', 'djinn': 'djinn'}
    if value in irregular:
        return irregular[value]
    if value.endswith(('s', 'sh', 'ch', 'x')):
        return value + 'es'
    if value.endswith('y') and len(value) > 1 and value[-2] not in 'aeiou':
        return value[:-1] + 'ies'
    return value + 's'


def theme_catalog(cached, metadata):
    """Cached themes keep their exact membership; local options have an explicit origin."""
    types = {plural(slug(t)): t for t in metadata.get('creature_types', [])}
    local = {key: dict(slug=key, name=name, group=group, query=query, roles=list(roles), origin='local')
             for key, name, group, query, roles in LOCAL_THEMES}
    for key, name in types.items():
        local[key] = dict(slug=key, name=key.replace('-', ' ').title(), group='Typal',
                          query=f't:"{name}"', roles=[], subtype=name, origin='local')
    for card in metadata.get('companions', []):
        key = slug(card['name'].split(',')[0])
        local[key] = dict(slug=key, name=card['name'], group='Companions', query='',
                          roles=[], origin='local', companion=card['oracle_id'],
                          companion_name=card['name'], companion_identity=card.get('color_identity'),
                          companion_legal=card.get('legal'))
    for item in cached:
        key = item['slug']
        item = dict(item, group=local.get(key, {}).get('group', 'Themes'), origin='edhrec')
        local[key] = {**local.get(key, {}), **item}
    return sorted(local.values(), key=lambda row: row['name'].casefold())


def theme_matches(row, theme):
    if not theme:
        return True
    facts = row['entry'].extras.get('facts') or {}
    if theme.get('companion'):
        # Companion selection is an idea filter, not an assertion of deck legality.
        from copy import copy
        from .companions import companion_restriction
        entry = copy(row['entry'])
        entry.quantity = 1
        bad, unknown, _ = companion_restriction(theme.get('companion_name', theme['name']),
                                                 [entry], {entry.entry_id: facts})
        return not bad and not unknown
    key = theme.get('slug', '')
    roles = {r['name'].casefold() for r in row.get('roles', [])}
    tags = {slug(tag) for tag in facts.get('oracle_tags', [])}
    keywords = {slug(word) for word in facts.get('keywords') or []}
    if key in tags | keywords | {slug(role) for role in roles} or roles & {r.casefold() for r in theme.get('roles', [])}:
        return True
    faces = facts.get('card_faces') or [facts]
    text = ' '.join(f.get('oracle_text') or '' for f in faces).casefold()
    types = ' '.join(f.get('type_line') or '' for f in faces).casefold()
    if theme.get('subtype'):
        return theme['subtype'].casefold() in re.findall(r"[\w'-]+", types)
    if key == 'aggro':
        return 'creature' in types and isinstance(facts.get('cmc'), (int, float)) and facts['cmc'] <= 3
    if key == 'landfall':
        return 'landfall' in text or bool(re.search(r'whenever [^.]{0,50}land[^.]{0,80}enters', text))
    if key in {'artifacts', 'vehicles', 'enchantress', 'voltron'}:
        return any(term in types or term in text for term in {
            'artifacts': ('artifact',), 'vehicles': ('vehicle',),
            'enchantress': ('enchantment',), 'voltron': ('equipment', 'aura', 'equipped creature')}[key])
    if key == 'spellslinger':
        return 'instant' in types or 'sorcery' in types
    return False
