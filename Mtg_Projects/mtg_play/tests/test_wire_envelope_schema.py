"""Keep the public header schema aligned with the shared consumer corpus."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1] / "protocol"


def test_shared_envelopes_match_header_schema():
    schema = json.loads(
        (ROOT / "wire-envelope-v1.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    corpus = json.loads(
        (ROOT / "fixtures/wire-envelopes-v1.json").read_text(encoding="utf-8")
    )
    for case in corpus["positive"]:
        validator.validate(json.loads(case["text"]))
    for case in corpus["negative"]:
        # Raw syntax, duplicate keys and depth are parser responsibilities.
        if case["code"].startswith("ENVELOPE_"):
            assert not validator.is_valid(json.loads(case["text"])), case["name"]
