"""Browsing classifications from card facts, shared roles, and source metadata."""
from datetime import date, timedelta
import math
import re

from mtg_core.category_rules import clean_text
from mtg_core.role_analysis import analyze_effects
from mtg_core.discovery_themes import theme_matches

CATEGORIES = ("Top Cards", "New Cards", "High Lift", "Creatures", "Instants",
              "Sorceries", "Utility Artifacts", "Enchantments", "Planeswalkers",
              "Utility Lands", "Mana Artifacts", "Lands")
TYPE_CATEGORIES = {"Creature": "Creatures", "Instant": "Instants", "Sorcery": "Sorceries",
                   "Enchantment": "Enchantments", "Planeswalker": "Planeswalkers", "Land": "Lands"}


def card_types(entry):
    facts = entry.extras.get('facts') or {}
    lines = [facts.get('type_line') or ''] + [f.get('type_line') or '' for f in facts.get('card_faces') or []]
    return {word for line in lines for half in line.split('//')
            for word in half.split('\u2014')[0].split()} & set(TYPE_CATEGORIES) | (
                {'Artifact'} if any('Artifact' in line.split('\u2014')[0].split() for line in lines) else set())


def categories(row):
    if 'browse_categories' in row:
        return set(row['browse_categories'])
    facts = row['entry'].extras.get('facts') or {}
    types = card_types(row['entry'])
    effects = analyze_effects(facts)
    roles = {r['name'].casefold() for r in row.get('roles', [])}
    roles.update(role.casefold() for role in effects)
    result = {'Top Cards'} | {label for kind, label in TYPE_CATEGORIES.items() if kind in types}
    if 'Artifact' in types:
        mana = 'ramp' in roles
        if mana:
            result.add('Mana Artifacts')
        utility_roles = roles - {'ramp', 'artifact', 'artifacts', 'creature', 'creatures', 'commander', 'lands'}
        if not mana or utility_roles:
            result.add('Utility Artifacts')
    if 'Land' in types:
        utility_roles = roles - {'ramp', 'land', 'lands', 'commander'}
        faces = facts.get('card_faces') or [facts]
        # Exclude mana abilities and common mana-fixing/entry restrictions.
        utility_ability = False
        for face in faces:
            for line in (face.get('oracle_text') or '').splitlines():
                text = clean_text(line)
                if not text or re.search(r'\badd (?:\{|[^.]{0,60}mana\b)', text):
                    continue
                if re.search(r'\b(?:enters? tapped|enters? the battlefield tapped|as [^.]{0,60}enters|you may pay|unless you control)\b', text):
                    continue
                if ':' in text or re.search(r'\b(?:whenever|at the beginning|becomes a|have |has |can.t|cannot)\b', text):
                    utility_ability = True
        if utility_roles or utility_ability:
            result.add('Utility Lands')
    try:
        # A recent printing of an old card must not count as a new card.
        released = date.fromisoformat(facts.get('first_released_at') or '')
        if date.today() - timedelta(days=180) <= released <= date.today():
            result.add('New Cards')
    except (ValueError, TypeError):
        pass
    for source, evidence in row.get('source_evidence', {}).items():
        if source == 'edhrec':
            result.update('EDHREC: ' + label for label in evidence.get('categories', []) if isinstance(label, str) and label)
        if source not in {'archidekt', 'moxfield'}:
            continue
        baseline, inclusion, sample = evidence.get('baseline'), evidence.get('inclusion'), evidence.get('sample')
        if (all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                for value in (baseline, inclusion, sample)) and sample >= 20
                and 0 < baseline <= 1 and 0 <= inclusion <= 1 and inclusion / baseline >= 2):
            result.add('High Lift')
    return result


def matches(row, category='Top Cards', identity=None, mana_value=-1, theme=None):
    facts = row['entry'].extras.get('facts') or {}
    return (category in categories(row) and theme_matches(row, theme)
            and (identity is None or (facts.get('color_identity') is not None
                                     and set(facts['color_identity']) <= set(identity)))
            and (mana_value < 0 or facts.get('cmc') == mana_value))
