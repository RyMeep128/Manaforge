"""Additional real-engine scenarios; all game interaction uses the public adapter."""

from __future__ import annotations
import time
from mtg_core.decks import Deck, DeckDocument, DeckEntry
from .adapter import AdapterError
from .contracts import GameSetup, MatchSeat


def deck(*cards):
    return DeckDocument(
        deck=Deck(
            name="Acceptance fixture",
            entries=[
                DeckEntry(name, name, quantity, card_id="selected-" + name)
                for name, quantity in cards
            ],
        )
    )


def partners(adapter, background=False):
    document = deck(("Forest" if background else "Plains", 98))
    names = (
        ("Wilson, Refined Grizzly", "Raised by Giants")
        if background
        else ("Rograkh, Son of Rohgahh", "Yoshimaru, Ever Faithful")
    )
    for index, name in enumerate(names):
        document.deck.entries.append(
            DeckEntry(
                str(index), name, 1, section="commander", card_id="selected-" + name
            )
        )
    document.deck.commander_entry_ids = ["0", "1"]
    report = dict(
        multiple_commanders=False, distinct_designations=False, printings=False
    )

    def inspect(view):
        commanders = [c for c in view.commanders or () if c.owner_id == "one"]
        if {c.name for c in commanders} == set(names):
            report["multiple_commanders"] = True
            report["distinct_designations"] = (
                len({c.commander_id for c in commanders}) == 2
            )
            report["printings"] = all(
                c.card_identity and c.card_identity.printing_id == "selected-" + c.name
                for c in commanders
            )
        return all(report.values())

    report.update(
        drive(
            adapter,
            (document, document),
            inspect,
            lambda view: None,
            setup=GameSetup(
                (MatchSeat("one", "One"), MatchSeat("two", "Two")), format="commander"
            ),
        )
    )
    return report


def interruption(adapter):
    game = adapter.create_game(
        GameSetup((MatchSeat("one", "One"), MatchSeat("two", "Two"))),
        (deck(("Plains", 60)), deck(("Island", 60))),
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        for player in ("one", "two"):
            game.poll(player)
            try:
                view = game.snapshot(player)
            except AdapterError as error:
                if error.code == "SNAPSHOT_NOT_READY":
                    continue
                raise
            if view.decision:
                adapter.close()
                try:
                    game.snapshot(player)
                except AdapterError as error:
                    return dict(
                        pending_choice=True,
                        closed_rejected=error.code == "SESSION_CLOSED",
                    )
                raise AdapterError("CLOSED_SESSION_ACCEPTED")
        time.sleep(0.005)
    raise AdapterError("INTERRUPTION_NO_PENDING_CHOICE")


def blockers(adapter):
    report = dict(
        attack_submitted=False,
        block_submitted=False,
        combat_link=False,
        both_died=False,
    )
    summoned = set()

    def inspect(view):
        for obj in view.objects:
            if (
                obj.zone == "battlefield"
                and obj.characteristics
                and obj.characteristics.name == "Memnite"
            ):
                summoned.add(obj.owner_id)
        report["combat_link"] |= any(
            group.attackers and group.blockers and group.blocked
            for group in view.combat
        )
        dead = {
            obj.owner_id
            for obj in view.objects
            if obj.zone == "graveyard"
            and obj.characteristics
            and obj.characteristics.name == "Memnite"
        }
        report["both_died"] |= dead == {"one", "two"}
        return all(report.values())

    def select(view):
        for action in view.actions:
            if (
                action.kind == "cast_spell"
                and action.label == "Memnite"
                and view.viewer_id not in summoned
            ):
                return action
            if (
                action.kind == "declare_attacker"
                and view.viewer_id == "one"
                and summoned == {"one", "two"}
                and not report["attack_submitted"]
            ):
                report["attack_submitted"] = True
                return action
            if (
                action.kind == "declare_blocker"
                and view.viewer_id == "two"
                and not report["block_submitted"]
            ):
                report["block_submitted"] = True
                return action
        return None

    def respond(game, view):
        request = view.decision
        if request.family == "target" and view.step == "DECLARE_BLOCKERS":
            attackers = {
                obj.object_id
                for obj in view.objects
                if obj.zone == "battlefield" and obj.controller_id == "one"
            }
            option = next(
                (option for option in request.options if option.object_id in attackers),
                None,
            )
            if option:
                return game.choose(
                    view.viewer_id, request.decision_id, option.option_id
                )
        return None

    document = deck(("Memnite", 60))
    report.update(
        drive(adapter, (document, document), inspect, select, decision_handler=respond)
    )
    return report


def cancellation(adapter):
    report = dict(
        cancellable=False,
        cancelled=False,
        returned_to_hand=False,
        stale_rejected=False,
        recast_resolved=False,
    )
    attempted = False

    def inspect(view):
        if view.viewer_id != "one":
            return False
        if report["cancelled"]:
            report["returned_to_hand"] |= any(
                obj.zone == "hand"
                and obj.characteristics
                and obj.characteristics.name == "Walking Ballista"
                for obj in view.objects
            )
            report["recast_resolved"] |= any(
                obj.zone == "battlefield"
                and obj.characteristics
                and obj.characteristics.name == "Walking Ballista"
                and obj.characteristics.power == "1"
                for obj in view.objects
            )
        return all(report.values())

    def select(view):
        nonlocal attempted
        if view.viewer_id != "one":
            return None
        lands = sum(
            obj.zone == "battlefield"
            and obj.characteristics is not None
            and obj.characteristics.name == "Forest"
            for obj in view.objects
        )
        for action in view.actions:
            if action.kind == "play_land":
                return action
            if (
                action.kind == "cast_spell"
                and action.label == "Walking Ballista"
                and lands >= 2
                and (
                    not attempted
                    or report["returned_to_hand"]
                    and not report["recast_resolved"]
                )
            ):
                attempted = True
                return action
        return None

    def respond(game, view):
        request = view.decision
        if request.family == "number":
            return game.choose_number(view.viewer_id, request.decision_id, 1)
        if request.family == "mana" and not report["cancelled"]:
            report["cancellable"] = request.cancellable
            result = game.cancel(view.viewer_id, request.decision_id)
            report["cancelled"] = result.outcome == "submitted"
            report["stale_rejected"] = (
                game.cancel(view.viewer_id, request.decision_id).outcome == "rejected"
            )
            return result
        return None

    report.update(
        drive(
            adapter,
            (deck(("Forest", 30), ("Walking Ballista", 30)), deck(("Plains", 60))),
            inspect,
            select,
            decision_handler=respond,
        )
    )
    return report


def string_choice(adapter):
    report = dict(choice_seen=False, resolved=False)
    requested = False

    def inspect(view):
        report["resolved"] |= report["choice_seen"] and any(
            obj.zone == "battlefield"
            and obj.characteristics
            and obj.characteristics.name == "Utopia Sprawl"
            and obj.attached_to is not None
            for obj in view.objects
        )
        return all(report.values())

    def select(view):
        nonlocal requested
        if view.viewer_id != "one":
            return None
        for action in view.actions:
            if action.kind == "play_land":
                return action
            if (
                action.kind == "cast_spell"
                and action.label == "Utopia Sprawl"
                and not requested
            ):
                requested = True
                return action
        return None

    def respond(game, view):
        request = view.decision
        if request.family == "options":
            option = next(
                (
                    option
                    for option in request.options
                    if option.label.lower() == "blue"
                ),
                None,
            )
            if option is None:
                raise AdapterError("COLOR_CHOICE_MISSING")
            report["choice_seen"] = True
            return game.choose(view.viewer_id, request.decision_id, option.option_id)
        if (
            request.family == "target"
            and "starting player" not in request.prompt.lower()
        ):
            forests = {
                obj.object_id
                for obj in view.objects
                if obj.zone == "battlefield"
                and obj.characteristics
                and obj.characteristics.name == "Forest"
            }
            option = next(
                (option for option in request.options if option.object_id in forests),
                None,
            )
            if option:
                return game.choose(
                    view.viewer_id, request.decision_id, option.option_id
                )
        return None

    report.update(
        drive(
            adapter,
            (deck(("Forest", 30), ("Utopia Sprawl", 30)), deck(("Plains", 60))),
            inspect,
            select,
            decision_handler=respond,
        )
    )
    return report


def piles(adapter):
    report = dict(
        split_selection=False,
        piles_visible=False,
        choice_submitted=False,
        resolved=False,
    )
    requested = False

    def inspect(view):
        report["resolved"] |= report["choice_submitted"] and any(
            obj.zone == "graveyard"
            and obj.characteristics
            and obj.characteristics.name == "Fact or Fiction"
            for obj in view.objects
        )
        return all(report.values())

    def select(view):
        nonlocal requested
        if view.viewer_id != "one":
            return None
        for action in view.actions:
            if action.kind == "play_land":
                return action
            if (
                action.kind == "cast_spell"
                and action.label == "Fact or Fiction"
                and not requested
            ):
                requested = True
                return action
        return None

    def respond(game, view):
        request = view.decision
        if request.family == "piles":
            first = [obj for obj in view.objects if obj.zone == "decision"]
            second = [obj for obj in view.objects if obj.zone == "decision_pile_2"]
            report["piles_visible"] = (
                bool(first and second) and len(first) + len(second) == 5
            )
            result = game.choose(
                view.viewer_id, request.decision_id, request.options[0].option_id
            )
            report["choice_submitted"] = result.outcome == "submitted"
            return result
        if request.family == "target" and "pile" in request.prompt.lower():
            report["split_selection"] = True
            if (
                sum(option.selected for option in request.options) >= 2
                and request.can_finish
            ):
                return game.finish_selection(view.viewer_id, request.decision_id)
            option = next(
                (
                    option
                    for option in request.options
                    if not option.selected and option.object_id
                ),
                None,
            )
            if option:
                return game.choose(
                    view.viewer_id, request.decision_id, option.option_id
                )
        return None

    report.update(
        drive(
            adapter,
            (deck(("Island", 30), ("Fact or Fiction", 30)), deck(("Plains", 60))),
            inspect,
            select,
            decision_handler=respond,
        )
    )
    return report


def companion(adapter):
    document = deck(("Plains", 99))
    document.deck.entries.extend(
        (
            DeckEntry(
                "commander", "Kenrith, the Returned King", 1, section="commander"
            ),
            DeckEntry("companion", "Jegantha, the Wellspring", 1, section="sideboard"),
        )
    )
    document.deck.commander_entry_ids = ["commander"]
    report = dict(pregame_choice=False, companion_visible=False)

    def inspect(view):
        report["companion_visible"] |= any(
            card.source == "companion" and card.name == "Jegantha, the Wellspring"
            for card in view.observations
        )
        return all(report.values())

    def respond(game, view):
        request = view.decision
        if request.family == "boolean" and "companion" in request.prompt.lower():
            report["pregame_choice"] = True
            option = next(option for option in request.options if option.label == "Yes")
            return game.choose(view.viewer_id, request.decision_id, option.option_id)
        return None

    report.update(
        drive(
            adapter,
            (document, document),
            inspect,
            lambda view: None,
            setup=GameSetup(
                (MatchSeat("one", "One"), MatchSeat("two", "Two")), format="commander"
            ),
            decision_handler=respond,
        )
    )
    return report


def drive(
    adapter,
    documents,
    inspect,
    select,
    *,
    setup=None,
    timeout=120,
    event_handler=None,
    decision_handler=None,
    performance=None,
    allow_stack_actions=False,
):
    setup = setup or GameSetup((MatchSeat("one", "One"), MatchSeat("two", "Two")))
    game = adapter.create_game(setup, documents)
    finished, results, conceded = set(), {}, False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for seat in setup.seats:
            events = game.poll(seat.seat_id)
            if event_handler is not None:
                event_handler(seat.seat_id, events)
            if any(event.kind == "session_failed" for event in events):
                raise AdapterError(
                    next(
                        event.code for event in events if event.kind == "session_failed"
                    )
                )
            try:
                view = game.snapshot(seat.seat_id)
            except AdapterError as error:
                if error.code == "SNAPSHOT_NOT_READY":
                    continue
                raise
            if view.status == "finished":
                finished.add(seat.seat_id)
                if view.result is not None:
                    results[seat.seat_id] = view.result
                continue
            if view.status == "active" and inspect(view) and not conceded:
                for other in setup.seats[1:]:
                    result = game.concede(other.seat_id)
                    if result.outcome != "submitted":
                        raise AdapterError(result.code or "CONCESSION_FAILED")
                conceded = True
                continue
            if view.decision is None or (conceded and seat != setup.seats[0]):
                continue
            request = view.decision
            handled = (
                decision_handler(game, view) if decision_handler is not None else None
            )
            if handled is not None:
                if handled.outcome != "submitted":
                    raise AdapterError(handled.code or "SCENARIO_RESPONSE_FAILED")
                continue
            if request.family == "boolean" and "mulligan" in request.prompt.lower():
                option = next(
                    option for option in request.options if option.label == "No"
                )
                result = game.choose(
                    seat.seat_id, request.decision_id, option.option_id
                )
            elif (
                request.family == "target"
                and request.prompt == "Select a starting player"
            ):
                option = next(
                    option
                    for option in request.options
                    if option.player_id == setup.seats[0].seat_id
                )
                result = game.choose(
                    seat.seat_id, request.decision_id, option.option_id
                )
            elif request.family == "ability":
                # Explicit fixture policy: choose the first engine-offered ability/order.
                result = game.choose(
                    seat.seat_id, request.decision_id, request.options[0].option_id
                )
            elif request.family == "mana":
                source = next(
                    (
                        obj
                        for obj in view.objects
                        if obj.zone == "battlefield"
                        and obj.controller_id == seat.seat_id
                        and obj.characteristics
                        and obj.characteristics.name
                        in ("Plains", "Island", "Swamp", "Mountain", "Forest")
                        and obj.tapped is False
                    ),
                    None,
                )
                if source is None:
                    raise AdapterError("SCENARIO_MANA_SOURCE_MISSING")
                result = game.select_mana_source(
                    seat.seat_id, request.decision_id, source.object_id
                )
            elif request.family == "selection":
                # Fixture policy: resolve the current stack before starting another
                # operation. Otherwise zero-cost duplicates can all be cast before
                # an inspector has seen the first permanent resolve.
                action = (
                    None
                    if conceded
                    or (
                        not allow_stack_actions
                        and any(obj.zone == "stack" for obj in view.objects)
                    )
                    else select(view)
                )
                if action is None:
                    action = next(
                        action for action in view.actions if action.kind == "pass"
                    )
                result = game.perform(
                    seat.seat_id, request.decision_id, action.action_id
                )
            elif request.family == "target":
                # Scripted target for these fixtures, never a policy in the adapter.
                hand = {obj.object_id for obj in view.objects if obj.zone == "hand"}
                targets = {
                    obj.object_id
                    for obj in view.objects
                    if obj.zone == "battlefield"
                    and obj.controller_id == seat.seat_id
                    and obj.characteristics
                    and obj.characteristics.name == "Memnite"
                }
                candidates = hand if "discard" in request.prompt.lower() else targets
                option = next(
                    (
                        option
                        for option in request.options
                        if option.object_id in candidates
                    ),
                    None,
                )
                if option is None and (
                    view.step == "DECLARE_ATTACKERS"
                    or "player" in request.prompt.lower()
                ):
                    option = next(
                        (
                            option
                            for option in request.options
                            if option.player_id != seat.seat_id
                        ),
                        None,
                    )
                if option is None:
                    raise AdapterError("SCENARIO_TARGET_UNSUPPORTED")
                result = game.choose(
                    seat.seat_id, request.decision_id, option.option_id
                )
            else:
                # Preserve only the bounded decision family in sanitized reports;
                # do not include private prompt text.
                family = (
                    request.family
                    if request.family
                    in {
                        "boolean",
                        "mana",
                        "options",
                        "number",
                        "amounts",
                        "piles",
                        "selection",
                        "target",
                        "ability",
                    }
                    else "unknown"
                )
                raise AdapterError("SCENARIO_DECISION_UNSUPPORTED_" + family.upper())
            if result.outcome != "submitted":
                raise AdapterError(result.code or "SCENARIO_RESPONSE_FAILED")
        if len(finished) == len(setup.seats) and len(results) == len(setup.seats):
            if not conceded:
                raise AdapterError("SCENARIO_ENDED_BEFORE_EVIDENCE")
            if performance is not None:
                performance.update(game.performance_report())
            return dict(results=results, engine_result=True)
        time.sleep(0.005)
    raise AdapterError("SCENARIO_TIMEOUT")


def identity(adapter):
    report = dict(
        original_seen=False,
        blink_requested=False,
        blink_on_stack=False,
        new_identity=False,
        printing_preserved=False,
    )
    reference = None

    def inspect(view):
        nonlocal reference
        if view.viewer_id != "one":
            return False
        report["blink_on_stack"] |= any(
            obj.zone == "stack"
            and obj.characteristics
            and obj.characteristics.name == "Cloudshift"
            for obj in view.objects
        )
        creature = next(
            (
                obj
                for obj in view.objects
                if obj.zone == "battlefield"
                and obj.characteristics
                and obj.characteristics.name == "Memnite"
            ),
            None,
        )
        if creature:
            if reference is None:
                reference = creature.object_id
                report["original_seen"] = True
            elif creature.object_id != reference:
                if not report["blink_on_stack"]:
                    raise AdapterError("IDENTITY_CHANGED_WITHOUT_BLINK")
                report["new_identity"] = True
                report["printing_preserved"] = (
                    creature.card_identity is not None
                    and creature.card_identity.printing_id == "selected-Memnite"
                )
        return report["new_identity"] and report["printing_preserved"]

    def select(view):
        if view.viewer_id != "one":
            return None
        for action in view.actions:
            if action.kind == "play_land":
                return action
            if (
                action.kind == "cast_spell"
                and action.label == "Memnite"
                and not report["original_seen"]
            ):
                return action
            if (
                action.kind == "cast_spell"
                and action.label == "Cloudshift"
                and report["original_seen"]
                and not report["blink_requested"]
            ):
                report["blink_requested"] = True
                return action
        return None

    report.update(
        drive(
            adapter,
            (
                deck(("Plains", 20), ("Memnite", 20), ("Cloudshift", 20)),
                deck(("Plains", 60)),
            ),
            inspect,
            select,
        )
    )
    return report


def commander_play(adapter):
    document = deck(("Plains", 99))
    document.deck.entries.append(
        DeckEntry(
            "commander",
            "Isamaru, Hound of Konda",
            1,
            section="commander",
            card_id="selected-commander",
        )
    )
    document.deck.commander_entry_ids = ["commander"]
    setup = GameSetup(
        (MatchSeat("one", "One"), MatchSeat("two", "Two")), format="commander"
    )
    report = dict(
        command_zone_plays=False,
        commander_damage=False,
        engine_tax=False,
        stable_designation=True,
        printing_preserved=False,
    )
    reference = None

    def inspect(view):
        nonlocal reference
        if view.viewer_id != "one":
            return False
        current = next(
            (
                commander
                for commander in view.commanders or ()
                if commander.owner_id == "one"
            ),
            None,
        )
        if current:
            if reference is None:
                reference = current.commander_id
            elif reference != current.commander_id:
                raise AdapterError("COMMANDER_DESIGNATION_ID_CHANGED")
            report["command_zone_plays"] |= current.command_zone_plays == 1
            report["engine_tax"] |= (
                current.command_zone_plays == 1
                and current.additional_cast_cost == "{2}"
            )
            report["commander_damage"] |= any(
                player == "two" and damage >= 2
                for player, damage in current.damage_dealt
            )
            report["printing_preserved"] |= (
                current.card_identity is not None
                and current.card_identity.printing_id == "selected-commander"
            )
        return all(report.values())

    def select(view):
        if view.viewer_id != "one":
            return None
        attacking = {
            reference for group in view.combat for reference in group.attackers
        }
        return next(
            (
                action
                for action in view.actions
                if action.kind == "play_land"
                or action.kind == "cast_spell"
                and action.label == "Isamaru, Hound of Konda"
                or action.kind == "declare_attacker"
                and action.object_id not in attacking
            ),
            None,
        )

    report.update(drive(adapter, (document, document), inspect, select, setup=setup))
    return report


def visibility(adapter):
    report = dict(
        private_peek=False,
        opponent_excluded=True,
        concealed=False,
        observation_refs_opaque=True,
    )
    requested = False

    def events(player, events):
        for event in events:
            looked = [card for card in event.observations if card.source == "looked_at"]
            if looked:
                if player != "one":
                    raise AdapterError("PRIVATE_PEEK_SENT_TO_OTHER_SEAT")
                if len(looked) != 7 or any(
                    card.name != "Plains" or card.hidden for card in looked
                ):
                    raise AdapterError("PRIVATE_PEEK_INCOMPLETE")
                report["private_peek"] = True
            if (
                player == "one"
                and event.kind == "observations_cleared"
                and report["private_peek"]
            ):
                report["concealed"] = True

    def inspect(view):
        if view.viewer_id == "two" and any(
            card.source == "looked_at" for card in view.observations
        ):
            raise AdapterError("PRIVATE_PEEK_SENT_TO_OTHER_SEAT")
        return report["private_peek"] and report["concealed"]

    def select(view):
        nonlocal requested
        if view.viewer_id != "one":
            return None
        for action in view.actions:
            if action.kind == "play_land":
                return action
            if (
                action.kind == "cast_spell"
                and action.label == "Gitaxian Probe"
                and not requested
            ):
                requested = True
                return action
        return None

    def respond(game, view):
        request = view.decision
        if request.family == "boolean" and "life" in request.prompt.lower():
            option = next(option for option in request.options if option.label == "Yes")
            return game.choose(view.viewer_id, request.decision_id, option.option_id)
        return None

    report.update(
        drive(
            adapter,
            (
                deck(("Island", 20), ("Gitaxian Probe", 20), ("Memnite", 20)),
                deck(("Plains", 60)),
            ),
            inspect,
            select,
            event_handler=events,
            decision_handler=respond,
        )
    )
    return report


def decisions(adapter, family="number"):
    land, spell = (
        ("Swamp", "Diabolic Intent")
        if family == "sacrifice"
        else ("Forest", "Walking Ballista" if family == "number" else "Evolution Charm")
    )
    document = deck((land, 20), (spell, 20), ("Memnite", 20))
    report = dict(decision_seen=False, target_selected=False, resolved=False)
    requested, creature_seen = False, False

    def inspect(view):
        nonlocal creature_seen
        if view.viewer_id != "one":
            return False
        creatures = [
            obj
            for obj in view.objects
            if obj.zone == "battlefield"
            and obj.characteristics
            and obj.characteristics.name == "Memnite"
        ]
        creature_seen |= bool(creatures)
        graveyard = {
            obj.characteristics.name
            for obj in view.objects
            if obj.zone == "graveyard" and obj.characteristics
        }
        if family == "number":
            report["resolved"] |= any(
                obj.zone == "battlefield"
                and obj.characteristics
                and obj.characteristics.name == spell
                and obj.characteristics.power == "1"
                and obj.characteristics.toughness == "1"
                for obj in view.objects
            )
            report["target_selected"] = True  # This numeric fixture needs no target.
        else:
            report["resolved"] |= (
                spell in graveyard
                and report["decision_seen"]
                and report["target_selected"]
            )
        if family == "sacrifice":
            report["sacrificed"] = "Memnite" in graveyard
        return all(report.values())

    def select(view):
        nonlocal requested
        if view.viewer_id != "one":
            return None
        lands = [
            obj
            for obj in view.objects
            if obj.zone == "battlefield"
            and obj.characteristics
            and obj.characteristics.name == land
        ]
        for action in view.actions:
            if action.kind == "play_land":
                return action
            if (
                action.kind == "cast_spell"
                and action.label == "Memnite"
                and family == "sacrifice"
                and not creature_seen
            ):
                return action
            if (
                action.kind == "cast_spell"
                and action.label == spell
                and not requested
                and len(lands) >= 2
                and (family != "sacrifice" or creature_seen)
            ):
                requested = True
                return action
        return None

    def respond(game, view):
        request = view.decision
        if request.family == "number" and family == "number":
            report["decision_seen"] = True
            return game.choose_number(view.viewer_id, request.decision_id, 1)
        if (
            request.family in ("options", "ability")
            and family == "modes"
            and "choose mode" in request.prompt.lower()
        ):
            option = next(
                (
                    option
                    for option in request.options
                    if "search" in option.label.lower()
                ),
                None,
            )
            if option is None:
                raise AdapterError("SEARCH_MODE_NOT_OFFERED")
            report["decision_seen"] = True
            return game.choose(view.viewer_id, request.decision_id, option.option_id)
        if request.family == "target":
            search = {
                obj.object_id
                for obj in view.objects
                if obj.zone == "decision"
                and obj.characteristics
                and obj.characteristics.name == land
            }
            option = next(
                (option for option in request.options if option.object_id in search),
                None,
            )
            if option is not None:
                report["target_selected"] = True
                if family == "sacrifice":
                    report["decision_seen"] = True
                return game.choose(
                    view.viewer_id, request.decision_id, option.option_id
                )
        return None

    report.update(
        drive(
            adapter,
            (document, deck((land, 60))),
            inspect,
            select,
            decision_handler=respond,
        )
    )
    return report


def distribution(adapter):
    report = dict(two_targets=False, distribution=False, damage=False, resolved=False)
    requested, creature_seen = False, False

    def inspect(view):
        nonlocal creature_seen
        if view.viewer_id != "one":
            return False
        creature_seen |= any(
            obj.zone == "battlefield"
            and obj.characteristics
            and obj.characteristics.name == "Memnite"
            for obj in view.objects
        )
        graveyard = {
            obj.characteristics.name
            for obj in view.objects
            if obj.zone == "graveyard" and obj.characteristics
        }
        report["damage"] |= (
            any(
                player.player_id == "two" and player.life == 18
                for player in view.players
            )
            and "Memnite" in graveyard
        )
        report["resolved"] |= "Pyrotechnics" in graveyard
        return all(report.values())

    def select(view):
        nonlocal requested
        if view.viewer_id != "one":
            return None
        for action in view.actions:
            if action.kind == "play_land":
                return action
            if (
                action.kind == "cast_spell"
                and action.label == "Memnite"
                and not creature_seen
            ):
                return action
            if (
                action.kind == "cast_spell"
                and action.label == "Pyrotechnics"
                and creature_seen
                and not requested
            ):
                requested = True
                return action
        return None

    def respond(game, view):
        request = view.decision
        if request.family == "target" and "divide" in request.prompt.lower():
            selected = [option for option in request.options if option.selected]
            if len(selected) >= 2 and request.can_finish:
                report["two_targets"] = True
                return game.finish_selection(view.viewer_id, request.decision_id)
            target = next(
                (
                    option
                    for option in request.options
                    if option.player_id == "two" and not option.selected
                ),
                None,
            )
            if target is None:
                creatures = {
                    obj.object_id
                    for obj in view.objects
                    if obj.zone == "battlefield"
                    and obj.characteristics
                    and obj.characteristics.name == "Memnite"
                }
                target = next(
                    (
                        option
                        for option in request.options
                        if option.object_id in creatures and not option.selected
                    ),
                    None,
                )
            if target is None:
                raise AdapterError("DISTRIBUTION_TARGET_NOT_OFFERED")
            return game.choose(view.viewer_id, request.decision_id, target.option_id)
        if request.family == "amounts":
            if (
                len(request.amounts) != 2
                or request.minimum != 4
                or request.maximum != 4
            ):
                raise AdapterError("DISTRIBUTION_CONSTRAINTS_INCORRECT")
            report["distribution"] = True
            return game.choose_amounts(view.viewer_id, request.decision_id, (2, 2))
        return None

    report.update(
        drive(
            adapter,
            (
                deck(("Mountain", 30), ("Memnite", 15), ("Pyrotechnics", 15)),
                deck(("Mountain", 60)),
            ),
            inspect,
            select,
            decision_handler=respond,
            timeout=180,
        )
    )
    return report


def triggers(adapter):
    report = dict(two_sources=False, explicit_order=False, triggers_resolved=False)
    requested_creature = False

    def inspect(view):
        if view.viewer_id != "one":
            return False
        wardens = [
            obj
            for obj in view.objects
            if obj.zone == "battlefield"
            and obj.characteristics
            and obj.characteristics.name == "Soul Warden"
        ]
        report["two_sources"] |= (
            len(wardens) == 2 and len({obj.object_id for obj in wardens}) == 2
        )
        report["triggers_resolved"] |= any(
            player.player_id == "one" and player.life >= 23 for player in view.players
        )
        return all(report.values())

    def select(view):
        nonlocal requested_creature
        if view.viewer_id != "one":
            return None
        wardens = [
            obj
            for obj in view.objects
            if obj.zone == "battlefield"
            and obj.characteristics
            and obj.characteristics.name == "Soul Warden"
        ]
        for action in view.actions:
            if action.kind == "play_land":
                return action
            if (
                action.kind == "cast_spell"
                and action.label == "Soul Warden"
                and len(wardens) < 2
            ):
                return action
            if (
                action.kind == "cast_spell"
                and action.label == "Memnite"
                and len(wardens) == 2
                and not requested_creature
            ):
                requested_creature = True
                return action
        return None

    def respond(game, view):
        request = view.decision
        if (
            request.family in ("ability", "target")
            and "triggered ability" in request.prompt.lower()
        ):
            if len(request.options) < 2:
                raise AdapterError("TRIGGER_ORDER_OPTIONS_MISSING")
            report["explicit_order"] = True
            return game.choose(
                view.viewer_id, request.decision_id, request.options[0].option_id
            )
        return None

    report.update(
        drive(
            adapter,
            (
                deck(("Plains", 20), ("Soul Warden", 20), ("Memnite", 20)),
                deck(("Plains", 60)),
            ),
            inspect,
            select,
            decision_handler=respond,
        )
    )
    return report


def copy_identity(adapter):
    report = dict(
        original_seen=False,
        copied=False,
        distinct_objects=False,
        original_printing=False,
    )
    requested = False

    def inspect(view):
        if view.viewer_id != "one":
            return False
        copies = [
            obj
            for obj in view.objects
            if obj.zone == "battlefield"
            and obj.characteristics
            and obj.characteristics.is_copy
        ]
        originals = [
            obj
            for obj in view.objects
            if obj.zone == "battlefield"
            and obj.characteristics
            and obj.characteristics.name == "Memnite"
            and not obj.characteristics.is_copy
        ]
        report["original_seen"] |= bool(originals)
        if copies:
            report["copied"] = (
                copies[0].characteristics.name == "Memnite"
                and copies[0].characteristics.power == "1"
            )
            report["distinct_objects"] = (
                bool(originals) and copies[0].object_id != originals[0].object_id
            )
            report["original_printing"] = (
                copies[0].card_identity is not None
                and copies[0].card_identity.printing_id == "selected-Clone"
            )
        return all(report.values())

    def select(view):
        nonlocal requested
        if view.viewer_id != "one":
            return None
        for action in view.actions:
            if action.kind == "play_land":
                return action
            if (
                action.kind == "cast_spell"
                and action.label == "Memnite"
                and not report["original_seen"]
            ):
                return action
            if (
                action.kind == "cast_spell"
                and action.label == "Clone"
                and report["original_seen"]
                and not requested
            ):
                requested = True
                return action
        return None

    def respond(game, view):
        request = view.decision
        if request.family == "boolean" and any(
            word in request.prompt.lower() for word in ("copy", "clone")
        ):
            option = next(option for option in request.options if option.label == "Yes")
            return game.choose(view.viewer_id, request.decision_id, option.option_id)
        return None

    report.update(
        drive(
            adapter,
            (
                deck(("Island", 30), ("Clone", 15), ("Memnite", 15)),
                deck(("Island", 60)),
            ),
            inspect,
            select,
            decision_handler=respond,
        )
    )
    return report


def transformation(adapter):
    canonical = "Delver of Secrets // Insectile Aberration"
    report = dict(
        front_seen=False,
        transformed=False,
        stable_identity=False,
        original_printing=False,
        ability_changed=False,
    )
    reference = None
    requested = False

    def inspect(view):
        nonlocal reference
        if view.viewer_id != "one":
            return False
        creature = next(
            (
                obj
                for obj in view.objects
                if obj.zone == "battlefield"
                and obj.characteristics
                and obj.characteristics.name
                in ("Delver of Secrets", "Insectile Aberration")
            ),
            None,
        )
        if creature is not None:
            if reference is None:
                reference = creature.object_id
                report["front_seen"] = (
                    creature.characteristics.name == "Delver of Secrets"
                )
            if creature.characteristics.name == "Insectile Aberration":
                report["transformed"] = creature.characteristics.transformed is True
                report["stable_identity"] = creature.object_id == reference
                report["original_printing"] = (
                    creature.card_identity is not None
                    and creature.card_identity.printing_id == "selected-" + canonical
                )
                report["ability_changed"] = any(
                    "flying" in rule.lower()
                    for rule in creature.characteristics.engine_view_text or ()
                )
        return all(report.values())

    def select(view):
        nonlocal requested
        if view.viewer_id != "one":
            return None
        for action in view.actions:
            if action.kind == "play_land":
                return action
            if (
                action.kind in ("cast_spell", "activate", "select_object")
                and action.label.startswith("Delver of Secrets")
                and not requested
            ):
                requested = True
                return action
        return None

    def respond(game, view):
        request = view.decision
        if request.family == "boolean" and any(
            word in request.prompt.lower() for word in ("reveal", "transform")
        ):
            option = next(option for option in request.options if option.label == "Yes")
            return game.choose(view.viewer_id, request.decision_id, option.option_id)
        return None

    report.update(
        drive(
            adapter,
            (
                deck(("Island", 20), (canonical, 20), ("Ponder", 20)),
                deck(("Island", 60)),
            ),
            inspect,
            select,
            decision_handler=respond,
        )
    )
    return report
