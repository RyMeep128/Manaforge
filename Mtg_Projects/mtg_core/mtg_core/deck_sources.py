"""Public deck-source adapters shared by the editor and Proxy."""
import html.parser
import json
import re
import urllib.parse
import urllib.request
import uuid
from collections import OrderedDict
from dataclasses import replace
from .decklists import DecklistEntry as DeckEntry


def _printing_id(*objects):
    for obj in objects:
        for key in ('scryfall_id', 'scryfallId', 'scryfallID', 'uid'):
            value = obj.get(key)
            if value:
                try:
                    return str(uuid.UUID(str(value)))
                except ValueError:
                    raise ValueError('The deck contains an invalid Scryfall printing identifier.')
        if obj.get('oracle_id') and obj.get('id'):
            try:
                return str(uuid.UUID(str(obj['id'])))
            except ValueError:
                pass  # Some sites use their own IDs rather than Scryfall IDs.
    return None


def _custom_art(*objects):
    """Only explicit overrides; a site's card thumbnail is not custom artwork."""
    front_url = back_url = None
    for obj in objects:
        override = obj.get('artOverride') or obj.get('art_override') or {}
        front_url = front_url or obj.get('customImageUrl') or obj.get('custom_image_url')
        back_url = back_url or obj.get('customBackImageUrl') or obj.get('custom_back_image_url')
        if isinstance(override, dict):
            front_url = front_url or override.get('front_url') or override.get('image_url')
            back_url = back_url or override.get('back_url')
    if any(value is not None and not isinstance(value, str) for value in (front_url, back_url)):
        raise ValueError('The custom artwork override could not be read.')
    return front_url, back_url


def _archidekt_section(card):
    if card.get('isCommander'):
        return 'commander'
    categories = card.get('categories') or []
    if isinstance(categories, str):
        categories = [categories]
    names = {str(c.get('name', '') if isinstance(c, dict) else c).casefold() for c in categories}
    names.add(str(card.get('section', '')).casefold())
    for label, section in (('commander', 'commander'), ('sideboard', 'sideboard'),
                           ('maybeboard', 'considering'), ('considering', 'considering'),
                           ('excluded', 'excluded')):
        if label in names:
            return section
    return 'mainboard'


def fetch_public_deck(url, *, fetch_json=None, fetch_text=None, cancelled=lambda: False):
    """Fetch supported public deck data. No card/artwork downloads or deck mutations."""
    from .sync import fetch_json as default_fetch_json
    url = url.strip()
    if not is_supported_deck_url(url):
        raise ValueError('Enter a public Archidekt, Moxfield, or Blueprint MTG deck URL.')
    if cancelled():
        return []
    json_fetch = fetch_json or default_fetch_json
    text_fetch = fetch_text or _fetch_text
    if is_archidekt_url(url):
        entries = parse_archidekt_html(text_fetch(url), preserve_sections=True)
    elif match := MOXFIELD_URL_RE.match(url):
        entries = parse_moxfield_json(json_fetch(
            f'https://api2.moxfield.com/v3/decks/all/{match.group("deck_id")}'), preserve_sections=True)
    else:
        match = BLUEPRINT_URL_RE.match(url)
        deck_id = _blueprint_deck_id(match.group('deck_slug'))
        payload = (json_fetch(_blueprint_api_url(deck_id)) if fetch_json else
                   _fetch_blueprint_deck(deck_id, fetch_text=text_fetch, cancelled=cancelled))
        if cancelled():
            return []
        entries = parse_blueprint_json(payload, preserve_sections=True)
    if cancelled():
        return []
    if not entries:
        raise ValueError('No cards were found. Check that the deck is public and its URL is correct.')
    return entries

ARCHIDEKT_URL_RE = re.compile(
    r"^https://(www\.)?archidekt\.com/decks/(?P<deck_id>\d+)(?:[/?#].*)?$",
    re.IGNORECASE,
)
MOXFIELD_URL_RE = re.compile(
    r"^https://(www\.)?moxfield\.com/decks/(?P<deck_id>[A-Za-z0-9_-]+)(?:[/?#].*)?$",
    re.IGNORECASE,
)
BLUEPRINT_URL_RE = re.compile(
    r"^https://(www\.)?blueprintmtg\.io/decks/(?P<deck_slug>[A-Za-z0-9_-]+)(?:[/?#].*)?$",
    re.IGNORECASE,
)
BLUEPRINT_APP_URL = "https://blueprintmtg.io/"
BLUEPRINT_DECK_SELECT = "id,name,visibility,payload"

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


def is_archidekt_url(value: str) -> bool:
    return ARCHIDEKT_URL_RE.match(value.strip()) is not None


def is_supported_deck_url(value: str) -> bool:
    value = value.strip()
    return any(pattern.match(value) is not None for pattern in (
        ARCHIDEKT_URL_RE,
        MOXFIELD_URL_RE,
        BLUEPRINT_URL_RE,
    ))


def parse_moxfield_json(payload: dict, *, preserve_sections=False) -> list[DeckEntry]:
    if not isinstance(payload, dict):
        raise ValueError('The Moxfield response could not be read.')
    boards = payload.get('boards') or payload
    if not isinstance(boards, dict):
        raise ValueError('The Moxfield response did not include readable boards.')
    entries = []
    for key, section in (('mainboard', 'mainboard'), ('sideboard', 'sideboard'),
                         ('maybeboard', 'considering'), ('commanders', 'commander'),
                         ('companions', 'sideboard')):
        collection = boards.get(key)
        if isinstance(collection, dict) and 'cards' in collection:
            collection = collection['cards']
        entries.extend(_entries_from_card_collection(collection, section=section if preserve_sections else 'mainboard',
                                                       preserve_printing=preserve_sections))
    if not entries:
        raise ValueError("The Moxfield response did not include a readable card list.")
    return _aggregate_entries(entries)


def parse_blueprint_json(payload: dict | list, *, preserve_sections=False) -> list[DeckEntry]:
    if isinstance(payload, list):
        if not payload:
            raise ValueError("The Blueprint MTG deck was not found or is private.")
        payload = payload[0]
    if not isinstance(payload, dict):
        raise ValueError("The Blueprint MTG response could not be read.")
    if payload.get("visibility") == "private":
        raise ValueError("Private Blueprint MTG decks cannot be imported.")
    deck_payload = payload.get("payload") or payload
    if not isinstance(deck_payload, dict):
        raise ValueError('The Blueprint MTG deck payload could not be read.')
    entries = []
    for key, section in (('deck', 'mainboard'), ('considering', 'considering'),
                         ('commanders', 'commander'), ('sideboard', 'sideboard')):
        entries.extend(_entries_from_card_collection(deck_payload.get(key),
            section=section if preserve_sections else 'mainboard', preserve_printing=preserve_sections))
    if not entries:
        raise ValueError("The Blueprint MTG response did not include a readable card list.")
    return _aggregate_entries(entries)


def _entries_from_card_collection(collection, *, section='mainboard', preserve_printing=False) -> list[DeckEntry]:
    if not collection:
        return []
    if not isinstance(collection, (dict, list)):
        raise ValueError('The deck source returned an unreadable card list. Try importing a text export.')
    values = collection.values() if isinstance(collection, dict) else collection
    entries = []
    for item in values:
        if not isinstance(item, dict):
            if preserve_printing:
                raise ValueError('The deck source contains an unreadable card. Try importing a text export.')
            continue
        card = item.get("card") if isinstance(item.get("card"), dict) else item
        oracle_card = card.get("oracleCard") if isinstance(card.get("oracleCard"), dict) else {}
        name = str(
            card.get("name") or card.get("displayName") or oracle_card.get("name") or ""
        ).strip()
        try:
            count = int(item.get("quantity", item.get("count", item.get("qty", 1))))
        except (TypeError, ValueError):
            if preserve_printing:
                raise ValueError(f'The deck source contains an invalid quantity for {name or "a card"}.')
            continue
        set_code = _first_optional(
            item,
            card,
            names=("setCode", "set_code", "editionCode", "editioncode", "set"),
        )
        if not set_code:
            set_record = card.get("set") or card.get("edition")
            if isinstance(set_record, dict):
                set_code = _first_optional(set_record, names=("code", "editioncode"))
        if set_code:
            set_code = set_code.lower()
        collector_number = _first_optional(
            item, card, names=("collectorNumber", "collector_number", "number")
        )
        if name and count > 0:
            entries.append(DeckEntry(count, _normalize_card_name(name), set_code, collector_number, section,
                                      _printing_id(item, card) if preserve_printing else None,
                                      *(_custom_art(item, card) if preserve_printing else (None, None))))
        elif not name and preserve_printing:
            raise ValueError('The deck source contains a card without a name. Try importing a text export.')
    return entries


def _first_optional(*objects: dict, names: tuple[str, ...]) -> str | None:
    for obj in objects:
        for name in names:
            raw_value = obj.get(name)
            if isinstance(raw_value, (dict, list)):
                continue
            value = str(raw_value).strip() if raw_value is not None else None
            if value:
                return value
    return None


def _aggregate_entries(entries: list[DeckEntry]) -> list[DeckEntry]:
    aggregated: OrderedDict[tuple[str, str | None, str | None], DeckEntry] = OrderedDict()
    for entry in entries:
        key = (entry.name.casefold(), entry.set_code, entry.collector_number, entry.section, entry.card_id, entry.image_url, entry.backside_image_url)
        previous = aggregated.get(key)
        aggregated[key] = replace(entry,
            count=entry.count + (previous.count if previous else 0),
            name=previous.name if previous else entry.name,
            set_code=entry.set_code,
            collector_number=entry.collector_number,
        )
    return list(aggregated.values())


def _blueprint_deck_id(slug: str) -> str:
    decoded = urllib.parse.unquote(slug)
    if decoded.startswith("deck-"):
        return decoded
    suffix = decoded.rsplit("-", 1)[-1]
    return f"deck-{suffix}" if suffix != decoded else decoded


def _blueprint_api_url(deck_id: str) -> str:
    query = urllib.parse.urlencode({"id": f"eq.{deck_id}", "select": BLUEPRINT_DECK_SELECT})
    return f"https://blueprintmtg.io/api/import/blueprint?{query}"


def _fetch_blueprint_deck(deck_id: str, fetch_text=None, cancelled=lambda: False) -> dict | list:
    fetch_text = fetch_text or _fetch_text
    app_html = fetch_text(BLUEPRINT_APP_URL)
    if cancelled():
        return []
    asset_match = re.search(r'<script[^>]+src="(?P<src>/assets/index-[^"]+\.js)"', app_html)
    if not asset_match:
        raise ValueError("Blueprint MTG connection details could not be discovered.")
    javascript = fetch_text(urllib.parse.urljoin(BLUEPRINT_APP_URL, asset_match.group("src")))
    if cancelled():
        return []
    url_match = re.search(r'VITE_SUPABASE_URL:"(?P<url>https://[^"]+)"', javascript)
    key_match = re.search(r'VITE_SUPABASE_PUBLISHABLE_KEY:"(?P<key>[^"]+)"', javascript)
    if not url_match or not key_match:
        # The connection settings currently live in Blueprint's shared data chunk.
        chunk_match = re.search(r'from"\./(?P<src>playtester-[^"]+\.js)"', javascript)
        if chunk_match:
            shared_js = fetch_text(urllib.parse.urljoin(BLUEPRINT_APP_URL + "assets/", chunk_match.group("src")))
            if cancelled():
                return []
            url_match = re.search(r'VITE_SUPABASE_URL:"(?P<url>https://[^"]+)"', shared_js)
            key_match = re.search(r'VITE_SUPABASE_PUBLISHABLE_KEY:"(?P<key>[^"]+)"', shared_js)
    if not url_match or not key_match:
        raise ValueError("Blueprint MTG connection details could not be discovered.")
    query = urllib.parse.urlencode({"id": f"eq.{deck_id}", "select": BLUEPRINT_DECK_SELECT})
    request = urllib.request.Request(
        f"{url_match.group('url')}/rest/v1/decks?{query}",
        headers={"Accept": "application/json", "apikey": key_match.group("key")},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_archidekt_html(html: str, *, preserve_sections=False) -> list[DeckEntry]:
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

    entries = []
    for card in card_map.values():
        name = _normalize_card_name(str(card.get("name", "")).strip())
        set_code = _normalize_optional_field(card.get("setCode"))
        collector_number = _first_optional(card, names=('collectorNumber',))
        quantity = card.get("qty", 0)
        try:
            count = int(quantity)
        except (TypeError, ValueError):
            continue

        if count <= 0 or not name:
            continue

        section = _archidekt_section(card) if preserve_sections else 'mainboard'
        entries.append(DeckEntry(count, name, set_code, collector_number, section,
                                 _printing_id(card) if preserve_sections else None,
                                 *(_custom_art(card) if preserve_sections else (None, None))))
    return _aggregate_entries(entries)


def _normalize_card_name(name: str) -> str:
    normalized = re.sub(r"\s+", " ", name.strip())
    normalized = normalized.replace(" / ", " // ")
    return normalized


def _normalize_optional_field(value):
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized.lower() if normalized else None


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


