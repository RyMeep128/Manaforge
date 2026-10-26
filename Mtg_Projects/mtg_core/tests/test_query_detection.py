import pytest
from mtg_core.search.syntax import is_scryfall_syntax_query


@pytest.mark.parametrize('query,expected', [
    ('Lightning Bolt', False), ('War and Peace', True),
    ('dragon AND red', True), ('dragon OR angel', True), ('NOT dragon', True),
    ('!"Sol Ring"', True), ('"Sol Ring"', True), ('pow>=5', True),
    ('name:"unfinished', True), ('(dragon', True), ('', False), (None, False),
])
def test_shared_query_detection(query, expected):
    assert is_scryfall_syntax_query(query) is expected
