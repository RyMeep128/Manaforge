"""Keep the public header schema aligned with the shared consumer corpus."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1] / "protocol"


@pytest.mark.parametrize("stem", ["wire-envelope", "wire-messages"])
def test_shared_envelopes_match_schema(stem):
    schema = json.loads((ROOT / f"{stem}-v1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    corpus = json.loads(
        (
            ROOT
            / "fixtures"
            / (
                "wire-envelopes-v1.json"
                if stem == "wire-envelope"
                else "wire-messages-v1.json"
            )
        ).read_text(encoding="utf-8")
    )
    for case in corpus["positive"]:
        validator.validate(
            json.loads(case["text"]) if "text" in case else case["envelope"]
        )
    for case in corpus["negative"]:
        # Raw syntax, duplicate keys and depth are parser responsibilities.
        if case["code"].startswith(("ENVELOPE_", "MESSAGE_")):
            assert not validator.is_valid(
                json.loads(case["text"]) if "text" in case else case["envelope"]
            ), case["name"]

    for case in corpus.get("current", []) + corpus.get("bindings", []):
        # A stale or unauthorized command may be structurally valid; current engine
        # context and authenticated seat binding are separate checks in both peers.
        validator.validate(case["envelope"])


def test_viewer_auth_schema_separates_shape_from_authentication():
    schema = json.loads(
        (ROOT / "viewer-auth-v1.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    corpus = json.loads(
        (ROOT / "fixtures/viewer-auth-v1.json").read_text(encoding="utf-8")
    )
    for case in corpus["positive"]:
        validator.validate(case["envelope"])
    for case in corpus["negative"]:
        if case["name"] in {"protocol_version", "owner_secret", "missing-proof"}:
            assert not validator.is_valid(case["envelope"])
        else:
            # Wrong proofs, pins, nonce/context and role can be structurally valid.
            # Runtime cryptographic verification must still reject them.
            validator.validate(case["envelope"])


def test_dummy_snapshot_uses_existing_dto_shape_without_concealed_identity():
    schema = json.loads(
        (ROOT / "python-contracts-v1.schema.json").read_text(encoding="utf-8")
    )
    schema["$ref"] = "#/$defs/GameSnapshot"
    fixture = json.loads(
        (ROOT / "fixtures/dummy-session-v1.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(fixture["snapshot"])
    assert fixture["snapshot"]["actions"]
    concealed = [obj for obj in fixture["snapshot"]["objects"] if obj["hidden"]]
    assert concealed
    for obj in concealed:
        assert obj["card_identity"] is None
        assert obj["characteristics"] is None


def test_receive_schema_and_context_checks_have_separate_responsibilities():
    schema = json.loads(
        (ROOT / "wire-receive-v1.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    corpus = json.loads(
        (ROOT / "fixtures/wire-receive-v1.json").read_text(encoding="utf-8")
    )
    for case in corpus["positive"]:
        validator.validate(case["envelope"])
    for case in corpus["negative"]:
        if case["code"] == "RECEIVE_SHAPE":
            assert not validator.is_valid(case["envelope"]), case["name"]
        else:
            validator.validate(case["envelope"])


def test_choice_amount_vector_boundary_is_a_transport_limit():
    schema = json.loads(
        (ROOT / "wire-messages-v1.schema.json").read_text(encoding="utf-8")
    )
    corpus = json.loads(
        (ROOT / "fixtures/wire-messages-v1.json").read_text(encoding="utf-8")
    )
    command = next(
        case["envelope"]
        for case in corpus["positive"]
        if case["name"] == "choose_amounts"
    )
    command["body"]["values"] = [0] * corpus["max_amount_values"]
    validator = Draft202012Validator(schema)
    validator.validate(command)
    command["body"]["values"].append(0)
    assert not validator.is_valid(command)


def test_terminal_error_schema_separates_shape_from_viewer_binding():
    schema = json.loads(
        (ROOT / "wire-errors-v1.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    corpus = json.loads(
        (ROOT / "fixtures/wire-errors-v1.json").read_text(encoding="utf-8")
    )
    for case in corpus["positive"]:
        validator.validate(case["envelope"])
    for case in corpus["negative"]:
        if case["code"] in {"ERROR_SESSION", "ERROR_VIEWER", "ERROR_CONTEXT"}:
            validator.validate(case["envelope"])
        else:
            assert not validator.is_valid(case["envelope"]), case["name"]


def test_receive_history_cases_preserve_existing_wire_shapes():
    schema = json.loads(
        (ROOT / "wire-receive-v1.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)
    corpus = json.loads(
        (ROOT / "fixtures/receive-history-v1.json").read_text(encoding="utf-8")
    )
    for case in corpus["cases"]:
        for step in case["steps"]:
            if step["outcome"] == "RECEIVE_SHAPE":
                assert not validator.is_valid(step["envelope"])
            else:
                validator.validate(step["envelope"])
