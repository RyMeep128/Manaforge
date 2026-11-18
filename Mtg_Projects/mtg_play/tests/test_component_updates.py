"""Release integrity, compatibility and activation regression cases (run in CI)."""

import hashlib
import json
import os
from pathlib import Path
import threading
import subprocess
import sys
import zipfile

import pytest

from mtg_core.downloads import atomic_json, DownloadCancelled
from mtg_play import component_updates as updates, runtime_distribution as runtime
from mtg_play import engine_fork
from mtg_proxy.constants import APP_VERSION


@pytest.fixture
def payload(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "component_root", lambda: tmp_path / "components")
    monkeypatch.setattr(runtime, "bundled_root", lambda: tmp_path / "bundled")
    monkeypatch.setattr(updates, "online", lambda: None)
    monkeypatch.setattr(updates.sys, "platform", "win32")
    monkeypatch.setattr(updates, "health", lambda root, cancel: None)
    revision = "a" * 40
    root = tmp_path / "bundled/xmage"
    content = {
        "engine.jar": b"engine",
        "bridge/classes/ManaforgeBridge.class": b"classes",
        "java/jre1.8.0_201/bin/java.exe": b"java",
    }
    lock = dict(
        lock_version=1,
        fork_commit=revision,
        engine="1.4.62-V1",
        artifacts={"engine.jar": hashlib.sha256(b"engine").hexdigest()},
    )
    content["manaforge-engine-lock.json"] = json.dumps(lock).encode()
    for name, raw in content.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    archive = tmp_path / "payload.zip"
    with zipfile.ZipFile(archive, "w") as target:
        for name, raw in content.items():
            target.writestr(name, raw)
    manifest = dict(
        schema=1,
        platform="windows-x64",
        bundle_id=revision,
        component_version="99.0.1-alpha.1",
        bridge_fingerprint="b" * 64,
        compatible_app_versions=[APP_VERSION],
        payload_sha256=runtime.sha256(archive),
        size=archive.stat().st_size,
        url=updates.REPOSITORY + "xmage-v99.0.1-alpha.1/Manaforge-XMage-Windows.zip",
        files={name: hashlib.sha256(raw).hexdigest() for name, raw in content.items()},
    )
    atomic_json(
        root / "component.json", dict(manifest, component_version="0.0.1-alpha.1")
    )
    (tmp_path / "app").mkdir()
    (tmp_path / "app/engine-lock.json").write_bytes(
        content["manaforge-engine-lock.json"]
    )
    monkeypatch.setattr(engine_fork, "HERE", tmp_path / "app")

    class Downloader:
        def download(self, url, path, **kwargs):
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read_bytes())

    return root, archive, manifest, Downloader()


def install(payload):
    return updates.install(
        payload[2],
        cancel=threading.Event(),
        progress=lambda p: None,
        downloader=payload[3],
    )


def test_install_activates_verified_approved_bundle_without_modifying_baseline(payload):
    baseline, _, manifest, _ = payload
    install(payload)
    selected = runtime.selected_engine()
    assert selected != baseline
    assert runtime.approved_record(selected) == manifest
    assert runtime.bridge_classes(selected).is_dir()
    assert (
        engine_fork.installation_manifest(selected)
        == selected / "manaforge-engine-lock.json"
    )
    assert (
        json.loads((baseline / "component.json").read_text())["component_version"]
        == "0.0.1-alpha.1"
    )


def test_failed_health_preserves_active_engine(payload, monkeypatch):
    monkeypatch.setattr(
        updates,
        "health",
        lambda *args: (_ for _ in ()).throw(ValueError("bad handshake")),
    )
    with pytest.raises(ValueError, match="bad handshake"):
        install(payload)
    assert runtime.selected_engine() == payload[0]
    assert not (runtime.component_root() / "active.json").exists()


def test_incompatible_app_and_bridge_are_rejected(payload):
    _, _, manifest, _ = payload
    for change in (
        dict(compatible_app_versions=["0.0.0-alpha.1"]),
        dict(bridge_fingerprint="c" * 64),
    ):
        with pytest.raises(ValueError, match="different Manaforge"):
            updates.validate_offer(dict(manifest, **change))


def test_corrupt_installed_engine_falls_back(payload):
    install(payload)
    selected = runtime.selected_engine()
    (selected / "engine.jar").write_bytes(b"corrupt")
    assert runtime.selected_engine() == payload[0]


def test_extra_engine_jar_cannot_enter_runtime_classpath(payload):
    install(payload)
    selected = runtime.selected_engine()
    (selected / "unapproved.jar").write_bytes(b"stale engine module")
    assert runtime.selected_engine() == payload[0]


def test_changed_app_ignores_incompatible_override(payload):
    install(payload)
    baseline = payload[0] / "component.json"
    value = json.loads(baseline.read_text())
    value["bridge_fingerprint"] = "d" * 64
    atomic_json(baseline, value)
    assert runtime.selected_engine() == payload[0]


@pytest.mark.parametrize(
    "name", ["../outside", "/outside", "C:/outside", "a\\outside", "a/../outside"]
)
def test_archive_traversal_rejected(payload, tmp_path, name):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as target:
        target.writestr(name, b"evil")
    destination = tmp_path / "extract"
    destination.mkdir()
    with pytest.raises(ValueError):
        updates.extract(archive, destination, payload[2], threading.Event())
    assert not (tmp_path / "outside").exists()


def test_unapproved_bundle_cannot_bless_itself(payload, tmp_path):
    bundle = tmp_path / "unknown"
    bundle.mkdir()
    (bundle / "manaforge-engine-lock.json").write_text('{"new": "engine"}')
    atomic_json(bundle / "component.json", payload[2])
    with pytest.raises(ValueError, match="not pinned"):
        engine_fork.installation_manifest(bundle)


def test_cancellation_before_activation_keeps_baseline(payload, monkeypatch):
    cancel = threading.Event()
    monkeypatch.setattr(updates, "health", lambda root, event: event.set())
    with pytest.raises(DownloadCancelled):
        updates.install(
            payload[2], cancel=cancel, progress=lambda p: None, downloader=payload[3]
        )
    assert runtime.selected_engine() == payload[0]


def test_active_game_defers_update(payload):
    errors = []
    with runtime.ownership():
        thread = threading.Thread(target=lambda: capture_install(payload, errors))
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert len(errors) == 1 and "active" in str(errors[0])
    assert runtime.selected_engine() == payload[0]


def capture_install(payload, errors):
    try:
        install(payload)
    except ValueError as error:
        errors.append(error)


def test_incomplete_archive_rejected(payload, tmp_path):
    archive = tmp_path / "empty.zip"
    with zipfile.ZipFile(archive, "w"):
        pass
    destination = tmp_path / "extract"
    destination.mkdir()
    with pytest.raises(ValueError, match="Incomplete"):
        updates.extract(archive, destination, payload[2], threading.Event())


def test_release_check_offers_only_exact_compatible_engine(payload, monkeypatch):
    manifest = payload[2]
    tag = "xmage-v" + manifest["component_version"]
    release = dict(
        tag_name=tag,
        assets=[
            dict(
                name="xmage-component.json",
                browser_download_url=updates.REPOSITORY + tag + "/xmage-component.json",
            )
        ],
    )
    monkeypatch.setattr(updates, "fetch_latest_release_json", lambda url: [release])

    class Metadata:
        def download(self, url, path, **kwargs):
            atomic_json(path, manifest)

    assert updates.check(cancel=threading.Event(), downloader=Metadata()) == manifest
    manifest["compatible_app_versions"] = ["0.0.0-alpha.1"]
    with pytest.raises(ValueError, match="No XMage release is approved"):
        updates.check(cancel=threading.Event(), downloader=Metadata())


def test_offline_check_never_fetches(payload, monkeypatch):
    def offline():
        raise ValueError("Offline mode")

    monkeypatch.setattr(updates, "online", offline)
    monkeypatch.setattr(
        updates, "fetch_latest_release_json", lambda url: pytest.fail("network request")
    )
    with pytest.raises(ValueError, match="Offline"):
        updates.check(cancel=threading.Event())


def test_second_process_cannot_activate_during_game(payload):
    code = """
import sys
from pathlib import Path
from mtg_play import runtime_distribution as runtime
runtime.component_root = lambda: Path(sys.argv[1])
try:
    with runtime.ownership():
        raise SystemExit(3)
except ValueError:
    print('deferred')
"""
    with runtime.ownership():
        process = subprocess.run(
            [sys.executable, "-c", code, str(runtime.component_root())],
            capture_output=True,
            text=True,
            timeout=20,
            env=dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path)),
        )
    assert process.returncode == 0, process.stderr
    assert process.stdout.strip() == "deferred"


def test_rollback_to_bundled_engine(payload, monkeypatch):
    install(payload)
    monkeypatch.setattr(runtime, "verify_bundled", lambda: None)
    updates.rollback(cancel=threading.Event(), progress=lambda p: None)
    # Previous external engine is retained for reversing the rollback.
    state = json.loads((runtime.component_root() / "active.json").read_text())
    assert state["active"] is None and state["previous"]
    assert runtime.selected_engine() == payload[0]
