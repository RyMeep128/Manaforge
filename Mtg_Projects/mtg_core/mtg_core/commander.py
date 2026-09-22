"""Explainable Commander deck-construction checks against dated local card data.

Rules: https://magic.wizards.com/en/rules (903, 702.124).
Vehicle/Spacecraft eligibility: Wizards' Edge of Eternities update bulletin.
This is a deck checker, not a rules engine or an online legality guarantee.
"""
from dataclasses import dataclass, field
import re
import time

RULE_VERSION = '2 (reviewed 2026-09-21)'
STALE_DAYS = 30


@dataclass
class Issue:
    severity: str
    code: str
    message: str
    entry_ids: tuple = ()


@dataclass
class Report:
    total: int
    issues: list = field(default_factory=list)
    oldest_cache: float | None = None

    @property
    def summary(self):
        errors = sum(i.severity == 'Error' for i in self.issues)
        unknown = sum(i.severity == 'Unknown' for i in self.issues)
        if errors:
            return f'{errors} violations found; {unknown} checks uncertain'
        return 'Review needed — incomplete or stale data' if unknown else 'No violations detected in local data'


def front(payload):
    return (payload.get('card_faces') or [payload])[0]


def oracle(payload):
    return str(front(payload).get('oracle_text') or '').replace('’', "'")


def abilities(payload):
    # Match ability lines, not ability names mentioned inside another card's text.
    text = re.sub(r'\([^)]*\)', '', oracle(payload)).casefold()
    return {line.strip().rstrip('.') for line in text.splitlines() if line.strip()}


def eligible(payload):
    face = front(payload)
    line = face.get('type_line')
    if not line or face.get('oracle_text') is None:
        return None
    text = oracle(payload).casefold()
    name = str(face.get('name') or payload.get('name') or '').casefold()
    if (name and f'{name} can be your commander.' in text) or 'this card can be your commander.' in text:
        return True
    if 'Legendary' not in line:
        return False
    if 'Creature' in line:
        return True
    if 'Vehicle' in line or 'Spacecraft' in line:
        return face.get('power') is not None and face.get('toughness') is not None
    return False


def compatible(left, right):
    """True/False/None: unknown data cannot establish an invalid pairing."""
    if any(not front(p).get('type_line') or front(p).get('oracle_text') is None for p in (left, right)):
        return None
    a, b = abilities(left), abilities(right)
    if eligible(left) and eligible(right):
        if 'partner' in a & b or 'friends forever' in a & b:
            return True
        if any(re.fullmatch(r'partner\s*[—–-]\s*.+', ability) for ability in a & b):
            return True
        names = [str(front(p).get('name') or p.get('name') or '').casefold() for p in (left, right)]
        if names[0] and names[1] and f'partner with {names[1]}' in a and f'partner with {names[0]}' in b:
            return True
    for chooser, background in ((left, right), (right, left)):
        line = front(background).get('type_line', '')
        if eligible(chooser) and 'choose a background' in abilities(chooser):
            if all(word in line.split() for word in ('Legendary', 'Enchantment', 'Background')):
                return True
        if "doctor's companion" in abilities(chooser) and eligible(chooser):
            doctor_type = front(background).get('type_line', '')
            types = doctor_type.partition('—')[2].strip()
            if 'Legendary' in doctor_type and 'Creature' in doctor_type and types == 'Time Lord Doctor':
                return True
    if any('partner' in word for word in a | b) and not (eligible(left) and eligible(right)):
        return None
    return False


def copy_limit(payload, default=1):
    face = front(payload)
    if not face.get('type_line') or face.get('oracle_text') is None:
        return None
    if 'Basic' in face['type_line'].split() and 'Land' in face['type_line'].split():
        return float('inf')
    text = oracle(payload).casefold()
    name = str(face.get('name') or payload.get('name') or '').casefold()
    if not name:
        return None
    if f'a deck can have any number of cards named {name}.' in text:
        return float('inf')
    match = re.search(r'a deck can have up to (\w+) cards named ' + re.escape(name) + r'\.', text)
    if match:
        words = dict(zip('one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen'.split(), range(1, 16)))
        return int(match[1]) if match[1].isdigit() else words.get(match[1])
    if 'a deck can have' in text:
        return None
    return default


def check_commander(document, records, *, now=None):
    now = time.time() if now is None else now
    entries = [e for e in document.deck.entries if e.section in ('mainboard', 'commander')]
    companion_id = document.deck.extras.get('companion_entry_id')
    companion = next((e for e in document.deck.entries if e.entry_id == companion_id), None)
    commanders = [e for e in entries if e.section == 'commander']
    report = Report(sum(e.quantity for e in entries))
    def issue(severity, code, message, selected=()):
        report.issues.append(Issue(severity, code, message, tuple(e.entry_id for e in selected)))
    payloads = {e.entry_id: records.get(e.card_id, {}).get('payload',
                {'name': e.name, **e.extras.get('facts', {})}) for e in entries}
    if report.total != 100:
        issue('Error', 'size', f'The main deck plus commanders contains {report.total} cards; expected 100.')
    if len(commanders) not in (1, 2):
        issue('Error', 'commanders', 'Choose one commander or a supported pair.', commanders)
    if any(e.quantity != 1 for e in commanders):
        issue('Error', 'commander_quantity', 'Each commander must have quantity 1.', commanders)
    if len(commanders) == 1:
        status = eligible(payloads[commanders[0].entry_id])
        if status is not True:
            issue('Unknown' if status is None else 'Error', 'eligibility',
                  'Commander eligibility is unknown.' if status is None else 'This card is not eligible as a single commander.', commanders)
    elif len(commanders) == 2:
        status = compatible(*(payloads[e.entry_id] for e in commanders))
        if status is not True:
            issue('Unknown' if status is None else 'Error', 'pairing',
                  'Commander pairing could not be established.' if status is None else 'These commanders do not have compatible partner/background abilities.', commanders)
    identity = set()
    identity_known = bool(commanders)
    for entry in commanders:
        colors = payloads[entry.entry_id].get('color_identity')
        if colors is None:
            identity_known = False
        else:
            identity.update(colors)
        if 'choose a color before the game begins' in oracle(payloads[entry.entry_id]).casefold():
            choice = document.deck.extras.get('commander_colors', {}).get(entry.entry_id)
            if isinstance(choice, str) and len(choice) == 1 and choice in 'WUBRG':
                identity.add(choice)
            else:
                identity_known = False
    if not identity_known:
        issue('Unknown', 'commander_identity', 'Commander color identity is missing or needs a pregame color choice.', commanders)
    groups, stale, undated, dates = {}, [], [], []
    oracle_names = {p['oracle_id']: p.get('name', '').casefold() for p in payloads.values() if p.get('oracle_id') and p.get('name')}
    checked_entries = list(entries)
    if companion:
        if companion.section != 'sideboard' or companion.quantity != 1:
            issue('Error', 'companion_selection', 'The companion must be one card outside the starting deck (sideboard).', [companion])
        if companion.entry_id not in payloads:
            payloads[companion.entry_id] = records.get(companion.card_id, {}).get('payload', {'name': companion.name, **companion.extras.get('facts', {})})
            checked_entries.append(companion)
        cp = payloads[companion.entry_id]
        if not any(a.startswith('companion') for a in abilities(cp)):
            issue('Unknown' if front(cp).get('oracle_text') is None else 'Error', 'companion_ability', 'Selected card does not have a verified companion ability.', [companion])
        else:
            from .companions import companion_restriction
            bad, unknown, explanation = companion_restriction(cp.get('name') or companion.name, entries, payloads)
            if bad:
                issue('Error', 'companion_restriction', explanation, [e for e in entries if e.entry_id in bad] or [companion])
            if unknown:
                issue('Unknown', 'companion_restriction', explanation + ' Some card characteristics need review.', [e for e in entries if e.entry_id in unknown])
    elif companion_id:
        issue('Error', 'companion_selection', 'The saved companion is missing from the deck.')
    for entry in checked_entries:
        payload = payloads[entry.entry_id]
        name = oracle_names.get(payload.get('oracle_id') or entry.oracle_id) or str(payload.get('name') or entry.name).casefold()
        groups.setdefault(name, []).append(entry)
        if entry.quantity < 1:
            issue('Error', 'quantity', f'{entry.name}: quantity must be positive.', [entry])
        colors = payload.get('color_identity')
        if colors is None:
            issue('Unknown', 'identity', f'{entry.name}: color identity unavailable.', [entry])
        elif identity_known and set(colors) - identity:
            issue('Error', 'identity', f'{entry.name}: color identity exceeds the commanders’ identity.', [entry])
        land_colors = set()
        for face in payload.get('card_faces') or [payload]:
            line = face.get('type_line') or ''
            if 'Land' in line.split():
                land_colors.update(c for kind, c in zip(('Plains', 'Island', 'Swamp', 'Mountain', 'Forest'), 'WUBRG') if kind in line.split())
        if identity_known and land_colors - identity:
            issue('Error', 'land_types', f'{entry.name}: basic land types produce colors outside the commander identity.', [entry])
        legality = (payload.get('legalities') or {}).get('commander')
        if legality != 'legal':
            known = legality in ('banned', 'not_legal')
            issue('Error' if known else 'Unknown', 'legality',
                  f'{entry.name}: {legality or "unknown legality"} in local Commander data.', [entry])
        cached = records.get(entry.card_id, {}).get('cached_at')
        if not cached or cached > now:
            undated.append(entry)
        else:
            dates.append(cached)
            if now - cached > STALE_DAYS * 86400:
                stale.append(entry)
    for copies in groups.values():
        count = sum(e.quantity for e in copies)
        if count <= 1:
            continue
        limits = [copy_limit(payloads[e.entry_id]) for e in copies]
        if any(limit is None for limit in limits):
            issue('Unknown', 'singleton', f'{copies[0].name}: cannot verify the {count} copies with incomplete Oracle data.', copies)
        elif count > min(limits):
            issue('Error', 'singleton', f'{copies[0].name}: {count} copies; allowed {min(limits)}.', copies)
    if stale:
        issue('Unknown', 'stale', f'{len(stale)} entries have card data cached more than {STALE_DAYS} days ago. Refresh Core data.', stale)
    if undated:
        issue('Unknown', 'undated', f'{len(undated)} entries have no reliable cache date. Current legality is unverified.', undated)
    report.oldest_cache = min(dates) if dates else None
    return report


def set_commanders(document, ids):
    """Replace commander selection without deleting cards or changing quantities."""
    ids = list(ids)
    if len(ids) > 2 or len(set(ids)) != len(ids):
        raise ValueError('Choose at most two different cards.')
    if set(ids) - {e.entry_id for e in document.deck.entries}:
        raise ValueError('A selected commander is no longer in this deck.')
    for entry in document.deck.entries:
        if entry.entry_id in ids:
            entry.section = 'commander'
        elif entry.section == 'commander':
            entry.section = 'mainboard'
    document.deck.commander_entry_ids = ids
