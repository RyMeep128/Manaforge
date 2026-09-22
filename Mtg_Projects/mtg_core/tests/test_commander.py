from copy import deepcopy
import pytest
from mtg_core.commander import check_commander, compatible, eligible, set_commanders, copy_limit
from mtg_core.decks import DeckDocument, DeckEntry, DeckHistory

NOW = 1800000000


def card(name='Leader', line='Legendary Creature — Human', text='', colors=('G',)):
    return {'name': name, 'type_line': line, 'oracle_text': text, 'color_identity': list(colors),
            'legalities': {'commander': 'legal'}}


def deck():
    doc = DeckDocument()
    doc.deck.entries = [DeckEntry('leader', 'Leader', card_id='leader', section='commander'),
                        DeckEntry('land', 'Forest', card_id='land', quantity=99)]
    doc.deck.commander_entry_ids = ['leader']
    records = {'leader': {'payload': card(), 'cached_at': NOW},
               'land': {'payload': card('Forest', 'Basic Land — Forest'), 'cached_at': NOW}}
    return doc, records


def codes(doc, records):
    return {i.code for i in check_commander(doc, records, now=NOW).issues}


def test_valid_deck_print_flags_and_nonplaying_sections():
    doc, records = deck()
    doc.deck.entries[1].do_not_print = True
    doc.deck.entries.append(DeckEntry('side', 'Bad', section='sideboard', quantity=80))
    report = check_commander(doc, records, now=NOW)
    assert report.total == 100 and not report.issues
    assert report.oldest_cache == NOW


def test_size_duplicates_ban_identity_and_land_types():
    doc, records = deck()
    doc.deck.entries[1].quantity = 96
    doc.deck.entries.extend([DeckEntry('a', 'Spell', card_id='a'), DeckEntry('b', 'Spell', card_id='b')])
    for key in ('a', 'b'):
        records[key] = {'payload': card('Spell', 'Instant', colors=('R',)), 'cached_at': NOW}
    records['a']['payload']['legalities']['commander'] = 'banned'
    assert {'size', 'singleton', 'identity', 'legality'} <= codes(doc, records)
    records['land']['payload']['type_line'] = 'Basic Land — Island'
    assert 'land_types' in codes(doc, records)


def test_unknown_and_stale_never_report_clean():
    doc, records = deck()
    records['land']['cached_at'] = NOW - 31 * 86400
    records['leader']['payload'].pop('color_identity')
    records['leader']['payload']['legalities'] = {}
    report = check_commander(doc, records, now=NOW)
    assert {'stale', 'identity', 'commander_identity', 'legality'} <= {i.code for i in report.issues}
    assert 'Review needed' in report.summary
    assert 'undated' in codes(doc, {})


@pytest.mark.parametrize('left,right,expected', [
    (card(text='Partner'), card('Other', text='Partner'), True),
    (card(text='Partner'), card('Other', text='Friends forever'), False),
    (card(text='Friends forever'), card('Other', text='Friends forever'), True),
    (card(text='Partner—Survivors'), card('Other', text='Partner—Survivors'), True),
    (card(text='Partner with Other'), card('Other', text='Partner with Leader'), True),
    (card(text='Partner with Other'), card('Other', text='Partner with Someone else'), False),
    (card(text='Choose a Background'), card('Story', 'Legendary Enchantment — Background'), True),
    (card(text='Choose a Background'), card('Story', 'Enchantment — Background'), False),
    (card(text="Doctor's companion"), card('Doctor', 'Legendary Creature — Time Lord Doctor'), True),
    (card(text="Doctor's companion"), card('Doctor', 'Legendary Creature — Human Time Lord Doctor'), False),
    (card(), {}, None),
])
def test_pairing(left, right, expected):
    assert compatible(left, right) is expected
    assert compatible(right, left) is expected


@pytest.mark.parametrize('payload,expected', [
    (card(), True), (card(line='Creature — Human'), False),
    (card(line='Legendary Enchantment — Background'), False),
    (card(line='Legendary Planeswalker — Test', text='Leader can be your commander.'), True),
    ({**card(line='Legendary Artifact — Vehicle'), 'power': '4', 'toughness': '4'}, True),
    ({**card(line='Legendary Artifact — Spacecraft'), 'power': '4', 'toughness': '4'}, True),
    (card(line='Legendary Artifact — Spacecraft'), False),
    ({'card_faces': [card(line='Artifact'), card()]}, False),
    ({}, None),
])
def test_commander_eligibility(payload, expected):
    assert eligible(payload) is expected


@pytest.mark.parametrize('payload,expected', [
    (card('Forest', 'Basic Land — Forest'), float('inf')),
    (card('Rat', text='A deck can have any number of cards named Rat.'), float('inf')),
    (card('Dwarves', text='A deck can have up to seven cards named Dwarves.'), 7),
    (card('Nazgûl', text='A deck can have up to nine cards named Nazgûl.'), 9),
    (card('Other'), 1), ({}, None),
])
def test_copy_exceptions(payload, expected):
    assert copy_limit(payload) == expected


def test_selection_preserves_quantities_and_undo_persistence():
    doc, _ = deck()
    history = DeckHistory(doc)
    before = doc.to_dict()
    history.execute(lambda d: set_commanders(d, ['land']))
    assert doc.deck.entries[1].quantity == 99
    assert doc.deck.entries[0].section == 'mainboard'
    assert DeckDocument.from_dict(doc.to_dict()).deck.commander_entry_ids == ['land']
    history.undo()
    assert doc.to_dict() == before
    with pytest.raises(ValueError):
        set_commanders(doc, ['leader', 'leader'])
    assert doc.to_dict() == before


def test_background_and_pregame_color_are_not_false_failures():
    doc, records = deck()
    records['leader']['payload']['oracle_text'] = 'Choose a Background'
    doc.deck.entries.append(DeckEntry('bg', 'Story', card_id='bg', section='commander'))
    records['bg'] = {'payload': card('Story', 'Legendary Enchantment — Background'), 'cached_at': NOW}
    doc.deck.entries[1].quantity = 98
    assert not codes(doc, records)
    records['leader']['payload']['oracle_text'] += '\nIf Leader is your commander, choose a color before the game begins.'
    assert 'commander_identity' in codes(doc, records)


def test_local_database_cache_dates(tmp_path):
    from mtg_core.db import CardDatabase
    db = CardDatabase(tmp_path / 'cards.sqlite3')
    # Use the same public ingest path as the card service.
    payload = {**card(), 'id': 'test', 'oracle_id': 'oracle', 'set': 'tst', 'collector_number': '1'}
    db.upsert_card_payload(payload)
    records = db.legality_data(['test', 'test', None, 'missing'])
    assert set(records) == {'test'}
    assert records['test']['payload']['legalities']['commander'] == 'legal'
    assert records['test']['cached_at'] > 0
