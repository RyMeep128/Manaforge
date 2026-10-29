"""Local XMage adapter. Engine details stay behind Manaforge-owned contracts."""

from __future__ import annotations
from dataclasses import replace
from functools import wraps
import hashlib
import html
import json
from pathlib import Path
import queue
import re
import threading
import time
import uuid
from typing import TYPE_CHECKING
from . import connection_proof as transport
from .contracts import (
    ADAPTER_VERSION,
    AmountConstraint,
    GAME_PROTOCOL_VERSION,
    Capability,
    CardCharacteristics,
    CardObservation,
    ChoiceOption,
    ChoiceRequest,
    CombatAssignment,
    CommanderState,
    CommandResult,
    Compatibility,
    GameEvent,
    GameObject,
    GameSetup,
    GameSnapshot,
    LegalAction,
    PlayerView,
    RuntimeReport,
)
from .decks import prepare_deck

if TYPE_CHECKING:
    from mtg_core.decks import DeckDocument


def _id() -> str:
    return uuid.uuid4().hex


def _text(value: str | None) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value or ""))


def _pairs(value):
    return None if value is None else tuple(tuple(item) for item in value)


def _timed(metric):
    """Bounded numeric diagnostics only; never retain views or prompt contents."""

    def decorate(function):
        @wraps(function)
        def measured(self, *args, **kwargs):
            started = time.perf_counter()
            value = None
            try:
                value = function(self, *args, **kwargs)
                return value
            finally:
                if hasattr(self, "_timings"):
                    elapsed = (time.perf_counter() - started) * 1000
                    row = self._timings.setdefault(
                        metric, dict(count=0, total_ms=0.0, max_ms=0.0)
                    )
                    row["count"] += 1
                    row["total_ms"] += elapsed
                    row["max_ms"] = max(row["max_ms"], elapsed)
                    if metric == "snapshot_construction" and value is not None:
                        size = len(value.objects)
                        band = (
                            "0-15" if size < 16 else "16-63" if size < 64 else "64-plus"
                        )
                        bucket = self._timings.setdefault(
                            "snapshot_objects_" + band,
                            dict(count=0, total_ms=0.0, max_ms=0.0),
                        )
                        bucket["count"] += 1
                        bucket["total_ms"] += elapsed
                        bucket["max_ms"] = max(bucket["max_ms"], elapsed)

        return measured

    return decorate


class AdapterError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class LocalGameAdapter:
    """Context-managed owner of one isolated server and its local player sessions.

    Calls are serialized by the consumer; independent consumers should receive a
    seat-scoped GameSession view through their application's authorization layer.
    No automatic reconnect/replay is attempted after a transport failure.
    """

    def __init__(
        self,
        *,
        bundle: Path = transport.DEFAULT_BUNDLE,
        jdk: Path = transport.DEFAULT_JDK,
    ):
        self._bundle, self._jdk = Path(bundle).resolve(), Path(jdk).resolve()
        self._ready, self._release, self._done = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )
        self._thread = None
        self._runtime = None
        self._session = None
        self._runtime_result = None

    def __enter__(self):
        if self._thread is not None:
            raise AdapterError("RUNTIME_ALREADY_STARTED")

        def consume(*runtime):
            self._runtime = runtime
            self._ready.set()
            self._release.wait()

        def run():
            try:
                self._runtime_result = transport.run_proof(
                    self._bundle, self._jdk, runtime_consumer=consume
                )
            except Exception:
                self._runtime_result = {
                    "success": False,
                    "error": "ENGINE_STARTUP_FAILED",
                }
            finally:
                self._ready.set()
                self._done.set()

        self._thread = threading.Thread(
            target=run, name="manaforge-local-engine", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(240) or self._runtime is None or self._done.is_set():
            self.close()
            raise AdapterError("ENGINE_STARTUP_FAILED")
        return self

    @property
    def result(self) -> RuntimeReport | None:
        if self._runtime_result is None:
            return None
        processes = {
            key: value
            for key, value in self._runtime_result.items()
            if key in ("server", "bridge") or key.startswith("peer_")
        }
        return RuntimeReport(
            bool(self._runtime_result.get("success")),
            self._runtime_result.get("workspace"),
            tuple((key, value.get("exit_code")) for key, value in processes.items()),
            any(value.get("forced", False) for value in processes.values()),
            None if self._runtime_result.get("success") else "ENGINE_RUNTIME_FAILED",
        )

    @property
    def compatibility(self) -> Compatibility:
        # Read the application version without importing its Qt/printing startup dependencies.
        constants = (transport.HERE.parent / "mtg_proxy/constants.py").read_text(
            encoding="utf-8"
        )
        match = re.search(r'^APP_VERSION = "([^"\n]+)"', constants, re.MULTILINE)
        manifest_bytes = (transport.HERE / "artifacts.json").read_bytes()
        return Compatibility(
            match.group(1) if match else "unknown",
            GAME_PROTOCOL_VERSION,
            ADAPTER_VERSION,
            json.loads(manifest_bytes)["engine"],
            hashlib.sha256(manifest_bytes).hexdigest(),
        )

    @property
    def capabilities(self) -> tuple[Capability, ...]:
        return (
            Capability("local_two_player_freeform", "verified"),
            Capability(
                "commander",
                "verified",
                "2–5 seats; partner designations; casting, damage and engine-calculated tax",
            ),
            Capability(
                "continuous_power_toughness", "verified", "Giant Growth and expiration"
            ),
            Capability("continuous_type_color", "verified", "Snakeform and expiration"),
            Capability(
                "mana_source_selection",
                "verified",
                "Engine validates selected sources; exhaustive source enumeration unavailable",
            ),
            Capability(
                "complex_decisions",
                "verified",
                "Numbers, modes, search, sacrifice, distribution, trigger ordering and cancellation",
            ),
            Capability(
                "x_mana_payment", "verified", "Walking Ballista number and mana prompts"
            ),
            Capability("legacy_x_mana_prompt", "unsupported"),
            Capability("commander_damage_tax", "verified"),
            Capability(
                "revealed_information",
                "verified",
                "Private Gitaxian Probe peek and concealment",
            ),
            Capability(
                "unobserved_zone_change_identity",
                "verified",
                "Cloudshift and engine incarnation metadata",
            ),
            Capability(
                "copy_and_transform",
                "verified",
                "Clone and Delver; physical printing preserved",
            ),
            Capability(
                "blocking",
                "verified",
                "Two Memnites, block assignment and combat deaths",
            ),
            Capability("pending_choice_shutdown", "verified"),
            Capability(
                "pile_choices", "verified", "Fact or Fiction split and both piles"
            ),
            Capability(
                "backgrounds_and_companions",
                "verified",
                "Wilson/Raised by Giants; Kenrith/Jegantha pregame choice",
            ),
            Capability(
                "string_choices", "verified", "Utopia Sprawl color and attachment"
            ),
            Capability("complete_dynamic_rules_text", "unsupported"),
            Capability("reconnection", "unsupported"),
            Capability("remote_multiplayer", "unsupported"),
        )

    def _server_request(self, **fields):
        if self._runtime is None or self._done.is_set():
            raise AdapterError("ENGINE_UNAVAILABLE")
        server, directory = self._runtime[4:]
        request = str(uuid.uuid4())
        try:
            server.stdin.write(json.dumps({"request_id": request, **fields}) + "\n")
            server.stdin.flush()
        except (OSError, ValueError) as error:
            raise AdapterError("ENGINE_CONTROL_LOST") from error
        response = directory / "manaforge-responses" / (request + ".json")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if response.is_file():
                payload = json.loads(response.read_text(encoding="utf-8"))
                response.unlink()  # Private deck-resolution payload is transient.
                return payload
            if server.poll() is not None:
                raise AdapterError("ENGINE_EXITED")
            time.sleep(0.01)
        raise AdapterError("SERVER_CONTROL_TIMEOUT")

    def _resolve(self, queries):
        return self._server_request(cards=queries)

    def _metadata(self, view):
        cards = [
            card for zone in ("hand", "stack", "exile") for card in view.get(zone, ())
        ]
        cards += [
            card
            for row in view["players"]
            for zone in ("battlefield", "graveyard", "command")
            for card in row.get(zone, ())
        ]
        return self._server_request(
            command="metadata",
            game=view["game_id"],
            player=view["viewer"],
            cycle=view["cycle"],
            object_ids=[card["id"] for card in cards],
            identified_ids=[
                card["id"] for card in cards if not card.get("hidden", True)
            ],
        )

    def create_game(
        self, setup: GameSetup, decks: tuple[DeckDocument, ...], *, oracle_lookup=None
    ):
        if self._session is not None:
            raise AdapterError("SESSION_ALREADY_CREATED")
        if self._runtime is None or self._done.is_set():
            raise AdapterError("ENGINE_UNAVAILABLE")
        if (
            type(setup.protocol_version) is not int
            or setup.protocol_version != GAME_PROTOCOL_VERSION
        ):
            raise AdapterError("INCOMPATIBLE_GAME_PROTOCOL")
        if len(setup.seats) < 2 or len(setup.seats) != len(decks):
            raise AdapterError("INVALID_SEATS")
        if len({seat.seat_id for seat in setup.seats}) != len(setup.seats) or any(
            not seat.seat_id for seat in setup.seats
        ):
            raise AdapterError("INVALID_SEAT_IDENTITIES")
        if setup.format not in ("freeform", "commander") or (
            setup.format == "freeform" and len(setup.seats) != 2
        ):
            raise AdapterError("UNSUPPORTED_GAME_SETUP")
        prepared = tuple(
            prepare_deck(
                deck,
                self._resolve,
                oracle_lookup,
                commander=setup.format == "commander",
            )
            for deck in decks
        )
        self._session = XmageGameSession(self, setup, prepared)
        self._session._start()
        return self._session

    def close(self):
        if self._session is not None:
            self._session._closed = True
        self._release.set()
        if self._thread is not None and not self._done.wait(45):
            raise AdapterError("ENGINE_CLEANUP_TIMEOUT")
        if self.result is not None and not self.result.success:
            raise AdapterError("ENGINE_RUNTIME_FAILED")

    def __exit__(self, exc_type, exc, traceback):
        try:
            self.close()
        except AdapterError:
            if exc is None:
                raise


class XmageGameSession:
    """One local game. Public values contain no engine identifiers or payloads."""

    def __init__(self, owner, setup, decks):
        self._timings = {}
        self.session_id = _id()
        self._owner, self._setup, self._decks = owner, setup, decks
        self._clients, self._views, self._pending, self._replies = {}, {}, {}, {}
        self._player_ids, self._names, self._game_ids = {}, {}, {}
        self._objects, self._wire_objects, self._choices, self._actions = {}, {}, {}, {}
        self._notifications = {seat.seat_id: [] for seat in setup.seats}
        self._status = {seat.seat_id: "starting" for seat in setup.seats}
        self._revision = {seat.seat_id: 0 for seat in setup.seats}
        self._sequences = {seat.seat_id: -1 for seat in setup.seats}
        self._results = {}
        self._outstanding = set()
        self._decision_sequences = {seat.seat_id: -1 for seat in setup.seats}
        self._deferred_views = {}
        self._metadata_wait_since = {}
        self._commander_refs = {}
        self._observation_signatures = {}
        self._observation_sequences = {seat.seat_id: -1 for seat in setup.seats}
        self._closed = False

    def _start(self):
        first, events, launch, port, _, _ = self._owner._runtime
        for index, seat in enumerate(self._setup.seats):
            if index == 0:
                process, stream = first, events
            else:
                process, stream = launch()
            self._clients[seat.seat_id] = process, stream
            if index > 0:
                request = _id()
                username = "mf_" + _id()[:10]
                self._names[username] = seat.seat_id
                transport.send(
                    process, "connect", request, port=port, username=username
                )
                stream.wait("connected", time.monotonic() + 30, request)
        # The initial proof client already connected; discover its generated username.
        first_seat = self._setup.seats[0].seat_id
        self._request(first_seat, "status", "status")
        created = self._request(
            first_seat,
            "create_game",
            "table_created",
            format=self._setup.format,
            seats=len(self._setup.seats),
        )
        table = created["table_id"]
        for seat, deck in zip(self._setup.seats, self._decks):
            self._request(
                seat.seat_id,
                "join_table",
                "joined",
                table_id=table,
                cards=deck.cards,
                sideboard=deck.sideboard,
            )
        self._request(first_seat, "start_game", "started", table_id=table)

    def _check(self, player):
        if player not in self._clients:
            raise AdapterError("UNKNOWN_PLAYER")
        if self._closed:
            raise AdapterError("SESSION_CLOSED")

    @_timed("command_round_trip")
    def _request(self, player, operation, expected, **fields):
        request = _id()
        self._outstanding.add(request)
        try:
            transport.send(self._clients[player][0], operation, request, **fields)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                self._pump()
                reply = self._replies.pop(request, None)
                if reply is not None:
                    if reply["event"] == "error":
                        known = (
                            "STALE_DECISION",
                            "UNSUPPORTED_SEAT_COUNT",
                            "UNSUPPORTED_GAME_SETUP",
                            "AMOUNT_OUT_OF_RANGE",
                        )
                        code = next(
                            (
                                code
                                for code in known
                                if code in reply.get("message", "")
                            ),
                            "DECK_REJECTED_BY_ENGINE"
                            if operation == "join_table"
                            else "ENGINE_COMMAND_REJECTED",
                        )
                        raise AdapterError(code)
                    if reply["event"] != expected:
                        raise AdapterError("UNEXPECTED_COMMAND_RESPONSE")
                    return reply
                if self._status[player] == "failed":
                    raise AdapterError("ENGINE_UNAVAILABLE")
                time.sleep(0.005)
            raise AdapterError("COMMAND_OUTCOME_UNCERTAIN")
        except (OSError, ValueError, transport.ProofError) as error:
            self._fail(player, "ENGINE_CONNECTION_LOST")
            raise AdapterError("COMMAND_OUTCOME_UNCERTAIN") from error
        finally:
            self._outstanding.discard(request)
            self._replies.pop(request, None)

    def _pump(self):
        for player, (_, stream) in self._clients.items():
            while True:
                try:
                    event = stream.events.get_nowait()
                except queue.Empty:
                    break
                if event is None or isinstance(event, Exception):
                    self._fail(player, "ENGINE_CONNECTION_LOST")
                    break
                if event.get("request_id") is not None:
                    if event["request_id"] in self._outstanding:
                        self._replies[event["request_id"]] = event
                    continue
                kind = event["event"]
                if kind == "game_started":
                    self._game_ids[player] = event["game_id"]
                    self._player_ids[event["player_id"]] = player
                elif kind == "game_state":
                    sequence = event.get("sequence", -1)
                    if sequence <= self._sequences[player]:
                        continue
                    if event.get("game_id"):
                        self._game_ids.setdefault(player, event["game_id"])
                    try:
                        self._record_observations(player, event)
                    except AdapterError as error:
                        self._fail(player, error.code)
                        continue
                    deferred = self._deferred_views.get(player)
                    if deferred is None or sequence > deferred["sequence"]:
                        self._deferred_views[player] = event
                        self._metadata_wait_since.setdefault(player, time.monotonic())
                elif kind == "decision":
                    if event["decision_id"] > self._decision_sequences[player]:
                        self._decision_sequences[player] = event["decision_id"]
                        self._pending[player] = event
                        if player in self._views:
                            self._refresh(player)
                elif kind == "game_result":
                    self._results[player] = "won" if event["won"] else "did_not_win"
                    self._refresh(player)
                elif kind == "game_over":
                    self._status[player] = "finished"
                    self._pending.pop(player, None)
                    self._refresh(player)
                elif kind in ("error", "disconnected"):
                    self._fail(
                        player,
                        "UNSUPPORTED_DECISION"
                        if "UNSUPPORTED_DECISION" in event.get("message", "")
                        else "ENGINE_CONNECTION_FAILED",
                    )

        for player, view in tuple(self._deferred_views.items()):
            if self._enrich_view(player, view):
                self._publish_view(player, view)
                self._deferred_views.pop(player, None)
                self._metadata_wait_since.pop(player, None)

    def _record_observations(self, player, event):
        if event.get("sequence", -1) <= self._observation_sequences[player]:
            return
        self._observation_sequences[player] = event.get("sequence", -1)
        source = event.get("observations", ())
        queries = [
            dict(key=str(index), set=item["set"], number=item["number"])
            for index, item in enumerate(source)
            if not item.get("hidden", True)
            and item.get("name") is None
            and item.get("set")
            and item.get("number")
        ]
        names = (
            self._owner._server_request(command="printing_names", printings=queries)
            if queries
            else {}
        )
        observations = tuple(
            CardObservation(
                _id(),
                item["source"],
                item.get("hidden", True),
                None
                if item.get("hidden", True)
                else item.get("name", names.get(str(index))),
                None if item.get("hidden", True) else item.get("set"),
                None if item.get("hidden", True) else item.get("number"),
            )
            for index, item in enumerate(source)
        )
        signature = tuple(
            (item.source, item.hidden, item.name, item.set_code, item.collector_number)
            for item in observations
        )
        previous = self._observation_signatures.get(player, ())
        self._observation_signatures[player] = signature
        event["_observations"] = observations
        if signature != previous:
            self._notifications[player].append(
                GameEvent(
                    "cards_observed" if observations else "observations_cleared",
                    player,
                    self._revision[player],
                    observations=observations,
                )
            )

    @_timed("metadata_enrichment")
    def _enrich_view(self, player, view):
        if "cycle" not in view:  # Controlled transport fixtures, never the real bridge.
            return True
        try:
            metadata = self._owner._metadata(view)
        except AdapterError as error:
            self._fail(player, error.code)
            self._deferred_views.pop(player, None)
            return False
        if metadata["status"] == "retry":
            if (
                time.monotonic()
                - self._metadata_wait_since.get(player, time.monotonic())
                > 30
            ):
                self._fail(player, "ENGINE_METADATA_TIMEOUT")
                self._deferred_views.pop(player, None)
            return False
        if metadata["status"] == "finished":
            view["_metadata_unavailable"] = True
            if self._status[player] not in ("finished", "failed"):
                self._status[player] = "finishing"
                self._pending.pop(player, None)
            return True
        if metadata["status"] != "ok" or metadata["cycle"] != view["cycle"]:
            self._fail(
                player,
                "PINNED_METADATA_INTERFACE_CHANGED"
                if metadata.get("code") == "PINNED_METADATA_INTERFACE_CHANGED"
                else "INCOHERENT_ENGINE_METADATA",
            )
            self._deferred_views.pop(player, None)
            return False
        cards = [
            card for zone in ("hand", "stack", "exile") for card in view.get(zone, ())
        ]
        cards += [
            card
            for row in view["players"]
            for zone in ("battlefield", "graveyard", "command")
            for card in row.get(zone, ())
        ]
        if any(card["id"] not in metadata["objects"] for card in cards):
            self._fail(player, "INCOMPLETE_ENGINE_METADATA")
            self._deferred_views.pop(player, None)
            return False
        for card in cards:
            card.update(metadata["objects"][card["id"]])
        players = {row["id"]: row for row in metadata["players"]}
        for row in view["players"]:
            row["eliminated"] = players[row["id"]]["lost"] or players[row["id"]]["left"]
        view["commanders"] = metadata["commanders"]
        return True

    @staticmethod
    def _object_key(card, zone):
        return card["id"], zone, card.get("hidden", True), card.get("incarnation")

    def _publish_view(self, player, event):
        self._sequences[player] = event.get("sequence", -1)
        # Retire references on every authoritative zone/visibility transition,
        # including transitions the consumer did not poll between.
        visible = set()
        for zone in ("hand", "stack", "exile"):
            visible.update(self._object_key(card, zone) for card in event.get(zone, ()))
        for row in event["players"]:
            for zone in ("battlefield", "graveyard", "command"):
                visible.update(
                    self._object_key(card, zone) for card in row.get(zone, ())
                )
        self._objects[player] = {
            key: value
            for key, value in self._objects.get(player, {}).items()
            if key in visible
        }
        self._views[player] = event
        # The local viewer is authoritative for its own seat identity.
        if event.get("viewer"):
            self._player_ids[event["viewer"]] = player
        for row in event["players"]:
            if row["id"] in self._player_ids:
                self._names[row["name"]] = self._player_ids[row["id"]]
            elif row["name"] in self._names:
                self._player_ids[row["id"]] = self._names[row["name"]]
        if self._status[player] == "starting":
            self._status[player] = "active"
        self._refresh(player)

    def _fail(self, player, code):
        if self._status[player] != "failed":
            self._status[player] = "failed"
            self._notifications[player].append(
                GameEvent("session_failed", player, self._revision[player], code)
            )

    def _public_text(self, value):
        text = _text(value)
        labels = {seat.seat_id: seat.name for seat in self._setup.seats}
        for username, seat in self._names.items():
            text = text.replace(username, labels[seat])
        return re.sub(
            r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b",
            "[object]",
            text,
        )

    def _refresh(self, player):
        self._revision[player] += 1
        event = GameEvent("snapshot_changed", player, self._revision[player])
        if (
            self._notifications[player]
            and self._notifications[player][-1].kind == "snapshot_changed"
        ):
            self._notifications[player][-1] = event
        else:
            self._notifications[player].append(event)
        self._actions[player] = {}
        self._choices[player] = {}

    def performance_report(self):
        """Aggregate timings in milliseconds, including retries and failed calls.

        Snapshot timing includes pumping/enrichment and must not be added to the
        metadata timing. Resource usage of owned JVMs is currently unavailable.
        """
        return {name: dict(values) for name, values in self._timings.items()}

    @_timed("snapshot_construction")
    def snapshot(self, player_id):
        self._check(player_id)
        self._pump()
        if self._status[player_id] == "failed":
            return GameSnapshot(
                session_id=self.session_id,
                viewer_id=player_id,
                revision=self._revision[player_id],
                status="failed",
                turn=None,
                phase=None,
                step=None,
                active_player_id=None,
                priority_player_id=None,
                players=(),
                objects=(),
                actions=(),
                decision=None,
                unsupported_fields=("state_unavailable",),
            )
        view = self._views.get(player_id)
        if view is None or player_id in self._deferred_views:
            raise AdapterError("SNAPSHOT_NOT_READY")
        pending = self._pending.get(player_id)
        if (
            pending is not None
            and "cycle" in pending
            and (
                pending["cycle"] != view.get("cycle")
                or pending["decision_id"] > view.get("sequence", -1)
            )
        ):
            raise AdapterError("SNAPSHOT_NOT_READY")
        player_names = {seat.seat_id: seat.name for seat in self._setup.seats}
        players = []
        zones = []
        for row in view["players"]:
            seat = self._player_ids.get(row["id"])
            if seat is None:
                raise AdapterError("SNAPSHOT_NOT_READY")
            players.append(
                PlayerView(
                    seat,
                    player_names[seat],
                    row["life"],
                    row["hand_count"],
                    row["library_count"],
                    row.get("eliminated"),
                    row.get("left"),
                    _pairs(row.get("mana")),
                    _pairs(row.get("counters")),
                )
            )
            for zone in ("battlefield", "graveyard", "command"):
                for card in row.get(zone, ()):
                    zones.append((zone, card, seat))
        zones.extend(("hand", card, player_id) for card in view["hand"])
        zones.extend(("stack", card, None) for card in view["stack"])
        zones.extend(("exile", card, None) for card in view.get("exile", ()))
        pending = self._pending.get(player_id)
        known = {card["id"] for _, card, _ in zones}
        if pending is not None:
            zones.extend(
                ("decision", card, None)
                for card in pending.get("cards", ())
                if card["id"] not in known
            )
        if pending is not None:
            zones.extend(
                ("decision_pile_2", card, None)
                for card in pending.get("second_pile", ())
                if card["id"] not in known
            )
        commanders = []
        for commander in view.get("commanders", ()):
            owner = self._player_ids.get(commander["owner"])
            if owner is None:
                raise AdapterError("SNAPSHOT_NOT_READY")
            deck = self._decks[
                next(
                    index
                    for index, seat in enumerate(self._setup.seats)
                    if seat.seat_id == owner
                )
            ]
            reference = self._commander_refs.setdefault(commander["id"], _id())
            commanders.append(
                CommanderState(
                    reference,
                    owner,
                    commander.get("name"),
                    deck.bindings.get((commander.get("set"), commander.get("number"))),
                    commander.get("plays"),
                    tuple(
                        (self._player_ids[raw], amount)
                        for raw, amount in commander["damage"].items()
                        if raw in self._player_ids
                    ),
                    commander.get("tax"),
                )
            )
        old_objects = self._objects.get(player_id, {})
        references, wire, objects = {}, {}, []
        for zone, card, seat in zones:
            hidden = card.get("hidden", True)
            key = self._object_key(card, zone)
            reference = old_objects.get(key, _id())
            references[key] = reference
            wire[reference] = card["id"]
            if zone == "battlefield":
                controller = self._names.get(card.get("controller_name"))
                # Pinned PermanentView deliberately leaves nameOwner empty when
                # owner equals controller. Decode that sentinel, not game rules.
                owner = (
                    self._names.get(card["owner_name"])
                    if card.get("owner_name")
                    else controller
                )
            else:
                owner = self._player_ids.get(card.get("owner"), seat)
                controller = self._player_ids.get(card.get("controller"), seat)
            owner = self._player_ids.get(card.get("owner"), owner)
            controller = self._player_ids.get(card.get("controller"), controller)
            identity = None
            if (
                not hidden
                and not card.get("token")
                and owner in player_names
                and not view.get("_metadata_unavailable")
            ):
                deck = self._decks[
                    next(
                        index
                        for index, match in enumerate(self._setup.seats)
                        if match.seat_id == owner
                    )
                ]
                identity = deck.bindings.get(
                    (
                        card.get("physical_set", card.get("set")),
                        card.get("physical_number", card.get("number")),
                    )
                )
            characteristics = (
                None
                if hidden
                else CardCharacteristics(
                    card.get("name"),
                    card.get("power"),
                    card.get("toughness"),
                    card.get("type"),
                    card.get("color"),
                    None
                    if card.get("view_rules") is None
                    else tuple(self._public_text(rule) for rule in card["view_rules"]),
                    card.get("loyalty"),
                    card.get("defense"),
                    card.get("transformed"),
                    _pairs(card.get("counters")),
                    card.get("copy"),
                    card.get("flipped"),
                    current_abilities=None
                    if "live_abilities" not in card
                    else tuple(
                        self._public_text(rule) for rule in card["live_abilities"]
                    ),
                )
            )
            objects.append(
                GameObject(
                    reference,
                    zone,
                    owner,
                    controller,
                    hidden,
                    characteristics,
                    identity,
                    card.get("tapped"),
                    card.get("damage"),
                    card.get("can_attack"),
                    card.get("can_block"),
                    card.get("face_down"),
                    commander_id=self._commander_refs.get(card["id"])
                    if not hidden
                    else None,
                )
            )
        self._objects[player_id] = references
        self._wire_objects[player_id] = wire
        reverse = {raw: ref for ref, raw in wire.items()}
        cards_by_ref = {
            references[self._object_key(card, zone)]: card for zone, card, _ in zones
        }
        objects = [
            replace(
                obj,
                attachments=tuple(
                    reverse[raw]
                    for raw in cards_by_ref[obj.object_id].get("attachments", ())
                    if raw in reverse
                )
                if "attachments" in cards_by_ref[obj.object_id]
                else None,
                attached_to=reverse.get(cards_by_ref[obj.object_id].get("attached_to")),
                copy_source_id=reverse.get(
                    cards_by_ref[obj.object_id].get("copy_source")
                ),
            )
            for obj in objects
        ]
        request = self._pending.get(player_id)
        decision, actions = None, []
        action_map, choice_map = (
            self._actions.setdefault(player_id, {}),
            self._choices.setdefault(player_id, {}),
        )
        if request is not None and self._status[player_id] == "active":
            token = request.setdefault("token", _id())
            method = request["kind"]
            family = {
                "GAME_ASK": "boolean",
                "GAME_SELECT": "selection",
                "GAME_TARGET": "target",
                "GAME_CHOOSE_ABILITY": "ability",
                "GAME_GET_AMOUNT": "number",
                "GAME_CHOOSE_CHOICE": "options",
                "GAME_PLAY_MANA": "mana",
                "GAME_GET_MULTI_AMOUNT": "amounts",
                "GAME_CHOOSE_PILE": "piles",
            }.get(method)
            if family is None:
                self._fail(player_id, "UNSUPPORTED_DECISION")
                raise AdapterError("UNSUPPORTED_DECISION")
            options = []
            if family == "boolean":
                for value, label in ((True, "Yes"), (False, "No")):
                    option = token + ("-yes" if value else "-no")
                    choice_map[option] = ("boolean", value)
                    options.append(ChoiceOption(option, label))
            elif family in ("selection", "mana"):
                offered = (
                    request.get("attackers")
                    or request.get("blockers")
                    or view.get("playable", ())
                )
                for raw in offered:
                    if raw not in reverse:
                        continue
                    reference = reverse[raw]
                    action = token + "-" + reference
                    action_map[action] = ("object", raw)
                    obj = next(obj for obj in objects if obj.object_id == reference)
                    kind = (
                        "declare_attacker"
                        if request.get("attackers")
                        else "declare_blocker"
                        if request.get("blockers")
                        else "pay_mana"
                        if family == "mana"
                        else view.get("action_kinds", {}).get(raw, "select_object")
                    )
                    actions.append(
                        LegalAction(
                            action,
                            kind,
                            reference,
                            obj.characteristics.name
                            if obj.characteristics and obj.characteristics.name
                            else "Select object",
                        )
                    )
                action = token + "-pass"
                action_map[action] = ("boolean", False)
                actions.append(
                    LegalAction(action, "pass", None, "Pass / finish selection")
                )
            elif family == "piles":
                for value, label in ((True, "Pile 1"), (False, "Pile 2")):
                    option = token + ("-pile-one" if value else "-pile-two")
                    choice_map[option] = ("boolean", value)
                    options.append(ChoiceOption(option, label))
            elif family not in ("number", "amounts"):
                values = (
                    (
                        request.get("key_choices")
                        or {value: value for value in request.get("choices", ())}
                    )
                    if family in ("ability", "options")
                    else {
                        raw: "Select player"
                        if raw in self._player_ids
                        else "Select object"
                        for raw in (
                            tuple(
                                request.get("targets")
                                or [card["id"] for card in request.get("cards", ())]
                            )
                            + tuple(request.get("selected_targets") or ())
                        )
                    }
                )
                for raw, label in values.items():
                    option = request.setdefault("option_tokens", {}).setdefault(
                        raw, _id()
                    )
                    choice_map[option] = (
                        "string" if family == "options" else "object",
                        raw,
                    )
                    options.append(
                        ChoiceOption(
                            option,
                            self._public_text(label),
                            reverse.get(raw),
                            self._player_ids.get(raw),
                            raw in (request.get("selected_targets") or ()),
                        )
                    )
            decision = ChoiceRequest(
                token,
                player_id,
                family,
                self._public_text(request.get("message")),
                tuple(options),
                request.get("min") if family in ("number", "amounts") else None,
                request.get("max") if family in ("number", "amounts") else None,
                request.get("cancellable", False),
                tuple(
                    AmountConstraint(
                        self._public_text(row["message"]),
                        row["min"],
                        row["max"],
                        row.get("default"),
                    )
                    for row in request.get("amounts", ())
                ),
                request.get("can_finish", False),
            )
        combat = tuple(
            CombatAssignment(
                tuple(reverse[x] for x in group["attackers"] if x in reverse),
                tuple(reverse[x] for x in group["blockers"] if x in reverse),
                self._player_ids.get(group["defender"], reverse.get(group["defender"])),
                group["blocked"],
            )
            for group in view.get("combat", ())
        )
        return GameSnapshot(
            self.session_id,
            player_id,
            self._revision[player_id],
            self._status[player_id],
            view.get("turn"),
            view.get("phase"),
            view.get("step"),
            self._names.get(view.get("active_player")),
            self._names.get(view.get("priority_player")),
            tuple(players),
            tuple(objects),
            tuple(actions),
            decision,
            combat,
            result=self._results.get(player_id),
            commanders=tuple(commanders) if "commanders" in view else None,
            observations=view.get("_observations", ()),
            unsupported_fields=(
                (
                    "object_incarnations",
                    "physical_printing",
                    "commander_metadata",
                    "live_abilities",
                )
                if view.get("_metadata_unavailable")
                else ()
            ),
        )

    def poll(self, player_id, timeout=0):
        self._check(player_id)
        deadline = time.monotonic() + max(0, timeout)
        while True:
            self._pump()
            notifications = self._notifications[player_id]
            if notifications or time.monotonic() >= deadline:
                result = tuple(notifications)
                notifications.clear()
                return result
            time.sleep(0.005)

    def _submit(self, player, decision, identifier, options):
        command = _id()
        self._check(player)
        self._pump()
        pending = self._pending.get(player)
        if player in self._deferred_views:
            return CommandResult(command, "rejected", "SNAPSHOT_NOT_READY")
        if self._status[player] != "active":
            return CommandResult(command, "rejected", "SESSION_NOT_ACTIVE")
        if (
            pending is None
            or pending.get("token") != decision
            or identifier not in options.get(player, {})
        ):
            return CommandResult(command, "rejected", "STALE_OR_INVALID_DECISION")
        kind, value = options[player][identifier]
        self._pending.pop(player)
        self._refresh(player)
        try:
            reply = self._request(
                player,
                "respond",
                "response_sent",
                game_id=self._game_ids[player],
                decision_id=pending["decision_id"],
                kind=kind,
                value=value,
            )
            if not reply["accepted"]:
                self._fail(player, "ENGINE_RESPONSE_NOT_CONFIRMED")
            return CommandResult(
                command,
                "submitted" if reply["accepted"] else "uncertain",
                None if reply["accepted"] else "ENGINE_RESPONSE_NOT_CONFIRMED",
            )
        except AdapterError as error:
            if error.code in ("COMMAND_OUTCOME_UNCERTAIN", "ENGINE_UNAVAILABLE"):
                self._fail(player, error.code)
            return CommandResult(
                command,
                "uncertain"
                if error.code in ("COMMAND_OUTCOME_UNCERTAIN", "ENGINE_UNAVAILABLE")
                else "rejected",
                error.code,
            )

    def perform(self, player_id, decision_id, action_id):
        return self._submit(player_id, decision_id, action_id, self._actions)

    def choose(self, player_id, decision_id, option_id):
        return self._submit(player_id, decision_id, option_id, self._choices)

    def select_mana_source(self, player_id, decision_id, object_id):
        # XMage's payment request accepts a source click and verifies its usable
        # mana abilities. The client API does not enumerate all legal sources.
        snapshot = self.snapshot(player_id)
        if (
            snapshot.decision is None
            or snapshot.decision.decision_id != decision_id
            or snapshot.decision.family != "mana"
        ):
            return CommandResult(_id(), "rejected", "STALE_OR_INVALID_DECISION")
        raw = self._wire_objects[player_id].get(object_id)
        if raw is None:
            return CommandResult(_id(), "rejected", "STALE_OR_INVALID_OBJECT")
        option = _id()
        self._choices[player_id][option] = ("object", raw)
        return self._submit(player_id, decision_id, option, self._choices)

    def choose_number(self, player_id, decision_id, value):
        self._check(player_id)
        snapshot = self.snapshot(player_id)
        request = snapshot.decision
        if (
            request is None
            or request.decision_id != decision_id
            or request.family != "number"
        ):
            return CommandResult(_id(), "rejected", "STALE_OR_INVALID_DECISION")
        if type(value) is not int or not request.minimum <= value <= request.maximum:
            return CommandResult(_id(), "rejected", "AMOUNT_OUT_OF_RANGE")
        option = _id()
        self._choices[player_id][option] = ("integer", value)
        return self._submit(player_id, decision_id, option, self._choices)

    def choose_amounts(self, player_id, decision_id, values):
        request = self.snapshot(player_id).decision
        if (
            request is None
            or request.decision_id != decision_id
            or request.family != "amounts"
        ):
            return CommandResult(_id(), "rejected", "STALE_OR_INVALID_DECISION")
        if (
            len(values) != len(request.amounts)
            or any(
                type(value) is not int
                or not constraint.minimum <= value <= constraint.maximum
                for value, constraint in zip(values, request.amounts)
            )
            or not request.minimum <= sum(values) <= request.maximum
        ):
            return CommandResult(_id(), "rejected", "AMOUNT_OUT_OF_RANGE")
        option = _id()
        self._choices[player_id][option] = (
            "string",
            " ".join(str(value) for value in values),
        )
        return self._submit(player_id, decision_id, option, self._choices)

    def finish_selection(self, player_id, decision_id):
        request = self.snapshot(player_id).decision
        if (
            request is None
            or request.decision_id != decision_id
            or not request.can_finish
        ):
            return CommandResult(_id(), "rejected", "SELECTION_NOT_FINISHABLE")
        option = _id()
        self._choices[player_id][option] = ("boolean", False)
        return self._submit(player_id, decision_id, option, self._choices)

    def cancel(self, player_id, decision_id):
        request = self.snapshot(player_id).decision
        if (
            request is None
            or request.decision_id != decision_id
            or not request.cancellable
        ):
            return CommandResult(_id(), "rejected", "CANCELLATION_UNSUPPORTED")
        option = _id()
        self._choices[player_id][option] = (
            ("string", "") if request.family == "options" else ("boolean", False)
        )
        return self._submit(player_id, decision_id, option, self._choices)

    def concede(self, player_id):
        self._check(player_id)
        command = _id()
        if self._status[player_id] != "active":
            return CommandResult(command, "rejected", "SESSION_NOT_ACTIVE")
        try:
            self._request(player_id, "concede", "concede_sent")
            return CommandResult(command, "submitted")
        except AdapterError as error:
            return CommandResult(command, "uncertain", error.code)
