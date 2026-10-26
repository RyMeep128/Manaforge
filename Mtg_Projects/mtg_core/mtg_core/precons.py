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
                if key not in ('featured', 'colors', 'colors_complete', 'cover_asset_id', '_search_text', 'metadata_ready')}
    document.deck.extras['precon_origin'] = dict(schema_version=1, id=record['id'],
        name=record['name'], source_url=record['source_url'], release_date=record['release_date'],
        original=original, original_entries=[asdict(e) for e in decklist_entries(record)])
    if cover_asset_id:
        document.deck.extras['cover_image_asset_id'] = cover_asset_id


def browser_metadata(service, records, *, cancelled=lambda: False):
    """Yield small deck batches; cache summaries until the local catalog changes.

    Database and WAL timestamps invalidate both found and missing card summaries.
    Artwork is deliberately left to the browser's visible-thumbnail requests.
    """
    import os
    import tempfile

    database = getattr(service, 'database', None)
    db_path = getattr(database, 'db_path', None)
    cache_path, stamp, cards = None, None, {}
    if db_path and db_path != ':memory:':
        path = Path(db_path).resolve()
        def file_stamp(path):
            try:
                stat = path.stat()
                return [stat.st_mtime_ns, stat.st_size]
            except OSError:
                return None
        stamp = [str(path), file_stamp(path), file_stamp(Path(str(path)+'-wal'))]
        key = hashlib.sha256(str(path).encode()).hexdigest()[:20]
        cache_path = core_data_root() / f'precon-summaries-v1-{key}.json'
        try:
            cached = json.loads(cache_path.read_text(encoding='utf-8'))
            if cached.get('stamp') == stamp and isinstance(cached.get('cards'), dict):
                cards = cached['cards']
        except (OSError, ValueError):
            pass
    for offset in range(0, len(records), 40):
        if cancelled():
            return
        batch = records[offset:offset+40]
        playable = [[r for r in record['entries'] if r['section'] in ('commander', 'mainboard')]
                    for record in batch]
        for rows in playable:
            rows.sort(key=lambda r: r['section'] != 'commander')
        missing = list(dict.fromkeys(row['name'] for rows in playable for row in rows
                                    if row['name'] not in cards))
        if not missing:
            pass
        elif database is not None and hasattr(database, 'precon_card_summaries'):
            cards.update(database.precon_card_summaries(missing, cancelled=cancelled))
        else:
            for name in missing:
                if cancelled():
                    return
                card = service.get_card(exact_name=name)
                cards[name] = (dict(id=card.get('id'), color_identity=card.get('color_identity', []))
                               if card else None)
        results = []
        for index, rows in enumerate(playable, offset):
            if cancelled():
                return
            found = [cards.get(row['name']) for row in rows]
            colors = {color for card in found if card for color in card['color_identity']}
            results.append((index, ''.join(c for c in 'WUBRG' if c in colors),
                            all(found), next((card for card in found if card), None)))
        yield results
    if cache_path is not None and not cancelled():
        temporary = None
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                    dir=cache_path.parent, delete=False) as stream:
                temporary = stream.name
                json.dump(dict(stamp=stamp, cards=cards), stream, separators=(',', ':'))
            os.replace(temporary, cache_path)
        except OSError:
            pass  # A read-only cache must not prevent browsing.
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
