from types import SimpleNamespace

import pytest

from mtg_core.commander_discovery import search_commanders
from mtg_core.discovery_starter import starter_data, snapshot_path
from mtg_core.discovery_themes import theme_catalog, theme_matches
from mtg_core.edhrec import EdhrecSource
from mtg_core.edhrec_discovery import DiscoveryStore
from mtg_core.services import CardService
from mtg_core.decks import DeckEntry


def test_bundled_snapshot_contains_real_resolvable_cards_and_exact_cohorts(tmp_path, monkeypatch):
    monkeypatch.setattr('socket.socket.connect', lambda *args: pytest.fail('Unexpected network request'))
    data = starter_data()
    cards = {card['payload']['oracle_id']: card for card in data['cards']}
    assert len(cards) >= 2000 and len(data['pages']) >= 30
    store = DiscoveryStore(snapshot_path(tmp_path, 'edhrec-discovery.sqlite3'))
    source = EdhrecSource(snapshot_path(tmp_path, 'edhrec.sqlite3'))
    snapshot = store.snapshot()
    assert snapshot['coverage'] == 'starter' and len(snapshot['themes']) >= 300
    for cohort in data['cohorts']:
        assert all(oid in cards for oid in cohort['identities'])
        ranked = source.snapshot(cohort['identities'])
        assert ranked['results']
        assert all(row['oracle_id'] in cards for row in ranked['results'])
    # A collected file always wins; materialization never overwrites it.
    collected = tmp_path / 'edhrec.sqlite3'
    collected.write_bytes(b'private collected data')
    assert snapshot_path(tmp_path, 'edhrec.sqlite3') == collected
    assert collected.read_bytes() == b'private collected data'


def test_metadata_groups_actual_types_and_keeps_cached_origins():
    catalog = theme_catalog([{'slug': 'elves', 'name': 'Elves', 'cohorts': 3}],
                            {'creature_types': ['Elf', 'Mouse', 'Dragon', 'Capybara'],
                             'companions': [{'name': 'Example, Companion', 'oracle_id': 'companion'}]})
    options = {row['slug']: row for row in catalog}
    assert options['elves']['origin'] == 'edhrec'
    assert options['elves']['subtype'] == 'Elf'
    assert options['mice']['group'] == options['capybaras']['group'] == 'Typal'
    assert options['example']['group'] == 'Companions'
    row = {'oracle_id': 'elf', 'roles': [],
           'entry': DeckEntry('elf', 'Elf', extras={'facts': {'type_line': 'Creature \u2014 Elf'}})}
    assert theme_matches(row, options['elves'])
    assert not theme_matches(row, options['dragons'])


def test_first_release_and_tags_come_from_all_local_printings(tmp_path):
    service = CardService(db_path=str(tmp_path / 'cards.sqlite3'),
                          fetch_json_fn=lambda *args: pytest.fail('Unexpected network request'))
    for card_id, released in [('old', '1993-08-05'), ('new', '2026-10-01')]:
        service.database.upsert_card_payload(dict(id=card_id, oracle_id='oracle', name='Example',
                                                  released_at=released, type_line='Artifact'))
    with service.database.connect() as db:
        db.execute("INSERT INTO oracle_tags VALUES ('oracle', 'ramp')")
    facts = service.database.recommendation_metadata(['oracle'])['oracle']
    assert facts == {'first_released_at': '1993-08-05', 'oracle_tags': ['ramp']}


def test_commander_identity_and_theme_membership_use_real_local_results(tmp_path):
    service = CardService(db_path=str(tmp_path / 'cards.sqlite3'),
                          fetch_json_fn=lambda *args: pytest.fail('Unexpected network request'))
    for key, colors in [('white', ['W']), ('blue', ['U'])]:
        service.database.upsert_card_payload(dict(id=key, oracle_id=key, name=key,
            type_line='Legendary Creature \u2014 Human', color_identity=colors,
            legalities={'commander': 'legal'}, oracle_text='Whenever you gain life, draw a card.'))
    store = SimpleNamespace(snapshot=lambda *args, **kwargs: dict(themes=[], members=[], status='No cache'))
    snapshot = search_commanders(service, {'identity': 'W', 'theme': 'lifegain'}, store)
    assert [row['card'].oracle_id for row in snapshot['results']] == ['white']
    assert snapshot['themes'] and not snapshot['ranked']


def test_pair_color_filter_uses_combined_identity(tmp_path):
    service = CardService(db_path=str(tmp_path / 'cards.sqlite3'),
                          fetch_json_fn=lambda *args: pytest.fail('Unexpected network request'))
    for key, colors in [('white', ['W']), ('blue', ['U'])]:
        service.database.upsert_card_payload(dict(id=key, oracle_id=key, name=key,
            type_line='Legendary Creature \u2014 Human', color_identity=colors, keywords=['Partner'],
            legalities={'commander': 'legal'}, oracle_text='Partner'))
    store = SimpleNamespace(snapshot=lambda *args, **kwargs: dict(themes=[], members=[], status='No cache'))
    snapshot = search_commanders(service, {'identity': 'WU', 'partner_card_id': 'white'}, store)
    assert [row['card'].oracle_id for row in snapshot['results']] == ['blue']


def test_starter_catalog_fills_missing_cards_without_overwriting_existing(tmp_path, monkeypatch):
    from mtg_core.discovery_starter import ensure_starter_catalog
    monkeypatch.setattr('mtg_core.paths.core_data_root', lambda: tmp_path)
    service = CardService(db_path=str(tmp_path / 'cards.sqlite3'),
                          fetch_json_fn=lambda *args: pytest.fail('Unexpected network request'))
    service.database.upsert_card_payload(dict(id='existing', oracle_id='existing', name='My printing'))
    cards = [dict(payload=dict(id=key, oracle_id=key, name='Bundled name', type_line='Artifact'),
                  first_released_at='2000-01-01', tags=['ramp']) for key in ['existing', 'missing']]
    monkeypatch.setattr('mtg_core.discovery_starter.starter_data', lambda: {'cards': cards})
    ensure_starter_catalog(service)
    assert service.get_card(card_id='existing')['name'] == 'My printing'
    assert service.get_card(card_id='missing')['name'] == 'Bundled name'
    assert service.get_oracle_tags('missing') == ['ramp']
    assert service.database.recommendation_metadata(['missing'])['missing']['first_released_at'] == '2000-01-01'
