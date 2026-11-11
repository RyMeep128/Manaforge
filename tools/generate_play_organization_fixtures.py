"""Deterministic reviewed organization corpus; no engine or user data."""

import argparse
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "Mtg_Projects/mtg_play/protocol/fixtures/organization-v1.json"


def corpus():
    context = {
        "match_epoch": "match",
        "viewer_id": "viewer-a",
        "basis_revision": 7,
        "seats": {"host-a": "seat-a", "host-b": "seat-b"},
        "bindings": [
            {
                "incarnation": "SECRET-INCARNATION-1",
                "handle": "h1",
                "object_reference": "object-1",
                "host_seat": "host-a",
            },
            {
                "incarnation": "SECRET-INCARNATION-2",
                "handle": "h2",
                "object_reference": "object-2",
                "host_seat": "host-b",
            },
        ],
        "admitted": ["object-1", "object-2"],
    }
    cases = []

    def envelope(kind, body):
        return {
            "wire_version": 1,
            "organization_version": 1,
            "message_type": "organization_" + kind,
            "message_id": "message-1",
            "body": body,
        }

    def add(name, message, valid=True, schema_valid=None):
        text = (
            message
            if isinstance(message, str)
            else json.dumps(message, ensure_ascii=True, separators=(",", ":"))
        )
        cases.append(
            {
                "name": name,
                "text": text,
                "schema_valid": valid if schema_valid is None else schema_valid,
                "valid": valid,
            }
        )

    caps = envelope("capabilities", {"versions": [1]})
    add("capabilities", caps)
    add("unsupported-capabilities", envelope("capabilities", {"versions": [2]}))
    add("empty-capabilities", envelope("capabilities", {"versions": []}))
    add("duplicate-capabilities", envelope("capabilities", {"versions": [1, 1]}), False)
    operations = {
        "create": dict(group_id="g-new", name="Mana Rocks", x=250000, y=750000),
        "rename": dict(group_id="g1", name="Protection"),
        "delete": dict(group_id="g1"),
        "position": dict(group_id="g1", x=0, y=1000000),
        "reorder": dict(group_id="g1", index=0),
        "move": dict(group_id="g1", index=0, members=["h1"]),
    }
    messages = {}
    for kind, fields in operations.items():
        operation = dict(
            kind=kind, group_id=None, name=None, x=None, y=None, index=None, members=[]
        )
        operation.update(fields)
        message = envelope(
            "command",
            dict(
                match_epoch="match",
                command_id="cmd-1",
                expected_organization_revision=0,
                basis_revision=7,
                operation=operation,
            ),
        )
        messages[kind] = message
        add("command-" + kind, message)
    root_move = copy.deepcopy(messages["move"])
    root_move["body"]["operation"]["group_id"] = None
    add("move-to-root", root_move)
    for outcome, reason in [("applied", None), ("rejected", "STALE_BASIS_REVISION")]:
        add(
            "receipt-" + outcome,
            envelope(
                "receipt",
                dict(
                    match_epoch="match",
                    command_id="cmd-1",
                    outcome=outcome,
                    organization_revision=3,
                    basis_revision=7,
                    reason_code=reason,
                ),
            ),
        )
    snapshot = envelope(
        "snapshot",
        dict(
            match_epoch="match",
            organization_revision=3,
            basis_revision=7,
            viewer_id="viewer-a",
            seats=[
                dict(
                    seat_id="seat-a",
                    root=[],
                    groups=[
                        dict(
                            group_id="g1",
                            name="Mana Rocks",
                            x=250000,
                            y=750000,
                            members=["h1"],
                        )
                    ],
                ),
                dict(seat_id="seat-b", root=["h2"], groups=[]),
            ],
            mappings=[
                dict(handle="h1", object_reference="object-1", seat_id="seat-a"),
                dict(handle="h2", object_reference="object-2", seat_id="seat-b"),
            ],
        ),
    )
    add("snapshot", snapshot)

    def altered(name, source, change, schema_valid=False):
        value = copy.deepcopy(source)
        change(value)
        add(name, value, False, schema_valid)

    altered(
        "foreign-match",
        messages["move"],
        lambda m: m["body"].update(match_epoch="foreign"),
        True,
    )
    altered(
        "stale-basis",
        messages["move"],
        lambda m: m["body"].update(basis_revision=6),
        True,
    )
    altered(
        "unknown-handle",
        messages["move"],
        lambda m: m["body"]["operation"].update(members=["unknown"]),
        True,
    )
    altered(
        "duplicate-selection",
        messages["move"],
        lambda m: m["body"]["operation"].update(members=["h1", "h1"]),
        True,
    )
    altered(
        "editable-actor", messages["move"], lambda m: m["body"].update(actor="host-a")
    )
    altered(
        "coordinate-too-large",
        messages["position"],
        lambda m: m["body"]["operation"].update(x=1000001),
    )
    altered(
        "fractional-coordinate",
        messages["position"],
        lambda m: m["body"]["operation"].update(x=0.0),
        True,
    )
    altered(
        "unused-operation-field",
        messages["delete"],
        lambda m: m["body"]["operation"].update(name="Unexpected"),
    )
    altered(
        "blank-name",
        messages["rename"],
        lambda m: m["body"]["operation"].update(name=" \u00a0\u3000"),
        True,
    )
    altered(
        "control-character",
        messages["rename"],
        lambda m: m["body"]["operation"].update(name="bad\nname"),
    )
    unicode_name = copy.deepcopy(messages["rename"])
    unicode_name["body"]["operation"]["name"] = "\U0001f525" * 64
    add("unicode-64-scalars", unicode_name)
    altered(
        "unicode-65-scalars",
        unicode_name,
        lambda m: m["body"]["operation"].update(name="\U0001f525" * 65),
    )
    altered(
        "lone-surrogate",
        messages["rename"],
        lambda m: m["body"]["operation"].update(name="\ud800"),
        True,
    )
    altered(
        "selection-over-limit",
        messages["move"],
        lambda m: m["body"]["operation"].update(members=["h1"] * 129),
    )
    altered(
        "revision-overflow",
        messages["move"],
        lambda m: m["body"].update(expected_organization_revision=9223372036854775808),
    )
    altered(
        "foreign-viewer",
        snapshot,
        lambda m: m["body"].update(viewer_id="viewer-b"),
        True,
    )
    altered(
        "unadmitted-object",
        snapshot,
        lambda m: m["body"]["mappings"][0].update(object_reference="SECRET-OBJECT"),
        True,
    )
    altered(
        "wrong-seat",
        snapshot,
        lambda m: m["body"]["mappings"][0].update(seat_id="seat-b"),
        True,
    )
    altered(
        "host-incarnation-field",
        snapshot,
        lambda m: m["body"]["mappings"][0].update(incarnation="SECRET-INCARNATION-1"),
    )
    altered(
        "duplicate-membership",
        snapshot,
        lambda m: m["body"]["seats"][0]["root"].append("h1"),
        True,
    )
    altered("missing-mapping", snapshot, lambda m: m["body"]["mappings"].pop(), True)
    altered(
        "duplicate-group",
        snapshot,
        lambda m: m["body"]["seats"][1]["groups"].append(
            dict(group_id="g1", name="Duplicate", x=0, y=0, members=[])
        ),
        True,
    )
    altered(
        "too-many-seats",
        snapshot,
        lambda m: m["body"].update(seats=m["body"]["seats"] * 5),
    )
    altered(
        "too-many-groups",
        snapshot,
        lambda m: m["body"]["seats"][0].update(
            groups=m["body"]["seats"][0]["groups"] * 33
        ),
    )
    altered("unsupported-version", caps, lambda m: m.update(organization_version=2))
    altered("legacy-message-type", caps, lambda m: m.update(message_type="snapshot"))
    receipt = envelope(
        "receipt",
        dict(
            match_epoch="match",
            command_id="cmd-1",
            outcome="applied",
            organization_revision=0,
            basis_revision=7,
            reason_code="INVALID_ID",
        ),
    )
    add("applied-with-reason", receipt, False)
    receipt["body"].update(outcome="rejected", reason_code=None)
    add("rejected-without-reason", receipt, False)
    for code in (
        "COMMAND_LIMIT_REACHED",
        "ORGANIZATION_LIMIT_REACHED",
        "FOREIGN_MATCH",
    ):
        receipt["body"]["reason_code"] = code
        add("receipt-" + code.lower(), receipt, True)
    raw = json.dumps(caps, separators=(",", ":"))
    add(
        "duplicate-key",
        raw.replace('"wire_version":1', '"wire_version":1,"wire_version":1'),
        False,
        True,
    )
    add("trailing-data", raw + "{}", False)
    add(
        "depth-over-limit",
        raw[:-1] + ',"extra":' + "[" * 34 + "0" + "]" * 34 + "}",
        False,
    )
    add("exact-byte-limit", raw + " " * (262144 - len(raw.encode())), True)
    add("over-byte-limit", raw + " " * (262145 - len(raw.encode())), False, True)
    return {"context": context, "cases": cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(corpus(), indent=2, ensure_ascii=True) + "\n"
    if args.check:
        if OUTPUT.read_text(encoding="utf-8") != text:
            parser.exit(1, "Organization fixture drift\n")
    else:
        OUTPUT.write_text(text, encoding="utf-8")
    print(
        "Organization shared fixtures match"
        if args.check
        else "Generated organization shared fixtures"
    )


if __name__ == "__main__":
    main()
