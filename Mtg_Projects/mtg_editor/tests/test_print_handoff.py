from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_editor.proxy_adapter import prepare_print, project_payload, launch_print
from mtg_ui.project_lock import acquire_project_lock
import project_library


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr(project_library, 'cwd', str(tmp_path))
    monkeypatch.setattr(project_library, '_initial_project_dict', lambda path: {
        'pagesize': 'Letter', 'backside_default': '__back.png', 'card_entries': []})
    monkeypatch.setattr(project_library, '_resolve_thumbnail_path', lambda *args: None)
    return tmp_path


def document():
    value = DeckDocument()
    value.deck.entries = [DeckEntry('a', 'Alpha', card_id='print-a', quantity=2, image_asset_id='art-a',
        extras={'oversized': True, 'backside_asset_id': 'art-back', 'backside_name': '__back-a.png',
                'art_override': {'identifier': 'chosen-alt'}}),
        DeckEntry('b', 'Beta', card_id='print-b', image_asset_id='art-b', section='considering'),
        DeckEntry('c', 'Owned', image_asset_id='art-c', do_not_print=True)]
    return value


def test_handoff_preserves_art_backs_layout_and_latest_proxy_settings(library):
    value = document()
    service = SimpleNamespace(get_card=lambda **kwargs: None)
    project = prepare_print(value, service, {'mainboard', 'commander'})
    path = Path(project['path'])
    data = json.loads(path.read_text(encoding='utf-8'))
    entries = {e['entry_id']: e for e in data['card_entries']}
    assert entries['a']['count'] == 2
    assert entries['a']['backside_asset_id'] == 'art-back'
    assert entries['a']['oversized']
    assert entries['b']['do_not_print'] and entries['c']['do_not_print']
    assert data['high_res_front_overrides']['a.png']['identifier'] == 'chosen-alt'
    data['backside_offset'] = '2.5'
    data['backside_separate_file'] = True
    data['manual_layout'] = {'version': 1, 'placements': [
        {'copy_id': json.dumps(['a', 0]), 'entry_id': 'a', 'ordinal': 0, 'page': 1, 'row': 1, 'column': 0},
        {'copy_id': json.dumps(['a', 1]), 'entry_id': 'a', 'ordinal': 1, 'page': 1, 'row': 2, 'column': 0}]}
    path.write_text(json.dumps(data), encoding='utf-8')
    value.extras['proxy_project_id'] = project['id']
    value.deck.entries[0].quantity = 3
    prepare_print(value, service, {'mainboard'})
    updated = json.loads(path.read_text(encoding='utf-8'))
    assert updated['backside_offset'] == '2.5'
    assert updated['backside_separate_file']
    assert updated['manual_layout']['placements'][:2] == data['manual_layout']['placements']
    assert len(updated['manual_layout']['placements']) == 3
    assert len(project_library.list_projects()) == 1


def test_locked_handoff_leaves_project_and_deck_unchanged(library):
    value = document()
    service = SimpleNamespace(get_card=lambda **kwargs: None)
    project = prepare_print(value, service, {'mainboard'})
    value.extras['proxy_project_id'] = project['id']
    before = Path(project['path']).read_bytes()
    snapshot = value.to_dict()
    lock = acquire_project_lock(project['path'])
    try:
        with pytest.raises(OSError, match='another process'):
            prepare_print(value, service, {'mainboard'})
    finally:
        lock.unlock()
    assert Path(project['path']).read_bytes() == before
    assert value.to_dict() == snapshot


def test_failed_new_handoff_does_not_leave_empty_project(library):
    value = DeckDocument()
    value.deck.entries.append(DeckEntry('x', 'No artwork'))
    with pytest.raises(ValueError, match='No printable artwork'):
        prepare_print(value, SimpleNamespace(get_card=lambda **kwargs: None), {'mainboard'})
    assert not project_library.list_projects()


def test_dfc_resolution_uses_existing_proxy_import_and_preserves_override(library, monkeypatch):
    import deck_import
    calls = []
    def download(card, entry, folder, print_fn, fetch_bytes, card_service):
        calls.append(card['id'])
        return SimpleNamespace(image_asset_id='standard-front', backside_asset_id='paired-back'), '__paired.png'
    monkeypatch.setattr(deck_import, 'download_card_image_set', download)
    value = DeckDocument()
    value.deck.entries.append(DeckEntry('dfc', 'Front // Back', card_id='dfc-id', image_asset_id='chosen-front'))
    service = SimpleNamespace(get_card=lambda **kwargs: {'id': 'dfc-id'}, fetch_bytes_fn=lambda url: b'')
    project = prepare_print(value, service, {'mainboard'})
    data = json.loads(Path(project['path']).read_text(encoding='utf-8'))
    assert calls == ['dfc-id']
    assert data['card_entries'][0]['image_asset_id'] == 'chosen-front'
    assert data['card_entries'][0]['backside_asset_id'] == 'paired-back'
    assert data['card_entries'][0]['backside_pre_cropped']
    assert data['backside_enabled']


def test_legacy_maps_keep_backs_oversized_and_unknown_payload():
    legacy = {'cards': {'a.png': 2}, 'backsides': {'a.png': '__a.png'},
              'oversized': {'a.png': True}, 'unknown_setting': {'keep': True},
              'high_res_front_overrides': {'a.png': {'identifier': 'alternate'}}}
    value = DeckDocument.from_legacy_proxy(legacy)
    payload = project_payload(value)
    assert payload['card_entries'][0]['backside_name'] == '__a.png'
    assert payload['card_entries'][0]['oversized']
    assert payload['unknown_setting'] == {'keep': True}
    assert payload['high_res_front_overrides'] == legacy['high_res_front_overrides']


def test_launch_passes_project_path_as_separate_argument(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr('mtg_editor.proxy_adapter.subprocess.Popen', lambda args, **kwargs: calls.append((args, kwargs)))
    path = str(tmp_path / 'deck with spaces.json')
    launch_print({'path': path})
    assert calls[0][0][-2:] == ['--open-project', path]


def test_empty_section_selection_does_not_create_project(library):
    with pytest.raises(ValueError, match='No printable cards'):
        prepare_print(document(), object(), set())
    assert not project_library.list_projects()


def test_art_picker_cancellation_keeps_document_unchanged(monkeypatch):
    from mtg_editor.proxy_adapter import choose_art, enable_proxy_imports
    enable_proxy_imports()
    import dialogs
    class Picker:
        def __init__(self, *args, **kwargs):
            assert kwargs['selection_mode']
        def exec(self):
            return 0
    monkeypatch.setattr(dialogs, 'HighResPickerDialog', Picker)
    value = document()
    before = value.to_dict()
    assert choose_art(None, value, 'a') is None
    assert value.to_dict() == before


@pytest.mark.parametrize('bleed', ['0', '1'])
def test_precropped_catalog_art_survives_unique_names_and_processing(library, monkeypatch, bleed):
    import io
    from PIL import Image
    from mtg_core import get_default_card_service
    from models import ProjectState
    import runtime_images
    service = get_default_card_service()
    image = Image.new('RGB', (300, 420), 'green')
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    asset = service.store_image_bytes(stream.getvalue(), extension='png', source='scryfall')
    monkeypatch.setattr(service, 'get_card', lambda **kwargs: None)
    monkeypatch.setattr(runtime_images, 'get_default_card_service', lambda: service)
    monkeypatch.setattr(runtime_images.CFG, 'VibranceBump', False)
    value = DeckDocument()
    value.deck.entries = [DeckEntry(eid, 'Catalog card', card_id='same-print', image_asset_id=asset)
                          for eid in ('copy-one', 'copy-two')]
    project = prepare_print(value, service, {'mainboard'})
    state = ProjectState.from_dict(json.loads(Path(project['path']).read_text(encoding='utf-8')))
    state.bleed_edge = bleed
    for name in ('copy-one.png', 'copy-two.png'):
        assert state.get_card_entry(name).pre_cropped
        processed = runtime_images.get_processed_path(state, name)
        with Image.open(processed) as result:
            assert result.size == image.size
    roundtrip = ProjectState.from_dict(state.to_dict())
    assert roundtrip.get_card_entry('copy-one.png').pre_cropped
    migrated = DeckDocument.from_legacy_proxy(roundtrip.to_dict())
    assert project_payload(migrated)['card_entries'][0]['pre_cropped']


def test_custom_art_is_not_marked_as_catalog_crop():
    value = DeckDocument()
    value.deck.entries = [DeckEntry('custom', 'Custom', card_id='id', image_asset_id='custom',
                                  extras={'art_override': {'identifier': 'alternate'}}),
                          DeckEntry('explicit', 'Explicit', card_id='id', extras={'pre_cropped': False})]
    entries = project_payload(value)['card_entries']
    assert not any(e['pre_cropped'] for e in entries)
