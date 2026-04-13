import csv
import html.parser
import json
import logging
import os
import re
import urllib.error
import urllib.request
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

from mtg_core import CardService, RemoteLookupUnavailable
from mtg_core.sync import fetch_json as core_fetch_json
from mtg_core.sync import fetch_bytes as core_fetch_bytes
from models import ProjectState, as_project_state

logger = logging.getLogger(__name__)

RECOVERABLE_IMPORT_ERRORS = (
    OSError,
    ValueError,
    TypeError,
    KeyError,
    json.JSONDecodeError,
    urllib.error.URLError,
    urllib.error.HTTPError,
    RemoteLookupUnavailable,
)


def _sync_legacy_project_dict(target, state: ProjectState) -> ProjectState:
    if isinstance(target, ProjectState):
        target.copy_from(state)
        return target
    target.clear()
    target.update(state.to_dict())
    return state


PRINT_FN = Callable[[str], None]
ARCHIDEKT_URL_RE = re.compile(
    r"^https://(www\.)?archidekt\.com/decks/(?P<deck_id>\d+)(/.*)?$",
    re.IGNORECASE,
)

SECTION_HEADERS = {
    "deck",
    "sideboard",
    "commander",
    "companions",
    "companion",
    "maybeboard",
}

LINE_PATTERN = re.compile(
    r"^(?:(?:SB|MB|CMDR|COMMANDER):\s*)?(?P<count>\d+)\s+(?P<name>.+?)"
    r"(?:\s+\((?P<set_code>[A-Za-z0-9]+)\)(?:\s+(?P<collector_number>[A-Za-z0-9]+))?)?$"
)


@dataclass(frozen=True)
class DeckEntry:
    count: int
    name: str
    set_code: str | None = None
    collector_number: str | None = None


@dataclass(frozen=True)
class ImportedCard:
    entry: DeckEntry
    filename: str
    card_id: str | None = None
    oracle_id: str | None = None
    image_asset_id: str | None = None
    backside_asset_id: str | None = None


@dataclass
class ImportResult:
    imported: list[ImportedCard]
    unmatched_lines: list[str]
    failed_cards: list[str]
    backside_pairs: dict[str, str]

    @property
    def imported_count(self) -> int:
        return sum(card.entry.count for card in self.imported)


class ArchidektHTMLParser(html.parser.HTMLParser):
    def __init__(self, *, convert_charrefs=True):
        super().__init__(convert_charrefs=convert_charrefs)
        self.decklist_json = ""
        self._found_deck_tag = False

    def handle_starttag(self, tag, attrs):
        attributes = {key: value for key, value in attrs}
        if (
            tag == "script"
            and attributes.get("id") == "__NEXT_DATA__"
            and attributes.get("type") == "application/json"
        ):
            self._found_deck_tag = True

    def handle_data(self, data):
        if self._found_deck_tag:
            self.decklist_json = data
            self._found_deck_tag = False


def parse_decklist(deck_text: str) -> tuple[list[DeckEntry], list[str]]:
    if _looks_like_csv(deck_text):
        return _parse_csv_decklist(deck_text)
    return _parse_text_decklist(deck_text)


def _parse_text_decklist(deck_text: str) -> tuple[list[DeckEntry], list[str]]:
    aggregated: OrderedDict[tuple[str, str | None, str | None], DeckEntry] = OrderedDict()
    unmatched_lines: list[str] = []

    for raw_line in deck_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().rstrip(":") in SECTION_HEADERS:
            continue

        match = LINE_PATTERN.match(line)
        if match is None:
            unmatched_lines.append(line)
            continue

        count = int(match.group("count"))
        name = _normalize_card_name(match.group("name"))
        set_code = match.group("set_code")
        collector_number = match.group("collector_number")
        key = (name.casefold(), set_code.lower() if set_code else None, collector_number)

        if key in aggregated:
            previous = aggregated[key]
            aggregated[key] = DeckEntry(
                count=previous.count + count,
                name=previous.name,
                set_code=previous.set_code,
                collector_number=previous.collector_number,
            )
        else:
            aggregated[key] = DeckEntry(
                count=count,
                name=name,
                set_code=set_code.lower() if set_code else None,
                collector_number=collector_number,
            )

    return list(aggregated.values()), unmatched_lines


def _parse_csv_decklist(deck_text: str) -> tuple[list[DeckEntry], list[str]]:
    aggregated: OrderedDict[tuple[str, str | None, str | None], DeckEntry] = OrderedDict()
    unmatched_lines: list[str] = []

    reader = csv.DictReader(deck_text.splitlines())
    fieldnames = {_normalize_csv_field_name(field_name) for field_name in (reader.fieldnames or [])}
    required_fields = {"count", "name", "set_code", "collector_number"}
    if not required_fields.issubset(fieldnames):
        return _parse_text_decklist(deck_text)

    for row_number, row in enumerate(reader, start=2):
        normalized_row = {
            _normalize_csv_field_name(key): (value or "").strip()
            for key, value in row.items()
            if key is not None
        }

        count_raw = normalized_row.get("count", "")
        name_raw = normalized_row.get("name", "")
        set_code = normalized_row.get("set_code") or None
        collector_number = normalized_row.get("collector_number") or None

        if not count_raw or not count_raw.isdigit() or not name_raw or not set_code or not collector_number:
            unmatched_lines.append(f"CSV row {row_number}")
            continue

        name = _normalize_card_name(name_raw)
        key = (name.casefold(), set_code.lower(), collector_number)
        count = int(count_raw)

        if key in aggregated:
            previous = aggregated[key]
            aggregated[key] = DeckEntry(
                count=previous.count + count,
                name=previous.name,
                set_code=previous.set_code,
                collector_number=previous.collector_number,
            )
        else:
            aggregated[key] = DeckEntry(
                count=count,
                name=name,
                set_code=set_code.lower(),
                collector_number=collector_number,
            )

    return list(aggregated.values()), unmatched_lines


def import_decklist(
    deck_text: str,
    image_dir: str,
    print_fn: PRINT_FN | None = None,
    fetch_json: Callable[[str], dict] | None = None,
    fetch_bytes: Callable[[str], bytes] | None = None,
) -> ImportResult:
    print_fn = print_fn if print_fn is not None else lambda _text: None
    fetch_json = fetch_json if fetch_json is not None else _fetch_json
    fetch_bytes = fetch_bytes if fetch_bytes is not None else _fetch_bytes
    card_service = _build_card_service(fetch_json)

    entries, unmatched_lines = parse_decklist(deck_text)
    return import_entries(
        entries,
        image_dir,
        unmatched_lines=unmatched_lines,
        print_fn=print_fn,
        card_service=card_service,
        fetch_bytes=fetch_bytes,
    )


def import_archidekt_url(
    archidekt_url: str,
    image_dir: str,
    print_fn: PRINT_FN | None = None,
    fetch_json: Callable[[str], dict] | None = None,
    fetch_bytes: Callable[[str], bytes] | None = None,
    fetch_text: Callable[[str], str] | None = None,
) -> ImportResult:
    print_fn = print_fn if print_fn is not None else lambda _text: None
    fetch_json = fetch_json if fetch_json is not None else _fetch_json
    fetch_bytes = fetch_bytes if fetch_bytes is not None else _fetch_bytes
    fetch_text = fetch_text if fetch_text is not None else _fetch_text
    card_service = _build_card_service(fetch_json)

    if not is_archidekt_url(archidekt_url):
        raise ValueError("The URL is not a valid public Archidekt deck link.")

    print_fn("Importing Archidekt deck...\nDownloading public deck page")
    html = fetch_text(archidekt_url)
    entries = parse_archidekt_html(html)
    if not entries:
        raise ValueError("No cards were found in the public Archidekt deck.")

    return import_entries(
        entries,
        image_dir,
        unmatched_lines=[],
        print_fn=print_fn,
        card_service=card_service,
        fetch_bytes=fetch_bytes,
    )


def import_entries(
    entries: list[DeckEntry],
    image_dir: str,
    unmatched_lines: list[str],
    print_fn: PRINT_FN | None = None,
    card_service: CardService | None = None,
    fetch_bytes: Callable[[str], bytes] | None = None,
) -> ImportResult:
    print_fn = print_fn if print_fn is not None else lambda _text: None
    fetch_bytes = fetch_bytes if fetch_bytes is not None else _fetch_bytes
    card_service = card_service or _build_card_service()

    imported: list[ImportedCard] = []
    failed_cards: list[str] = []
    backside_pairs: dict[str, str] = {}

    for index, entry in enumerate(entries, start=1):
        label = f"{entry.name} ({index}/{len(entries)})"
        print_fn(f"Importing decklist...\nResolving {label}")
        try:
            card_data = resolve_card(entry, card_service=card_service)
            imported_card, backside_name = download_card_image_set(
                card_data,
                entry,
                image_dir,
                print_fn,
                fetch_bytes,
                card_service=card_service,
            )
            imported.append(imported_card)
            if backside_name is not None:
                backside_pairs[imported_card.filename] = backside_name
        except RECOVERABLE_IMPORT_ERRORS:
            logger.exception(
                "deck import entry failed operation=import_entry name=%s set_code=%s collector_number=%s image_dir=%s",
                entry.name,
                entry.set_code,
                entry.collector_number,
                image_dir,
            )
            failed_cards.append(_format_failed_card(entry))

    return ImportResult(
        imported=imported,
        unmatched_lines=unmatched_lines,
        failed_cards=failed_cards,
        backside_pairs=backside_pairs,
    )


def apply_imported_counts(print_dict: dict, imported_cards: list[ImportedCard]):
    state = as_project_state(print_dict)
    for imported_card in imported_cards:
        state.set_card_count(imported_card.filename, imported_card.entry.count)
    return _sync_legacy_project_dict(print_dict, state)


def apply_imported_metadata(print_dict: dict, imported_cards: list[ImportedCard]):
    state = as_project_state(print_dict)
    for imported_card in imported_cards:
        state.set_card_metadata(
            imported_card.filename,
            {
                "name": imported_card.entry.name,
                "set_code": imported_card.entry.set_code,
                "collector_number": imported_card.entry.collector_number,
            },
        )
    return _sync_legacy_project_dict(print_dict, state)


def apply_import_result(print_dict: dict, import_result: ImportResult):
    state = as_project_state(print_dict)
    apply_imported_counts(state, import_result.imported)
    apply_imported_metadata(state, import_result.imported)
    if import_result.backside_pairs:
        for front_name, back_name in import_result.backside_pairs.items():
            state.set_backside(front_name, back_name)
    for imported_card in import_result.imported:
        state.set_card_image_refs(
            imported_card.filename,
            card_id=imported_card.card_id,
            oracle_id=imported_card.oracle_id,
            image_asset_id=imported_card.image_asset_id,
            backside_asset_id=imported_card.backside_asset_id,
        )
    return _sync_legacy_project_dict(print_dict, state)


def read_decklist_file(path: str) -> str:
    with open(path, "rb") as fp:
        raw = fp.read()

    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def is_archidekt_url(value: str) -> bool:
    return ARCHIDEKT_URL_RE.match(value.strip()) is not None


def parse_archidekt_html(html: str) -> list[DeckEntry]:
    parser = ArchidektHTMLParser()
    parser.feed(html)
    parser.close()
    if not parser.decklist_json:
        raise ValueError("The Archidekt page did not include deck data.")

    try:
        payload = json.loads(parser.decklist_json)
    except json.JSONDecodeError as exc:
        raise ValueError("The Archidekt deck data could not be parsed.") from exc

    try:
        card_map = payload["props"]["pageProps"]["redux"]["deck"]["cardMap"]
    except KeyError as exc:
        raise ValueError("The Archidekt deck data is missing its card list.") from exc

    aggregated: OrderedDict[tuple[str, str | None, str | None], DeckEntry] = OrderedDict()
    for card in card_map.values():
        name = _normalize_card_name(str(card.get("name", "")).strip())
        set_code = _normalize_optional_field(card.get("setCode"))
        collector_number = _normalize_optional_field(card.get("collectorNumber"))
        quantity = card.get("qty", 0)
        try:
            count = int(quantity)
        except (TypeError, ValueError):
            continue

        if count <= 0 or not name:
            continue

        key = (name.casefold(), set_code, collector_number)
        if key in aggregated:
            previous = aggregated[key]
            aggregated[key] = DeckEntry(
                count=previous.count + count,
                name=previous.name,
                set_code=previous.set_code,
                collector_number=previous.collector_number,
            )
        else:
            aggregated[key] = DeckEntry(
                count=count,
                name=name,
                set_code=set_code,
                collector_number=collector_number,
            )

    return list(aggregated.values())


def resolve_card(
    entry: DeckEntry,
    fetch_json: Callable[[str], dict] | None = None,
    card_service: CardService | None = None,
) -> dict:
    service = card_service or _build_card_service(fetch_json)
    if entry.set_code and entry.collector_number:
        card = service.get_print(set_code=entry.set_code, collector_number=entry.collector_number)
        if card is not None:
            return card
    if entry.name:
        card = service.get_card(exact_name=entry.name)
        if card is not None and not entry.set_code:
            return card
    return service.fetch_missing_card(
        exact_name=entry.name,
        set_code=entry.set_code,
        collector_number=entry.collector_number,
    )


def extract_image_url(card_data: dict) -> str | None:
    image_uris = card_data.get("image_uris")
    if image_uris:
        return image_uris.get("png") or image_uris.get("large") or image_uris.get("normal")

    for face in card_data.get("card_faces", []):
        image_uris = face.get("image_uris")
        if image_uris:
            return image_uris.get("png") or image_uris.get("large") or image_uris.get("normal")
    return None


def extract_face_image_urls(card_data: dict) -> list[str]:
    urls = []
    for face in card_data.get("card_faces", []):
        image_uris = face.get("image_uris")
        if not image_uris:
            continue
        url = image_uris.get("png") or image_uris.get("large") or image_uris.get("normal")
        if url:
            urls.append(url)
    return urls


def build_image_filename(card_data: dict) -> str:
    name = card_data.get("name", "card")
    if "//" in name:
        name = name.split("//", 1)[0].strip()

    set_code = (card_data.get("set") or "unknown").lower()
    collector_number = str(card_data.get("collector_number") or "0")
    slug = slugify_filename(name)
    return f"scryfall_{set_code}_{collector_number}_{slug}.png"


def build_face_image_filename(card_data: dict, face_name: str, hidden=False) -> str:
    prefix = "__scryfall_" if hidden else "scryfall_"
    set_code = (card_data.get("set") or "unknown").lower()
    collector_number = str(card_data.get("collector_number") or "0")
    slug = slugify_filename(face_name)
    return f"{prefix}{set_code}_{collector_number}_{slug}.png"


def download_card_image_set(
    card_data: dict,
    entry: DeckEntry,
    image_dir: str,
    print_fn: PRINT_FN,
    fetch_bytes: Callable[[str], bytes],
    *,
    card_service: CardService | None = None,
) -> tuple[ImportedCard, str | None]:
    card_service = card_service or _build_card_service()
    face_urls = extract_face_image_urls(card_data)
    face_names = [face.get("name") or card_data.get("name", "card") for face in card_data.get("card_faces", [])]
    card_id = str(card_data.get("id") or "") or None
    oracle_id = str(card_data.get("oracle_id") or "") or None
    front_record = card_service.database.get_image_record(card_id, "default") if card_id else None
    back_record = card_service.database.get_image_record(card_id, "back") if card_id else None

    if len(face_urls) >= 2 and len(face_names) >= 2:
        front_name = build_face_image_filename(card_data, face_names[0], hidden=False)
        back_name = build_face_image_filename(card_data, face_names[1], hidden=True)
        front_path = card_service.get_image_path(card_id, "default") if card_id else None
        back_path = card_service.get_image_path(card_id, "back") if card_id else None
        if front_path and back_path and front_record is not None:
            return ImportedCard(
                entry=entry,
                filename=front_name,
                card_id=card_id,
                oracle_id=oracle_id,
                image_asset_id=front_record.asset_id,
                backside_asset_id=None if back_record is None else back_record.asset_id,
            ), back_name

        print_fn(f"Importing decklist...\nDownloading {entry.name} front")
        front_bytes = fetch_bytes(face_urls[0])
        front_asset_id = card_service.store_image_bytes(
            front_bytes,
            extension=os.path.splitext(front_name)[1].lstrip(".") or "png",
            source="scryfall",
            source_url=face_urls[0],
        )
        write_downloaded_image(image_dir, front_name, front_bytes)
        print_fn(f"Importing decklist...\nDownloading {entry.name} back")
        back_bytes = fetch_bytes(face_urls[1])
        back_asset_id = card_service.store_image_bytes(
            back_bytes,
            extension=os.path.splitext(back_name)[1].lstrip(".") or "png",
            source="scryfall",
            source_url=face_urls[1],
        )
        write_downloaded_image(image_dir, back_name, back_bytes)
        if card_id:
            card_service.set_print_image_asset(
                card_id,
                front_asset_id,
                variant="default",
                source="scryfall",
                preferred_name=front_name,
            )
            card_service.set_print_image_asset(
                card_id,
                back_asset_id,
                variant="back",
                source="scryfall",
                preferred_name=back_name,
            )

        return ImportedCard(
            entry=entry,
            filename=front_name,
            card_id=card_id,
            oracle_id=oracle_id,
            image_asset_id=front_asset_id,
            backside_asset_id=back_asset_id,
        ), back_name

    image_url = extract_image_url(card_data)
    if image_url is None:
        raise ValueError("No downloadable image URL found")

    filename = build_image_filename(card_data)
    local_path = card_service.get_image_path(card_id, "default") if card_id else None
    if local_path and front_record is not None:
        return ImportedCard(
            entry=entry,
            filename=filename,
            card_id=card_id,
            oracle_id=oracle_id,
            image_asset_id=front_record.asset_id,
        ), None
    print_fn(f"Importing decklist...\nDownloading {entry.name}")
    image_bytes = fetch_bytes(image_url)
    image_asset_id = card_service.store_image_bytes(
        image_bytes,
        extension=os.path.splitext(filename)[1].lstrip(".") or "png",
        source="scryfall",
        source_url=image_url,
    )
    write_downloaded_image(image_dir, filename, image_bytes)
    if card_id:
        card_service.set_print_image_asset(
            card_id,
            image_asset_id,
            variant="default",
            source="scryfall",
            preferred_name=filename,
        )
    return ImportedCard(
        entry=entry,
        filename=filename,
        card_id=card_id,
        oracle_id=oracle_id,
        image_asset_id=image_asset_id,
    ), None


def slugify_filename(value: str) -> str:
    slug = value.replace("//", " ")
    slug = re.sub(r"[^\w\s-]", "", slug, flags=re.ASCII)
    slug = re.sub(r"[-\s]+", "-", slug.strip(), flags=re.ASCII)
    return slug.lower() or "card"


def write_downloaded_image(image_dir: str, filename: str, image_bytes: bytes):
    os.makedirs(image_dir, exist_ok=True)
    path = os.path.join(image_dir, filename)
    with open(path, "wb") as fp:
        fp.write(image_bytes)


def _normalize_card_name(name: str) -> str:
    normalized = re.sub(r"\s+", " ", name.strip())
    normalized = normalized.replace(" / ", " // ")
    return normalized


def _normalize_optional_field(value):
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized.lower() if normalized else None


def _looks_like_csv(deck_text: str) -> bool:
    first_line = next((line for line in deck_text.splitlines() if line.strip()), "")
    if "," not in first_line:
        return False
    normalized_headers = {
        _normalize_csv_field_name(part) for part in first_line.split(",")
    }
    return "count" in normalized_headers and "name" in normalized_headers


def _normalize_csv_field_name(value: str) -> str:
    return value.strip().lower()


def _format_failed_card(entry: DeckEntry) -> str:
    detail = entry.name
    if entry.set_code:
        detail += f" ({entry.set_code})"
    if entry.collector_number:
        detail += f" {entry.collector_number}"
    return detail


def _fetch_json(url: str) -> dict:
    return core_fetch_json(url)


def _fetch_bytes(url: str) -> bytes:
    return core_fetch_bytes(url)


def _fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "print-proxy-prep/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def _build_card_service(fetch_json: Callable[[str], dict] | None = None) -> CardService:
    fetch_json = fetch_json or _fetch_json
    db_path = None
    if fetch_json is not _fetch_json:
        db_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".mtg_core_test_cache")
        os.makedirs(db_root, exist_ok=True)
        db_path = os.path.join(db_root, f"card_data_{uuid.uuid4().hex}.sqlite3")
    return CardService(db_path=db_path, fetch_json_fn=fetch_json)
