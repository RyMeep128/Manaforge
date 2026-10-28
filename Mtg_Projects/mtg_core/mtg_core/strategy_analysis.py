"""Deck-local strategic evidence; no card names, network access, or UI state."""
from collections import Counter
import re
from .category_rules import clean_text, keyword_profile

# Direct payoffs/engines seed themes. Merely being an artifact or enchantment
# does not create a theme; those types join only after sufficient support.
THEMES = {
    'Goad': r"\bgoad(?:ed)?\b|\b(?:creatures|creature) [^.]{0,70}attacks? [^.]{0,40}(?:other than you|opponent)",
    'Enchantment Matters': r'\b(?:enchantment|aura)s? (?:you control|spells?|enters|cards?)|\bconstellation\b',
    'Sacrifice / Aristocrats': r'\bsacrifice (?:another|a|an) [^.]{0,45}:|\bwhenever [^.]{0,100}(?:dies|die|you sacrifice)\b',
    'Tokens': r'\bcreate [^.]{0,100}\btokens?\b|\b(?:tokens you control|populate)\b',
    'Counters': r'\+1/\+1 counters?|\bproliferate\b',
    'Lifegain': r'\bwhenever you gain life\b|\bgain [^.]{0,35}life\b',
    'Landfall': r'\blandfall\b|\bwhenever a land [^.]{0,70}enters',
    'Reanimator': r'\b(?:return|put) [^.]{0,100}\bgraveyard [^.]{0,55}\bbattlefield',
    'Graveyard': r'\b(?:from|in|into) your graveyard\b|\b(?:dredge|delve|surveil)\b',
    'Artifacts': r'\b(?:artifact spells|artifacts you control|whenever [^.]{0,60}artifact[^.]{0,50}enters|affinity for artifacts|metalcraft|improvise)\b',
    'Spellslinger': r'\b(?:instant or sorcery|noncreature) spell|\b(?:magecraft|storm|prowess)\b',
    'Blink': r'\bexile [^.]{0,90}you control[^.]{0,100}return|\bwhenever [^.]{0,70}enters[^.]{0,90}under your control',
    'Voltron': r'\b(?:equipped creature|enchanted creature|equipment you control|auras you control|equip costs?)\b',
    'Mill': r'\b(?:opponent|player)[^.]{0,35}mills?\b',
}
PATTERNS = {role: re.compile(pattern) for role, pattern in THEMES.items()}


def facts(payload):
    faces = payload.get('card_faces') or [payload]
    return clean_text(' '.join(str(f.get('oracle_text') or '') for f in faces)), str(faces[0].get('type_line') or '').casefold()


def seeds(payload):
    text, _ = facts(payload)
    roles = {role for role, pattern in PATTERNS.items() if pattern.search(text)}
    if 'Tokens' in roles and re.search(r'\b(?:treasure|gold|clue|food|blood|map|powerstone) tokens?\b', text) and not re.search(r'\bcreature tokens?\b|\btokens you control\b|\bpopulate\b', text):
        roles.discard('Tokens')
    if re.search(r'\btokens? would be created\b', text):
        roles.add('Tokens')
    possessed, granted = keyword_profile(payload)
    if len(possessed) >= 3 or len(granted) >= 2:
        roles.add('Keyword Soup')
    return roles


def creature_types(payload):
    _, types = facts(payload)
    if 'creature' not in types or '\u2014' not in types:
        return set()
    return set(types.split('\u2014', 1)[1].split('//')[0].split())


def mentions(text, tribe):
    plural = {'elf': 'elves', 'dwarf': 'dwarves', 'mouse': 'mice', 'wolf': 'wolves'}.get(tribe, tribe + 's')
    return bool(re.search(r'\b(?:' + re.escape(tribe) + '|' + re.escape(plural) + r')\b', text))


def strategy_context(payloads, commanders):
    payloads, commanders = list(payloads), list(commanders)
    counts = Counter(role for p in payloads for role in seeds(p))
    commander_roles = set().union(*(seeds(p) for p in commanders)) if commanders else set()
    themes = sorted(role for role, count in counts.items()
                    if count >= 5 or (role in commander_roles and count >= 2))
    types = Counter(t for p in payloads for t in creature_types(p))
    creatures = sum(bool(creature_types(p)) for p in payloads)
    tribes = []
    for tribe, count in sorted(types.items()):
        # A commander naming its own type is not itself a tribal payoff.
        commander_support = any(mentions(facts(p)[0], tribe) and re.search(
            r'\b(?:other|whenever|spells|each|for each|you control|cost)\b', facts(p)[0]) for p in commanders)
        payoffs = sum(mentions(facts(p)[0], tribe) and bool(re.search(
            r'\b(?:you control|spells|for each|whenever|chosen (?:creature )?type)\b', facts(p)[0])) for p in payloads)
        if (count >= 8 and count >= creatures * .25) or (count >= 4 and (commander_support or payoffs >= 2)):
            tribes.append(tribe)
    return {'themes': themes, 'tribes': tribes, 'commander_themes': sorted(commander_roles)}


def memberships(payload, context):
    text, types = facts(payload)
    roles = seeds(payload).intersection(context.get('themes', []))
    for role, kind in (('Enchantment Matters', 'enchantment'), ('Artifacts', 'artifact'), ('Voltron', 'aura')):
        if role in context.get('themes', []) and kind in types:
            roles.add(role)
    tribes = context.get('tribes', [])
    if tribes and (creature_types(payload).intersection(tribes) or 'changeling' in text
                   or any(mentions(text, tribe) for tribe in tribes)
                   or re.search(r'\b(?:chosen creature type|choose a creature type|every creature type)\b', text)):
        roles.add('Tribal')
    return roles
