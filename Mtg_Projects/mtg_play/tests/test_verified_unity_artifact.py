"""Release packaging only admits a successful, exact-source Unity artifact."""

import hashlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
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
    monkeypatch,
    helper,
    *,
    source="a" * 40,
    extra=None,
    run="success",
    job="success",
    tamper=False,
):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("Artifacts/commit.txt", source)
        archive.writestr("Builds/Windows/ManaforgePlay.exe", b"public fixture player")
        archive.writestr("Builds/Windows/UnityPlayer.dll", b"public fixture library")
        if extra:
            archive.writestr(extra, b"unexpected")
    payload = stream.getvalue()
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    if tamper:
        payload += b"changed"

    def api(path):
        if "workflows/" in path:
            return {
                "workflow_runs": [
                    {
                        "id": 7,
                        "head_sha": "a" * 40,
                        "status": "completed",
                        "conclusion": run,
                        "html_url": "https://github.com/example/run/7",
                    }
                ]
            }
        if "/jobs?" in path:
            return {"jobs": [{"conclusion": job}]}
        if "/artifacts?" in path:
            return {
                "artifacts": [
                    {
                        "name": "unity-play-" + "a" * 40,
                        "expired": False,
                        "digest": digest,
                        "size_in_bytes": len(payload),
                        "archive_download_url": "https://api.github.com/example/artifact",
                    }
                ]
            }
        raise AssertionError(path)

    monkeypatch.setattr(helper, "api", api)
    monkeypatch.setenv("GH_TOKEN", "public-fixture-token")
    monkeypatch.setattr(
        helper.urllib.request,
        "build_opener",
        lambda *args: SimpleNamespace(open=lambda *args, **kwargs: io.BytesIO(payload)),
    )


def test_exact_successful_player_can_be_packaged(helper, monkeypatch, tmp_path):
    artifact(monkeypatch, helper)
    target = tmp_path / "Windows"
    helper.prepare("example/repo", "a" * 40, target)
    assert (target / "ManaforgePlay.exe").read_bytes() == b"public fixture player"
    assert (target / "UnityPlayer.dll").is_file()


@pytest.mark.parametrize("options", [{"run": "failure"}, {"job": "skipped"}])
def test_incomplete_checks_cannot_supply_a_player(
    helper, monkeypatch, tmp_path, options
):
    artifact(monkeypatch, helper, **options)
    with pytest.raises(SystemExit, match="VERIFIED_UNITY_PLAYER_UNAVAILABLE"):
        helper.prepare("example/repo", "a" * 40, tmp_path / "Windows")


@pytest.mark.parametrize(
    "options",
    [{"source": "b" * 40}, {"tamper": True}, {"extra": "Builds/Windows/../escape.exe"}],
)
def test_untrusted_payloads_are_rejected_before_extraction(
    helper, monkeypatch, tmp_path, options
):
    artifact(monkeypatch, helper, **options)
    target = tmp_path / "Windows"
    with pytest.raises(ValueError):
        helper.prepare("example/repo", "a" * 40, target)
    assert not target.exists()
    assert not (tmp_path / "escape.exe").exists()
