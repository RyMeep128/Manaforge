import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator

from mtg_play.viewer_bootstrap import ViewerBootstrapError, export_viewer_bootstrap
from mtg_play.viewer_bootstrap import frame_viewer_bootstrap


ROOT = Path(__file__).resolve().parents[1] / "protocol"


def test_private_frame_has_exact_big_endian_length_and_no_extra_lifeline_data():
    payload = export_viewer_bootstrap(**arguments())
    framed = frame_viewer_bootstrap(payload)
    assert int.from_bytes(framed[:4], "big") == len(payload)
    assert framed[4:] == payload


def test_private_frame_reaches_inherited_child_stdin_without_argument_credentials():
    child = """
import json, sys
stream = sys.stdin.buffer
header = stream.read(4)
assert len(header) == 4
size = int.from_bytes(header, 'big')
assert 1 <= size <= 16384
value = json.loads(stream.read(size))
assert value['viewer_id'] == 'seat-one'
assert stream.read(1) == b''
print('bootstrap-received')
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", child],
        input=frame_viewer_bootstrap(export_viewer_bootstrap(**arguments())),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert result.stdout.strip() == b"bootstrap-received"
    assert result.stderr == b""


@pytest.mark.parametrize("value", [b"", b"x" * 16385, "private", None])
def test_invalid_frame_input_is_sanitized(value):
    with pytest.raises(ViewerBootstrapError, match="^VIEWER_BOOTSTRAP_INVALID$"):
        frame_viewer_bootstrap(value)


def arguments():
    return dict(
        port=43210,
        session_id="fixture-session",
        viewer_id="seat-one",
        engine_version="fixture-engine",
        artifact_manifest_sha256="a" * 64,
        viewer_key=bytes(range(32)),
    )


def test_export_matches_shared_synthetic_fixture_and_schema():
    payload = export_viewer_bootstrap(**arguments())
    corpus = json.loads((ROOT / "fixtures/viewer-bootstrap-v1.json").read_text())
    schema = json.loads((ROOT / "viewer-bootstrap-v1.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    assert json.loads(payload) == corpus["positive"][0]
    validator.validate(json.loads(payload))
    for case in corpus["negative"]:
        assert not validator.is_valid(case["value"]), case["name"]
    assert b"owner" not in payload and b"deck" not in payload


def test_optional_artwork_pin_is_context_only_and_key_input_is_unchanged(tmp_path):
    args = arguments()
    key = bytearray(args["viewer_key"])
    args.update(
        viewer_key=key,
        artwork_directory=str(tmp_path),
        artwork_manifest_sha256="b" * 64,
    )
    value = json.loads(export_viewer_bootstrap(**args))
    assert value["artwork"] == dict(directory=str(tmp_path), manifest_sha256="b" * 64)
    assert bytes(key) == bytes(range(32))
    assert list(tmp_path.iterdir()) == []


def test_network_or_invalid_unicode_artwork_paths_are_sanitized(tmp_path):
    for directory in (
        r"\\server\private",
        "//server/private",
        str(tmp_path) + "/\ud800",
    ):
        args = arguments()
        args.update(artwork_directory=directory, artwork_manifest_sha256="b" * 64)
        with pytest.raises(ViewerBootstrapError, match="^VIEWER_BOOTSTRAP_INVALID$"):
            export_viewer_bootstrap(**args)


@pytest.mark.parametrize(
    "field,value",
    [
        ("port", True),
        ("port", 0),
        ("port", 65536),
        ("session_id", "private name"),
        ("viewer_id", ""),
        ("engine_version", "engine\n"),
        ("artifact_manifest_sha256", "A" * 64),
        ("viewer_key", b"short"),
        ("viewer_key", "0" * 64),
        ("artwork_directory", "relative"),
        ("artwork_manifest_sha256", "b" * 64),
    ],
)
def test_invalid_bootstrap_is_sanitized(field, value):
    args = arguments()
    args[field] = value
    with pytest.raises(ViewerBootstrapError, match="^VIEWER_BOOTSTRAP_INVALID$"):
        export_viewer_bootstrap(**args)
