"""Match preparation identities. Canonical decks remain independent of pilots."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Literal

from .contracts import GameSetup, MatchSeat

if TYPE_CHECKING:
    from mtg_core.decks import DeckDocument


@dataclass(frozen=True)
class PlayerIdentity:
    player_id: str
    name: str


@dataclass(frozen=True)
class SeatPilot:
    pilot_id: str
    controller: Literal["local_human", "engine_ai", "remote_human"]


@dataclass(frozen=True)
class DeckSelection:
    deck_id: str
    owner_id: str | None
    document: DeckDocument = field(repr=False, compare=False)

    @classmethod
    def local(cls, document, *, owner_id=None):
        # Core documents do not establish ownership; do not infer it from piloting.
        return cls(document.deck.deck_id, owner_id, document)


@dataclass(frozen=True)
class LobbySeat:
    seat_id: str
    player: PlayerIdentity
    pilot: SeatPilot
    deck: DeckSelection | None = None


@dataclass(frozen=True)
class MatchLobby:
    format: str
    seats: tuple[LobbySeat, ...]
    local_player_id: str

    def __post_init__(self):
        if len({seat.seat_id for seat in self.seats}) != len(self.seats) or any(
            not seat.seat_id or not seat.player.player_id or not seat.pilot.pilot_id
            for seat in self.seats
        ):
            raise ValueError("Match seats require distinct, nonempty identities.")
        if len({seat.player.player_id for seat in self.seats}) != len(self.seats):
            raise ValueError("Each match player requires an independent identity.")
        if (
            sum(seat.player.player_id == self.local_player_id for seat in self.seats)
            != 1
        ):
            raise ValueError("The local player must occupy one match seat.")

    @property
    def local_seat_id(self):
        return next(
            seat.seat_id
            for seat in self.seats
            if seat.player.player_id == self.local_player_id
        )

    def select_deck(self, seat_id, selection):
        if seat_id not in {seat.seat_id for seat in self.seats}:
            raise ValueError("Unknown match seat.")
        if (
            selection is not None
            and selection.deck_id != selection.document.deck.deck_id
        ):
            raise ValueError("The selected deck identity does not match its document.")
        return replace(
            self,
            seats=tuple(
                replace(seat, deck=selection) if seat.seat_id == seat_id else seat
                for seat in self.seats
            ),
        )

    def offline_setup(self):
        if self.format not in {"freeform", "commander"}:
            raise ValueError("Choose a supported offline format.")
        if (
            len(self.seats) != 2
            or self.seats[0].player.player_id != self.local_player_id
            or self.seats[0].pilot.controller != "local_human"
            or self.seats[1].pilot.controller != "engine_ai"
        ):
            raise ValueError("Offline Play requires your seat and one AI opponent.")
        return GameSetup(
            tuple(
                MatchSeat(seat.seat_id, seat.player.name, seat.pilot.controller)
                for seat in self.seats
            ),
            format=self.format,
        )

    def selected_documents(self):
        if any(seat.deck is None for seat in self.seats):
            raise ValueError("Choose a deck for each seat before starting.")
        # SessionController copies these on its worker before engine submission.
        return tuple(seat.deck.document for seat in self.seats)


def offline_lobby(*, format="freeform", seat_ids=("one", "two")):
    if len(seat_ids) != 2:
        raise ValueError("Offline Play requires two seats.")
    return MatchLobby(
        format,
        (
            LobbySeat(
                seat_ids[0],
                PlayerIdentity("local-player", "You"),
                SeatPilot("local-pilot", "local_human"),
            ),
            LobbySeat(
                seat_ids[1],
                PlayerIdentity("opponent-player", "Opponent"),
                SeatPilot("opponent-pilot", "engine_ai"),
            ),
        ),
        local_player_id="local-player",
    )
