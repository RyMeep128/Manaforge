"""Read-only catalog of native decks and managed print projects."""
import json
from pathlib import Path
from mtg_core.diagnostics import get_logger
from mtg_core.decks import DeckDocument


def project_catalog(deck_root, project_root):
    rows, errors, seen = [], [], set()
    candidates = [(p, 'Deck', '') for p in Path(deck_root).glob('*.manaforge.json')]
    index = Path(project_root) / 'library.json'
    if index.exists():
        try:
            library = json.loads(index.read_text(encoding='utf-8'))
            if not isinstance(library, dict) or not isinstance(library.get('projects'), list):
                raise ValueError('Invalid project index')
            for item in library.get('projects', []):
                if isinstance(item, dict) and item.get('path'):
                    candidates.append((Path(item['path']), 'Print project', item.get('display_name', '')))
        except (OSError, ValueError, AttributeError) as exc:
            get_logger(__name__).exception('Print library index read failed path=%s', index)
            errors.append(f'Could not read print library: {exc}')
    for path, kind, title in candidates:
        key = str(path.resolve()).casefold()
        if key in seen:
            continue
        seen.add(key)
        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
            native = raw if 'deck' in raw else raw.get('deck_document')
            document = (DeckDocument.from_dict(native) if isinstance(native, dict)
                        else DeckDocument.from_legacy_proxy(raw, name=path.stem))
            deck = document.deck
            entries = deck.entries
            cover = next((entry for entry in entries if entry.entry_id in deck.commander_entry_ids
                          or entry.section == 'commander'), entries[0] if entries else None)
            name = title or deck.name or path.stem
            rows.append({'path': str(path.resolve()), 'kind': kind, 'name': name,
                         'modified': path.stat().st_mtime, 'format': deck.format,
                         'card_count': sum(entry.quantity for entry in entries),
                         'cover': ((None, deck.extras['cover_image_asset_id'])
                                   if deck.extras.get('cover_image_asset_id') else
                                   (cover.card_id, cover.image_asset_id) if cover else (None, None))})
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            get_logger(__name__).exception('Project read failed path=%s kind=%s', path, kind)
            errors.append(f'{path.name}: {exc}')
    return sorted(rows, key=lambda row: -row['modified']), errors
