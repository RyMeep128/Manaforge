from dataclasses import asdict, replace
import hashlib
import io
from pathlib import Path
import shutil
import threading
import zipfile

import pytest

from mtg_core.datasets import (
    DatasetInstaller,
    DatasetManifest,
    InstallationState,
    parse_manifest,
)
from mtg_core.downloads import DownloadCancelled


def setup_installer(tmp_path, payload=b"new data", **options):
    archive = tmp_path / "fixture"
    archive.write_bytes(payload)
    manifest = DatasetManifest(
        "recommendations",
        "2026.10",
        1,
        "https://fixtures.example/data",
        hashlib.sha256(payload).hexdigest(),
        len(payload),
        **options,
    )
    state = InstallationState(tmp_path / "state.sqlite3")
    state.set("recommendations_root", str(tmp_path / "managed"))

    class Downloader:
        def download(self, url, destination, **kwargs):
            assert kwargs["sha256"] == manifest.sha256
            shutil.copyfile(archive, destination)

    return DatasetInstaller(state, Downloader()), manifest


def test_manifest_schema_is_independent_of_app_version(tmp_path):
    _, manifest = setup_installer(tmp_path)
    document = {"manifest_version": 1, "datasets": [asdict(manifest)]}
    assert parse_manifest(document) == [manifest]
    manifest.require_compatible({"recommendations": {1}})
    with pytest.raises(ValueError, match="schema"):
        manifest.require_compatible({"recommendations": {2}})
    document["datasets"].append(asdict(manifest))
    with pytest.raises(ValueError, match="Duplicate"):
        parse_manifest(document)


def test_failed_update_keeps_old_generation_and_preferences(tmp_path):
    installer, manifest = setup_installer(tmp_path)
    state = installer.state
    state.set("setup_complete", True)
    state.set("artwork_mode", "full_offline")
    old = installer.install(
        manifest, supported_schemas={"recommendations": {1}}, validate=lambda p: None
    )
    old_record = state.installed(manifest.dataset_id)

    def reject(path):
        raise ValueError("Bad dataset contents")

    with pytest.raises(ValueError, match="contents"):
        installer.install(
            replace(manifest, version="2026.11"),
            supported_schemas={"recommendations": {1}},
            validate=reject,
        )
    reopened = InstallationState(state.path)
    assert reopened.installed(manifest.dataset_id) == old_record
    assert old.read_bytes() == b"new data"
    assert reopened.get("setup_complete") is True
    assert reopened.get("artwork_mode") == "full_offline"
    assert list(old.parent.parent.glob("2026.11-*")) == []


def test_successful_update_retains_previous_generation(tmp_path):
    installer, manifest = setup_installer(tmp_path)
    old = installer.install(
        manifest, supported_schemas={"recommendations": {1}}, validate=lambda p: None
    )
    new = installer.install(
        replace(manifest, version="2026.11"),
        supported_schemas={"recommendations": {1}},
        validate=lambda p: None,
    )
    record = installer.state.installed(manifest.dataset_id)
    assert Path(record["path"]) == new and Path(record["previous"]) == old
    assert old.exists() and new.exists()


@pytest.mark.parametrize(
    "filename",
    ["../outside", "/outside", "C:/outside", "data:stream", "CON.txt", "dir\\outside"],
)
def test_unsafe_archive_cannot_escape_staging_or_activate(tmp_path, filename):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(filename, b"bad")
    installer, manifest = setup_installer(
        tmp_path, stream.getvalue(), format="zip", expanded_size=100
    )
    with pytest.raises(ValueError):
        installer.install(
            manifest,
            supported_schemas={"recommendations": {1}},
            validate=lambda p: None,
        )
    assert installer.state.installed(manifest.dataset_id) is None
    assert not (tmp_path / "outside").exists()


def test_extraction_size_limit_and_cancel_preserve_state(tmp_path):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("data.json", b"x" * 100)
    installer, manifest = setup_installer(
        tmp_path, stream.getvalue(), format="zip", expanded_size=10
    )
    with pytest.raises(ValueError, match="size"):
        installer.install(
            manifest,
            supported_schemas={"recommendations": {1}},
            validate=lambda p: None,
        )
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(DownloadCancelled):
        installer.install(
            replace(manifest, expanded_size=100),
            supported_schemas={"recommendations": {1}},
            validate=lambda p: None,
            cancel=cancelled,
        )
    assert installer.state.installed(manifest.dataset_id) is None
