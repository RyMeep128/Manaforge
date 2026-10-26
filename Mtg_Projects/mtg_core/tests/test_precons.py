from copy import deepcopy
from types import SimpleNamespace
import pytest

from mtg_core.decks import DeckDocument, DeckEntry
from mtg_core.precons import (normalize_catalog, decklist_entries, prepare_precon,
                              apply_precon, load_catalog, write_catalog, cover_asset)


def source():
    card = dict(name='Original', count=3, set_code='abc', number='42', foil=True,
                mtgjson_uuid='source-printing')
    return [dict(name='Original product', set_name='Product set', set_code='abc',
        release_date='2024-01-01', format='commander', cards=[card],
        commander=[dict(card, name='Partner A', count=1), dict(card, name='Partner B', count=1)],
        sideboard=[dict(card, name='Sideboard', count=2)],
        planarDeck=[dict(card, name='Plane', count=1)],
        schemeDeck=[dict(card, name='Scheme', count=1)],
        displayCommander=[dict(card, name='Display', count=1)])]


def test_normalization_preserves_printings_quantities_and_every_zone():
    raw = source()
    untouched = deepcopy(raw)
    record = normalize_catalog(raw)['decks'][0]
    assert raw == untouched
    rows = decklist_entries(record)
    assert [r.section for r in rows] == ['mainboard', 'commander', 'commander', 'sideboard',
                                        'planar', 'scheme', 'display_commander']
    assert sum(r.count for r in rows) == 10
    assert rows[0].set_code == 'abc' and rows[0].collector_number == '42'
    assert normalize_catalog(raw)['decks'][0]['id'] == record['id']
    assert record['entries'][0]['foil'] is True


def test_independent_decks_and_origin_roundtrip(monkeypatch):
    from mtg_core import precons
    record = normalize_catalog(source())['decks'][0]
    def resolve(rows, service, **options):
        return ([DeckEntry(str(i), row.name, quantity=row.count, section=row.section,
                           card_id=str(i)) for i, row in enumerate(rows)], {}, [])
    monkeypatch.setattr(precons, 'resolve_entries', resolve)
    result = prepare_precon(record, object())
    a, b = DeckDocument(), DeckDocument()
    apply_precon(a, record, result, 'My upgrade', 'product-art')
    apply_precon(b, record, result)
    assert a.deck.deck_id != b.deck.deck_id
    assert a.deck.name == 'My upgrade' and b.deck.name == record['name']
    assert a.deck.format == 'Commander'
    assert len(a.deck.commander_entry_ids) == 2
    assert a.deck.entries[-1].do_not_print
    assert a.deck.entries[0].extras['precon_printing']['foil']
    a.deck.entries[0].quantity = 99
    assert b.deck.entries[0].quantity == 3
    restored = DeckDocument.from_dict(a.to_dict())
    assert restored.deck.extras['cover_image_asset_id'] == 'product-art'
    assert restored.deck.extras['precon_origin']['original_entries'][0]['count'] == 3
    with pytest.raises(ValueError, match='empty deck'):
        apply_precon(a, record, result)


def test_unresolved_import_never_creates_partial_precon(monkeypatch):
    from mtg_core import precons
    monkeypatch.setattr(precons, 'resolve_entries', lambda *a, **k: ([], {}, ['Missing printing']))
    record = normalize_catalog(source())['decks'][0]
    with pytest.raises(ValueError, match='Missing printing'):
        prepare_precon(record, object())
    document = DeckDocument()
    with pytest.raises(ValueError, match='complete'):
        apply_precon(document, record, ([], {}, []))
    assert not document.deck.entries
    monkeypatch.setattr(precons, 'resolve_entries', lambda *a, **k: None)
    assert prepare_precon(record, object()) is None


def test_refresh_is_atomic_on_invalid_source(tmp_path):
    target = tmp_path / 'precons.json'
    write_catalog(source(), target)
    original = target.read_bytes()
    invalid = source()
    invalid[0]['cards'][0]['count'] = -1
    with pytest.raises(ValueError):
        write_catalog(invalid, target)
    assert target.read_bytes() == original
    assert load_catalog(target)[0]['name'] == 'Original product'


def test_bundled_catalog_is_available_without_installation(tmp_path):
    records = load_catalog(tmp_path / 'missing.json')
    assert len(records) > 1000
    assert records[0]['format'] == 'Commander'
    assert all(record['entries'] for record in records)


def test_artwork_priority_cache_and_offline_mode(monkeypatch):
    from mtg_core import decklists
    downloads = []
    monkeypatch.setattr(decklists, 'import_image', lambda service, url: downloads.append(url) or 'downloaded')
    service = SimpleNamespace(database=SimpleNamespace(find_image_asset_by_url=lambda url: None),
                              get_image_bytes=lambda asset: b'image')
    record = dict(artwork=dict(key_art_url='https://example.com/key.png',
                              product_image_url='https://example.com/box.png'))
    assert cover_asset(record, service, offline=True) is None
    assert downloads == []
    assert cover_asset(record, service) == 'downloaded'
    assert downloads == ['https://example.com/key.png']
    service.database.find_image_asset_by_url = lambda url: 'cached'
    assert cover_asset(record, service, offline=True) == 'cached'
    assert cover_asset(record, service) == 'cached'
    assert len(downloads) == 1


def test_extension_zones_export_and_parse_roundtrip():
    from mtg_core.decklists import export_decklist, parse_decklist
    document = DeckDocument()
    document.deck.entries = [DeckEntry('p', 'Plane', quantity=2, section='planar'),
                             DeckEntry('s', 'Scheme', section='scheme')]
    rows, warnings = parse_decklist(export_decklist(document))
    assert not warnings
    assert [(r.name, r.count, r.section) for r in rows] == [('Plane', 2, 'planar'), ('Scheme', 1, 'scheme')]


def test_precon_uses_shared_exact_printing_resolver(tmp_path):
    import uuid
    from mtg_core.services import CardService
    service = CardService(db_path=str(tmp_path / 'cards.sqlite3'))
    identities = [str(uuid.uuid4()), str(uuid.uuid4())]
    for index, name in enumerate(('Original', 'Commander')):
        service.database.upsert_card_payload(dict(id=identities[index], oracle_id=str(uuid.uuid4()),
            name=name, set='abc', collector_number=str(index + 1), color_identity=['G'],
            type_line='Legendary Creature' if index else 'Basic Land — Forest',
            legalities={'commander': 'legal'}))
    record = normalize_catalog([dict(name='Precon', set_code='abc', set_name='Product',
        release_date='2024-01-01', format='commander',
        cards=[dict(name='Original', count=99, set_code='abc', number='1')],
        commander=[dict(name='Commander', count=1, set_code='abc', number='2')])])['decks'][0]
    result = prepare_precon(record, service, allow_remote=False)
    document = DeckDocument()
    apply_precon(document, record, result)
    assert [(entry.card_id, entry.quantity) for entry in document.deck.entries] == [
        (identities[0], 99), (identities[1], 1)]
    assert document.deck.commander_entry_ids == [document.deck.entries[1].entry_id]


def test_browser_metadata_reuses_cache_and_invalidates_on_database_change(tmp_path, monkeypatch):
    from mtg_core import precons
    monkeypatch.setattr(precons, 'core_data_root', lambda: tmp_path)
    db_path = tmp_path / 'catalog.db'
    db_path.write_bytes(b'initial database')
    class Database:
        calls = 0
        def precon_card_summaries(self, names, **kwargs):
            self.calls += 1
            return {name: dict(id=name, color_identity=['U', 'G']) for name in names}
    database = Database()
    database.db_path = str(db_path)
    service = SimpleNamespace(database=database)
    records = normalize_catalog(source())['decks']
    first = list(precons.browser_metadata(service, records))
    assert first[0][0][1:3] == ('UG', True)
    assert first[0][0][3]['id'] == 'Partner A'
    calls = database.calls
    assert list(precons.browser_metadata(service, records)) == first
    assert database.calls == calls
    db_path.write_bytes(b'updated database with new cards')
    assert list(precons.browser_metadata(service, records)) == first
    assert database.calls > calls
    calls = database.calls
    assert list(precons.browser_metadata(service, records, cancelled=lambda: True)) == []
    assert database.calls == calls


def test_precon_summaries_select_latest_print_and_handle_missing_and_colorless(tmp_path):
    import json
    import sqlite3
    from mtg_core.db.cards import CardOperations
    path = tmp_path / 'summaries.sqlite3'
    class Database(CardOperations):
        def connect(self):
            connection = sqlite3.connect(path)
            connection.row_factory = sqlite3.Row
            return connection
    database = Database()
    with database.connect() as connection:
        connection.execute('CREATE TABLE prints (card_id TEXT, name TEXT, updated_at REAL, payload_json TEXT)')
        connection.executemany('INSERT INTO prints VALUES (?, ?, ?, ?)', [
            ('older', 'Commander', 1, json.dumps(dict(color_identity=['R']))),
            ('newer', 'Commander', 2, json.dumps(dict(color_identity=['W', 'U']))),
            ('land', 'Land', 1, json.dumps(dict(color_identity=[])))])
    summaries = database.precon_card_summaries(['commander', 'Land', 'Missing'])
    assert summaries == {'commander': dict(id='newer', color_identity=['W', 'U']),
                         'Land': dict(id='land', color_identity=[]), 'Missing': None}
    assert database.precon_card_summaries(['commander'], cancelled=lambda: True) == {}
