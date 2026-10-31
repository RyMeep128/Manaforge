import json
from pathlib import Path
from jsonschema import Draft202012Validator


def test_shared_challenge_schema_matches_public_corpus():
    root = Path(__file__).resolve().parents[1] / "protocol"
    schema = json.loads((root / "viewer-challenge-v1.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    corpus = json.loads((root / "fixtures/viewer-challenge-v1.json").read_text())
    for item in corpus["positive"]:
        validator.validate(item["envelope"])
    for item in corpus["negative"]:
        assert not validator.is_valid(item["envelope"])
