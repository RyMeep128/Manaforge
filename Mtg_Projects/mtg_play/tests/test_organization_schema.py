"""Schema half of the corpus; Java/C# additionally enforce lexical/context rules."""

import json
from pathlib import Path

import jsonschema
import pytest

PROTOCOL = Path(__file__).resolve().parents[1] / "protocol"
CASES = []
for version in (1, 2, 3):
    schema = json.loads(
        (PROTOCOL / f"organization-v{version}.schema.json").read_text(encoding="utf-8")
    )
    corpus = json.loads(
        (PROTOCOL / f"fixtures/organization-v{version}.json").read_text(
            encoding="utf-8"
        )
    )
    CASES.extend(
        pytest.param(schema, case, id=f"v{version}-" + case["name"])
        for case in corpus["cases"]
    )


@pytest.mark.parametrize("schema,case", CASES)
def test_organization_schema_corpus(schema, case):
    try:
        message = json.loads(case["text"])
    except ValueError:
        valid = False
    else:
        valid = jsonschema.Draft202012Validator(schema).is_valid(message)
    assert valid == case["schema_valid"]


@pytest.mark.parametrize(
    "members,x,valid",
    [
        (["h1"], 250000, True),
        ([], 0, False),
        (["h1", "h2"], 0, False),
        (["h1"], -1, False),
        (["h1"], 1000001, False),
    ],
)
def test_v4_free_placement_is_bounded_and_single_member(members, x, valid):
    schema = json.loads((PROTOCOL / "organization-v4.schema.json").read_text())
    packet = {
        "wire_version": 1,
        "organization_version": 4,
        "message_type": "organization_command",
        "message_id": "place",
        "body": {
            "match_epoch": "match",
            "command_id": "place",
            "expected_organization_revision": 0,
            "basis_revision": 1,
            "operation": {
                "kind": "place",
                "group_id": None,
                "name": None,
                "x": x,
                "y": 500000,
                "index": None,
                "members": members,
                "presentation_mode": None,
            },
        },
    }
    assert jsonschema.Draft202012Validator(schema).is_valid(packet) is valid
