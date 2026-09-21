"""Explicit boundary to existing Proxy dialogs, assets, and project workflows."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from mtg_core.decks import DeckDocument
from mtg_ui.project_lock import acquire_project_lock


def enable_proxy_imports():
    root = Path(__file__).resolve().parents[1] / 'mtg_proxy'
    if str(root) not in sys.path:
        sys.path.append(str(root))
    return root


def project_payload(document, base=None):
    adapter = DeckDocument.from_dict(document.to_dict())
    if base is not None:
        adapter.print_settings['proxy_project'] = deepcopy(base)
    # Stable unique filenames also distinguish two entries of the same printing.
    for entry in adapter.deck.entries:
        entry.extras.setdefault('proxy_front_name', f'{entry.entry_id}.png')
    payload = adapter.apply_to_legacy_proxy()
    by_id = {e.entry_id: e for e in adapter.deck.entries}
    for raw in payload['card_entries']:
        entry = by_id[raw['entry_id']]
        raw['oversized'] = entry.extras.get('oversized', raw.get('oversized', False))
        for key in ('backside_name', 'backside_asset_id', 'backside_short_edge'):
            if key in entry.extras:
                raw[key] = entry.extras[key]
        override = entry.extras.get('art_override')
        if override:
            payload.setdefault('high_res_front_overrides', {})[raw['front_name']] = deepcopy(override)
    payload['oversized_enabled'] = payload.get('oversized_enabled', False) or any(r.get('oversized') for r in payload['card_entries'])
    # Embed deck metadata without recursively embedding the entire print project.
    embedded = adapter.to_dict()
    embedded['print_settings'] = {}
    payload['deck_document'] = embedded
    return payload


def choose_art(parent, document, entry_id):
    enable_proxy_imports()
    from dialogs import HighResPickerDialog
    from models import ProjectState
    from PyQt6.QtWidgets import QDialog
    state = ProjectState.from_dict(project_payload(document))
    raw = next(e for e in state.card_entries_store.values() if e.entry_id == entry_id)
    dialog = HighResPickerDialog(parent, state, {}, raw.front_name, selection_mode=True)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.selected_candidate(), state, raw.front_name


def apply_art(selection):
    candidate, state, name = selection
    import high_res
    from config import CFG
    context = high_res.build_card_context(name, state)
    backend = CFG.HighResBackendURL
    back = high_res.maybe_find_matching_backside(state, name, context, candidate, backend)
    with tempfile.TemporaryDirectory(prefix='manaforge-art-') as folder:
        state.image_dir = folder
        high_res.apply_high_res_candidate(state, folder, name, candidate, backside_match=back)
    entry = state.get_card_entry(name)
    return dict(image_asset_id=entry.image_asset_id,
                backside_name=entry.backside_name, backside_asset_id=entry.backside_asset_id,
                art_override=state.high_res_front_overrides_dict().get(name))


def prepare_print(document, service, sections):
    if not any(e.quantity > 0 and e.section in sections and not e.do_not_print for e in document.deck.entries):
        raise ValueError('No printable cards in the selected sections.')
    enable_proxy_imports()
    import project_library
    import deck_import
    from models import ProjectState
    linked = document.extras.get('proxy_project_id')
    project = project_library.get_project(linked) if linked else None
    created = project is None
    if project is None:
        project = project_library.create_project(document.deck.name)
    lock = acquire_project_lock(project['path'])
    try:
        base = json.loads(Path(project['path']).read_text(encoding='utf-8'))
        # Initial migration retains original print settings; repeat handoffs use the managed project.
        if not linked:
            base.update(deepcopy(document.print_settings.get('proxy_project', {})))
        payload = project_payload(document, base)
        entries = {e.entry_id: e for e in document.deck.entries}
        for raw in payload['card_entries']:
            entry = entries[raw['entry_id']]
            raw['do_not_print'] = entry.do_not_print or entry.section not in sections
            if raw['do_not_print'] or not entry.quantity:
                continue
            if not raw.get('image_asset_id'):
                legacy_folder = document.print_settings.get('proxy_project', {}).get('image_dir')
                if legacy_folder:
                    path = Path(legacy_folder) / Path(raw['front_name']).name
                    if path.is_file():
                        raw['image_asset_id'] = service.store_image_bytes(path.read_bytes(),
                            extension=path.suffix.lstrip('.') or 'png', source='editor_legacy')
            if raw.get('image_asset_id') and raw.get('backside_asset_id'):
                continue
            card = service.get_card(card_id=entry.card_id) if entry.card_id else None
            if card:
                with tempfile.TemporaryDirectory(prefix='manaforge-print-') as folder:
                    imported, back_name = deck_import.download_card_image_set(
                        card, deck_import.DeckEntry(entry.quantity, entry.name, entry.set_code, entry.collector_number),
                        folder, lambda message: None, service.fetch_bytes_fn, card_service=service)
                    raw['image_asset_id'] = raw.get('image_asset_id') or imported.image_asset_id
                    raw['backside_asset_id'] = raw.get('backside_asset_id') or imported.backside_asset_id
                    raw['backside_name'] = raw.get('backside_name') or back_name
            if not raw.get('image_asset_id'):
                raise ValueError(f'No printable artwork for {entry.name}. Choose artwork and retry.')
        payload['backside_enabled'] = payload.get('backside_enabled', False) or any(r.get('backside_asset_id') for r in payload['card_entries'])
        state = ProjectState.from_dict(payload)
        from constants import page_sizes, card_size_without_bleed_inch
        from util import mm_to_inch, inch_to_point
        from services import layout_service
        size = page_sizes[state.pagesize]
        if state.orient == 'Landscape':
            size = size[::-1]
        bleed = max(0, mm_to_inch(float(state.bleed_edge)))
        columns, rows = [int(side // inch_to_point(card + 2 * bleed))
                         for side, card in zip(size, card_size_without_bleed_inch)]
        _, relocated = layout_service.resolve(state, columns, rows)
        project_library.save_project(project['id'], state)
        project['relocated_copies'] = relocated
        return project
    except Exception:
        if created:
            project_library.remove_project(project['id'])
        raise
    finally:
        lock.unlock()


def launch_print(project):
    root = enable_proxy_imports()
    return subprocess.Popen([sys.executable, str(root / 'main.py'), '--open-project', project['path']],
                            cwd=str(root), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
