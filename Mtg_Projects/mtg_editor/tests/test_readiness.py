from io import BytesIO

from PIL import Image
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_editor.readiness import inspect_readiness


def image_bytes(size):
    buffer = BytesIO()
    Image.new('RGB', size).save(buffer, format='PNG')
    return buffer.getvalue()


def test_local_scan_counts_copies_and_checks_assigned_assets_without_downloads():
    assets = {'small': image_bytes((100, 140)), 'large': image_bytes((1000, 1400)),
              'broken': b'not an image'}
    class Service:
        def get_image_bytes(self, asset_id):
            return assets.get(asset_id)
        def get_image_path(self, card_id):
            return None
        def ensure_image(self, *args, **kwargs):
            raise AssertionError('Readiness must not download images')
    document = DeckDocument()
    document.print_settings = {'proxy_project': {'backside_enabled': False}}
    document.deck.entries = [
        DeckEntry('a', 'Small DFC', quantity=3, image_asset_id='small', extras={
            'facts': {'layout': 'transform'}, 'pre_cropped': True, 'oversized': True}),
        DeckEntry('b', 'Broken', image_asset_id='broken', do_not_print=True,
                  extras={'facts': {'layout': 'normal'}}),
        DeckEntry('c', 'Custom back', image_asset_id='large', extras={
            'facts': {'layout': 'normal'}, 'backside_asset_id': 'gone'}),
        DeckEntry('d', 'Complete', image_asset_id='large', extras={
            'facts': {'layout': 'modal_dfc'}, 'backside_asset_id': 'large'})]
    before = document.to_dict()
    result = inspect_readiness(document, Service())
    assert result['groups']['missing-art'] == {'b'}
    assert result['groups']['low-dpi'] == {'a'}
    assert result['counts']['low-dpi'] == 3
    assert result['groups']['missing-back'] == {'a', 'c'}
    assert result['groups']['dfc'] == {'a', 'd'}
    assert result['groups']['excluded'] == {'b'}
    assert result['groups']['oversized'] == {'a'}
    assert document.to_dict() == before


def test_duplex_default_back_and_missing_front_are_checked_independently():
    class Service:
        def get_image_bytes(self, asset_id):
            return None
        def get_image_path(self, card_id):
            return None
    document = DeckDocument()
    document.print_settings = {'proxy_project': {'backside_enabled': True,
                                                'backside_default_asset_id': 'gone'}}
    document.deck.entries = [DeckEntry('a', 'Missing', extras={'facts': {'layout': 'normal'}})]
    result = inspect_readiness(document, Service())
    assert result['groups']['missing-art'] == {'a'}
    assert result['groups']['missing-back'] == {'a'}
