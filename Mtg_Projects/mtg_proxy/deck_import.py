import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Callable

from mtg_core import CardService, RemoteLookupUnavailable
from mtg_core.sync import fetch_json as core_fetch_json
from mtg_core.sync import fetch_bytes as core_fetch_bytes
from models import ProjectState, as_project_state
import card_layouts

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
from mtg_core.deck_sources import (ARCHIDEKT_URL_RE, MOXFIELD_URL_RE, BLUEPRINT_URL_RE,
    is_archidekt_url, is_supported_deck_url, parse_archidekt_html, parse_moxfield_json,
    parse_blueprint_json, _blueprint_deck_id, _blueprint_api_url, _fetch_blueprint_deck)

from mtg_core.decklists import (DecklistEntry as DeckEntry, parse_decklist as core_parse_decklist,
                                resolve_card as core_resolve_card, read_decklist_file)


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


def parse_decklist(deck_text: str) -> tuple[list[DeckEntry], list[str]]:
    return core_parse_decklist(deck_text, preserve_sections=False)


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


def import_deck_url(
    deck_url: str,
    image_dir: str,
    print_fn: PRINT_FN | None = None,
    fetch_json: Callable[[str], dict] | None = None,
    fetch_bytes: Callable[[str], bytes] | None = None,
    fetch_text: Callable[[str], str] | None = None,
) -> ImportResult:
    """Import a public Archidekt, Moxfield, or Blueprint MTG deck URL."""
    if is_archidekt_url(deck_url):
        return import_archidekt_url(
            deck_url, image_dir, print_fn, fetch_json, fetch_bytes, fetch_text
        )

    print_fn = print_fn if print_fn is not None else lambda _text: None
    fetch_json = fetch_json if fetch_json is not None else _fetch_json
    fetch_bytes = fetch_bytes if fetch_bytes is not None else _fetch_bytes
    card_service = _build_card_service(fetch_json)

    moxfield_match = MOXFIELD_URL_RE.match(deck_url.strip())
    blueprint_match = BLUEPRINT_URL_RE.match(deck_url.strip())
    if moxfield_match:
        source = "Moxfield"
        deck_id = moxfield_match.group("deck_id")
        print_fn("Importing Moxfield deck...\nDownloading public deck data")
        payload = fetch_json(f"https://api2.moxfield.com/v3/decks/all/{deck_id}")
        entries = parse_moxfield_json(payload)
    elif blueprint_match:
        source = "Blueprint MTG"
        deck_id = _blueprint_deck_id(blueprint_match.group("deck_slug"))
        print_fn("Importing Blueprint MTG deck...\nDownloading public deck data")
        if fetch_json is _fetch_json:
            payload = _fetch_blueprint_deck(deck_id, fetch_text=fetch_text)
        else:
            payload = fetch_json(_blueprint_api_url(deck_id))
        entries = parse_blueprint_json(payload)
    else:
        raise ValueError(
            "Enter a valid public Archidekt, Moxfield, or Blueprint MTG deck URL."
        )

    if not entries:
        raise ValueError(f"No cards were found in the public {source} deck.")
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


def resolve_card(entry, fetch_json=None, card_service=None):
    return core_resolve_card(entry, card_service or _build_card_service(fetch_json))


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

    if card_layouts.has_printed_back(card_data) and len(face_urls) >= 2 and len(face_names) >= 2:
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
