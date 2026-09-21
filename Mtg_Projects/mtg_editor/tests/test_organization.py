import pytest
from mtg_core.decks import DeckDocument, DeckEntry, DeckCategory, DeckHistory
from mtg_editor.organization import grouped_entries, move_entries, remove_category, assign


def deck():
    document = DeckDocument()
    document.deck.entries = [DeckEntry('a', 'Alpha', sort_order=0, category_ids=['ramp', 'draw']),
                             DeckEntry('b', 'Beta', sort_order=1),
                             DeckEntry('c', 'Commander', section='commander', sort_order=2)]
    document.deck.categories = [DeckCategory('ramp', 'Ramp'), DeckCategory('draw', 'Draw', 1)]
    return document


def test_move_and_category_deletion_preserve_quantities_and_other_memberships():
    document = deck()
    history = DeckHistory(document)
    history.execute(lambda d: move_entries(d, {'a', 'b'}, 'Section', 'Sideboard', 'c'))
    assert [e.section for e in document.deck.entries[:2]] == ['sideboard', 'sideboard']
    assert sum(e.quantity for e in document.deck.entries) == 3
    history.undo()
    assert document.deck.entries[0].section == 'mainboard'
    history.execute(lambda d: remove_category(d, 'ramp'))
    assert document.deck.entries[0].category_ids == ['draw']
    history.undo()
    assert document.deck.entries[0].category_ids == ['ramp', 'draw']


def test_commanders_first_filtering_and_numeric_mana_group_order():
    document = deck()
    document.deck.entries[0].extras['facts'] = {'cmc': 10}
    document.deck.entries[1].extras['facts'] = {'cmc': 2}
    assert [key for key, _, _ in grouped_entries(document.deck, 'Mana Value')] == ['Commander', 'MV 2', 'MV 10']
    assert grouped_entries(document.deck, query='Alpha')[0][2][0].entry_id == 'a'


def test_failed_command_rolls_back_without_history():
    document = deck()
    before = document.to_dict()
    history = DeckHistory(document)
    def fail(d):
        d.deck.entries[0].quantity = 500
        raise ValueError('invalid operation')
    with pytest.raises(ValueError):
        history.execute(fail)
    assert document.to_dict() == before
    assert not history.can_undo


def test_move_primary_category_retains_extra_categories_and_commander_ids():
    document = deck()
    move_entries(document, {'a', 'c'}, 'Category', 'draw')
    assert document.deck.entries[0].category_ids == ['draw', 'ramp']
    assert document.deck.entries[2].section == 'mainboard'
    assert not document.deck.commander_entry_ids
    assign(document, {'a', 'b'}, 'section', 'commander')
    assert document.deck.commander_entry_ids == ['a', 'b']


def test_empty_categories_hide_without_removing_assignments_or_definitions():
    document = deck()
    before = document.to_dict()
    assert [key for key, _, _ in grouped_entries(document.deck, 'Category')] == ['Commander', 'ramp', 'Uncategorized']
    assert 'draw' in [key for key, _, _ in grouped_entries(document.deck, 'Category', show_empty_categories=True)]
    assert document.to_dict() == before
    assign(document, {'a'}, 'category', 'draw')
    keys = [key for key, _, _ in grouped_entries(document.deck, 'Category')]
    assert 'draw' in keys and 'ramp' not in keys
    assert [key for key, _, _ in grouped_entries(document.deck, 'Category', query='missing')] == []


def test_color_sort_wubrg_multicolor_colorless_unknown():
    document = DeckDocument()
    colors = [None, [], ['G', 'W'], ['G'], ['R'], ['B'], ['U'], ['W']]
    document.deck.entries = [DeckEntry(str(i), str(i), extras={'facts': {'colors': c}})
                             for i, c in enumerate(colors)]
    entries = grouped_entries(document.deck, 'Section', sort='Color')
    mainboard = next(cards for key, _, cards in entries if key == 'Mainboard')
    assert [e.entry_id for e in mainboard] == ['7', '6', '5', '4', '3', '2', '1', '0']
