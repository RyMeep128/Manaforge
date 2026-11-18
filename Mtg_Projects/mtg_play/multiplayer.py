"""Host-owned seat setup. No engine rules or network IO in this model."""
from dataclasses import dataclass
from copy import deepcopy
import base64
import json
import re
import secrets
from urllib.parse import urlsplit, urlunsplit

FORMATS = ("freeform", "commander", "unrestricted_commander")
SHARED_RELAY_URL = "wss://manaforge-multiplayer-relay.rshafer128.workers.dev"
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def relay_url(value, *, development=False):
    parts = urlsplit(value.strip())
    local = parts.hostname in ("127.0.0.1", "localhost", "::1")
    if (parts.scheme != "wss" and not (development and local and parts.scheme == "ws")) or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("RELAY_URL_INVALID")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def new_code():
    return "".join(secrets.choice(ALPHABET) for _ in range(12))


def invite(endpoint, code):
    return "manaforge1:" + base64.urlsafe_b64encode(json.dumps([endpoint, code], separators=(",", ":")).encode()).decode().rstrip("=")


def parse_invite(value, endpoint, *, development=False):
    if len(value) > 4096:
        raise ValueError("INVITE_INVALID")
    try:
        if value.startswith("manaforge1:"):
            data = value.split(":", 1)[1]
            endpoint, value = json.loads(base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)))
        endpoint = relay_url(endpoint, development=development)
        code = value.strip().upper().replace("-", "").replace(" ", "")
        if not re.fullmatch(r"[A-HJ-NP-Z2-9]{12}", code):
            raise ValueError()
        return endpoint, code
    except (ValueError, TypeError, UnicodeError) as error:
        raise ValueError("INVITE_INVALID") from error


@dataclass
class Seat:
    seat_id: str
    kind: str = "open"
    name: str = "Open seat"
    deck: object = None
    ready: bool = False
    payment: str = "auto"


class MultiplayerLobby:
    def __init__(self, format="freeform", players=2, online=True):
        if format not in FORMATS or type(players) is not int or players != 2 or type(online) is not bool:
            raise ValueError("LOBBY_SETUP_UNSUPPORTED")
        self.format, self.online, self.started = format, online, False
        self.seats = [Seat("one", "human", "Host"), Seat("two", "open" if online else "ai", "Open seat" if online else "XMage AI")]

    def editable(self):
        if self.started:
            raise ValueError("LOBBY_STARTED")

    def invalidate(self):
        for seat in self.seats:
            if seat.kind == "human":
                seat.ready = False

    def set_kind(self, index, kind):
        self.editable()
        if index == 0 or kind not in ("open", "ai") or self.seats[index].kind == "human" or (not self.online and kind != "ai"):
            raise ValueError("SEAT_UNAVAILABLE")
        self.seats[index] = Seat(self.seats[index].seat_id, kind, "XMage AI" if kind == "ai" else "Open seat")
        self.invalidate()

    def join(self):
        self.editable()
        if self.seats[1].kind != "open":
            raise ValueError("SEAT_UNAVAILABLE")
        self.seats[1] = Seat("two", "human", "Guest")
        self.invalidate()

    def leave(self):
        self.editable()
        self.seats[1] = Seat("two")
        self.invalidate()

    def select(self, index, document, payment="auto"):
        self.editable()
        if self.seats[index].kind == "open" or payment not in ("auto", "manual", "full-control"):
            raise ValueError("SEAT_UNAVAILABLE")
        self.clear(index)
        # Structural validation only; XMage validates rules and legality before launch.
        from .launch_manifest import _project_deck
        _project_deck(document, commander=self.format != "freeform", unrestricted=self.format == "unrestricted_commander")
        self.seats[index].deck = deepcopy(document)
        self.seats[index].payment = payment
        self.invalidate()
        self.seats[index].ready = self.seats[index].kind == "ai"

    def clear(self, index):
        self.editable()
        self.seats[index].deck = None
        self.seats[index].ready = False
        self.invalidate()

    def ready(self, index, value):
        self.editable()
        seat = self.seats[index]
        if type(value) is not bool or seat.kind != "human" or seat.deck is None:
            raise ValueError("DECK_REQUIRED")
        seat.ready = value

    @property
    def can_start(self):
        return not self.started and all(s.kind != "open" and s.deck is not None and (s.kind == "ai" or s.ready) for s in self.seats)

    def start(self):
        if not self.can_start:
            raise ValueError("LOBBY_NOT_READY")
        self.started = True

    def public(self):
        return {"format": self.format, "started": self.started, "seats": [{"kind": s.kind, "name": s.name, "deck_selected": s.deck is not None, "ready": s.ready} for s in self.seats]}


def export_remote_deck(document, format):
    from .launch_manifest import _project_deck
    value = _project_deck(document, commander=format != "freeform", unrestricted=format == "unrestricted_commander")
    # _project_deck returns a document; remove personal asset and ownership fields.
    for entry in value["deck"]["entries"]:
        entry.update(owned=0, image_asset_id=None, backside_asset_id=None)
    value["deck"]["name"] = "Guest deck"
    return value


def import_remote_deck(value, format):
    from mtg_core.decks import DeckDocument
    if not isinstance(value, dict) or set(value) != {"schema_version", "deck"}:
        raise ValueError("REMOTE_DECK_INVALID")
    deck = value["deck"]
    if not isinstance(deck, dict) or len(deck.get("entries", [])) > 4096:
        raise ValueError("REMOTE_DECK_INVALID")
    document = DeckDocument.from_dict(value)
    if export_remote_deck(document, format) != value:
        raise ValueError("REMOTE_DECK_INVALID")
    return document
