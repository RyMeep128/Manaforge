"""Shared text/CSV decklists and local-first card resolution, independent of Qt/printing."""
import csv
import io
import re
import uuid
from dataclasses import dataclass, replace
from .decks import DeckEntry
from .categorization import analyze_entries, apply_categories
from .services import RemoteLookupUnavailable


@dataclass(frozen=True)
class DecklistEntry:
    count: int
    name: str
    set_code: str | None = None
    collector_number: str | None = None
    section: str = 'mainboard'
    card_id: str | None = None
    image_url: str | None = None
    backside_image_url: str | None = None


SECTIONS = {'deck': 'mainboard', 'mainboard': 'mainboard', 'main': 'mainboard',
            'sideboard': 'sideboard', 'commander': 'commander', 'commanders': 'commander',
            'companion': 'sideboard', 'companions': 'sideboard', 'maybeboard': 'considering',
            'considering': 'considering', 'excluded': 'excluded'}
PREFIXES = {'SB': 'sideboard', 'MB': 'mainboard', 'CMDR': 'commander', 'COMMANDER': 'commander'}
LINE = re.compile(r'^(?:(?P<count>\d+)(?:x)?\s+)?(?P<name>.+?)'
                  r'(?:\s+\((?P<set_code>[A-Za-z0-9]+)\)(?:\s+(?P<collector_number>[A-Za-z0-9-]+))?)?$')


def normalize_name(name):
    return re.sub(r'\s+', ' ', name.strip()).replace(' / ', ' // ')


def parse_decklist(text, *, preserve_sections=True):
    """Keep sections for editor imports; Proxy's compatibility wrapper flattens them."""
    text = text.lstrip('\ufeff\r\n ')
    first = next((line for line in text.splitlines() if line.strip()), '')
    headers = {h.strip().lower() for h in next(csv.reader([first]), [])}
    entries, unmatched = [], []
    if 'name' in headers and ('count' in headers or 'quantity' in headers):
        reader = csv.DictReader(io.StringIO(text))
        for number, row in enumerate(reader, 2):
            fields = {k.strip().lower(): (v or '').strip() for k, v in row.items() if k is not None}
            count = fields.get('count', fields.get('quantity', '1'))
            name = normalize_name(fields.get('name', ''))
            code = fields.get('set_code') or None
            collector = fields.get('collector_number') or None
            section_text = fields.get('section', 'mainboard').casefold()
            section = SECTIONS.get(section_text, 'mainboard')
            # Legacy Proxy CSV import required complete printing coordinates.
            invalid = not count.isdigit() or not name or (preserve_sections and int(count) < 1)
            invalid |= not preserve_sections and (not code or not collector)
            if invalid:
                unmatched.append(f'CSV row {number}')
                continue
            entries.append(DecklistEntry(int(count), name, code.lower() if code else None, collector,
                                         section if preserve_sections else 'mainboard',
                                         image_url=fields.get('image_url') or None if preserve_sections else None,
                                         backside_image_url=fields.get('backside_image_url') or None if preserve_sections else None))
    else:
        section = 'mainboard'
        for raw in text.splitlines():
            line = raw.strip()
            heading = line.casefold().rstrip(':')
            if heading in SECTIONS:
                section = SECTIONS[heading]
                continue
            if not line or line.startswith(('#', '//')):
                continue
            target = section
            prefix = re.match(r'^(SB|MB|CMDR|COMMANDER):\s*', line, re.IGNORECASE)
            if prefix:
                target = PREFIXES[prefix[1].upper()]
                line = line[prefix.end():]
            match = LINE.match(line)
            if not match:
                unmatched.append(raw.strip())
                continue
            count = int(match['count'] or 1)
            name = normalize_name(match['name'])
            if count < 1 or not any(c.isalpha() for c in name):
                unmatched.append(raw.strip())
                continue
            code = match['set_code']
            entries.append(DecklistEntry(count, name, code.lower() if code else None, match['collector_number'],
                                         target if preserve_sections else 'mainboard'))
    aggregated = {}
    for entry in entries:
        key = (entry.name.casefold(), entry.set_code, entry.collector_number, entry.section, entry.image_url, entry.backside_image_url)
        previous = aggregated.get(key)
        aggregated[key] = replace(previous, count=previous.count + entry.count) if previous else entry
    return list(aggregated.values()), unmatched


def resolve_card(entry, service, *, allow_remote=True):
    if entry.card_id:
        card = service.get_card(card_id=entry.card_id)
        if card is not None:
            return card
        if not allow_remote:
            raise ValueError('Requested artwork/printing is not available in the local catalog')
        return service.fetch_missing_card(card_id=entry.card_id)
    code, collector = entry.set_code, entry.collector_number
    if code and code.casefold() == 'plst' and collector:
        collector = collector.upper()
    if code and collector:
        card = service.get_print(set_code=code, collector_number=collector)
        if card is not None:
            return card
    if entry.name:
        card = service.get_card(exact_name=entry.name)
        if card is not None and not code:
            return card
        if card is not None and code and not collector:
            if str(card.get('set', '')).casefold() == code.casefold():
                return card
            if hasattr(service, 'get_prints') and card.get('oracle_id'):
                match = next((p for p in service.get_prints(card['oracle_id'])
                              if str(p.get('set', '')).casefold() == code.casefold()), None)
                if match is not None:
                    return match
    if not allow_remote:
        raise ValueError('Requested card/printing is not available in the local catalog')
    return service.fetch_missing_card(exact_name=entry.name, set_code=code, collector_number=collector)


def read_decklist_file(path):
    with open(path, 'rb') as stream:
        raw = stream.read()
    for encoding in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass


def export_decklist(document, *, include_printings=True, include_sections=True):
    """Common quantity/name text; exact printing coordinates and sections are optional."""
    labels = {'mainboard': 'Deck', 'commander': 'Commander', 'sideboard': 'Sideboard',
              'considering': 'Maybeboard', 'excluded': 'Excluded'}
    lines = []
    for section, label in labels.items():
        entries = [e for e in document.deck.entries if e.section == section and e.quantity > 0]
        if not entries:
            continue
        if include_sections:
            if lines:
                lines.append('')
            lines.append(label)
        for entry in entries:
            line = f'{entry.quantity} {entry.name}'
            if include_printings and entry.set_code:
                line += f' ({entry.set_code})'
                if entry.collector_number:
                    line += ' ' + entry.collector_number
            lines.append(line)
    return '\n'.join(lines) + ('\n' if lines else '')


def resolve_decklist(text, service, *, allow_remote=False, progress=None, cancelled=lambda: False, import_artwork=True):
    """Prepare an import off-thread. No deck mutations occur until accepted by the caller."""
    parsed, warnings = parse_decklist(text)
    warnings = ['Unrecognized: ' + line for line in warnings]
    return resolve_entries(parsed, service, allow_remote=allow_remote, progress=progress,
                           cancelled=cancelled, warnings=warnings, import_artwork=import_artwork)


def resolve_entries(parsed, service, *, allow_remote=False, progress=None, cancelled=lambda: False, warnings=(), import_artwork=True):
    warnings = list(warnings)
    entries = []
    for index, source in enumerate(parsed):
        if cancelled():
            return None
        try:
            payload = resolve_card(source, service, allow_remote=allow_remote)
            if not payload or not payload.get('id'):
                raise ValueError('No matching printing found')
            entry = DeckEntry(str(uuid.uuid4()), payload.get('name') or source.name,
                quantity=source.count, section=source.section, card_id=payload['id'],
                oracle_id=payload.get('oracle_id'), set_code=payload.get('set'),
                collector_number=payload.get('collector_number'),
                extras={'pre_cropped': True, 'facts': {key: payload.get(key) for key in
                    ('type_line', 'cmc', 'colors', 'oracle_text', 'keywords', 'layout', 'card_faces')}})
            if import_artwork:
                for url, field in ((source.image_url, 'image_asset_id'), (source.backside_image_url, 'backside_asset_id')):
                    if cancelled():
                        return None
                    if url:
                        asset = import_image(service, url)
                        if field == 'image_asset_id':
                            entry.image_asset_id = asset
                        else:
                            entry.extras[field] = asset
                            entry.extras['backside_name'] = f'__back_{entry.entry_id}.png'
                            entry.extras['backside_pre_cropped'] = True
                if source.image_url or source.backside_image_url:
                    entry.extras['imported_artwork'] = {'front_url': source.image_url, 'back_url': source.backside_image_url}
            entries.append(entry)
        except (ValueError, OSError, RemoteLookupUnavailable) as exc:
            printing = f' ({source.set_code}) {source.collector_number or ""}' if source.set_code else ''
            warnings.append(f'{source.count} {source.name}{printing}: {exc}')
        if progress:
            progress(index + 1, len(parsed))
    if cancelled():
        return None
    proposals = analyze_entries(service.database, entries) if entries else {}
    return entries, proposals, warnings


def import_image(service, url):
    from urllib.parse import urlsplit
    from io import BytesIO
    from PIL import Image
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
        raise ValueError('Custom artwork needs a public HTTP(S) image URL')
    content = service.fetch_bytes_fn(url)
    if len(content) > 50 * 1024 * 1024:
        raise ValueError('Custom artwork exceeds 50 MB')
    with Image.open(BytesIO(content)) as image:
        extension = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}.get(image.format)
        if not extension:
            raise ValueError('Custom artwork must be PNG, JPEG, or WebP')
        image.verify()
    return service.store_image_bytes(content, extension=extension, source='deck_import', source_url=url)


def apply_decklist(document, result):
    """Append/merge quantities and categorize new entries in the caller's undo transaction."""
    from copy import deepcopy
    entries, proposals, _ = result
    for prepared in entries:
        existing = next((e for e in document.deck.entries if e.card_id == prepared.card_id
                         and e.section == prepared.section and not e.extras.get('art_override')
                         and e.image_asset_id == prepared.image_asset_id
                         and e.extras.get('backside_asset_id') == prepared.extras.get('backside_asset_id')
                         and not e.do_not_print), None)
        if existing:
            existing.quantity += prepared.quantity
            continue
        entry = deepcopy(prepared)
        entry.sort_order = max((e.sort_order for e in document.deck.entries), default=-1) + 1
        document.deck.entries.append(entry)
        apply_categories(document, {entry.entry_id: proposals.get(entry.entry_id, [])})
    document.deck.commander_entry_ids = [e.entry_id for e in document.deck.entries if e.section == 'commander']
