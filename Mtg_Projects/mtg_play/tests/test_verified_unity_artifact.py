"""Local Unity evidence must match the release source and player bytes."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import zipfile

import pytest


@pytest.fixture
def helper():
    path = (
        Path(__file__).resolve().parents[3] / "tools/prepare_verified_unity_player.py"
    )
    spec = importlib.util.spec_from_file_location("verified_unity_player", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def artifact(
    helper,
    *,
    commit="a" * 40,
    dirty=False,
    status="passed",
    missing=False,
    extra=None,
    tamper=False,
):
    files = {
        "Builds/Windows/ManaforgePlay.exe": b"fixture player",
        "Builds/Windows/UnityPlayer.dll": b"fixture library",
        "Artifacts/editmode.xml": b"fixture tests",
        "Artifacts/playmode.xml": b"fixture tests",
    }
    if extra:
        files[extra] = b"unexpected"
    stages = [{"name": name, "status": "passed"} for name in helper.REQUIRED_STAGES]
    report = {
        "schema": 1,
        "commit": commit,
        "dirty": dirty,
        "status": status,
        "stages": stages[:-1] if missing else stages,
        "files": {
            name: hashlib.sha256(data).hexdigest() for name, data in files.items()
        },
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("validation.json", json.dumps(report))
        for name, data in files.items():
            archive.writestr(name, data + b"changed" if tamper else data)
    stream.seek(0)
    return stream


def test_exact_successful_local_player_can_be_packaged(helper, tmp_path):
    target = tmp_path / "Windows"
    helper.extract(artifact(helper), "a" * 40, target)
    assert (target / "ManaforgePlay.exe").read_bytes() == b"fixture player"
    assert (
        json.loads((target / "local-validation.json").read_text())["commit"] == "a" * 40
    )
    assert not (tmp_path / "Artifacts").exists()


@pytest.mark.parametrize(
    "options",
    [
        {"commit": "b" * 40},
        {"dirty": True},
        {"status": "failed"},
        {"missing": True},
        {"tamper": True},
        {"extra": "Builds/Windows/../escape.exe"},
        {"extra": "Builds/Windows/C:escape.exe"},
        {"extra": "Builds/Windows/manaforgeplay.exe"},
    ],
)
def test_invalid_evidence_is_rejected_before_extraction(helper, tmp_path, options):
    target = tmp_path / "Windows"
    with pytest.raises(ValueError):
        helper.extract(artifact(helper, **options), "a" * 40, target)
    assert not target.exists()
    assert not (tmp_path / "escape.exe").exists()


def test_download_checksum_is_checked_before_import(helper, monkeypatch, tmp_path):
    class Response(io.BytesIO):
        url = "https://example.com/unity.zip"

    monkeypatch.setattr(
        helper.urllib.request,
        "urlopen",
        lambda *args, **kwargs: Response(artifact(helper).getvalue()),
    )
    target = tmp_path / "Windows"
    with pytest.raises(ValueError, match="archive checksum"):
        helper.prepare("https://example.com/unity.zip", "0" * 64, "a" * 40, target)
    assert not target.exists()
