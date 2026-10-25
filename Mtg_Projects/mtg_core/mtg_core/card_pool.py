"""Shared deck-aware search defaults, separate from explicit browsing filters."""
import json
import re

from .search.syntax import Parser


def oracle_tag_query(value):
    value = str(value).strip()
    return 'otag:' + (json.dumps(value, ensure_ascii=False)
                      if any(c.isspace() or c in '\\"' for c in value) else value)


def pool_context(document):
    format_name = (document.deck.format or '').casefold()
    if format_name == 'custom':
        format_name = ''
    identity = None
    if format_name == 'commander':
        commanders = [e for e in document.deck.entries if e.quantity > 0 and
                      (e.section == 'commander' or e.entry_id in document.deck.commander_entry_ids)]
        facts = [e.extras.get('facts') or {} for e in commanders]
        if facts and all(f.get('color_identity') is not None for f in facts):
            colors = set().union(*(set(f['color_identity']) for f in facts))
            known = True
            for entry, fact in zip(commanders, facts):
                text = ' '.join(f.get('oracle_text') or '' for f in fact.get('card_faces') or [fact])
                if 'choose a color before the game begins' in text.casefold():
                    choice = document.deck.extras.get('commander_colors', {}).get(entry.entry_id)
                    if isinstance(choice, str) and len(choice) == 1 and choice in 'WUBRG':
                        colors.add(choice)
                    else:
                        known = False
            if known:
                identity = ''.join(c for c in 'WUBRG' if c in colors)
    return format_name, identity, bool(document.editor_preferences.get('include_illegal_cards', False))


def deck_query(query, document):
    """Explicit format/identity terms override only their corresponding default.

    Inspect lexer tokens so operator-looking text inside quoted names or Oracle
    text does not disable the defaults. Leave malformed input to the search UI.
    """
    query = query.strip()
    if not query:
        return query
    format_name, identity, include_illegal = pool_context(document)
    if include_illegal:
        return query
    try:
        tokens = Parser(query).tokens
    except ValueError:
        return query
    fields = {m[1].casefold() for token in tokens
              if (m := re.match(r'^-?([a-zA-Z_]+)(?::|[<>=!])', token))}
    terms = ['(' + query + ')']
    if format_name and not fields & {'f', 'format', 'legal', 'banned', 'restricted'}:
        terms.append('(legal:vintage or restricted:vintage)' if format_name == 'vintage' else 'legal:' + format_name)
    if identity is not None and not fields & {'id', 'ci', 'identity'}:
        terms.append('id<=' + (identity or 'C'))
    return ' '.join(terms) if len(terms) > 1 else query


def in_card_pool(payload, document):
    format_name, identity, include_illegal = pool_context(document)
    if include_illegal:
        return True
    # Vintage restricted cards are still playable (one copy).
    if format_name and (payload.get('legalities') or {}).get(format_name) not in (
            ('legal', 'restricted') if format_name == 'vintage' else ('legal',)):
        return False
    return identity is None or (payload.get('color_identity') is not None and
                                set(payload['color_identity']) <= set(identity))
