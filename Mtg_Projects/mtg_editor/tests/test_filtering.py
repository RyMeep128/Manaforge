import pytest
from mtg_core.decks import DeckDocument, DeckEntry, DeckCategory
from mtg_editor.filtering import compile_filter, matches
from mtg_editor.organization import grouped_entries, card_facts


def test_combined_filters_preserve_deck_and_print_state():
    document = DeckDocument()
    document.deck.categories = [DeckCategory('draw', 'Card Draw')]
    entry = DeckEntry('a', "Scholar's Familiar", quantity=4, category_ids=['draw'],
                      set_code='ABC', tags=['Flying'], extras={'facts': card_facts({
                          'type_line': 'Creature — Bird', 'cmc': 2, 'colors': ['U'],
                          'color_identity': ['W', 'U'], 'legalities': {'commander': 'legal'},
                          'card_faces': [{'oracle_text': 'Draw a card.'}]})})
    document.deck.entries = [entry, DeckEntry('b', 'Forest')]
    before = document.to_dict()
    groups = grouped_entries(document.deck, query='t:bird mv<=2 id:wu c=u category:"Card Draw" legal:commander -s:xyz o:"draw a card"')
    assert [e.entry_id for _, _, entries in groups for e in entries] == ['a']
    assert document.to_dict() == before
    assert matches(entry, compile_filter("name:Scholar's"), {})


def test_unknown_data_is_not_colorless_or_zero_and_symbolic_power_is_not_numeric():
    unknown = DeckEntry('a', 'Unknown', extras={'facts': {'power': '*'}})
    for query in ('c:c', 'mv=0', 'power>0', 'legal:commander'):
        assert not matches(unknown, compile_filter(query), {})
    assert matches(unknown, compile_filter('-c:u'), {})
    unknown.extras['facts']['colors'] = []
    assert matches(unknown, compile_filter('c:c'), {})


@pytest.mark.parametrize('query', ['mv:abc', 'c:purple', 'is:missing', 'unknown:foo',
                                  'name>foo', 'tag:', 'tag:"unfinished'])
def test_invalid_filters_explain_errors(query):
    with pytest.raises(ValueError):
        compile_filter(query)


def test_entry_flags_and_treatment():
    entry = DeckEntry('a', 'Example', owned=2, do_not_print=True, extras={
        'oversized': True, 'backside_asset_id': 'back',
        'facts': {'finishes': ['foil'], 'border_color': 'borderless', 'layout': 'modal_dfc'}})
    assert matches(entry, compile_filter('is:owned is:do-not-print is:back is:dfc is:oversized treatment:foil treatment:borderless'), {})
    assert not matches(entry, compile_filter('is:excluded'), {})
