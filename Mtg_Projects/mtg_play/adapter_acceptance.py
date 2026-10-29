"""Real-engine acceptance through the public Manaforge GameSession only."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import time
from mtg_core.decks import DeckDocument, Deck, DeckEntry
from .adapter import AdapterError, LocalGameAdapter
from .contracts import GameSetup, MatchSeat


def fixture_deck() -> DeckDocument:
    return DeckDocument(
        deck=Deck(
            name="Adapter fixture",
            entries=[
                DeckEntry(
                    "forest",
                    "Forest",
                    30,
                    card_id="selected-forest",
                    set_code="M10",
                    collector_number="248",
                ),
                DeckEntry(
                    "memnite",
                    "Memnite",
                    30,
                    card_id="selected-memnite",
                    set_code="SOM",
                    collector_number="174",
                ),
            ],
        )
    )


def acceptance(adapter: LocalGameAdapter) -> dict:
    documents = (fixture_deck(), fixture_deck())
    originals = [document.to_dict() for document in documents]
    setup = GameSetup((MatchSeat("one", "Player One"), MatchSeat("two", "Player Two")))
    session = adapter.create_game(setup, documents)
    report = dict(
        opening_hands=[],
        mulligans=[],
        land=False,
        stack=False,
        resolved=False,
        selected_printing=False,
        stale_rejected=False,
        finished=[],
        hidden_hands=True,
    )
    conceded = False
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        for seat in setup.seats:
            session.poll(seat.seat_id)
            try:
                snapshot = session.snapshot(seat.seat_id)
            except AdapterError as error:
                if error.code == "SNAPSHOT_NOT_READY":
                    continue
                raise
            if snapshot.status == "failed":
                raise AdapterError("ACCEPTANCE_SESSION_FAILED")
            hand = [obj for obj in snapshot.objects if obj.zone == "hand"]
            if any(obj.owner_id != seat.seat_id for obj in hand):
                raise AdapterError("OPPONENT_HAND_EXPOSED")
            if len(hand) == 7 and seat.seat_id not in report["opening_hands"]:
                report["opening_hands"].append(seat.seat_id)
                if len({obj.object_id for obj in hand}) != 7:
                    raise AdapterError("DUPLICATE_OBJECT_REFERENCES")
            for obj in snapshot.objects:
                name = obj.characteristics.name if obj.characteristics else None
                report["land"] |= name == "Forest" and obj.zone == "battlefield"
                report["stack"] |= name == "Memnite" and obj.zone == "stack"
                report["resolved"] |= name == "Memnite" and obj.zone == "battlefield"
                report["selected_printing"] |= (
                    obj.card_identity is not None
                    and obj.card_identity.printing_id
                    in ("selected-forest", "selected-memnite")
                )
            if snapshot.status == "finished" and seat.seat_id not in report["finished"]:
                report["finished"].append(seat.seat_id)
            decision = snapshot.decision
            if decision is None:
                continue
            if decision.family == "boolean" and "mulligan" in decision.prompt.lower():
                option = next(
                    option for option in decision.options if option.label == "No"
                )
                result = session.choose(
                    seat.seat_id, decision.decision_id, option.option_id
                )
                report["mulligans"].append(seat.seat_id)
                if not report["stale_rejected"]:
                    stale = session.choose(
                        seat.seat_id, decision.decision_id, option.option_id
                    )
                    report["stale_rejected"] = stale.outcome == "rejected"
            elif (
                decision.family == "target"
                and decision.prompt == "Select a starting player"
            ):
                result = session.choose(
                    seat.seat_id, decision.decision_id, decision.options[0].option_id
                )
            elif decision.family == "ability":
                result = session.choose(
                    seat.seat_id, decision.decision_id, decision.options[0].option_id
                )
            elif decision.family == "selection":
                preferred = (
                    ("play_land", "cast_spell")
                    if not report["land"]
                    else ("cast_spell",)
                )
                selected = next(
                    (
                        action
                        for kind in preferred
                        for action in snapshot.actions
                        if action.kind == kind
                    ),
                    next(
                        action for action in snapshot.actions if action.kind == "pass"
                    ),
                )
                result = session.perform(
                    seat.seat_id, decision.decision_id, selected.action_id
                )
            else:
                raise AdapterError("UNSUPPORTED_ACCEPTANCE_PROMPT")
            if result.outcome != "submitted":
                raise AdapterError(result.code or "ACCEPTANCE_COMMAND_FAILED")
        if report["land"] and report["stack"] and report["resolved"] and not conceded:
            session.concede("two")
            conceded = True
        if len(report["finished"]) == 2:
            if (
                len(set(report["mulligans"])) != 2
                or len(report["opening_hands"]) != 2
                or not report["stale_rejected"]
                or not report["selected_printing"]
            ):
                raise AdapterError("ACCEPTANCE_EVIDENCE_MISSING")
            if [document.to_dict() for document in documents] != originals:
                raise AdapterError("SOURCE_DECK_CHANGED")
            return report
        time.sleep(0.005)
    raise AdapterError("ACCEPTANCE_TIMEOUT")


def combat_acceptance(adapter: LocalGameAdapter) -> dict:
    document = fixture_deck()
    for entry in document.deck.entries:
        entry.quantity = 20
    document.deck.entries.append(
        DeckEntry("growth", "Giant Growth", 10, card_id="selected-growth")
    )
    document.deck.entries.append(
        DeckEntry("snakeform", "Snakeform", 10, card_id="selected-snakeform")
    )
    setup = GameSetup((MatchSeat("one", "Player One"), MatchSeat("two", "Player Two")))
    session = adapter.create_game(setup, (document, fixture_deck()))
    report = dict(
        spell_resolved=False,
        boosted=False,
        expired=False,
        type_color_changed=False,
        type_color_expired=False,
        continuous_identity_preserved=False,
        battlefield_printing_preserved=False,
        combat=False,
        combat_damage=False,
        finished=[],
        results={},
    )
    conceded = False
    creature_reference = None
    creature_requested = False
    boosted_turn = None
    changed_turn = None
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        for seat in setup.seats:
            session.poll(seat.seat_id)
            try:
                view = session.snapshot(seat.seat_id)
            except AdapterError as error:
                if error.code == "SNAPSHOT_NOT_READY":
                    continue
                raise
            if view.status == "failed":
                raise AdapterError("COMBAT_SESSION_FAILED")
            creatures = [
                obj
                for obj in view.objects
                if obj.zone == "battlefield"
                and obj.controller_id == "one"
                and obj.characteristics
                and obj.characteristics.name == "Memnite"
            ]
            if creatures and seat.seat_id == "one" and view.status == "active":
                if len(creatures) != 1:
                    raise AdapterError("COMBAT_FIXTURE_REQUIRES_ONE_CREATURE")
                report["spell_resolved"] = True
                if creature_reference is None:
                    creature_reference = creatures[0].object_id
                if creatures[0].object_id != creature_reference:
                    raise AdapterError("CONTINUOUS_EFFECT_CHANGED_OBJECT_ID")
                if (
                    creatures[0].card_identity is None
                    or creatures[0].card_identity.printing_id != "selected-memnite"
                ):
                    raise AdapterError("BATTLEFIELD_PRINTING_ASSOCIATION_LOST")
                report["continuous_identity_preserved"] = True
                report["battlefield_printing_preserved"] = True
                if any(
                    obj.characteristics.power == "4"
                    and obj.characteristics.toughness == "4"
                    for obj in creatures
                ):
                    report["boosted"] = True
                    boosted_turn = view.turn
                if boosted_turn is not None and (
                    view.turn > boosted_turn or view.step == "CLEANUP"
                ):
                    report["expired"] |= any(
                        obj.characteristics.power == "1"
                        and obj.characteristics.toughness == "1"
                        for obj in creatures
                    )
                if any(
                    "Snake" in (obj.characteristics.type_line or "")
                    and obj.characteristics.color == "Green"
                    for obj in creatures
                ):
                    report["type_color_changed"] = True
                    changed_turn = view.turn
                if changed_turn is not None and (
                    view.turn > changed_turn or view.step == "CLEANUP"
                ):
                    report["type_color_expired"] |= any(
                        "Construct" in (obj.characteristics.type_line or "")
                        and obj.characteristics.color == "Colorless"
                        for obj in creatures
                    )
            report["combat"] |= any(group.attackers for group in view.combat)
            report["combat_damage"] |= any(
                player.player_id == "two" and player.life < 20
                for player in view.players
            )
            if view.status == "finished" and seat.seat_id not in report["finished"]:
                report["finished"].append(seat.seat_id)
            if view.result is not None:
                report["results"][seat.seat_id] = view.result
            decision = view.decision
            if decision is None:
                continue
            if decision.family == "boolean" and "mulligan" in decision.prompt.lower():
                option = next(
                    option for option in decision.options if option.label == "No"
                )
                result = session.choose(
                    seat.seat_id, decision.decision_id, option.option_id
                )
            elif decision.family == "target":
                if decision.prompt == "Select a starting player":
                    option = next(
                        option
                        for option in decision.options
                        if option.player_id == "one"
                    )
                else:
                    references = {obj.object_id for obj in creatures}
                    option = next(
                        (
                            option
                            for option in decision.options
                            if option.object_id in references
                        ),
                        None,
                    )
                    if option is None and "discard" in decision.prompt.lower():
                        hand = {
                            obj.object_id for obj in view.objects if obj.zone == "hand"
                        }
                        option = next(
                            (
                                option
                                for option in decision.options
                                if option.object_id in hand
                            ),
                            None,
                        )
                    if option is None and view.step == "DECLARE_ATTACKERS":
                        option = next(
                            (
                                option
                                for option in decision.options
                                if option.player_id == "two"
                            ),
                            None,
                        )
                    if option is None:
                        raise AdapterError(
                            "UNSUPPORTED_COMBAT_TARGET: "
                            + str((view.step, len(decision.options), len(creatures)))
                        )
                result = session.choose(
                    seat.seat_id, decision.decision_id, option.option_id
                )
            elif decision.family == "ability":
                result = session.choose(
                    seat.seat_id, decision.decision_id, decision.options[0].option_id
                )
            elif decision.family == "mana":
                source = next(
                    (
                        obj
                        for obj in view.objects
                        if obj.zone == "battlefield"
                        and obj.controller_id == seat.seat_id
                        and obj.characteristics
                        and obj.characteristics.name == "Forest"
                        and obj.tapped is False
                    ),
                    None,
                )
                if source is None:
                    raise AdapterError("NO_SCENARIO_MANA_SOURCE")
                result = session.select_mana_source(
                    seat.seat_id, decision.decision_id, source.object_id
                )
            elif decision.family == "selection":
                selected = next(
                    action for action in view.actions if action.kind == "pass"
                )
                if seat.seat_id == "one" and not any(
                    obj.zone == "stack" for obj in view.objects
                ):
                    attacking = {
                        reference
                        for group in view.combat
                        for reference in group.attackers
                    }
                    preferred = [
                        action
                        for action in view.actions
                        if (action.kind == "play_land")
                        or (
                            action.kind == "cast_spell"
                            and action.label == "Memnite"
                            and not creature_requested
                        )
                        or (
                            action.kind == "cast_spell"
                            and action.label == "Giant Growth"
                            and creatures
                            and not report["boosted"]
                        )
                        or (
                            action.kind == "cast_spell"
                            and action.label == "Snakeform"
                            and creatures
                            and report["expired"]
                            and not report["type_color_changed"]
                        )
                        or (
                            action.kind == "declare_attacker"
                            and action.object_id not in attacking
                        )
                        or (action.kind == "pay_mana")
                    ]
                    if preferred:
                        selected = preferred[0]
                    if selected.kind == "cast_spell" and selected.label == "Memnite":
                        creature_requested = True
                result = session.perform(
                    seat.seat_id, decision.decision_id, selected.action_id
                )
            else:
                raise AdapterError("UNSUPPORTED_COMBAT_PROMPT")
            if result.outcome != "submitted":
                raise AdapterError(result.code or "COMBAT_COMMAND_FAILED")
        if (
            all(
                report[key]
                for key in (
                    "boosted",
                    "expired",
                    "type_color_changed",
                    "type_color_expired",
                    "combat",
                    "combat_damage",
                )
            )
            and not conceded
        ):
            session.concede("two")
            conceded = True
        if len(report["finished"]) == 2 and len(report["results"]) == 2:
            return report
        time.sleep(0.005)
    raise AdapterError("COMBAT_ACCEPTANCE_TIMEOUT: " + json.dumps(report))


def commander_acceptance(adapter: LocalGameAdapter, seats: int) -> dict:
    document = DeckDocument(
        deck=Deck(
            name="Commander fixture",
            entries=[
                DeckEntry("plains", "Plains", 99, card_id="selected-plains"),
                DeckEntry(
                    "commander",
                    "Isamaru, Hound of Konda",
                    1,
                    section="commander",
                    card_id="selected-commander",
                ),
            ],
            commander_entry_ids=["commander"],
        )
    )
    setup = GameSetup(
        tuple(
            MatchSeat(str(index), "Player " + str(index + 1)) for index in range(seats)
        ),
        format="commander",
    )
    session = adapter.create_game(setup, tuple(document for _ in setup.seats))
    report = dict(
        seats=seats,
        started=[],
        command_zones=[],
        opening_hands=[],
        finished=[],
        results={},
    )
    conceded = set()
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        for seat in setup.seats:
            session.poll(seat.seat_id)
            try:
                view = session.snapshot(seat.seat_id)
            except AdapterError as error:
                if error.code == "SNAPSHOT_NOT_READY":
                    continue
                raise
            if view.status == "failed":
                raise AdapterError("COMMANDER_SESSION_FAILED")
            if view.status == "active" and seat.seat_id not in report["started"]:
                report["started"].append(seat.seat_id)
            commanders = [
                obj
                for obj in view.objects
                if obj.zone == "command"
                and obj.characteristics
                and obj.characteristics.name == "Isamaru, Hound of Konda"
            ]
            if len(commanders) == seats and seat.seat_id not in report["command_zones"]:
                report["command_zones"].append(seat.seat_id)
            if (
                len([obj for obj in view.objects if obj.zone == "hand"]) == 7
                and seat.seat_id not in report["opening_hands"]
            ):
                report["opening_hands"].append(seat.seat_id)
            if view.status == "finished" and seat.seat_id not in report["finished"]:
                report["finished"].append(seat.seat_id)
            if view.result is not None:
                report["results"][seat.seat_id] = view.result
            decision = view.decision
            if decision is None or seat.seat_id in conceded:
                continue
            if decision.family == "boolean" and "mulligan" in decision.prompt.lower():
                result = session.choose(
                    seat.seat_id,
                    decision.decision_id,
                    next(
                        option for option in decision.options if option.label == "No"
                    ).option_id,
                )
            elif (
                decision.family == "target"
                and decision.prompt == "Select a starting player"
            ):
                result = session.choose(
                    seat.seat_id, decision.decision_id, decision.options[0].option_id
                )
            elif decision.family == "selection":
                result = session.perform(
                    seat.seat_id,
                    decision.decision_id,
                    next(
                        action for action in view.actions if action.kind == "pass"
                    ).action_id,
                )
            else:
                raise AdapterError("UNSUPPORTED_COMMANDER_PROMPT: " + decision.family)
            if result.outcome != "submitted":
                raise AdapterError(result.code or "COMMANDER_COMMAND_FAILED")
        if (
            len(report["command_zones"]) == seats
            and len(report["opening_hands"]) == seats
        ):
            for seat in setup.seats[1:]:
                if seat.seat_id not in conceded:
                    session.concede(seat.seat_id)
                    conceded.add(seat.seat_id)
        if len(report["finished"]) == seats and len(report["results"]) == seats:
            return report
        time.sleep(0.005)
    raise AdapterError("COMMANDER_ACCEPTANCE_TIMEOUT: " + json.dumps(report))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--xmage-root", type=Path)
    parser.add_argument("--jdk-path", type=Path)
    parser.add_argument(
        "--scenario",
        choices=(
            "basic",
            "combat",
            "commander",
            "identity",
            "commander-play",
            "visibility",
            "number",
            "modes",
            "sacrifice",
            "distribution",
            "triggers",
            "copy",
            "transform",
            "partners",
            "interruption",
            "blockers",
            "cancellation",
            "string-choice",
            "background",
            "piles",
            "companion",
            "real-decks",
            "complex-board",
        ),
        default="basic",
    )
    parser.add_argument("--seats", type=int, default=2)
    args = parser.parse_args()
    from . import acceptance_scenarios
    from . import real_deck_acceptance
    from .decks import DeckTranslationError
    from .diagnostics import diagnostic_category

    options = {}
    if args.xmage_root is not None:
        options["bundle"] = args.xmage_root
    if args.jdk_path is not None:
        options["jdk"] = args.jdk_path
    scenarios = {
        "basic": acceptance,
        "combat": combat_acceptance,
        "commander": lambda adapter: commander_acceptance(adapter, args.seats),
        "identity": acceptance_scenarios.identity,
        "commander-play": acceptance_scenarios.commander_play,
        "visibility": acceptance_scenarios.visibility,
        "number": lambda adapter: acceptance_scenarios.decisions(adapter, "number"),
        "modes": lambda adapter: acceptance_scenarios.decisions(adapter, "modes"),
        "sacrifice": lambda adapter: acceptance_scenarios.decisions(
            adapter, "sacrifice"
        ),
        "distribution": acceptance_scenarios.distribution,
        "triggers": acceptance_scenarios.triggers,
        "copy": acceptance_scenarios.copy_identity,
        "transform": acceptance_scenarios.transformation,
        "partners": acceptance_scenarios.partners,
        "background": lambda adapter: acceptance_scenarios.partners(
            adapter, background=True
        ),
        "interruption": acceptance_scenarios.interruption,
        "blockers": acceptance_scenarios.blockers,
        "cancellation": acceptance_scenarios.cancellation,
        "string-choice": acceptance_scenarios.string_choice,
        "piles": acceptance_scenarios.piles,
        "companion": acceptance_scenarios.companion,
        "real-decks": real_deck_acceptance.real_decks,
        "complex-board": real_deck_acceptance.complex_board,
    }
    adapter = LocalGameAdapter(**options)
    result = dict(scenario=args.scenario, success=False)
    try:
        with adapter:
            result["compatibility"] = adapter.compatibility.to_dict()
            result["gameplay"] = scenarios[args.scenario](adapter)
        result["success"] = True
    except DeckTranslationError as error:
        # Fixture entry IDs only; never export a source deck or raw JVM log.
        result["issues"] = [
            dict(code=i.code, category=i.category, entry_id=i.entry_id)
            for i in error.issues
        ]
    except AdapterError as error:
        code = error.code.split(":", 1)[0]
        result["error"] = dict(code=code, category=diagnostic_category(code))
    finally:
        if adapter.result is not None:
            result["runtime"] = adapter.result.to_dict()
    payload = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    if not result["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
