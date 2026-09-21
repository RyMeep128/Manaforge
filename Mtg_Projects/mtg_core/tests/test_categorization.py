from copy import deepcopy
import pytest
from mtg_core.categorization import classify, apply_categories, analyze_entries
from mtg_core.decks import DeckDocument, DeckEntry, DeckCategory, DeckHistory
from mtg_core.db import CardDatabase


def test_functional_roles_are_deterministic_and_explainable():
    result = classify({'type_line': 'Artifact'}, ['card-draw', 'ramp', 'unrecognized'])
    assert [r['name'] for r in result] == ['Ramp', 'Draw']
    assert result == classify({'type_line': 'Artifact'}, ['ramp', 'card-draw'])
    assert all('Local Oracle Tags:' in r['reason'] for r in result)
    assert classify({'oracle_text': 'Draw a card.'})[0]['name'] == 'Draw'


def test_front_face_and_missing_data():
    assert classify({'type_line': 'Sorcery'})[0]['name'] == 'Sorceries'
    assert classify({'type_line': 'Land'}, ['ramp'])[0]['name'] == 'Lands'
    result = classify({'type_line': 'Sorcery // Land', 'card_faces': [
        {'type_line': 'Sorcery'}, {'type_line': 'Land'}]})
    assert result[0]['name'] == 'Sorceries'
    assert classify({}) == []


def test_manual_protection_idempotence_history_and_serialization():
    doc = DeckDocument()
    doc.deck.categories = [DeckCategory('custom-ramp', 'Ramp')]
    doc.deck.entries = [DeckEntry('auto', 'Automatic', quantity=4, section='commander',
        image_asset_id='exact-art', extras={'oversized': True, 'unknown': 1}),
        DeckEntry('manual', 'Manual', category_ids=['custom-ramp']),
        DeckEntry('empty', 'Explicit uncategorized', extras={'auto_categories': {'manual': True}})]
    proposals = {e.entry_id: classify({}, ['ramp', 'card-draw']) for e in doc.deck.entries}
    history = DeckHistory(doc)
    before = deepcopy(doc.to_dict())
    history.execute(lambda d: apply_categories(d, proposals))
    after = deepcopy(doc.to_dict())
    assert doc.deck.entries[0].category_ids == ['custom-ramp', 'auto:draw']
    assert doc.deck.entries[1].category_ids == ['custom-ramp']
    assert doc.deck.entries[2].category_ids == []
    assert doc.deck.entries[0].image_asset_id == 'exact-art'
    assert doc.deck.entries[0].quantity == 4
    assert doc.deck.entries[0].extras['oversized']
    apply_categories(doc, proposals)
    assert doc.to_dict() == after
    assert DeckDocument.from_dict(after).to_dict() == after
    history.undo()
    assert doc.to_dict() == before
    history.redo()
    assert doc.to_dict() == after


def test_role_update_preserves_additional_associations():
    doc = DeckDocument()
    doc.deck.entries = [DeckEntry('a', 'Card')]
    apply_categories(doc, {'a': classify({}, ['ramp'])})
    doc.deck.entries[0].category_ids.append('my-secondary')
    apply_categories(doc, {'a': classify({}, ['card-draw'])})
    assert doc.deck.entries[0].category_ids == ['auto:draw', 'my-secondary']


def test_500_entries_use_batched_local_reads(tmp_path):
    db = CardDatabase(str(tmp_path / 'cards.sqlite3'))
    db.upsert_card_payload({'id': 'card', 'oracle_id': 'oracle', 'name': 'Example',
                            'type_line': 'Artifact', 'set': 'abc', 'collector_number': '1'})
    with db.connect() as connection:
        connection.execute("INSERT INTO oracle_tags VALUES ('oracle', 'ramp')")
    entries = [DeckEntry(str(i), 'Example', card_id='card') for i in range(500)]
    calls = []
    connect = db.connect
    def traced():
        connection = connect()
        connection.set_trace_callback(calls.append)
        return connection
    db.connect = traced
    result = analyze_entries(db, entries)
    assert len(result) == 500
    assert all(r[0]['name'] == 'Ramp' for r in result.values())
    assert len([q for q in calls if q.startswith('SELECT')]) == 2


@pytest.mark.parametrize('text,primary', [
    ('Search your library for up to two basic land cards, reveal those cards, put one onto the battlefield tapped and the other into your hand, then shuffle.', 'Ramp'),
    ('{T}: Add {C}{C}.', 'Ramp'),
    ('You may play an additional land on each of your turns.', 'Ramp'),
    ('Destroy target permanent. Its controller creates a 3/3 green Beast creature token.', 'Removal'),
    ('Draw three cards.', 'Draw'),
    ('Draw X cards.', 'Draw'),
    ('Draw cards equal to the number of creatures you control.', 'Draw'),
    ('Whenever you cast a creature spell, draw a card.', 'Draw'),
    ('Exile all artifacts. Exile all creatures. Exile all enchantments.', 'Board Wipes'),
    ('Destroy all creatures.', 'Board Wipes'),
    ('All creatures get -X/-X until end of turn.', 'Board Wipes'),
    ('This spell deals 3 damage to each creature.', 'Board Wipes'),
    ('Each player sacrifices all creatures they control.', 'Board Wipes'),
    ("Return all nonland permanents to their owners' hands.", 'Board Wipes'),
    ('Return target card from your graveyard to your hand.', 'Recursion'),
    ('Return up to two target creature cards from your graveyard to your hand.', 'Recursion'),
    ('You may cast creature spells from your graveyard.', 'Recursion'),
    ('Search your library for an instant or sorcery card, reveal it, then shuffle and put that card on top.', 'Tutors'),
    ('Search your library for a basic land card or creature card, put it onto the battlefield, then shuffle.', 'Tutors'),
    ('Permanents you control gain hexproof and indestructible until end of turn.', 'Protection'),
    ('Protection from red', 'Protection'),
    ('Any number of target creatures you control phase out.', 'Protection'),
    ('Regenerate target creature.', 'Protection'),
    ('Exile target creature you control, then return that card to the battlefield under your control.', 'Protection'),
    ('Counter target spell.', 'Counterspells'),
    ('Counter target activated or triggered ability.', 'Counterspells'),
    ('Exile the top two cards of your library. Until the end of your next turn, you may play those cards.', 'Card Advantage'),
    ('You may play lands and cast spells from the top of your library.', 'Card Advantage'),
    ('Look at the top four cards of your library, put two of them into your hand and the rest on the bottom.', 'Card Advantage'),
    ('Create two 1/1 white Soldier creature tokens.', 'Tokens'),
    ('You gain 5 life.', 'Lifegain'),
    ('Mill three cards.', 'Graveyard'),
    ('Exile target creature card from a graveyard.', 'Graveyard'),
    ('Sacrifice another creature: Add {C}.', 'Ramp'),
    ('Whenever another creature dies, each opponent loses 1 life and you gain 1 life.', 'Lifegain'),
    ('If you have forty or more life, you win the game.', 'Win Conditions'),
    ('Creatures you control get +X/+X and gain trample until end of turn.', 'Win Conditions'),
    ('Scry 2.', 'Utility'),
])
def test_oracle_wording_roles(text, primary):
    roles = classify({'type_line': 'Instant', 'oracle_text': text})
    assert roles[0]['name'] == primary
    assert all('Oracle text:' in r['reason'] for r in roles)


@pytest.mark.parametrize('text,absent', [
    ('At the beginning of your draw step, lose 1 life.', 'Draw'),
    ("Players can't draw cards.", 'Draw'),
    ('Target opponent draws two cards.', 'Draw'),
    ('Each opponent may draw a card.', 'Draw'),
    ('Flying (This creature can only be blocked by creatures with flying. Draw a card.)', 'Draw'),
    ('Target creature gets +3/+3 until end of turn.', 'Protection'),
    ('Creatures your opponents control lose hexproof.', 'Protection'),
    ('Reminder (A creature with protection from red cannot be damaged by red sources.)', 'Protection'),
    ('Put a +1/+1 counter on target creature.', 'Counterspells'),
    ("This spell can't be countered.", 'Counterspells'),
    ('Exile all cards from all graveyards.', 'Board Wipes'),
    ('Exile target creature card from a graveyard.', 'Removal'),
    ('Destroy target creature. Its controller creates a token.', 'Tokens'),
    ('Return target creature to its owner\'s hand.', 'Recursion'),
    ('Return 1 target creature card from your graveyard to your hand.', 'Card Advantage'),
    ('Search your library for a basic land card, put it onto the battlefield, then shuffle.', 'Tutors'),
    ('Search your library for a basic land card, put it into your hand, then shuffle.', 'Ramp'),
])
def test_wording_false_positives(text, absent):
    assert absent not in {r['name'] for r in classify({'oracle_text': text})}


def test_secondary_roles_and_cantrips():
    roles = classify({'oracle_text': 'Destroy target creature. Draw a card.'})
    assert [r['name'] for r in roles] == ['Removal', 'Draw']
    assert {'Board Wipes', 'Removal'} <= {r['name'] for r in classify({'oracle_text': 'Destroy all creatures.'})}
    assert 'Sacrifice / Aristocrats' in {r['name'] for r in classify({'oracle_text': 'Sacrifice a creature: Draw a card.'})}
    assert {'Lifegain', 'Sacrifice / Aristocrats'} <= {r['name'] for r in classify({
        'oracle_text': 'Whenever another creature dies, you gain 1 life.'})}


def test_faces_keywords_and_names_are_not_inference_inputs():
    result = classify({'type_line': 'Creature // Land', 'keywords': ['Lifelink'], 'card_faces': [
        {'type_line': 'Creature', 'oracle_text': 'Draw two cards.'},
        {'type_line': 'Land', 'oracle_text': '{T}: Add {G}.'}]})
    assert {r['name'] for r in result} == {'Ramp', 'Draw', 'Lifegain'}
    assert classify({'name': 'Ramp Tutor Draw Removal'}) == []
    assert classify({'keywords': ['Flashback']})[0]['name'] == 'Recursion'


@pytest.mark.parametrize('cost', ['Sacrifice Goblin Flectomancer', 'Sacrifice this creature'])
def test_spell_redirection_is_interaction_not_self_sacrifice_outlet(cost):
    payload = {'type_line': 'Creature — Goblin Wizard', 'oracle_text':
        cost + ': You may change the targets of target instant or sorcery spell.'}
    roles = classify(payload)
    assert roles[0]['name'] == 'Interaction'
    assert 'Sacrifice / Aristocrats' not in {r['name'] for r in roles}
    # Broad local tags must not displace the actual spell-redirection effect.
    assert classify(payload, ['sacrifice-outlet'])[0]['name'] == 'Interaction'


@pytest.mark.parametrize('tags', [[], ['recursion'], ['card-draw', 'recursion']])
def test_electric_revelation_draw_is_primary_over_flashback(tags):
    roles = classify({'type_line': 'Instant', 'keywords': ['Flashback'], 'oracle_text':
        'As an additional cost to cast this spell, discard a card.\nDraw two cards.\n'
        'Flashback {3}{R} (You may cast this card from your graveyard for its flashback cost.)'}, tags)
    assert [r['name'] for r in roles] == ['Draw', 'Recursion']
    assert roles[0]['score'] > roles[1]['score']


def test_flashback_does_not_demote_actual_recursion_effect():
    roles = classify({'keywords': ['Flashback'], 'oracle_text':
        'Return target creature card from your graveyard to your hand. Draw a card.'})
    assert [r['name'] for r in roles] == ['Recursion', 'Draw']
    assert 'Sacrifice / Aristocrats' in {r['name'] for r in classify({
        'oracle_text': 'Sacrifice another creature: Draw a card.'})}


@pytest.mark.parametrize('text', [
    'Haste\nProwess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nInstant and sorcery spells you cast cost {1} less to cast.',
    'Whenever you cast an instant or sorcery spell with mana value greater than the number of experience counters you have, you get an experience counter.\nInstant and sorcery spells you cast cost {1} less to cast for each experience counter you have.',
    'Creature spells you cast cost {2} less to cast.',
    'Spells you cast cost {1} less to cast.',
    'Spells you cast that target a creature cost {1} less to cast.',
    'Instant and sorcery spells you cast cost 1 less to cast.',
])
def test_spell_cost_reducers_are_ramp(text):
    roles = classify({'type_line': 'Creature', 'oracle_text': text})
    assert roles[0]['name'] == 'Ramp'
    assert 'reduces the cost' in roles[0]['reason']


@pytest.mark.parametrize('text', [
    'This spell costs {1} less to cast for each artifact you control.',
    'Spells your opponents cast cost {1} less to cast.',
    'Spells you cast cost {1} more to cast.',
    'Spells you cast cannot be countered. This spell costs {1} less to cast.',
    'Reminder (Spells you cast cost {1} less to cast.)',
])
def test_self_discount_and_opponent_discount_are_not_ramp(text):
    assert 'Ramp' not in {r['name'] for r in classify({'oracle_text': text})}
