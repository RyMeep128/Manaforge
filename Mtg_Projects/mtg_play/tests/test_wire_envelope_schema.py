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

    for case in corpus.get("current", []):
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
