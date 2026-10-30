"""Focused validation of the existing DTO baseline, not future transport safety."""

from copy import deepcopy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from generate_protocol_fixtures import artifacts
from mtg_play.protocol_schema import contract_schema

DIRECTORY = Path(__file__).resolve().parents[1] / "protocol"
SCHEMA = json.loads((DIRECTORY / "python-contracts-v1.schema.json").read_text())
FIXTURES = json.loads((DIRECTORY / "fixtures/python-baseline-v1.json").read_text())


def validate(record, payload):
    Draft202012Validator({**SCHEMA, "$ref": f"#/$defs/{record}"}).validate(payload)


def snapshot(name="visible-hand"):
    return deepcopy(
        next(case["payload"] for case in FIXTURES["cases"] if case["name"] == name)
    )


def test_schema_is_valid_and_artifacts_are_reproducible():
    Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA == contract_schema()
    for name, payload in artifacts().items():
        # JSON serialization intentionally converts tuple fields to arrays.
        assert json.loads((DIRECTORY / name).read_text()) == json.loads(
            json.dumps(payload)
        )


@pytest.mark.parametrize("case", FIXTURES["cases"], ids=lambda case: case["name"])
def test_sanitized_adapter_fixtures_validate(case):
    validate(case["record"], case["payload"])
    payload = json.dumps(case["payload"])
    for private_marker in (
        "engine-card",
        "engine-player-",
        "internal-one",
        "PRIVATE_CARD_NAME",
    ):
        assert private_marker not in payload


def test_unknown_null_and_valid_zero_remain_distinct():
    payload = snapshot()
    assert payload["phase"] is None
    assert payload["players"][0]["life"] == 0
    assert payload["players"][0]["library_count"] == 0
    validate("GameSnapshot", payload)
    payload["players"][0]["life"] = None
    with pytest.raises(ValidationError):
        validate("GameSnapshot", payload)


@pytest.mark.parametrize(
    "mutation",
    [
        "version",
        "missing",
        "boolean-integer",
        "unknown",
        "negative-revision",
        "malformed-pair",
    ],
)
def test_invalid_snapshot_shapes_are_rejected(mutation):
    payload = snapshot()
    if mutation == "version":
        payload["protocol_version"] = 2
    elif mutation == "missing":
        del payload["viewer_id"]
    elif mutation == "boolean-integer":
        payload["players"][0]["life"] = True
    elif mutation == "unknown":
        payload["raw_engine_state"] = {}
    elif mutation == "negative-revision":
        payload["revision"] = -1
    else:
        payload["players"][0]["mana"] = [["G", 1, "extra"]]
    with pytest.raises(ValidationError):
        validate("GameSnapshot", payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("characteristics", {"name": "LEAK"}),
        (
            "card_identity",
            {"oracle_id": "LEAK", "printing_id": "LEAK", "deck_entry_id": None},
        ),
        ("commander_id", "LEAK"),
        ("copy_source_id", "LEAK"),
    ],
)
def test_concealed_object_cannot_carry_identity(field, value):
    payload = snapshot("concealed-object")
    assert payload["objects"][0]["hidden"] is True
    payload["objects"][0][field] = value
    with pytest.raises(ValidationError):
        validate("GameSnapshot", payload)


def test_hidden_observation_cannot_carry_printing_information():
    observation = dict(
        observation_id="fixture",
        source="look",
        hidden=True,
        name=None,
        set_code=None,
        collector_number=None,
    )
    validate("CardObservation", observation)
    observation["collector_number"] = "174"
    with pytest.raises(ValidationError):
        validate("CardObservation", observation)


def test_unknown_outcome_does_not_become_confirmation():
    with pytest.raises(ValidationError):
        validate(
            "CommandResult", dict(command_id="fixture", outcome="accepted", code=None)
        )


def test_printing_identity_and_unsupported_fields_survive_serialization():
    validate(
        "CardIdentity",
        dict(
            oracle_id="fixture-oracle",
            printing_id="fixture-print",
            deck_entry_id="fixture-entry",
        ),
    )
    payload = snapshot()
    fields = payload["objects"][0]["characteristics"]["unsupported_fields"]
    assert "current_rules_text" in fields
    assert "copy_provenance_history" in fields
