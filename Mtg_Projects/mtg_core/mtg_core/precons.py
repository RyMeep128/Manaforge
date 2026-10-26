"""Lossless precon catalog, shared by collection and deck creation (no Qt)."""
from copy import deepcopy
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path

from .decklists import DecklistEntry, resolve_entries, apply_decklist
from .paths import core_data_root

SOURCE = 'https://raw.githubusercontent.com/taw/magic-preconstructed-decks-data/master/decks_v2.json'
BUNDLE = Path(__file__).with_name('data') / 'precons.json.gz'
ZONES = {'cards': 'mainboard', 'commander': 'commander', 'sideboard': 'sideboard',
         'planarDeck': 'planar', 'schemeDeck': 'scheme', 'displayCommander': 'display_commander'}


def normalize_catalog(payload):
    if not isinstance(payload, list) or not payload:
        raise ValueError('Expected a nonempty precon array')
    records = []
    seen = set()
    for raw in payload:
        identity = json.dumps([raw['set_code'], raw['name'], raw['release_date']])
        key = hashlib.sha256(identity.encode()).hexdigest()
        if key in seen:
            raise ValueError('Duplicate precon identity')
        seen.add(key)
        entries = []
        for source, zone in ZONES.items():
            for card in raw.get(source, []):
                if type(card['count']) is not int or card['count'] <= 0 or not card['name'].strip():
                    raise ValueError('Invalid precon card quantity or name')
                entries.append(dict(name=card['name'], count=card['count'], section=zone,
                    set_code=card.get('set_code'), collector_number=card.get('number'),
                    mtgjson_uuid=card.get('mtgjson_uuid'), foil=card.get('foil', False)))
        if not entries:
            # Upstream includes products whose lists have not been entered yet.
            # They cannot serve as an original deck and must not be offered.
            continue
        records.append(dict(id=key, name=raw['name'], set_code=raw['set_code'],
            set_name=raw['set_name'], release_date=raw['release_date'],
            format=(raw.get('format') or 'Custom').title(), product_type=raw.get('type', ''),
            source_url=SOURCE, entries=entries,
            artwork=deepcopy(raw.get('artwork', {}))))
    if not records:
        raise ValueError('No complete precon lists supplied')
    return dict(schema_version=1, source_url=SOURCE, decks=records)


def write_catalog(payload, destination):
    from .archidekt_ingest import atomic_json
    catalog = normalize_catalog(payload)
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    atomic_json(Path(destination), catalog)
    return catalog


def load_catalog(path=None):
    path = Path(path) if path else core_data_root() / 'precons.json'
    if path.exists():
        catalog = json.loads(path.read_text(encoding='utf-8'))
    else:
        with gzip.open(BUNDLE, 'rt', encoding='utf-8') as stream:
            catalog = json.load(stream)
    if catalog.get('schema_version') != 1:
        raise ValueError('Unsupported precon catalog version')
    return sorted(catalog['decks'], key=lambda d: (d['format'] != 'Commander', d['name']))


def refresh_catalog(fetch, path=None):
    """Use the caller's shared downloader; publish only after normalization succeeds."""
    return write_catalog(fetch(SOURCE), path or core_data_root() / 'precons.json')


def cover_asset(record, service, *, offline=False):
    """Priority-ordered product art in the existing content-addressed image store."""
    from .decklists import import_image
    for key in ('key_art_url', 'product_image_url'):
        url = record.get('artwork', {}).get(key)
        if not url:
            continue
        asset = service.database.find_image_asset_by_url(url)
        if asset and service.get_image_bytes(asset):
            return asset
        if not offline:
            try:
                return import_image(service, url)
            except (ValueError, OSError):
                continue
    return None


def decklist_entries(record):
    return [DecklistEntry(**{k: row.get(k) for k in
            ('count', 'name', 'set_code', 'collector_number', 'section')}) for row in record['entries']]


def prepare_precon(record, service, **options):
    """Never silently create an incomplete original deck when a lookup fails."""
    result = resolve_entries(decklist_entries(record), service, import_artwork=False, **options)
    if result is not None and result[2]:
        raise ValueError('Cannot create the complete original deck:\n' + '\n'.join(result[2]))
    if result is not None:
        for entry, original in zip(result[0], record['entries']):
            entry.extras['precon_printing'] = {key: original.get(key) for key in
                ('mtgjson_uuid', 'foil', 'set_code', 'collector_number')}
            if entry.section == 'display_commander':
                entry.do_not_print = True
    return result


def apply_precon(document, record, result, name=None, cover_asset_id=None):
    if document.deck.entries:
        raise ValueError('Precons must be created in an empty deck')
    if result is None or result[2] or len(result[0]) != len(record['entries']):
        raise ValueError('A complete precon import is required')
    apply_decklist(document, result)
    document.deck.name = (name or '').strip() or record['name']
    document.deck.format = record['format']
    document.deck.extras['manual_name'] = True
    original = {key: deepcopy(value) for key, value in record.items()
                if key not in ('featured', 'colors', 'colors_complete', 'cover_asset_id')}
    document.deck.extras['precon_origin'] = dict(schema_version=1, id=record['id'],
        name=record['name'], source_url=record['source_url'], release_date=record['release_date'],
        original=original, original_entries=[asdict(e) for e in decklist_entries(record)])
    if cover_asset_id:
        document.deck.extras['cover_image_asset_id'] = cover_asset_id
