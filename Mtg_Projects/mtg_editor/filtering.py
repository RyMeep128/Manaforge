"""Read-only deck filters over cached card facts; no database work while typing."""
import operator
import re
import shlex
from functools import lru_cache

ALIASES = {'t': 'type', 'o': 'oracle', 'c': 'color', 'id': 'identity',
           'cmc': 'mv', 'r': 'rarity', 's': 'set', 'kw': 'keyword'}
FIELDS = {'name', 'tag', 'category', 'section', 'type', 'oracle', 'color',
          'identity', 'mv', 'power', 'toughness', 'rarity', 'set', 'artist',
          'keyword', 'legal', 'treatment', 'is'}
OPS = {'=': operator.eq, ':': operator.eq, '>': operator.gt,
       '<': operator.lt, '>=': operator.ge, '<=': operator.le}
FLAGS = {'oversized', 'excluded', 'do-not-print', 'owned', 'back', 'dfc'}
HELP = ('Combine filters with spaces; prefix a term with - to exclude it. '
        'Use double quotes for phrases. Examples: type:creature mv<=3, '
        'id:wu, color=c, category:"Card Draw", legal:commander, is:oversized. '
        'Fields: name, tag, category, section, type, oracle, color, identity, mv, '
        'power, toughness, rarity, set, artist, keyword, legal, treatment. '
        'Flags: oversized, excluded, do-not-print, owned, back, dfc. '
        'Color : means contains; = means exact. Missing metadata does not match '
        'positive filters. Filters affect the view only.')


@lru_cache(maxsize=128)
def compile_filter(query):
    if not re.search(r'[a-zA-Z]+[:=<>]|(?:^|\s)-|"', query):
        return (('', ':', query.casefold(), False),) if query else ()
    lexer = shlex.shlex(query, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ''
    lexer.quotes = '"'
    terms = []
    for token in lexer:
        negate = token.startswith('-')
        token = token[1:] if negate else token
        match = re.fullmatch(r'([a-zA-Z]+)(:|<=|>=|=|<|>)(.*)', token)
        field, op, value = match.groups() if match else ('', ':', token)
        field = ALIASES.get(field.lower(), field.lower())
        value = value.casefold()
        if field and field not in FIELDS:
            raise ValueError(f'Unknown filter: {field}')
        if not value:
            raise ValueError('Enter a value after the filter operator.')
        if field in ('mv', 'power', 'toughness'):
            try:
                float(value)
            except ValueError:
                raise ValueError(f'{field} requires a number.') from None
        elif op not in (':', '='):
            raise ValueError(f'{field or "Text"} supports : or =.')
        if field in ('color', 'identity') and (set(value) - set('wubrgc') or ('c' in value and value != 'c')):
            raise ValueError('Use W, U, B, R, G, or C for colorless.')
        if field == 'is' and value not in FLAGS:
            raise ValueError(f'Unknown flag: {value}')
        terms.append((field, op, value, negate))
    return tuple(terms)


def matches(entry, terms, categories):
    facts = entry.extras.get('facts', {})
    faces = facts.get('card_faces') or []

    def test(field, op, value):
        if field in ('mv', 'power', 'toughness'):
            raw = facts.get('cmc' if field == 'mv' else field)
            try:
                return OPS[op](float(raw), float(value))
            except (TypeError, ValueError):
                return False
        if field in ('color', 'identity'):
            raw = facts.get('colors' if field == 'color' else 'color_identity')
            if raw is None:
                return False
            actual, wanted = set(''.join(raw).lower()), set() if value == 'c' else set(value)
            return actual == wanted if op == '=' or not wanted else wanted <= actual
        if field == 'legal':
            return (facts.get('legalities') or {}).get(value) == 'legal'
        if field == 'is':
            return {'oversized': bool(entry.extras.get('oversized')),
                    'excluded': entry.section == 'excluded',
                    'do-not-print': entry.do_not_print, 'owned': entry.owned > 0,
                    'back': bool(entry.extras.get('backside_asset_id') or entry.extras.get('backside_name')),
                    'dfc': facts.get('layout') in ('transform', 'modal_dfc', 'double_faced_token', 'reversible_card', 'art_series')}[value]
        if field == 'treatment':
            raw = list(facts.get('finishes') or []) + list(facts.get('frame_effects') or [])
            raw += [key for key in ('promo', 'textless', 'full_art', 'borderless') if facts.get(key)]
            raw += [facts.get('border_color') or '']
        elif field in ('type', 'oracle'):
            key = 'type_line' if field == 'type' else 'oracle_text'
            raw = [facts.get(key) or ''] + [face.get(key) or '' for face in faces]
        else:
            raw = {'': [entry.name, *entry.tags], 'name': entry.name,
                   'tag': entry.tags, 'category': [categories.get(c, c) for c in entry.category_ids],
                   'section': entry.section, 'set': entry.set_code,
                   'keyword': facts.get('keywords')}.get(field, facts.get(field))
        if raw is None:
            return False
        values = raw if isinstance(raw, list) else [raw]
        return any(value == str(item).casefold() if op == '=' else value in str(item).casefold()
                   for item in values)

    return all(test(field, op, value) != negate for field, op, value, negate in terms)
