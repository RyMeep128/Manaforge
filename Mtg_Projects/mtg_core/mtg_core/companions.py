"""Companion deck restrictions; unsupported or incomplete characteristics stay unknown."""
import re

TYPES = {'Artifact', 'Battle', 'Creature', 'Enchantment', 'Instant', 'Kindred', 'Planeswalker', 'Sorcery', 'Land'}
ACTIVATED = {'cycling', 'equip', 'crew', 'reconfigure', 'ninjutsu', 'commander ninjutsu', 'unearth',
             'transmute', 'transfigure', 'level up', 'outlast', 'scavenge', 'adapt', 'monstrosity',
             'embalm', 'eternalize', 'encore', 'forecast', 'fortify', 'reinforce', 'station', 'craft'}


def characteristics(payload):
    if payload.get('layout') == 'split':
        return {**payload, 'mana_cost': ''.join(f.get('mana_cost', '') for f in payload.get('card_faces', []))}
    face = (payload.get('card_faces') or [payload])[0]
    result = {**payload, **face}
    if payload.get('card_faces'):
        result['keywords'] = [key for key in ACTIVATED if re.search(r'^' + re.escape(key) + r'\b', face.get('oracle_text') or '', re.I | re.M)]
    return result


def activated(face):
    text = face.get('oracle_text')
    if text is None:
        return None
    line = face.get('type_line') or ''
    if 'Land' in line and any(t in line.split() for t in ('Plains', 'Island', 'Swamp', 'Mountain', 'Forest')):
        return True
    keywords = {str(k).casefold() for k in face.get('keywords', [])}
    if keywords & ACTIVATED or any(k.endswith('cycling') for k in keywords):
        return True
    unquoted = re.sub(r'["“].*?["”]', '', text, flags=re.S)
    for clause in unquoted.splitlines():
        if ':' in clause and not re.search(r'\b(has|have|gains?|with)\b', clause.split(':')[0], re.I):
            return True
    if ':' in text or re.search(r'\b(has|have|gains?)\b.*activated', text, re.I):
        return None
    return False


def companion_restriction(name, entries, payloads, *, commander=True):
    """Return (violating entry IDs, uncertain entry IDs, explanation)."""
    kind = name.split(',')[0].casefold()
    supported = {'gyruda', 'jegantha', 'kaheera', 'keruga', 'lurrus', 'lutri', 'obosh', 'umori', 'yorion', 'zirda'}
    if kind not in supported:
        return [], [e.entry_id for e in entries] or ['deck'], 'This companion restriction is not supported by this checker.'
    if kind == 'yorion':
        minimum = 120 if commander else 80
        bad = sum(e.quantity for e in entries) < minimum
        return (['deck'] if bad else []), [], f'Yorion requires at least {minimum} starting cards; Commander permits exactly 100.' if commander else 'Yorion requires at least 80 starting cards.'
    violations, unknown, common, names = [], [], None, {}
    for entry in entries:
        face = characteristics(payloads[entry.entry_id])
        if not face.get('type_line'):
            unknown.append(entry.entry_id)
            continue
        words = set(face['type_line'].replace('Tribal', 'Kindred').split())
        land = 'Land' in words
        permanent = bool(words & {'Artifact', 'Battle', 'Creature', 'Enchantment', 'Land', 'Planeswalker'})
        mana = face.get('cmc')
        result = True
        if kind in ('gyruda', 'obosh', 'keruga', 'lurrus'):
            needs_check = kind == 'gyruda' or (kind in ('obosh', 'keruga') and not land) or (kind == 'lurrus' and permanent)
            if needs_check:
                result = None if mana is None else (mana % 2 == 0 if kind == 'gyruda' else
                    mana % 2 == 1 if kind == 'obosh' else mana >= 3 if kind == 'keruga' else mana <= 2)
        elif kind == 'jegantha':
            cost = face.get('mana_cost')
            symbols = re.findall(r'\{([^}]+)\}', cost or '')
            result = None if cost is None else len(symbols) == len(set(symbols))
        elif kind == 'kaheera' and 'Creature' in words:
            result = bool(words & {'Cat', 'Elemental', 'Nightmare', 'Dinosaur', 'Beast'}) or bool(re.search(r'^changeling\b', face.get('oracle_text') or '', re.I | re.M))
            if not result and face.get('oracle_text') is None:
                result = None
        elif kind == 'zirda' and permanent:
            result = activated(face)
        elif kind == 'umori' and not land:
            card_types = words & TYPES
            common = card_types if common is None else common & card_types
        elif kind == 'lutri' and not land:
            key = (face.get('name') or entry.name).casefold()
            names.setdefault(key, []).append(entry)
        if result is False:
            violations.append(entry.entry_id)
        elif result is None:
            unknown.append(entry.entry_id)
    if kind == 'umori' and common == set():
        violations = [e.entry_id for e in entries if 'Land' not in (characteristics(payloads[e.entry_id]).get('type_line') or '').split()]
    if kind == 'lutri':
        violations = [e.entry_id for group in names.values() if sum(e.quantity for e in group) > 1 for e in group]
    explanations = {'gyruda': 'Every starting card must have even mana value.',
        'jegantha': 'No starting card may repeat a mana symbol in its mana cost.',
        'kaheera': 'Every starting creature must be a Cat, Elemental, Nightmare, Dinosaur, or Beast.',
        'keruga': 'Every nonland starting card must have mana value 3 or greater.',
        'lurrus': 'Every starting permanent must have mana value 2 or less.',
        'lutri': 'Nonland starting cards must have different names.',
        'obosh': 'Every nonland starting card must have odd mana value.',
        'umori': 'All nonland starting cards must share a card type.',
        'zirda': 'Every starting permanent must have an activated ability.'}
    return violations, unknown, explanations[kind]
