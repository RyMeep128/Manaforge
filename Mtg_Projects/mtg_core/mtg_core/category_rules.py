"""Conservative Oracle-wording rules. Patterns match effects, not card names.

Each rule supplies a stable explanation. These are role hints, not a rules engine.
Reminder text is removed before matching, and faces are evaluated independently.
"""
import re


def clean_text(text):
    text = str(text or '').casefold().replace('’', "'")
    while re.search(r'\([^()]*\)', text):
        text = re.sub(r'\([^()]*\)', '', text)
    return re.sub(r'\s+', ' ', text).strip()


# Bounded to a sentence to avoid combining unrelated abilities.
GAP = r'[^.!?]{0,180}'
PERMANENTS = r'(?:creatures?|artifacts?|enchantments?|planeswalkers?|permanents?|lands?|battles?)'
RULES = (
    ('Board Wipes', 'mass destruction or exile', rf'\b(?:destroy|exile) all (?:\w+ ){{0,4}}{PERMANENTS}\b'),
    ('Board Wipes', 'mass toughness reduction', r'\b(?:all creatures|each creature|creatures your opponents control) gets? -[\dx]+/-[\dx]+'),
    ('Board Wipes', 'mass return to hand', rf"\breturn all (?:\w+ ){{0,4}}{PERMANENTS} {GAP}\bto (?:their|its) owners?'s? hands?"),
    ('Board Wipes', 'damage to each creature', rf'\bdeals? {GAP}damage to (?:each|all) (?:\w+ ){{0,3}}creatures?\b'),
    ('Board Wipes', 'mass creature sacrifice', rf'\bsacrifice all (?:\w+ ){{0,3}}creatures?\b|\b(?:each|every) player sacrifices all {PERMANENTS}\b'),
    ('Counterspells', 'counters a spell or ability', r'\bcounter (?:target|up to \w+ target|any number of target|all) (?:\w+ ){0,5}(?:spells?|abilit(?:y|ies))\b'),
    ('Ramp', 'reduces the cost of spells you cast',
     r'\bspells you cast\b[^.!?:]{0,100}\bcost (?:\{[0-9wubrgcx/]+\}\s*|\d+\s+|x\s+)+less to cast\b'),
    ('Interaction', 'redirects a spell or ability', rf'\b(?:change (?:the )?targets? of|choose new targets? for) {GAP}\b(?:spell|ability)\b'),
    ('Removal', 'targeted destruction or exile', rf'\b(?:destroy|exile) (?:up to \w+ )?target (?:\w+ ){{0,4}}{PERMANENTS}\b'),
    ('Removal', 'targeted damage', rf'\bdeals? {GAP}damage to (?:any target|target (?:\w+ ){{0,3}}(?:creature|planeswalker))\b'),
    ('Removal', 'targeted toughness reduction', r'\btarget creature gets? -[\dx]+/-[\dx]+'),
    ('Removal', 'opponent sacrifices a permanent', rf'\b(?:target|each) opponent sacrifices (?:an?|\w+) (?:\w+ ){{0,3}}{PERMANENTS}\b'),
    ('Removal', 'returns opposing permanent to hand', rf"\breturn target (?:\w+ ){{0,3}}{PERMANENTS} to (?:its|their) owners?'s? hands?"),
    ('Draw', 'draws cards', r'\b(?:draw (?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|x|\d+) cards?|draw cards equal to)\b'),
    ('Card Advantage', 'exiled cards may be played', rf'\bexile {GAP}(?:top|cards? from the top){GAP}\b(?:play|cast) (?:that card|those cards|them|it|one of)\b'),
    ('Card Advantage', 'plays cards from library', rf'\b(?:play|cast) {GAP}(?:from the top of your library|top card of your library)\b'),
    ('Card Advantage', 'selects library cards for hand', rf'\blook at the top {GAP}\bput {GAP}\binto your hand\b'),
    ('Card Advantage', 'returns multiple cards to hand', rf'\breturn (?:up to )?(?:all|two|three|four|x|[2-9]\d*) {GAP}(?:to your hand|to their owners?\W+s hands?)\b'),
    ('Recursion', 'returns a card from a graveyard', rf'\breturn {GAP}(?:from (?:your|a|any|target player\W+s) graveyard|cards? (?:in|from) (?:your|a|any) graveyard){GAP}\b(?:hand|battlefield)\b'),
    ('Recursion', 'casts or plays from graveyard', rf'\b(?:cast|play) {GAP}from (?:your|a|any) graveyard\b'),
    ('Protection', 'protective ability', r'\b(?:hexproof|shroud|indestructible|protection from|ward \{)\b'),
    ('Protection', 'phases out', r'\b(?:phases? out|phase out)\b'),
    ('Protection', 'regenerates a permanent', rf'\bregenerate (?:target|each|all|this|~)\b'),
    ('Tokens', 'creates tokens', rf'\bcreate {GAP}\btokens?\b'),
    ('Lifegain', 'gains life', r'\b(?:you gain|gain) (?:\d+|x|one|two|three|four|five|that much) life\b|\bgain life equal to\b'),
    ('Graveyard', 'mills cards', r'\bmill (?:\w+ ){0,3}cards?\b|\bmills (?:\w+ ){0,3}cards?\b'),
    ('Graveyard', 'moves library cards to graveyard', rf'\bput {GAP}\btop {GAP}\blibrary into (?:your|their|a) graveyard\b'),
    ('Graveyard', 'exiles graveyard cards', rf'\bexile {GAP}\b(?:from|in) (?:a|your|target player\W+s|all) graveyards?\b'),
    ('Sacrifice / Aristocrats', 'sacrifice outlet', rf'\bsacrifice (?:another|an?|one|two|three|x|[1-9]\d*) (?:\w+ ){{0,2}}{PERMANENTS}\s*:'),
    ('Sacrifice / Aristocrats', 'death or sacrifice payoff', rf'\bwhenever {GAP}(?:\bdies\b|\bdie\b|\byou sacrifice\b)'),
    ('Win Conditions', 'explicit win or opponent loss', r'\byou win the game\b|\b(?:target|each) opponent loses the game\b'),
    ('Win Conditions', 'team pump with evasion', r'\bcreatures you control get \+[\dx]+/\+[\dx]+[^.]{0,80}\b(?:trample|double strike|unblockable)\b'),
    ('Utility', 'filters draws', r'\b(?:scry|surveil) (?:\d+|x)\b'),
    ('Utility', 'untaps a permanent', rf'\buntap (?:another |target ){PERMANENTS}\b'),
)
COMPILED_RULES = tuple((role, label, re.compile(pattern)) for role, label, pattern in RULES)


def text_roles(payload):
    reasons = {}
    def add(role, reason):
        reasons.setdefault(role, []).append('Oracle text: ' + reason)
    faces = payload.get('card_faces') or [payload]
    for face in faces:
        text = clean_text(face.get('oracle_text'))
        for role, label, pattern in COMPILED_RULES:
            if pattern.search(text):
                if role == 'Removal' and label == 'targeted destruction or exile' and re.search(
                        r'\bexile target [^.]{0,80}\bcard[^.]{0,80}\bgraveyard\b', text):
                    continue
                if role == 'Protection' and label == 'protective ability':
                    if re.search(r"\b(?:lose|loses|without|remove|can't have) (?:hexproof|shroud|indestructible|protection)\b", text):
                        continue
                # A draw restriction or opponent-only instruction is not draw access.
                if role == 'Draw' and re.search(r"(?:can't|cannot) draw|(?:opponent|opponents) (?:may )?draw", text):
                    if not re.search(r'\byou (?:may )?draw|\. draw', text):
                        continue
                add(role, label)
        search = re.search(r'\bsearch your library(?: and/or (?:your )?graveyard)? for ([^.]{1,180})', text)
        if search:
            selection = search[1].split(',')[0]
            land_search = bool(re.search(r'\b(?:basic land|land|forest|island|swamp|mountain|plains) cards?\b', selection))
            land_search = land_search and not re.search(r'\b(?:creature|artifact|enchantment|instant|sorcery|planeswalker|battle)\b', selection)
            if land_search and 'battlefield' in search[1]:
                add('Ramp', 'library lands enter the battlefield')
            else:
                add('Tutors', 'searches your library for a card')
        if re.search(r'\badd (?:\{[wubrgc0-9]+\}|[^.]{0,60}\bmana\b)', text):
            add('Ramp', 'produces mana')
        if re.search(r'\b(?:play|put) (?:an? |one |two )?additional lands?\b', text):
            add('Ramp', 'additional land plays')
        if re.search(r'\bexile (?:another |target )[^.]{0,80}\byou control\b', text) and re.search(r'\breturn (?:it|that card|them)[^.]{0,90}\bbattlefield\b', text):
            add('Protection', 'blinks your permanent')
            if reasons.get('Removal') == ['Oracle text: targeted destruction or exile']:
                reasons.pop('Removal')
        # Impulse access commonly separates the exile and permission into sentences.
        if re.search(r'\bexile [^.]{0,100}\btop\b[^.]{0,90}\byour library\b', text) and re.search(r'\byou may (?:play|cast) (?:that card|those cards|them|it)\b', text):
            add('Card Advantage', 'exiled library cards may be played')
    keywords = {str(k).casefold() for k in payload.get('keywords') or []}
    for role, known in (('Protection', {'hexproof', 'shroud', 'ward', 'indestructible', 'protection', 'phasing'}),
                        ('Recursion', {'flashback', 'escape', 'disturb', 'unearth', 'aftermath', 'retrace'}),
                        ('Lifegain', {'lifelink'}), ('Graveyard', {'dredge', 'delve', 'surveil'})):
        found = keywords.intersection(known)
        if found:
            reasons.setdefault(role, []).append('Keywords: ' + ', '.join(sorted(found)))
    if 'Board Wipes' in reasons:
        add('Removal', 'mass removal')
    return reasons
