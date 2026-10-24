import sqlite3
from types import SimpleNamespace

import pytest

from mtg_core.search.cancellation import SearchCancelled, search_connection
from mtg_core.services import CardService


def test_sql_interrupt_closes_connection_and_allows_subsequent_reads(tmp_path):
    database = SimpleNamespace(db_path=str(tmp_path / 'cards.sqlite3'))
    database.connect = lambda: sqlite3.connect(database.db_path)
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls >= 5

    with pytest.raises(SearchCancelled):
        with search_connection(database, cancel) as connection:
            connection.execute('WITH RECURSIVE n(x) AS (VALUES(0) UNION ALL '
                               'SELECT x+1 FROM n WHERE x<10000000) SELECT sum(x) FROM n').fetchone()
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute('SELECT 1')
    with search_connection(database) as fresh:
        assert fresh.execute('SELECT 1').fetchone()[0] == 1


def test_cancellation_flows_through_service_and_role_reads(tmp_path):
    service = CardService(db_path=str(tmp_path / 'cards.sqlite3'),
                          fetch_json_fn=lambda url: pytest.fail('Search must remain local'))
    for read in (lambda: service.search_editor_cards('bird', should_cancel=lambda: True),
                 lambda: service.search_cards('bird', {'scryfall_syntax': True,
                     'allow_remote': False, 'should_cancel': lambda: True}),
                 lambda: service.database.categorization_data([], [], should_cancel=lambda: True)):
        with pytest.raises(SearchCancelled):
            read()
    assert service.search_editor_cards('bird') == []
