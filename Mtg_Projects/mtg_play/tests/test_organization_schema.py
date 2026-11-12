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
