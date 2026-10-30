"""Pinned-engine human-versus-AI proof. Fixture policy never ships in the UI."""

from __future__ import annotations

from copy import deepcopy
import time

from .adapter import AdapterError
from .adapter_acceptance import checked_poll, fixture_deck
from .contracts import GameSetup, MatchSeat


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
