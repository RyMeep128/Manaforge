"""Lobby identity/ownership regressions; no engine or UI is needed."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mtg_core"))
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_play.lobby import (
    DeckSelection,
    LobbySeat,
    MatchLobby,
    PlayerIdentity,
    SeatPilot,
    offline_lobby,
)


def test_offline_seat_player_pilot_deck_and_owner_identities_are_independent():
    document = DeckDocument()
    document.deck.entries = [
        DeckEntry("entry", "PRIVATE_DECK_CARD", card_id="exact-print")
    ]
    document.editor_preferences["custom"] = {"face": "back"}
    original = deepcopy(document.to_dict())
    selection = DeckSelection.local(document, owner_id="friend-owner")
    lobby = offline_lobby().select_deck("one", selection).select_deck("two", selection)
    assert lobby.local_seat_id == "one"
    assert lobby.seats[1].deck.owner_id == "friend-owner"
    assert lobby.seats[1].deck.deck_id == document.deck.deck_id
    assert lobby.seats[1].pilot.pilot_id != selection.owner_id
    assert lobby.seats[1].player.player_id != selection.owner_id
    assert [seat.controller for seat in lobby.offline_setup().seats] == [
        "local_human",
        "engine_ai",
    ]
    assert lobby.selected_documents() == (document, document)
    assert "PRIVATE_DECK_CARD" not in repr(lobby)
    assert document.to_dict() == original


@pytest.mark.parametrize("count", [2, 3, 4, 5, 6])
def test_generic_lobby_has_no_artificial_five_seat_maximum(count):
    seats = tuple(
        LobbySeat(
            f"seat-{index}",
            PlayerIdentity(f"player-{index}", f"Player {index}"),
            SeatPilot(
                f"pilot-{index}", "local_human" if index == 0 else "remote_human"
            ),
        )
        for index in range(count)
    )
    lobby = MatchLobby("commander", seats, "player-0")
    assert len(lobby.seats) == count
    with pytest.raises(ValueError, match="one AI opponent"):
        lobby.offline_setup()


@pytest.mark.parametrize(
    "change", ["duplicate_seat", "duplicate_player", "missing_local", "empty_pilot"]
)
def test_ambiguous_match_identities_are_rejected(change):
    lobby = offline_lobby()
    seats, local = lobby.seats, lobby.local_player_id
    if change == "duplicate_seat":
        seats = (seats[0], replace(seats[1], seat_id=seats[0].seat_id))
    elif change == "duplicate_player":
        seats = (seats[0], replace(seats[1], player=seats[0].player))
    elif change == "missing_local":
        local = "not-in-match"
    else:
        seats = (replace(seats[0], pilot=SeatPilot("", "local_human")), seats[1])
    with pytest.raises(ValueError):
        MatchLobby(lobby.format, seats, local)


def test_missing_or_mismatched_deck_selection_cannot_prepare_a_match():
    lobby = offline_lobby()
    with pytest.raises(ValueError, match="Choose a deck"):
        lobby.selected_documents()
    document = DeckDocument()
    with pytest.raises(ValueError, match="identity does not match"):
        lobby.select_deck("one", DeckSelection("other-deck", None, document))
    with pytest.raises(ValueError, match="Unknown match seat"):
        lobby.select_deck("unknown", DeckSelection.local(document))
    assert all(seat.deck is None for seat in lobby.seats)
