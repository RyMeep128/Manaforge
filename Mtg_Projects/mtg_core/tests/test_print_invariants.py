import pytest

from mtg_core.admin_service import CardAdminService
from mtg_core.db import CardDatabase


def payload(card_id='print-a', oracle_id='oracle-a', released_at='2000-01-01'):
    return dict(id=card_id, oracle_id=oracle_id, name='Example', set='tst',
                collector_number='1', released_at=released_at, type_line='Artifact')


def test_final_print_deletion_cleans_mapping_and_secondary_data(tmp_path):
    database = CardDatabase(str(tmp_path / 'cards.sqlite3'))
    database.upsert_card_payload(payload())
    admin = CardAdminService(database=database)
    asset = database.store_image_asset(b'image-bytes', source='test')
    database.upsert_image_record('print-a', variant='default', asset_id=asset.asset_id,
        path=None, status='stored', source='test', checksum=asset.checksum)
    assert admin.delete_print('print-a')
    assert database.get_canonical_print('oracle-a') is None
    assert database.search_syntax('Example') == []
    with database.connect() as connection:
        for table in ('prints', 'canonical_prints', 'print_search_data', 'image_manifest'):
            assert connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
        # The Oracle identity is not implicitly deleted with its last printing.
        assert connection.execute('SELECT count(*) FROM cards_oracle').fetchone()[0] == 1
    assert not admin.delete_print('print-a')
    assert database.get_image_asset(asset.asset_id) is not None


def test_refresh_removes_stale_mapping_with_no_prints_and_rolls_back(tmp_path):
    database = CardDatabase(str(tmp_path / 'cards.sqlite3'))
    database.upsert_card_payload(payload())
    with pytest.raises(RuntimeError):
        with database.connect() as connection:
            connection.execute('DELETE FROM prints')
            database.refresh_canonical_print(connection, 'oracle-a')
            assert connection.execute('SELECT count(*) FROM canonical_prints').fetchone()[0] == 0
            raise RuntimeError('abort transaction')
    assert database.get_canonical_print('oracle-a').card_id == 'print-a'


@pytest.mark.parametrize('admin_path', [False, True])
@pytest.mark.parametrize('has_remaining', [False, True])
def test_reassign_print_refreshes_both_oracle_mappings(tmp_path, admin_path, has_remaining):
    database = CardDatabase(str(tmp_path / 'cards.sqlite3'))
    database.upsert_card_payload(payload())
    if has_remaining:
        database.upsert_card_payload(payload('print-b', released_at='2001-01-01'))
    database.upsert_card_payload(payload('print-c', 'oracle-b', '2002-01-01'))
    if admin_path:
        CardAdminService(database=database).update_print('print-a', oracle_id='oracle-b',
            name='Example', set_code='tst', collector_number='1', released_at='2000-01-01')
    else:
        database.upsert_card_payload(payload(oracle_id='oracle-b'))
    old = database.get_canonical_print('oracle-a')
    assert (old.card_id if old else None) == ('print-b' if has_remaining else None)
    assert database.get_canonical_print('oracle-b').card_id == 'print-a'


def test_admin_and_core_share_full_print_conversion(tmp_path):
    database = CardDatabase(str(tmp_path / 'cards.sqlite3'))
    admin = CardAdminService(database=database)
    admin.create_card(oracle_id='oracle-a', name='Example', layout='transform')
    created = admin.create_print(card_id='print-a', oracle_id='oracle-a', name='Example',
        set_code='tst', set_name='Test Set', collector_number='7', released_at='2020-01-01',
        image_url='https://example.com/full.png', thumbnail_url='https://example.com/small.png',
        preview_url='https://example.com/normal.png', is_double_faced=True)
    assert created == database.get_print_by_card_id('print-a') == admin.list_prints().items[0]
    assert database.row_to_print_record(None) is None
