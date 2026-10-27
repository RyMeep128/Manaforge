"""Weighted effect evidence, independent of deck category names and card names.

Scores express strategic prominence, not probabilities. Rules are deliberately
bounded to an ability/sentence; this is not a Magic rules interpreter.
"""
from functools import lru_cache
import json
import re

from .category_rules import clean_text, text_roles


BASE_SCORES = {
    'Board Wipes': 180, 'Counterspells': 175, 'Interaction': 170,
    'Ramp': 160, 'Removal': 150, 'Tutors': 145, 'Recursion': 145,
    'Protection': 120, 'Win Conditions': 130, 'Draw': 142,
    'Card Advantage': 138, 'Tokens': 143, 'Lifegain': 135,
    'Graveyard': 135, 'Sacrifice / Aristocrats': 125, 'Utility': 50,
}

# Effects missing from the original conservative role hints. Different kinds of
# evidence within a role use max(), not occurrence counts.
EFFECTS = (
    ('Enchantment Matters', 140, 'rewards enchantments or Auras',
     r'\b(?:whenever|when) [^.]{0,90}(?:cast [^.]{0,40}(?:enchantment|aura)|(?:enchantment|aura)[^.]{0,60}enters)|\b(?:for each|number of) (?:aura|enchantment)s?\b|\b(?:aura|enchantment)s? you control\b'),
    ('Enchantment Matters', 140, 'rewards enchanted creatures',
     r'\bwhenever [^.]{0,70}\benchanted creature[^.]{0,70}\b(?:attacks|deals|dies)\b|\benchanted creatures you control\b'),
    ('Enchantment Matters', 140, 'finds or recovers enchantments or Auras',
     r'\b(?:search|put|return|attach) [^.]{0,160}\b(?:enchantment|aura) cards?\b'),
    ('Recursion', 145, 'attaches Auras from your graveyard',
     r'\battach [^.]{0,180}\baura cards?[^.]{0,100}\bfrom your graveyard\b'),
    ('Card Advantage', 138, 'reveals library cards for hand',
     r'\breveal [^.]{0,100}\b(?:top|library)\b[^.]{0,100}\. (?:you may )?put [^.]{0,160}\binto your hand\b'),
    ('Card Advantage', 138, 'reveals a library permanent onto the battlefield',
     r'\breveal [^.]{0,120}\blibrary until\b[^.]{0,100}\. put [^.]{0,80}\bonto the battlefield\b'),
    ('Draw', 160, 'draws cards equal to combat damage',
     r'\bwhenever [^.]{0,140}combat damage[^.]{0,100}\bdraw that many cards\b'),
    ('Protection', 155, 'prevents combat damage to your creatures',
     r'\bprevent all combat damage that would be dealt to creatures you control\b'),
    ('Graveyard', 150, 'exiles creatures instead of letting them die',
     r'\bif [^.]{0,100}\bcreature[^.]{0,100}\bwould die[^.]{0,40}\b(?:exile it instead|instead exile it)\b'),
    ('Counterspells', 175, 'returns a spell from the stack',
     r"\breturn target spell to (?:its|their) owner's hand"),
    ('Board Wipes', 180, 'sweeps opposing permanents conditionally',
     r'\bexile [^.]{0,90}\band each (?:artifact|creature|permanent)[^.]{0,70}\bopponents control'),
    ('Stax', 165, 'restricts payments or activated abilities',
     r"\bplayers (?:can't|cannot) (?:pay life|sacrifice)|\bactivated abilities [^.]{0,120}(?:can't|cannot) be activated"),
    ('Stax', 165, 'taxes opposing spells or limits casting',
     r"\bspells (?:your )?opponents cast cost [^.]{0,60}more|\b(?:each player|opponents|players) [^.]{0,35}(?:can't|cannot) cast more than"),
    ('Stax', 165, 'slows opposing artifacts and creatures',
     r'\bartifacts and creatures your opponents control enter tapped'),
    ('Stax', 110, 'slows opposing creatures entering',
     r'\bcreatures your opponents control enter tapped'),
    ('Stax', 135, 'taxes combat', r"\bcreatures can't (?:attack|block)[^.]{0,100}\bunless"),
    ('Protection', 155, 'taxes attacks against you',
     r"\bcreatures can't attack you[^.]{0,110}\bunless"),
    ('Protection', 155, 'protects you or your team',
     r"\byou (?:have|gain) (?:hexproof|protection)|\b(?:creatures|permanents) you control[^.]{0,80}\b(?:hexproof|indestructible|protection from)|\blife total can't change"),
    ('Anthem', 130, 'buffs a creature team',
     r'\b(?:other )?(?:\w+ ){0,3}\w+s you control(?: with \w+)? (?:get \+[\dx]+/\+[\dx]+|have vigilance|have flying|have first strike)'),
    ('Counters', 125, 'generates or distributes power counters',
     r'\b(?:put|enters with)[^.]{0,90}\+1/\+1 counters?'),
    ('Counters', 135, 'preserves or moves counters',
     r'\b(?:put those counters on|move (?:all|any number of) counters|proliferate)\b'),
    ('Counters', 160, 'amplifies counters with a replacement effect',
     r'\bif [^.]{0,80}\+1/\+1 counters? would be put[^.]{0,130}\binstead'),
    ('Tokens', 160, 'amplifies token creation with a replacement effect',
     r'\bif [^.]{0,90}\bcreate [^.]{0,60}\btokens?[^.]{0,130}\binstead'),
    ('Lifegain', 148, 'rewards gaining life',
     r'\bwhenever you gain life\b'),
    ('Lifegain', 140, 'repeated life gain from creatures or lands',
     r'\bwhenever [^.]{0,150}\benters\b[^.]{0,70}\b(?:you (?:may )?gain|gain life equal)'),
    ('Lifegain', 140, 'shares combat damage life gain',
     r'\bwhenever [^.]{0,100}combat damage[^.]{0,100}\bgain that much life'),
    ('Lifegain', 135, 'grants or offers lifelink', r'\blifelink\b'),
    ('Tokens', 155, 'creates creatures after reaching a life threshold',
     r'\bif you (?:have|gained)[^.]{0,140}\bcreate [^.]{0,100}\bcreature token'),
    ('Draw', 160, 'repeatable triggered card draw',
     r'\b(?:whenever|at the beginning)[^.]{0,240}\b(?:you (?:may )?)?draw (?:a|an|one|two|three|x|\d+) cards?'),
    ('Draw', 160, 'investigates for card access', r'\binvestigate\b'),
    ('Draw', 160, 'converts life gain into card draw',
     r'\bwhenever you gain life[^.]{0,160}\.[^.]{0,60}\bdraw x cards'),
    ('Draw', 142, 'lets a chosen player draw cards', r'\btarget player draws (?:a|two|three|x|\d+) cards?'),
    ('Lifegain', 135, 'lets a chosen player gain life', r'\btarget player gains (?:\d+|x) life'),
    ('Recursion', 145, 'puts a graveyard card onto the battlefield',
     r'\bput target [^.]{0,80}\bcard from (?:a|your|any) graveyard onto the battlefield'),
    ('Removal', 150, 'bounces a targeted opposing permanent',
     r"\breturn target (?:nonland )?permanent you don't control to its owner's hand"),
    ('Ramp', 160, 'puts lands from hand onto the battlefield',
     r'\bput (?:an? |one |two )?land cards? from your hand onto the battlefield'),
    ('Ramp', 160, 'generates mana tokens', r'\bcreate [^.]{0,70}\b(?:treasure|gold) tokens?'),
    ('Blink', 165, 'exiles and returns your permanents',
     r'\bexile (?:up to one |another )?target [^.]{0,60}\byou control[^.]{0,90}\breturn (?:it|that card|them)[^.]{0,100}\bbattlefield'),
    ('Equipment', 140, 'rewards equipment or equipping',
     r'\b(?:whenever you (?:attach|equip)|equipment you control|equipped creatures you control|whenever an equipment[^.]{0,70}enters)\b'),
    ('Spellslinger', 140, 'rewards casting instants or sorceries',
     r'\bwhenever you cast (?:an? )?(?:instant or sorcery|noncreature) spell'),
    ('Sacrifice / Aristocrats', 150, 'drains opponents when creatures die',
     r'\bwhenever [^.]{0,100}\b(?:dies|die|you sacrifice)\b[^.]{0,120}\b(?:each opponent|target opponent|target player) loses'),
    ('Removal', 150, 'exiles an opposing graveyard',
     r"\bexile (?:target player's|each opponent's|all opponents') graveyards?"),
    ('Graveyard', 150, 'exiles graveyards or replaces graveyard entry',
     r'\bexile all (?:cards from all )?graveyards|\bif [^.]{0,90}would be put into a graveyard[^.]{0,60}\bexile'),
)
COMPILED_EFFECTS = tuple((role, score, label, re.compile(pattern))
                         for role, score, label, pattern in EFFECTS)


def analyze_effects(payload):
    """Return fresh evidence dictionaries backed by a bounded immutable cache."""
    fields = ('oracle_text', 'type_line', 'keywords', 'card_faces')
    relevant = {k: payload.get(k) for k in fields}
    if relevant['card_faces']:
        relevant['card_faces'] = [{k: face.get(k) for k in fields if k != 'card_faces'}
                                  for face in relevant['card_faces']]
    key = json.dumps(relevant, sort_keys=True, ensure_ascii=True)
    return {role: {'score': score, 'reasons': list(reasons)}
            for role, score, reasons in _analyze_cached(key)}


@lru_cache(maxsize=4096)
def _analyze_cached(key):
    payload = json.loads(key)
    hints = text_roles(payload)
    result = {}

    def add(role, score, reason):
        item = result.setdefault(role, {'score': score, 'reasons': []})
        item['score'] = max(item['score'], score)
        if reason not in item['reasons']:
            item['reasons'].append(reason)

    for role, reasons in hints.items():
        for reason in reasons:
            score = BASE_SCORES.get(role, 100)
            if reason.startswith('Keywords:'):
                score = 40 if role == 'Recursion' else 80
            if role == 'Protection' and reason == 'Oracle text: protective ability':
                score = 55  # Self-resilience is usually incidental to its job.
            if role == 'Tokens' and 'death or sacrifice payoff' in ' '.join(hints.get('Sacrifice / Aristocrats', [])):
                score = 132
            add(role, score, reason)

    for face in payload.get('card_faces') or [payload]:
        text = clean_text(face.get('oracle_text'))
        for role, score, label, pattern in COMPILED_EFFECTS:
            if pattern.search(text):
                add(role, score, 'Oracle effect: ' + label)
        # Alternate casting costs can turn targeted removal into a sweep.
        keywords = {str(k).casefold() for k in payload.get('keywords') or []}
        if ('overload' in keywords or re.search(r'\boverload\b', text)) and 'Removal' in result:
            add('Board Wipes', 180, 'Oracle effect: overload converts targeted removal into a sweep')
        # The token is a mana source, not primarily a creature-token engine.
        if re.search(r'\bcreate [^.]{0,70}\b(?:treasure|gold) token', text):
            if 'Tokens' in result and not re.search(r'\bcreature tokens?\b', text):
                result['Tokens']['score'] = min(result['Tokens']['score'], 110)
            if 'Draw' in result and re.search(r'\bcreate [^.]{0,50}\btreasure tokens? if\b', text):
                result['Ramp']['score'] = 115
                result['Ramp']['reasons'].append('Oracle effect: conditional combat Treasure is a secondary reward')
        if 'Protection' in hints and 'Oracle text: blinks your permanent' in hints['Protection']:
            add('Protection', 155, 'Oracle effect: temporarily saves your permanent')

    # A self-keyword is incidental, but do not demote life gain on another face.
    texts = [clean_text(face.get('oracle_text')) for face in payload.get('card_faces') or [payload]]
    if 'Lifegain' in result and not any(re.search(
            r'\bgain(?:s)? [^.]{0,40}\blife\b|\bgain life equal|\b(?:choose|choice of)[^.]{0,80}lifelink|\b(?:gain|gains|have) lifelink',
            text) for text in texts):
        result['Lifegain']['score'] = min(result['Lifegain']['score'], 80)

    return tuple((role, item['score'], tuple(item['reasons'])) for role, item in result.items())


def deck_context(payloads, commander_payloads=()):
    """Bounded tie-break support from commanders and repeated deck mechanics."""
    support = {}
    for payload in payloads:
        for role, evidence in analyze_effects(payload).items():
            if evidence['score'] >= 120:
                support[role] = support.get(role, 0) + 1
    bonuses = {role: 3 for role, count in support.items() if count >= 6}
    for payload in commander_payloads:
        for role, evidence in analyze_effects(payload).items():
            if evidence['score'] >= 120:
                bonuses[role] = 8
    return bonuses
