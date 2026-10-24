"""Compatibility across the service's internal operation groups."""
from mtg_core.services import CardService


def test_artwork_selection_uses_overridden_print_lookup(tmp_path):
    class CustomService(CardService):
        def get_prints(self, oracle_id, *, allow_remote=False):
            assert oracle_id == 'oracle'
            return [{'id': 'first'}, {'id': 'favorite'}]

    service = CustomService(db_path=str(tmp_path / 'cards.sqlite3'))
    service.set_artwork_favorite('oracle', 'favorite')

    assert service.choose_preferred_print('oracle')['id'] == 'favorite'


def test_bulk_sync_uses_image_override_and_current_fetch_dependency(tmp_path):
    stored = []

    class CustomService(CardService):
        def store_image_bytes(self, payload, **kwargs):
            stored.append(payload)
            return super().store_image_bytes(payload, **kwargs)

    payload = {'id': 'print', 'oracle_id': 'oracle', 'name': 'Example',
               'set': 'tst', 'collector_number': '1',
               'image_uris': {'png': 'https://example.invalid/card.png'}}
    service = CustomService(
        db_path=str(tmp_path / 'cards.sqlite3'),
        image_root=str(tmp_path / 'images'),
        fetch_json_fn=lambda url: {'data': [payload], 'has_more': False},
        fetch_bytes_fn=lambda url: b'old',
    )
    service.fetch_bytes_fn = lambda url: b'current image'

    status = service.process_bulk_download_chunk(min_image_bytes=1)

    assert status.completed
    assert status.total_downloaded == 1
    assert stored == [b'current image']
    assert service.get_card(card_id='print')['name'] == 'Example'
    # The resumed downloader recognizes the asset written by the image group.
    service.reset_bulk_download_status(min_image_bytes=1)
    resumed = service.process_bulk_download_chunk(min_image_bytes=1)
    assert resumed.total_skipped == 1
    assert stored == [b'current image']
