"""Schema half of the corpus; Java/C# additionally enforce lexical/context rules."""

import json
from pathlib import Path

import jsonschema
import pytest

PROTOCOL = Path(__file__).resolve().parents[1] / "protocol"
SCHEMA = json.loads(
    (PROTOCOL / "organization-v1.schema.json").read_text(encoding="utf-8")
)
CORPUS = json.loads(
    (PROTOCOL / "fixtures/organization-v1.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", CORPUS["cases"], ids=lambda case: case["name"])
def test_organization_schema_corpus(case):
    try:
        message = json.loads(case["text"])
    except ValueError:
        valid = False
    else:
        valid = jsonschema.Draft202012Validator(SCHEMA).is_valid(message)
    assert valid == case["schema_valid"]
