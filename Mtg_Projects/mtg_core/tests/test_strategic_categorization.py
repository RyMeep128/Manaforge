"""Offline regression coverage; Oracle snapshots are input, never name rules."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import re

import pytest

from mtg_core.categorization import analyze_entries, apply_categories, classify
from mtg_core.decks import DeckCategory, DeckDocument, DeckEntry
from mtg_core.role_analysis import analyze_effects, _analyze_cached


FIXTURES = Path(__file__).parent / 'fixtures'
LYRA = json.loads((FIXTURES / 'lyra_oracle.json').read_text(encoding='utf-8'))['cards']
STRATEGIES = json.loads((FIXTURES / 'strategy_oracle.json').read_text(encoding='utf-8'))['cards']
REFERENCE = []
for line in (FIXTURES / 'lyra_reference.txt').read_text(encoding='utf-8').splitlines():
    match = re.fullmatch(r'(\d+)x (.+) \(([^)]+)\) \[([^]]+)\]', line)
    REFERENCE.append((int(match[1]), match[2], match[4].replace('{top}', '')))


class LocalCards:
    def __init__(self, cards):
        self.cards = {card['id']: card for card in cards.values()}
        self.calls = 0

    def categorization_data(self, card_ids, oracle_ids):
        self.calls += 1
        return {'cards': {key: self.cards[key] for key in card_ids if key in self.cards}, 'tags': {}}


def reference_document():
    doc = DeckDocument()
    for quantity, name, category in REFERENCE:
        card = LYRA[name]
        doc.deck.entries.append(DeckEntry(name, name, quantity=quantity, card_id=card['id'],
            oracle_id=card['oracle_id'], section='commander' if category == 'Commander' else 'mainboard'))
    doc.deck.categories = [DeckCategory('custom:' + name, name)
                           for name in dict.fromkeys(row[2] for row in REFERENCE)]
    doc.deck.commander_entry_ids = ['Lyra, Archangel of Dawn']
    return doc


def test_reference_list_quantities_are_computed_from_supplied_list():
    counts = Counter()
    for quantity, _, category in REFERENCE:
        counts[category] += quantity
    assert len(REFERENCE) == 77
    assert sum(counts.values()) == 110  # Supplied prose incorrectly says 100.
    assert counts['Land'] == 36
    assert counts['Draw'] == 11
    assert counts['Protection'] == 9


def test_entire_lyra_reference_assignments_and_local_batching():
    doc = reference_document()
    database = LocalCards(LYRA)
    proposals = analyze_entries(database, doc.deck.entries,
                                commander_entry_ids=doc.deck.commander_entry_ids)
    assert database.calls == 1
    apply_categories(doc, proposals)
    names = {c.category_id: c.name for c in doc.deck.categories}
    expected = {name: category for _, name, category in REFERENCE}
    for entry in doc.deck.entries:
        assert names[entry.category_ids[0]] == expected[entry.name], (entry.name, proposals[entry.entry_id])
    plains = next(e for e in doc.deck.entries if e.name == 'Plains')
    assert plains.quantity == 34
    assert names[plains.category_ids[0]] == 'Land'
    saved = deepcopy(doc.to_dict())
    apply_categories(doc, analyze_entries(database, doc.deck.entries))
    assert doc.to_dict() == saved
    assert DeckDocument.from_dict(saved).to_dict() == saved


@pytest.mark.parametrize('name,primary,secondary', [
    ('Battle Angels of Tyr', 'Draw', 'Ramp'),
    ('Blind Obedience', 'Stax', 'Lifegain'),
    ('Pristine Talisman', 'Ramp', 'Lifegain'),
    ('Heliod, Sun-Crowned', 'Lifegain', 'Counters'),
    ('Resplendent Angel', 'Tokens', 'Lifegain'),
    ('Winds of Abandon', 'Board Wipes', 'Removal'),
])
def test_multirole_evidence_is_ranked_without_card_name_rules(name, primary, secondary):
    payload = LYRA[name]
    roles = classify(payload)
    assert roles[0]['name'] == primary
    assert secondary in {r['name'] for r in roles}
    assert roles[0]['score'] > next(r['score'] for r in roles if r['name'] == secondary)
    assert roles == classify({**payload, 'name': 'Unrelated name', 'id': 'unrelated-id'})


@pytest.mark.parametrize('name,primary', [
    ('Sol Ring', 'Ramp'), ('Cultivate', 'Ramp'), ('Beast Whisperer', 'Draw'),
    ('Eternal Witness', 'Recursion'), ('Rest in Peace', 'Graveyard'),
    ('Avenger of Zendikar', 'Tokens'), ('Viscera Seer', 'Sacrifice / Aristocrats'),
    ('Blood Artist', 'Sacrifice / Aristocrats'), ('Hardened Scales', 'Counters'),
    ("Sigarda's Aid", 'Equipment'), ('Young Pyromancer', 'Tokens'),
    ('Austere Command', 'Board Wipes'), ('Cyclonic Rift', 'Board Wipes'),
    ('Kenrith, the Returned King', 'Recursion'),
])
def test_other_archetypes(name, primary):
    assert classify(STRATEGIES[name])[0]['name'] == primary


def test_commander_synergy_breaks_close_choices_but_not_obvious_functions():
    payoff = STRATEGIES['Young Pyromancer']
    commander = {'id': 'commander', 'type_line': 'Legendary Creature', 'oracle_text':
                 'Whenever you cast an instant or sorcery spell, scry 1.'}
    cards = {'payoff': payoff, 'commander': commander}
    database = LocalCards(cards)
    entries = [DeckEntry('payoff', 'Payoff', card_id=payoff['id']),
               DeckEntry('commander', 'Commander', card_id='commander', section='commander')]
    assert classify(payoff)[0]['name'] == 'Tokens'
    roles = analyze_entries(database, entries)
    assert roles['payoff'][0]['name'] == 'Spellslinger'
    assert 'Deck context:' in roles['payoff'][0]['reason']
    assert classify(LYRA['Pristine Talisman'], context={'Lifegain': 8})[0]['name'] == 'Ramp'
    assert classify(LYRA['Blind Obedience'], context={'Lifegain': 8})[0]['name'] == 'Stax'
    assert classify(STRATEGIES['Kenrith, the Returned King'], context={'Draw': 8})[0]['name'] == 'Draw'


def test_available_categories_aliases_renames_manual_control_and_deletion():
    doc = DeckDocument()
    doc.deck.categories = [DeckCategory('custom-life', 'Life Gain'), DeckCategory('custom-counters', 'Counters')]
    doc.deck.entries = [DeckEntry('auto', 'Automatic'),
                        DeckEntry('manual', 'Manual', category_ids=['custom-counters'])]
    proposals = {entry.entry_id: classify(LYRA['Heliod, Sun-Crowned']) for entry in doc.deck.entries}
    apply_categories(doc, proposals)
    assert doc.deck.entries[0].category_ids[0] == 'custom-life'
    assert doc.deck.entries[1].category_ids == ['custom-counters']
    # Only Counters is available: the strongest supported existing role wins.
    doc = DeckDocument()
    doc.deck.categories = [DeckCategory('mine', 'Counters')]
    doc.deck.entries = [DeckEntry('auto', 'Automatic')]
    apply_categories(doc, {'auto': classify(LYRA['Heliod, Sun-Crowned'])})
    assert doc.deck.entries[0].category_ids[0] == 'mine'
    before = deepcopy(doc.to_dict())
    apply_categories(doc, {'auto': classify(LYRA['Heliod, Sun-Crowned'])})
    assert doc.to_dict() == before
    doc = DeckDocument()
    doc.deck.entries = [DeckEntry('a', 'Rock')]
    proposal = {'a': classify(STRATEGIES['Sol Ring'])}
    apply_categories(doc, proposal)
    doc.deck.categories[0].name = 'My mana'
    apply_categories(doc, proposal)
    assert len(doc.deck.categories) == 1
    assert doc.deck.categories[0].name == 'My mana'
    doc.deck.categories.clear()
    apply_categories(doc, proposal)
    assert doc.deck.entries[0].category_ids == ['auto:ramp']
    assert len(doc.deck.categories) == 1


def test_context_subset_metadata_fallback_missing_data_and_analysis_cache():
    database = LocalCards({})
    commander = DeckEntry('commander', 'Commander', section='commander', extras={'facts': {
        'oracle_text': 'Whenever you cast an instant or sorcery spell, scry 1.'}})
    payoff = DeckEntry('payoff', 'Payoff', extras={'facts': STRATEGIES['Young Pyromancer']})
    roles = analyze_entries(database, [payoff], context_entries=[commander, payoff])
    assert roles['payoff'][0]['name'] == 'Spellslinger'
    assert classify({}) == []
    assert analyze_entries(database, [DeckEntry('missing', 'Missing')]) == {'missing': []}
    _analyze_cached.cache_clear()
    first = analyze_effects(STRATEGIES['Sol Ring'])
    first['Ramp']['reasons'].append('Caller mutation')
    second = analyze_effects(STRATEGIES['Sol Ring'])
    assert 'Caller mutation' not in second['Ramp']['reasons']
    assert _analyze_cached.cache_info().hits == 1


def test_large_deck_uses_one_batch_and_reuses_effect_parsing():
    database = LocalCards(STRATEGIES)
    entries = [DeckEntry(str(i), 'Rock', card_id=STRATEGIES['Sol Ring']['id']) for i in range(500)]
    _analyze_cached.cache_clear()
    roles = analyze_entries(database, entries)
    assert database.calls == 1
    assert all(evidence[0]['name'] == 'Ramp' for evidence in roles.values())
    assert _analyze_cached.cache_info().misses == 1
