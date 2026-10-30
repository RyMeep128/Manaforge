"""Accepted shared-library snapshots can be borrowed without remote access."""

from copy import deepcopy
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mtg_core"))
from mtg_core.decks import Deck, DeckDocument, DeckEntry, DeckStore
from mtg_core.library.client import LibraryClient, LibraryConnections
from mtg_core.library.following import FollowedDecks
from mtg_play.lobby import DeckSelection, offline_lobby
from mtg_play.setup import saved_decks


def test_play_borrows_accepted_cache_without_sync_or_modifying_sources(
    tmp_path, monkeypatch
):
    native = DeckDocument(
        deck=Deck(
            name="Native",
            entries=[DeckEntry("forest", "Forest", 60, card_id="native-print")],
        )
    )
    path = tmp_path / "decks" / "native.manaforge.json"
    DeckStore().save(path, native)
    native_bytes = path.read_bytes()
    connections = LibraryConnections(tmp_path)
    follows = FollowedDecks(connections)
    server_id = str(uuid4())
    publication = dict(
        deck_id=str(uuid4()),
        revision=1,
        owner="friend",
        color_identity=["G"],
        deck=Deck(
            name="Accepted deck",
            entries=[
                DeckEntry(
                    "land",
                    "Forest",
                    60,
                    card_id="accepted-print",
                    set_code="M10",
                    collector_number="248",
                )
            ],
        ).to_dict(),
    )
    follows.add(
        publication,
        server_id=server_id,
        address="https://friend.invalid",
        name="Friends",
    )
    update = deepcopy(publication)
    update.update(revision=2)
    update["deck"]["name"] = "Unaccepted update"

    class PendingUpdate:
        def __init__(self):
            self.server_id = server_id

        def check(self):
            pass

        def download(self, deck_id):
            return update

    follows.check(PendingUpdate())
    accepted = follows.get(server_id, publication["deck_id"])
    original = deepcopy(accepted["document"].to_dict())
    assert accepted["pending"] is not None

    def forbidden_remote(*args, **kwargs):
        raise AssertionError("Play catalog must not contact or refresh a library")

    monkeypatch.setattr(LibraryClient, "request", forbidden_remote)
    monkeypatch.setattr(FollowedDecks, "check", forbidden_remote)
    rows, errors = saved_decks(tmp_path)
    assert not errors and len(rows) == 2
    borrowed = next(row for row in rows if row.source_id)
    assert borrowed.document.deck.name == "Accepted deck"
    assert borrowed.document.to_dict() == original
    assert borrowed.path is None and borrowed.key.startswith("followed:")
    assert "friend" in borrowed.source_label and borrowed.owner_id
    selection = DeckSelection.local(
        borrowed.document, owner_id=borrowed.owner_id, source_id=borrowed.key
    )
    lobby = offline_lobby().select_deck("two", selection)
    assert lobby.seats[1].deck.owner_id != lobby.seats[1].pilot.pilot_id
    assert lobby.seats[1].deck.document.deck.entries[0].card_id == "accepted-print"
    borrowed.document.deck.name = "Only the in-memory selection changed"
    assert (
        follows.get(server_id, publication["deck_id"])["document"].to_dict() == original
    )
    assert follows.get(server_id, publication["deck_id"])["revision"] == 1
    assert path.read_bytes() == native_bytes
