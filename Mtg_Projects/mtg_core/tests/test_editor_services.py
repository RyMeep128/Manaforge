from copy import deepcopy

import pytest

from mtg_core.decks import DeckEntry
from mtg_core.services import CardService


def test_editor_analysis_is_batched_local_and_read_only(tmp_path):
    service = CardService(db_path=str(tmp_path / 'cards.sqlite3'),
        fetch_json_fn=lambda url: pytest.fail('Editor analysis must not download data'))
    service.database.upsert_card_payload({'id': 'card', 'oracle_id': 'oracle', 'name': 'Example',
        'type_line': 'Artifact', 'legalities': {'commander': 'legal'}})
    with service.database.connect() as connection:
        connection.execute("INSERT INTO oracle_tags VALUES ('oracle', 'ramp')")
    entries = [DeckEntry(str(i), 'Example', card_id='card', oracle_id='oracle') for i in range(500)]
    entries.append(DeckEntry('fallback', 'Unknown', extras={'facts': {'type_line': 'Land'}}))
    before = deepcopy(entries)
    calls = []
    connect = service.database.connect

    def traced():
        connection = connect()
        connection.set_trace_callback(calls.append)
        return connection

    service.database.connect = traced
    proposals = service.analyze_entries(iter(entries))
    assert len(proposals) == 501
    assert proposals['0'][0]['name'] == 'Ramp'
    assert proposals['fallback'][0]['name'] == 'Lands'
    assert len([sql for sql in calls if sql.startswith('SELECT')]) == 2
    assert entries == before
    calls.clear()
    records = service.get_deck_legality_data(iter(entries))
    assert set(records) == {'card'}
    assert records['card']['cached_at'] > 0
    assert records['card']['payload']['legalities'] == {'commander': 'legal'}
    assert len([sql for sql in calls if sql.startswith('SELECT')]) == 1
    assert service.get_oracle_tags('oracle') == ['ramp']
    assert service.get_oracle_tags(None) == []
    assert service.get_oracle_tags('missing') == []
    assert entries == before
