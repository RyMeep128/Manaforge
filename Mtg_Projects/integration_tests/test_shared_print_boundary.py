"""Shared printing imports must work without Proxy's directory or Qt."""
from pathlib import Path
import subprocess
import sys


def test_shared_printing_imports_and_layout_without_proxy_or_qt(tmp_path):
    products = Path(__file__).resolve().parents[1]
    script = r'''
import os
import sys
from types import SimpleNamespace
os.environ['PRINT_PROXY_PREP_DATA_DIR'] = sys.argv[3]
sys.path[:0] = [sys.argv[1], sys.argv[2]]
before = list(sys.path)

class RejectApplicationImports:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {
            'PyQt6', 'mtg_proxy', 'pdf', 'models', 'config', 'constants',
            'services', 'dialogs', 'project_library', 'fallback_image', 'util',
            'image', 'runtime_images', 'high_res', 'deck_import', 'background_tasks',
        }:
            raise AssertionError('Shared printing imported ' + fullname)

sys.meta_path.insert(0, RejectApplicationImports())
from mtg_print import layout
from mtg_print.project import project_payload
from mtg_print.card_layouts import has_printed_back
from mtg_print.models import ProjectState
from mtg_print import library
from mtg_print import image, high_res, runtime_images, deck_import
from mtg_print.services import deck_import_service, high_res_service
from mtg_editor.proxy_adapter import prepare_print
from mtg_core.decks import DeckDocument, DeckEntry

document = DeckDocument()
document.deck.entries = [DeckEntry('a', 'Card', quantity=2, card_id='print')]
snapshot = document.to_dict()
payload = project_payload(document)
assert payload['card_entries'][0]['count'] == 2
assert document.to_dict() == snapshot

entry = SimpleNamespace(entry_id='a', do_not_print=False)
state = SimpleNamespace(
    cards={'a.png': 2}, get_card_entry=lambda name: entry,
    get_card_metadata=lambda name: {}, oversized_enabled=False, oversized={},
    backside_short_edge={}, manual_layout=None,
)
items, relocated = layout.resolve(state, 3, 3)
assert len(items) == 2 and relocated == 0
items[1].update(page=2, row=1, column=1)
state.manual_layout = layout.record(items)
pages = layout.distribute_cards_to_pages(state, 3, 3)
assert len(pages) == 3 and not pages[1]['placements']
assert layout.distribute_cards_to_grid(pages[2], True, 3, 3)[1][1][0] == 'a.png'
project = library.create_project('Isolated shared project')
state = ProjectState.from_dict(payload)
state.deck_document.extras['unknown_extension'] = {'preserved': True}
library.save_project(project['id'], state)
restored = ProjectState.from_dict(library.load_recovery_snapshot(project['path']))
assert restored.deck_document.extras['unknown_extension'] == {'preserved': True}
assert sum(restored.cards.values()) == 2
assert len(library.list_projects()) == 1
assert sys.path == before
'''
    result = subprocess.run(
        [sys.executable, '-I', '-c', script, str(products), str(products / 'mtg_core'), str(tmp_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_proxy_compatibility_imports_share_models_config_and_library():
    import config
    import models
    import project_library
    from mtg_print import config as shared_config, library, models as shared_models

    assert config is shared_config
    assert models is shared_models
    assert project_library is library


def test_editor_dialog_imports_do_not_need_proxy_on_path(tmp_path):
    products = Path(__file__).resolve().parents[1]
    script = r'''
import os
import sys
os.environ['PRINT_PROXY_PREP_DATA_DIR'] = sys.argv[3]
sys.path[:0] = [sys.argv[1], sys.argv[2]]
before = list(sys.path)
from mtg_ui.print_dialogs import HighResPickerDialog, CardTagsDialog
from mtg_editor import proxy_adapter, readiness
assert not hasattr(proxy_adapter, 'enable_proxy_imports')
assert sys.path == before
assert 'dialogs' not in sys.modules and 'services' not in sys.modules
'''
    result = subprocess.run(
        [sys.executable, '-I', '-c', script, str(products), str(products / 'mtg_core'), str(tmp_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
