"""Regenerate sanitized baseline fixtures using the existing adapter test harness.

Run from repository root using the development Python environment. No engine runs.
"""

import argparse
from copy import deepcopy
import hashlib
from itertools import count
import json
from pathlib import Path
from unittest.mock import patch

from test_adapter import inject, make_session, state
from mtg_play.contracts import CardIdentity, CommandResult, GameSetup, MatchSeat
from mtg_play.protocol_schema import contract_schema

DIRECTORY = Path(__file__).resolve().parents[1] / "protocol"


def artifacts():
    cases = []
    for name, hidden, prompt in (
        ("visible-hand", False, None),
        ("concealed-object", True, None),
        ("mulligan-choice", False, "GAME_ASK"),
        ("numeric-choice", False, "GAME_GET_AMOUNT"),
        ("failed-session", False, "failure"),
    ):
        identifiers = count(1)
        with patch(
            "mtg_play.adapter._id",
            side_effect=lambda: f"fixture-{next(identifiers):04d}",
        ):
            session = make_session()
            event = state(1, hidden=hidden)
            event["hand"][0]["name"] = "Synthetic Fixture Card"
            inject(session, event)
            if prompt == "failure":
                inject(
                    session,
                    {"event": "error", "message": "UNSUPPORTED_DECISION: synthetic"},
                )
            elif prompt:
                inject(
                    session,
                    dict(
                        event="decision",
                        decision_id=2,
                        kind=prompt,
                        message="Synthetic fixture choice",
                        min=0,
                        max=4,
                    ),
                )
            cases.append(
                {
                    "name": name,
                    "record": "GameSnapshot",
                    "payload": session.snapshot("one").to_dict(),
                }
            )
            if prompt == "failure":
                cases.extend(
                    {
                        "name": f"failure-event-{i}",
                        "record": "GameEvent",
                        "payload": event.to_dict(),
                    }
                    for i, event in enumerate(session.poll("one"))
                )
    for outcome in ("submitted", "confirmed", "rejected", "uncertain"):
        cases.append(
            {
                "name": f"outcome-{outcome}",
                "record": "CommandResult",
                "payload": CommandResult("synthetic-command", outcome).to_dict(),
            }
        )
    for seats in (2, 5):
        setup = GameSetup(
            tuple(
                MatchSeat(
                    f"fixture-seat-{seat}",
                    f"Fixture seat {seat}",
                    "local_human" if seat == 0 else "engine_ai",
                )
                for seat in range(seats)
            )
        )
        cases.append(
            dict(
                name=f"setup-{seats}-seats-dto-only",
                record="GameSetup",
                payload=setup.to_dict(),
            )
        )
    cases.append(
        dict(
            name="printing-identity-dto-only",
            record="CardIdentity",
            payload=CardIdentity(
                "fixture-oracle", "fixture-print", "fixture-entry"
            ).to_dict(),
        )
    )
    negative = []
    visible = next(case["payload"] for case in cases if case["name"] == "visible-hand")
    hidden = next(
        case["payload"] for case in cases if case["name"] == "concealed-object"
    )
    for name in (
        "missing-viewer",
        "wrong-version",
        "unknown-field",
        "boolean-life",
        "null-life",
        "negative-revision",
        "malformed-pair",
        "hidden-characteristics",
        "hidden-printing",
        "hidden-commander",
        "hidden-copy-source",
    ):
        value = deepcopy(hidden if name.startswith("hidden-") else visible)
        if name == "missing-viewer":
            del value["viewer_id"]
        elif name == "wrong-version":
            value["protocol_version"] = 2
        elif name == "unknown-field":
            value["raw_engine_state"] = {}
        elif name == "boolean-life":
            value["players"][0]["life"] = True
        elif name == "null-life":
            value["players"][0]["life"] = None
        elif name == "negative-revision":
            value["revision"] = -1
        elif name == "malformed-pair":
            value["players"][0]["mana"] = [["G", 1, "extra"]]
        elif name == "hidden-characteristics":
            value["objects"][0]["characteristics"] = deepcopy(
                visible["objects"][0]["characteristics"]
            )
        elif name == "hidden-printing":
            value["objects"][0]["card_identity"] = dict(
                oracle_id="synthetic", printing_id="synthetic", deck_entry_id=None
            )
        elif name == "hidden-commander":
            value["objects"][0]["commander_id"] = "synthetic"
        elif name == "hidden-copy-source":
            value["objects"][0]["copy_source_id"] = "synthetic"
        negative.append(dict(name=name, record="GameSnapshot", payload=value))
    negative.append(
        dict(
            name="unknown-outcome",
            record="CommandResult",
            payload=dict(command_id="synthetic", outcome="accepted", code=None),
        )
    )
    sources = {}
    for path in (
        DIRECTORY.parent / "contracts.py",
        DIRECTORY.parent / "adapter.py",
        Path(__file__).with_name("test_adapter.py"),
    ):
        sources[path.name] = hashlib.sha256(
            path.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()
    return {
        "python-contracts-v1.schema.json": contract_schema(),
        "fixtures/python-baseline-v1.json": {
            "fixture_format": 1,
            "provenance": {
                "kind": "Synthetic existing-adapter test inputs; not real-engine captures. Outcome examples are DTO-only.",
                "source_sha256_utf8_lf": sources,
            },
            "cases": cases,
        },
        "fixtures/python-negative-v1.json": {"fixture_format": 1, "cases": negative},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, payload in artifacts().items():
        path = DIRECTORY / name
        expected = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != expected:
                parser.exit(1, f"Protocol artifact drift: {name}\n")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")
    print(
        "Protocol schema and synthetic adapter fixtures match source."
        if args.check
        else "Protocol artifacts regenerated."
    )


if __name__ == "__main__":
    main()
