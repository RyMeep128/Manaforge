"""Pinned-engine human-versus-AI proof. Fixture policy never ships in the UI."""

from __future__ import annotations

from copy import deepcopy
import time

from .adapter import AdapterError
from .adapter_acceptance import checked_poll, fixture_deck
from .contracts import GameSetup, MatchSeat
from .acceptance_scenarios import deck


def freeform(adapter):
    documents = (fixture_deck(), fixture_deck())
    originals = deepcopy([document.to_dict() for document in documents])
    setup = GameSetup(
        (MatchSeat("human", "You"), MatchSeat("ai", "Opponent", "engine_ai"))
    )
    game = adapter.create_game(setup, documents)
    report = dict(
        opening_hand=False,
        human_keep=False,
        human_land=False,
        human_spell=False,
        ai_land=False,
        ai_spell=False,
        ai_turn=False,
        ai_combat=False,
        hidden_hand=True,
        ai_view_rejected=False,
        ai_command_rejected=False,
        natural_result=False,
        source_decks_unchanged=False,
    )
    for operation, key in (
        (lambda: game.snapshot("ai"), "ai_view_rejected"),
        (lambda: game.concede("ai"), "ai_command_rejected"),
    ):
        try:
            operation()
        except AdapterError as error:
            if error.code != "UNAUTHORIZED_SEAT":
                raise
            report[key] = True
        else:
            raise AdapterError("AI_SEAT_ACCESSIBLE")
    cast_submitted = False
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        checked_poll(game, "human")
        try:
            view = game.snapshot("human")
        except AdapterError as error:
            if error.code == "SNAPSHOT_NOT_READY":
                time.sleep(0.005)
                continue
            raise
        hand = [obj for obj in view.objects if obj.zone == "hand"]
        if any(obj.owner_id != "human" for obj in hand):
            raise AdapterError("OPPONENT_HAND_EXPOSED")
        report["opening_hand"] |= len(hand) == 7
        report["ai_turn"] |= view.active_player_id == "ai" and (view.turn or 0) > 1
        ai_objects = set()
        for obj in view.objects:
            if obj.zone != "battlefield" or not obj.characteristics:
                continue
            owner = "ai" if obj.controller_id == "ai" else "human"
            if obj.controller_id == "ai":
                ai_objects.add(obj.object_id)
            name = obj.characteristics.name
            if name == "Forest":
                report[owner + "_land"] = True
            if name == "Memnite":
                report[owner + "_spell"] = True
        report["ai_combat"] |= any(
            ai_objects.intersection(group.attackers) for group in view.combat
        )
        if view.status == "finished" and view.result is not None:
            report["natural_result"] = view.result == "did_not_win"
            report["source_decks_unchanged"] = [
                document.to_dict() for document in documents
            ] == originals
            if not all(report.values()):
                raise AdapterError("AI_ACCEPTANCE_EVIDENCE_MISSING")
            return report
        request = view.decision
        if request is None:
            time.sleep(0.005)
            continue
        if request.family == "boolean" and "mulligan" in request.prompt.lower():
            option = next(option for option in request.options if option.label == "No")
            result = game.choose("human", request.decision_id, option.option_id)
            report["human_keep"] = True
        elif (
            request.family == "target" and request.prompt == "Select a starting player"
        ):
            option = next(
                option for option in request.options if option.player_id == "human"
            )
            result = game.choose("human", request.decision_id, option.option_id)
        elif request.family == "ability":
            result = game.choose(
                "human", request.decision_id, request.options[0].option_id
            )
        elif request.family == "selection":
            # Play one creature, then leave AI attacks unblocked. A real combat
            # loss proves completion without manufacturing an outcome or conceding.
            action = next(
                (
                    action
                    for action in view.actions
                    if action.kind == "play_land"
                    or (
                        action.kind == "cast_spell"
                        and action.label == "Memnite"
                        and not cast_submitted
                    )
                ),
                None,
            )
            if action is None:
                action = next(
                    action for action in view.actions if action.kind == "pass"
                )
            result = game.perform("human", request.decision_id, action.action_id)
            cast_submitted |= action.kind == "cast_spell"
        else:
            raise AdapterError("AI_ACCEPTANCE_UNSUPPORTED_DECISION")
        if result.outcome != "submitted":
            raise AdapterError(result.code or "AI_ACCEPTANCE_COMMAND_FAILED")
        time.sleep(0.005)
    raise AdapterError("AI_ACCEPTANCE_TIMEOUT")


def commander_deck():
    """Existing supported two-player Commander fixture, in canonical Core form."""
    from mtg_core.decks import DeckEntry

    document = deck(("Plains", 99))
    document.deck.name = "AI Commander acceptance fixture"
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
    return document


def _battlefield(view, player):
    return {
        obj.object_id: obj
        for obj in view.objects
        if obj.zone == "battlefield" and obj.controller_id == player
    }


def _ai_blocks_human(view):
    human = _battlefield(view, "human")
    opponent = _battlefield(view, "ai")
    return any(
        group.blocked
        and human.keys() & set(group.attackers)
        and opponent.keys() & set(group.blockers)
        for group in view.combat
    )


def _human_choice(game, view, select):
    """Bounded fixture policy; never answer an unknown human decision."""
    request = view.decision
    if request.family == "boolean" and "mulligan" in request.prompt.lower():
        option = next(option for option in request.options if option.label == "No")
        return game.choose("human", request.decision_id, option.option_id)
    if request.family == "target" and request.prompt == "Select a starting player":
        option = next(
            option for option in request.options if option.player_id == "human"
        )
        return game.choose("human", request.decision_id, option.option_id)
    if request.family == "selection":
        action = select(view)
        if action is None:
            action = next(action for action in view.actions if action.kind == "pass")
        return game.perform("human", request.decision_id, action.action_id)
    if request.family == "target" and view.step == "DECLARE_ATTACKERS":
        option = next(
            (option for option in request.options if option.player_id == "ai"), None
        )
        if option is not None:
            return game.choose("human", request.decision_id, option.option_id)
    raise AdapterError("AI_ACCEPTANCE_UNSUPPORTED_DECISION")


def _drive_to_evidence(adapter, documents, inspect, select, *, format="freeform"):
    originals = deepcopy([document.to_dict() for document in documents])
    setup = GameSetup(
        (MatchSeat("human", "You"), MatchSeat("ai", "Opponent", "engine_ai")),
        format=format,
    )
    game = adapter.create_game(setup, documents)
    report = dict(human_keep=False, hidden_hand=True, conceded_after_evidence=False)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        checked_poll(game, "human")
        try:
            view = game.snapshot("human")
        except AdapterError as error:
            if error.code == "SNAPSHOT_NOT_READY":
                time.sleep(0.005)
                continue
            raise
        if any(obj.zone == "hand" and obj.owner_id != "human" for obj in view.objects):
            raise AdapterError("OPPONENT_HAND_EXPOSED")
        if view.status == "finished" and view.result is not None:
            if (
                not report["human_keep"]
                or not report["conceded_after_evidence"]
                or view.result != "did_not_win"
            ):
                raise AdapterError("AI_ACCEPTANCE_EVIDENCE_MISSING")
            if [document.to_dict() for document in documents] != originals:
                raise AdapterError("SOURCE_DECK_CHANGED")
            return dict(report, result=view.result, source_decks_unchanged=True)
        if view.status == "active" and not report["conceded_after_evidence"]:
            if inspect(view) and report["human_keep"]:
                result = game.concede("human")
                report["conceded_after_evidence"] = True
            elif view.decision is not None:
                result = _human_choice(game, view, select)
                if (
                    view.decision.family == "boolean"
                    and "mulligan" in view.decision.prompt.lower()
                ):
                    report["human_keep"] = True
            else:
                time.sleep(0.005)
                continue
            if result.outcome != "submitted":
                raise AdapterError(result.code or "AI_ACCEPTANCE_COMMAND_FAILED")
        time.sleep(0.005)
    raise AdapterError("AI_ACCEPTANCE_TIMEOUT")


def commander(adapter):
    report = dict(
        command_zones=False,
        selected_printings=False,
        ai_commander_cast=False,
        ai_commander_damage=False,
        ai_combat=False,
        human_land=False,
        human_commander_available=False,
    )

    def inspect(view):
        commanders = view.commanders or ()
        report["command_zones"] |= {
            obj.owner_id for obj in view.objects if obj.zone == "command"
        } == {"human", "ai"}
        if {row.owner_id for row in commanders} == {"human", "ai"}:
            report["selected_printings"] |= all(
                row.card_identity
                and row.card_identity.printing_id == "selected-commander"
                for row in commanders
            )
        report["ai_commander_cast"] |= any(
            row.owner_id == "ai" and (row.command_zone_plays or 0) >= 1
            for row in commanders
        ) and any(
            obj.characteristics
            and obj.characteristics.name == "Isamaru, Hound of Konda"
            for obj in _battlefield(view, "ai").values()
        )
        report["ai_commander_damage"] |= any(
            row.owner_id == "ai"
            and any(
                player == "human" and damage >= 2 for player, damage in row.damage_dealt
            )
            for row in commanders
        )
        report["ai_combat"] |= any(
            _battlefield(view, "ai").keys() & set(group.attackers)
            for group in view.combat
        )
        report["human_land"] |= any(
            obj.characteristics and obj.characteristics.name == "Plains"
            for obj in _battlefield(view, "human").values()
        )
        report["human_commander_available"] |= any(
            action.kind == "cast_spell" and action.label == "Isamaru, Hound of Konda"
            for action in view.actions
        )
        return all(report.values())

    def select(view):
        # Leave the human commander uncast so the AI can attack an open board.
        return next(
            (action for action in view.actions if action.kind == "play_land"), None
        )

    result = _drive_to_evidence(
        adapter,
        (commander_deck(), commander_deck()),
        inspect,
        select,
        format="commander",
    )
    return dict(result, **report)


def blockers(adapter):
    report = dict(human_attacker=False, ai_block=False)
    cast_submitted = False

    def inspect(view):
        report["human_attacker"] |= any(
            _battlefield(view, "human").keys() & set(group.attackers)
            for group in view.combat
        )
        report["ai_block"] |= _ai_blocks_human(view)
        return all(report.values())

    def select(view):
        nonlocal cast_submitted
        attacking = {obj for group in view.combat for obj in group.attackers}
        for action in view.actions:
            if (
                action.kind == "cast_spell"
                and action.label == "Memnite"
                and not cast_submitted
            ):
                cast_submitted = True
                return action
            if (
                action.kind == "declare_attacker"
                and action.object_id not in attacking
                and _battlefield(view, "ai")
            ):
                return action
        return None

    result = _drive_to_evidence(
        adapter, (deck(("Memnite", 60)), deck(("Ornithopter", 60))), inspect, select
    )
    return dict(result, **report)
