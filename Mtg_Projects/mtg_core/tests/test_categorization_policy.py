"""System-wide primary-role invariants, plus reported examples as regressions."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from mtg_core.categorization import classify, apply_categories, theme_priorities
from mtg_core.categorization_policy import evidence_key
from mtg_core.categorization_policy import ordered_evidence
from mtg_core.decks import DeckCategory, DeckDocument, DeckEntry


THEMES = {'_strategy': {'themes': ['Enchantment Matters', 'Voltron', 'Artifacts', 'Tribal'],
                       'commander_themes': ['Enchantment Matters', 'Voltron'], 'tribes': ['human']},
          'Enchantment Matters': 8}


@pytest.mark.parametrize('kind', ['Creature', 'Artifact', 'Enchantment', 'Enchantment — Aura',
                                 'Instant', 'Sorcery', 'Planeswalker'])
@pytest.mark.parametrize('text,job', [
    ('Draw two cards.', 'Draw'),
    ('{T}: Add {G}.', 'Ramp'),
    ('Destroy target creature.', 'Removal'),
    ('Counter target spell.', 'Counterspells'),
    ('Return target creature card from your graveyard to your hand.', 'Recursion'),
    ('Target creature gains indestructible until end of turn.', 'Protection'),
    ('Copy target instant or sorcery spell.', 'Copy'),
])
def test_functions_win_across_types_tags_context_and_existing_categories(kind, text, job):
    payload = dict(type_line=kind, oracle_text=text)
    for context in (None, THEMES):
        evidence = classify(payload, ['enchantment-matters', 'equipment', 'spellslinger'], context)
        assert evidence[0]['name'] == job
        doc = DeckDocument()
        doc.deck.categories = [DeckCategory('theme', 'Enchantment Matters')]
        doc.deck.entries = [DeckEntry('card', 'Card')]
        apply_categories(doc, {'card': evidence})
        assert doc.deck.entries[0].category_ids[0] == 'auto:' + job.casefold().replace(' ', '-')


def test_layer_order_is_structural_not_a_score_tweak():
    evidence = [dict(name='Theme', layer='theme', score=1000000),
                dict(name='Function', layer='function', score=100),
                dict(name='Keyword', layer='incidental', score=2000000)]
    assert [item['name'] for item in ordered_evidence(evidence)] == ['Function', 'Theme', 'Keyword']


@pytest.mark.parametrize('text,primary', [
    ('Reveal the top six cards of your library. Put up to three enchantment cards from among them into your hand and the rest into your graveyard.', 'Card Advantage'),
    ('Enchant creature. When this Aura enters the battlefield, draw a card. Enchanted creature has protection from creatures.', 'Protection'),
    ("Enchant creature. When this Aura enters the battlefield, draw a card for each Aura you control that's attached to a creature. Enchanted creature gets +1/+1 for each Aura you control that's attached to a creature.", 'Draw'),
    ("Enchant creature. Enchanted creature gets +1/+1 for each card in its controller's hand. At the beginning of the draw step of enchanted creature's controller, that player draws an additional card.", 'Draw'),
    ("When this enchantment enters the battlefield, draw a card. Cards in graveyards can't be the targets of spells or abilities.", 'Graveyard Hate'),
    ("You may have this enchantment enter as a copy of any enchantment you control, except it has 'At the beginning of your upkeep, you may exile this enchantment. If you do, return it to the battlefield under its owner's control.'", 'Copy'),
    ("Flash. At the beginning of each player's draw step, that player draws an additional card.", 'Draw'),
    ('Enchant creature. Enchanted creature gets +2/+2 and has "Whenever this creature attacks, untap all lands you control." Umbra armor (If enchanted creature would be destroyed, instead remove all damage marked on it and destroy this Aura.)', 'Ramp'),
    ("Creatures you control have flying. Creatures your opponents control lose flying and can't have or gain flying.", 'Evasion'),
])
def test_reported_effects_keep_their_jobs_in_and_out_of_enchantment_decks(text, primary):
    payload = {'type_line': 'Enchantment', 'oracle_text': text}
    for context in (None, THEMES):
        evidence = classify(payload, context=context)
        assert evidence[0]['name'] == primary
        assert evidence[0]['layer'] == 'function'
        assert evidence == classify(dict(payload, name='Unrelated name'), context=context)


def test_all_fixture_functions_stay_above_theme_membership():
    fixtures = Path(__file__).parent / 'fixtures'
    for filename in ('lyra_oracle.json', 'strategy_oracle.json'):
        cards = json.loads((fixtures / filename).read_text(encoding='utf-8'))['cards']
        for name, payload in cards.items():
            evidence = classify(payload, context=THEMES)
            assert evidence == sorted(evidence, key=evidence_key), name
            functions = [item for item in evidence if item['layer'] == 'function']
            if functions and evidence[0]['name'] != 'Lands':
                assert evidence[0]['layer'] == 'function', (name, evidence)


def test_category_existence_cannot_reassign_the_primary_job():
    payload = {'type_line': 'Enchantment', 'oracle_text': 'Draw two cards.'}
    doc = DeckDocument()
    doc.deck.categories = [DeckCategory('custom-theme', 'Enchantment Matters')]
    doc.deck.entries = [DeckEntry('card', 'Card')]
    evidence = classify(payload, context=THEMES)
    apply_categories(doc, {'card': evidence})
    assert doc.deck.entries[0].category_ids[0] == 'auto:draw'
    assert 'custom-theme' in doc.deck.entries[0].category_ids
    snapshot = deepcopy(doc.to_dict())
    apply_categories(doc, {'card': evidence})
    assert doc.to_dict() == snapshot


def test_manual_theme_priorities_cannot_cross_evidence_layers():
    doc = DeckDocument()
    doc.editor_preferences['manual_themes'] = [{'roles': ['Enchantment Matters']}]
    evidence = classify({'type_line': 'Enchantment', 'oracle_text':
                         'Whenever an enchantment enters under your control, draw a card.'}, context=THEMES)
    result = theme_priorities(doc, evidence)
    assert result[0]['name'] == 'Draw'
    assert next(item for item in result if item['name'] == 'Enchantment Matters')['layer'] == 'theme'


def test_tag_only_claims_do_not_displace_supported_functions():
    evidence = classify({'oracle_text': 'Draw two cards.'}, ['ramp', 'enchantment-matters'], THEMES)
    assert evidence[0]['name'] == 'Draw'
    assert next(item for item in evidence if item['name'] == 'Ramp')['layer'] == 'tag'


@pytest.mark.parametrize('text', [
    'Exile all graveyards.',
    "Exile target player's graveyard.",
    'Exile target creature card from a graveyard.',
    "Cards in graveyards can't be the targets of spells or abilities.",
    "Players can't cast spells from graveyards.",
    "Creature cards in graveyards can't enter the battlefield.",
])
def test_graveyard_hate_is_distinct_from_own_graveyard_value(text):
    assert classify({'oracle_text': text})[0]['name'] == 'Graveyard Hate'
    assert classify({'oracle_text': 'Return target creature card from your graveyard to your hand.'})[0]['name'] == 'Recursion'


@pytest.mark.parametrize('beneficiary', ['you', 'creatures you control', 'permanents you control'])
@pytest.mark.parametrize('kind', ['Creature', 'Enchantment', 'Instant'])
def test_damage_prevention_is_primary_over_a_counter_reward(beneficiary, kind):
    payload = dict(type_line=kind, oracle_text=
        f'When this permanent enters, prevent all damage that would be dealt to {beneficiary} this turn. '
        'Whenever damage that would be dealt to you is prevented, put that many +1/+1 counters on this permanent.')
    context = dict(THEMES, Counters=8)
    evidence = classify(payload, ['counters'], context)
    assert evidence[0]['name'] == 'Protection'
    assert 'Counters' in {item['name'] for item in evidence}
    doc = DeckDocument()
    doc.deck.categories = [DeckCategory('counters', 'Counters')]
    doc.deck.entries = [DeckEntry('card', 'Card')]
    apply_categories(doc, {'card': evidence})
    assert doc.deck.entries[0].category_ids[0] == 'auto:protection'
    assert 'counters' in doc.deck.entries[0].category_ids


@pytest.mark.parametrize('text,absent', [
    ('Creatures your opponents control have flying.', 'Evasion'),
    ("Creatures you control lose flying and can't have flying.", 'Evasion'),
    ('Tap all lands you control.', 'Ramp'),
    ('At the beginning of each opponent\'s draw step, that opponent draws an additional card.', 'Draw'),
])
def test_effect_patterns_do_not_treat_opposing_effects_as_our_job(text, absent):
    assert absent not in {item['name'] for item in classify({'oracle_text': text})}
