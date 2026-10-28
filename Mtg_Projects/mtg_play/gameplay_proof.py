"""Isolated real-engine gameplay feasibility; no UI or rules implementation."""

from __future__ import annotations
import argparse
import json
import queue
import time
import uuid
from connection_proof import DEFAULT_BUNDLE, DEFAULT_JDK, ProofError, run_proof, send


def gameplay(first, first_events, launch_peer, port):
    second, second_events = launch_peer()
    send(
        second,
        "connect",
        "connect-peer",
        port=port,
        username="mf_" + uuid.uuid4().hex[:10],
    )
    second_events.wait("connected", time.monotonic() + 30, "connect-peer")
    send(first, "create_game", "create")
    table = first_events.wait("table_created", time.monotonic() + 30, "create")[
        "table_id"
    ]
    cards = [
        dict(name="Forest", set="M10", number="248", quantity=30),
        dict(name="Memnite", set="SOM", number="174", quantity=30),
    ]
    for process, events in ((first, first_events), (second, second_events)):
        send(process, "join_table", "join", table_id=table, cards=cards)
        events.wait("joined", time.monotonic() + 30, "join")
    send(first, "start_game", "start", table_id=table)
    states = [{}, {}]
    report = {
        "players_started": [],
        "opening_hands": [],
        "mulligan_prompts": [],
        "distinct_opening_objects": False,
        "decisions_answered": 0,
        "land_observed": False,
        "spell_on_stack": False,
        "spell_resolved": False,
        "game_over": [],
        "stale_response_rejected": False,
    }
    opening_ids = {}
    conceded = False
    stale_probe = None
    stale_sent = False
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        activity = False
        for seat, (process, events) in enumerate(
            ((first, first_events), (second, second_events))
        ):
            try:
                event = events.events.get_nowait()
            except queue.Empty:
                continue
            activity = True
            if event is None or isinstance(event, Exception):
                raise ProofError("Gameplay bridge ended unexpectedly")
            kind = event["event"]
            if (
                kind == "error"
                and event.get("request_id") == "stale-probe"
                and "STALE_DECISION" in event.get("message", "")
            ):
                report["stale_response_rejected"] = True
                continue
            if kind == "error":
                raise ProofError(event.get("message", "Gameplay error"))
            if kind == "game_started":
                report["players_started"].append(seat)
            elif kind == "game_state":
                states[seat] = event
                if len(event["hand"]) == 7 and seat not in report["opening_hands"]:
                    report["opening_hands"].append(seat)
                    opening_ids[seat] = {card["id"] for card in event["hand"]}
                    if len(opening_ids[seat]) != 7:
                        raise ProofError(
                            "Opening cards do not have independent object identities"
                        )
                    if len(opening_ids) == 2:
                        if opening_ids[0] & opening_ids[1]:
                            raise ProofError(
                                "Private opening hands share object identities"
                            )
                        report["distinct_opening_objects"] = True
                objects = [
                    obj for player in event["players"] for obj in player["battlefield"]
                ]
                report["land_observed"] |= any(
                    obj.get("name") == "Forest" for obj in objects
                )
                report["spell_resolved"] |= any(
                    obj.get("name") == "Memnite" for obj in objects
                )
                report["spell_on_stack"] |= any(
                    obj.get("name") == "Memnite" for obj in event["stack"]
                )
            elif kind == "decision":
                state = states[seat]
                method = event["kind"]
                response_kind, value = "boolean", False
                if method == "GAME_ASK":
                    # This scenario explicitly keeps each hand. No arbitrary optional answers.
                    if "mulligan" not in (event.get("message") or "").lower():
                        raise ProofError(
                            "Unexpected yes/no prompt in feasibility scenario"
                        )
                    report["mulligan_prompts"].append(seat)
                    value = False
                elif (
                    method == "GAME_TARGET"
                    and event.get("message") == "Select a starting player"
                ):
                    response_kind, value = "object", event["targets"][0]
                elif method == "GAME_CHOOSE_ABILITY":
                    options = event["key_choices"]
                    response_kind, value = "object", next(iter(options))
                elif method == "GAME_SELECT":
                    playable = set(state.get("playable", []))
                    hand = state.get("hand", [])
                    preferred = (
                        ["Forest", "Memnite"]
                        if not report["land_observed"]
                        else ["Memnite"]
                    )
                    candidates = [
                        card
                        for name in preferred
                        for card in hand
                        if card.get("name") == name and card["id"] in playable
                    ]
                    if candidates:
                        response_kind, value = "object", candidates[0]["id"]
                else:
                    raise ProofError("Unsupported scenario decision: " + method)
                fields = dict(
                    game_id=state["game_id"],
                    decision_id=event["decision_id"],
                    kind=response_kind,
                    value=value,
                )
                send(
                    process,
                    "respond",
                    "decision-" + str(event["decision_id"]),
                    **fields,
                )
                if stale_probe is None:
                    stale_probe = (process, fields)
                report["decisions_answered"] += 1
            elif kind == "response_sent":
                if not event["accepted"]:
                    raise ProofError("Engine refused decision transport")
                if stale_probe is not None and not stale_sent:
                    send(stale_probe[0], "respond", "stale-probe", **stale_probe[1])
                    stale_sent = True
            elif kind == "game_over":
                report["game_over"].append(seat)
        if (
            report["land_observed"]
            and report["spell_on_stack"]
            and report["spell_resolved"]
            and not conceded
        ):
            send(second, "concede", "finish")
            conceded = True
        if len(set(report["game_over"])) == 2 and report["stale_response_rejected"]:
            if (
                len(set(report["players_started"])) != 2
                or len(report["opening_hands"]) != 2
                or len(set(report["mulligan_prompts"])) != 2
                or not report["distinct_opening_objects"]
            ):
                raise ProofError("Missing independent player or opening-hand evidence")
            return report
        if not activity:
            time.sleep(0.01)
    raise ProofError("Gameplay scenario timed out: " + json.dumps(report))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--xmage-root", type=type(DEFAULT_BUNDLE), default=DEFAULT_BUNDLE
    )
    parser.add_argument("--jdk-path", type=type(DEFAULT_JDK), default=DEFAULT_JDK)
    args = parser.parse_args()
    result = run_proof(
        args.xmage_root.resolve(), args.jdk_path.resolve(), scenario=gameplay
    )
    print(json.dumps(result, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
