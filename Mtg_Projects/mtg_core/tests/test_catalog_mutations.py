import sqlite3

import pytest

from mtg_core.admin_service import CardAdminService
from mtg_core.db import CardDatabase


def setup_catalog(tmp_path):
    db = CardDatabase(str(tmp_path / 'cards.sqlite3'))
    db.create_oracle_card(oracle_id='oracle', name='Example', layout='normal')
    return db, CardAdminService(database=db)


def test_admin_writes_refresh_structured_search_and_preserve_payload(tmp_path):
    db, admin = setup_catalog(tmp_path)
    admin.create_print(card_id='print', oracle_id='oracle', name='Example', set_code='old',
        payload={'oracle_text': 'Draw a card.', 'type_line': 'Sorcery', 'cmc': 2})
    assert [r.card_id for r in db.search_syntax('s:old t:sorcery o:draw mv=2')] == ['print']
    record = admin.update_print('print', oracle_id='oracle', name='New Name', set_code='new')
    assert record.payload['oracle_text'] == 'Draw a card.'
    assert db.search_syntax('s:old') == []
    assert [r.card_id for r in db.search_syntax('s:new o:draw')] == ['print']
    assert [r.card_id for r in db.search_prints('New Name')] == ['print']
    assert admin.delete_print('print')
    assert db.search_syntax('s:new') == []


def test_oracle_delete_cleans_dependencies_but_retains_shared_assets(tmp_path):
    db, admin = setup_catalog(tmp_path)
    db.create_print(card_id='a', oracle_id='oracle', name='A')
    db.create_print(card_id='b', oracle_id='oracle', name='B')
    db.set_artwork_favorite('oracle', 'a')
    asset = db.store_image_asset(b'keep shared artwork', source='test')
    db.upsert_image_record('a', variant='default', asset_id=asset.asset_id, path=None,
                          status='stored', source='test', checksum=asset.checksum)
    with db.connect() as connection:
        connection.execute("INSERT INTO oracle_tags VALUES ('oracle', 'draw')")
    assert admin.delete_card('oracle')
    assert db.get_oracle_card('oracle') is None
    assert admin.get_card('oracle') is None
    assert db.get_artwork_favorite('oracle') is None
    assert db.oracle_tags_for_card('oracle') == []
    assert db.get_image_asset(asset.asset_id) is not None
    with db.connect() as connection:
        for table in ('prints', 'canonical_prints', 'image_manifest', 'print_search_data', 'print_search_fts'):
            assert connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
    assert not admin.delete_card('oracle')


def test_print_reassignment_and_delete_clear_stale_favorites(tmp_path):
    db, admin = setup_catalog(tmp_path)
    db.create_oracle_card(oracle_id='other', name='Other')
    db.create_print(card_id='a', oracle_id='oracle', name='A')
    db.set_artwork_favorite('oracle', 'a')
    admin.update_print('a', oracle_id='other', name='A')
    assert db.get_artwork_favorite('oracle') is None
    db.set_artwork_favorite('other', 'a')
    admin.delete_print('a')
    assert db.get_artwork_favorite('other') is None


def test_failed_search_refresh_rolls_back_print_and_all_derived_state(tmp_path, monkeypatch):
    db, admin = setup_catalog(tmp_path)
    original = db.create_print(card_id='a', oracle_id='oracle', name='Original', set_code='old')

    def fail(*args):
        raise RuntimeError('simulated index failure')

    monkeypatch.setattr(db, 'refresh_search_data_for_print', fail)
    with pytest.raises(RuntimeError):
        admin.update_print('a', oracle_id='oracle', name='Changed', set_code='new')
    assert db.get_print_by_card_id('a') == original
    assert db.get_canonical_print('oracle') == original
    assert db.search_prints('Changed') == []
    assert [r.card_id for r in db.search_syntax('s:old')] == ['a']
    with pytest.raises(RuntimeError):
        admin.create_print(card_id='b', oracle_id='oracle', name='Another')
    assert db.get_print_by_card_id('b') is None


def test_missing_parent_and_duplicate_ids_leave_existing_data_intact(tmp_path):
    db, admin = setup_catalog(tmp_path)
    original = db.create_print(card_id='a', oracle_id='oracle', name='A')
    with pytest.raises(ValueError, match='does not exist'):
        admin.update_print('a', oracle_id='missing', name='Changed')
    with pytest.raises(ValueError, match='was not found'):
        admin.update_card('missing', name='Changed')
    with pytest.raises(sqlite3.IntegrityError):
        db.create_print(card_id='a', oracle_id='oracle', name='Replacement')
    assert db.get_print_by_card_id('a') == original
