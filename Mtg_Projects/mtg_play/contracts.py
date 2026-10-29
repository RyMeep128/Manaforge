"""Versioned, engine-independent gameplay contracts. Imports only the standard library."""

from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Protocol, Literal

GAME_PROTOCOL_VERSION = 1
ADAPTER_VERSION = "0.2.0-alpha.1"


class Serializable:
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MatchSeat(Serializable):
    seat_id: str
    name: str


@dataclass(frozen=True)
class GameSetup(Serializable):
    seats: tuple[MatchSeat, ...]
    format: str = "freeform"
    protocol_version: int = GAME_PROTOCOL_VERSION


@dataclass(frozen=True)
class Compatibility(Serializable):
    manaforge_version: str
    protocol_version: int
    adapter_version: str
    engine_version: str
    artifact_manifest_sha256: str


@dataclass(frozen=True)
class Capability(Serializable):
    name: str
    status: Literal["verified", "unverified", "unsupported"]
    detail: str = ""


@dataclass(frozen=True)
class RuntimeReport(Serializable):
    success: bool
    workspace: str | None
    process_exit_codes: tuple[tuple[str, int | None], ...]
    forced_cleanup: bool
    code: str | None = None


@dataclass(frozen=True)
class CardIdentity(Serializable):
    oracle_id: str | None
    printing_id: str | None
    deck_entry_id: str | None


@dataclass(frozen=True)
class CardCharacteristics(Serializable):
    name: str | None = None
    power: str | None = None
    toughness: str | None = None
    type_line: str | None = None
    color: str | None = None
    engine_view_text: tuple[str, ...] | None = None
    loyalty: str | None = None
    defense: str | None = None
    transformed: bool | None = None
    counters: tuple[tuple[str, int], ...] | None = None
    is_copy: bool | None = None
    flipped: bool | None = None
    current_abilities: tuple[str, ...] | None = None
    unsupported_fields: tuple[str, ...] = (
        "current_rules_text",
        "ability_identities",
        "color_identity",
        "copy_provenance_history",
        "merged_components",
    )


@dataclass(frozen=True)
class GameObject(Serializable):
    object_id: str
    zone: str
    owner_id: str | None
    controller_id: str | None
    hidden: bool
    characteristics: CardCharacteristics | None
    card_identity: CardIdentity | None = None
    tapped: bool | None = None
    damage: int | None = None
    attacking_available: bool | None = None
    blocking_available: bool | None = None
    face_down: bool | None = None
    attachments: tuple[str, ...] | None = None
    attached_to: str | None = None
    commander_id: str | None = None
    copy_source_id: str | None = None


@dataclass(frozen=True)
class PlayerView(Serializable):
    player_id: str
    name: str
    life: int
    hand_count: int
    library_count: int
    eliminated: bool | None
    left_game: bool | None = None
    mana: tuple[tuple[str, int], ...] | None = None
    counters: tuple[tuple[str, int], ...] | None = None


@dataclass(frozen=True)
class LegalAction(Serializable):
    action_id: str
    kind: str
    object_id: str | None
    label: str


@dataclass(frozen=True)
class ChoiceOption(Serializable):
    option_id: str
    label: str
    object_id: str | None = None
    player_id: str | None = None
    selected: bool = False


@dataclass(frozen=True)
class AmountConstraint(Serializable):
    label: str
    minimum: int
    maximum: int
    default: int | None = None


@dataclass(frozen=True)
class ChoiceRequest(Serializable):
    decision_id: str
    player_id: str
    family: str
    prompt: str
    options: tuple[ChoiceOption, ...]
    minimum: int | None = None
    maximum: int | None = None
    cancellable: bool = False
    amounts: tuple[AmountConstraint, ...] = ()
    can_finish: bool = False


@dataclass(frozen=True)
class CombatAssignment(Serializable):
    attackers: tuple[str, ...]
    blockers: tuple[str, ...]
    defender_id: str | None
    blocked: bool


@dataclass(frozen=True)
class CommanderState(Serializable):
    commander_id: str
    owner_id: str
    name: str | None
    card_identity: CardIdentity | None
    command_zone_plays: int | None
    damage_dealt: tuple[tuple[str, int], ...]
    additional_cast_cost: str | None = None


@dataclass(frozen=True)
class CardObservation(Serializable):
    observation_id: str
    source: str
    hidden: bool
    name: str | None = None
    set_code: str | None = None
    collector_number: str | None = None


@dataclass(frozen=True)
class GameSnapshot(Serializable):
    session_id: str
    viewer_id: str
    revision: int
    status: str
    turn: int | None
    phase: str | None
    step: str | None
    active_player_id: str | None
    priority_player_id: str | None
    players: tuple[PlayerView, ...]
    objects: tuple[GameObject, ...]
    actions: tuple[LegalAction, ...]
    decision: ChoiceRequest | None
    combat: tuple[CombatAssignment, ...] = ()
    protocol_version: int = GAME_PROTOCOL_VERSION
    result: str | None = None
    commanders: tuple[CommanderState, ...] | None = None
    observations: tuple[CardObservation, ...] = ()
    unsupported_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class GameEvent(Serializable):
    kind: str
    player_id: str
    revision: int
    code: str | None = None
    observations: tuple[CardObservation, ...] = ()


@dataclass(frozen=True)
class CommandResult(Serializable):
    command_id: str
    outcome: Literal["submitted", "confirmed", "rejected", "uncertain"]
    code: str | None = None


class GameSession(Protocol):
    session_id: str

    def snapshot(self, player_id: str) -> GameSnapshot: ...
    def poll(self, player_id: str, timeout: float = 0) -> tuple[GameEvent, ...]: ...
    def perform(
        self, player_id: str, decision_id: str, action_id: str
    ) -> CommandResult: ...
    def choose(
        self, player_id: str, decision_id: str, option_id: str
    ) -> CommandResult: ...
    def select_mana_source(
        self, player_id: str, decision_id: str, object_id: str
    ) -> CommandResult: ...
    def choose_number(
        self, player_id: str, decision_id: str, value: int
    ) -> CommandResult: ...
    def choose_amounts(
        self, player_id: str, decision_id: str, values: tuple[int, ...]
    ) -> CommandResult: ...
    def finish_selection(self, player_id: str, decision_id: str) -> CommandResult: ...
    def cancel(self, player_id: str, decision_id: str) -> CommandResult: ...
    def concede(self, player_id: str) -> CommandResult: ...
