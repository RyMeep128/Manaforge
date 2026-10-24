"""Browse ranked candidates using card facts and comparable source evidence."""
from datetime import date, timedelta

CATEGORIES = ("Top Cards", "New Cards", "High Lift", "Creatures", "Instants",
              "Sorceries", "Utility Artifacts", "Enchantments", "Planeswalkers",
              "Utility Lands", "Mana Artifacts", "Lands")
TYPE_CATEGORIES = {"Creature": "Creatures", "Instant": "Instants", "Sorcery": "Sorceries",
                   "Enchantment": "Enchantments", "Planeswalker": "Planeswalkers", "Land": "Lands"}


def categories(row):
    from .recommendation_panel import card_types
    facts = row['entry'].extras.get('facts') or {}
    types = card_types(row['entry'])
    result = {'Top Cards'} | {label for kind, label in TYPE_CATEGORIES.items() if kind in types}
    text = " ".join([facts.get('oracle_text') or '', *[
        face.get('oracle_text') or '' for face in facts.get('card_faces') or []]]).casefold()
    roles = {r['name'].casefold() for r in row.get('roles', [])}
    if 'Artifact' in types:
        mana = ('add ' in text and ('mana' in text or '{' in text)) or bool(roles & {'ramp', 'mana ramp'})
        result.add('Mana Artifacts' if mana else 'Utility Artifacts')
    if 'Land' in types:
        # A non-mana activated ability, trigger, or static utility is evidence.
        lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith('(')]
        if any((':' in line and 'add ' not in line) or
               any(term in line for term in ('draw ', 'search your library', 'destroy ', 'exile ',
                                            'whenever ', 'creatures you control', 'becomes a ')) for line in lines):
            result.add('Utility Lands')
    try:
        released = date.fromisoformat(facts.get('released_at') or '')
        if date.today() - timedelta(days=180) <= released <= date.today():
            result.add('New Cards')
    except (ValueError, TypeError):
        pass
    # Compare inclusion and baseline only within the same supported source.
    # EDHREC synergy is deliberately not interpreted as lift.
    for source, evidence in row.get('source_evidence', {}).items():
        if source != 'archidekt':
            continue
        baseline, inclusion = evidence.get('baseline'), evidence.get('inclusion')
        if (evidence.get('sample', 0) > 0 and isinstance(baseline, (float, int))
                and isinstance(inclusion, (float, int)) and baseline > 0
                and inclusion / baseline >= 2):
            result.add('High Lift')
    return result


def matches(row, category='Top Cards', identity=None, mana_value=-1):
    facts = row['entry'].extras.get('facts') or {}
    return (category in categories(row)
            and (identity is None or ('color_identity' in facts and facts['color_identity'] is not None
                                     and set(facts['color_identity']) <= set(identity)))
            and (mana_value < 0 or facts.get('cmc') == mana_value))
