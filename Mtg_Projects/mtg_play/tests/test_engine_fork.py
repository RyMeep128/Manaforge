import hashlib
import json

import pytest

from mtg_play import engine_fork


def test_build_toolchain_drift_is_rejected():
    engine_fork.validate_toolchain(
        'openjdk version "23.0.2"', "Apache Maven 3.9.9 (hash)"
    )
    with pytest.raises(ValueError, match="JDK"):
        engine_fork.validate_toolchain('java version "24.0.1"', "Apache Maven 3.9.9")
    with pytest.raises(ValueError, match="Maven"):
        engine_fork.validate_toolchain('java version "23.0.2"', "Apache Maven 4.0.0")


def test_unapproved_bundle_cannot_pin_itself(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    app = tmp_path / "app"
    app.mkdir()
    monkeypatch.setattr(engine_fork, "HERE", app)
    marker = bundle / "manaforge-engine-lock.json"
    marker.write_text("untrusted")
    with pytest.raises(ValueError, match="not pinned"):
        engine_fork.installation_manifest(bundle)
    approved = app / "engine-lock.json"
    approved.write_text("different")
    with pytest.raises(ValueError, match="not pinned"):
        engine_fork.installation_manifest(bundle)
    approved.write_bytes(marker.read_bytes())
    assert engine_fork.installation_manifest(bundle) == approved
    marker.unlink()
    assert engine_fork.installation_manifest(bundle) == app / "artifacts.json"


def test_artifact_verification_rejects_tampering_and_path_escape(tmp_path):
    jar = tmp_path / "mage.jar"
    jar.write_bytes(b"original")
    manifest = {"artifacts": {"mage.jar": hashlib.sha256(jar.read_bytes()).hexdigest()}}
    engine_fork.verify_artifacts(tmp_path, manifest)
    jar.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        engine_fork.verify_artifacts(tmp_path, manifest)
    with pytest.raises(ValueError, match="unsafe"):
        engine_fork.verify_artifacts(tmp_path, {"artifacts": {"../escape": "wrong"}})


def test_lock_requires_source_and_artifacts(tmp_path):
    path = tmp_path / "lock.json"
    path.write_text(json.dumps({"lock_version": 1}))
    with pytest.raises(ValueError, match="Invalid engine lock"):
        engine_fork.read_lock(path)


def test_build_variants_are_distinct_and_old_app_owned_pins_remain_usable(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(engine_fork, "HERE", tmp_path)
    revision = "b" * 40
    identity = revision + "-" + "c" * 12
    raw = json.dumps(
        dict(
            lock_version=1,
            fork_commit=revision,
            bundle_id=identity,
            artifacts={"jar": "hash"},
        )
    ).encode()
    approved = tmp_path / "engine-lock.json"
    approved.write_bytes(raw)
    candidate = tmp_path / ".engines" / identity
    candidate.mkdir(parents=True)
    (candidate / "manaforge-engine-lock.json").write_bytes(raw)
    assert engine_fork.selected_bundle(tmp_path / "legacy") == candidate
    history = tmp_path / ".engines/pins" / (hashlib.sha256(raw).hexdigest() + ".json")
    history.parent.mkdir()
    history.write_bytes(raw)
    approved.write_text("new pin")
    assert engine_fork.installation_manifest(candidate) == history
    history.write_text("tampered")
    with pytest.raises(ValueError, match="not pinned"):
        engine_fork.installation_manifest(candidate)
    approved.write_text(
        json.dumps(
            dict(
                lock_version=1,
                fork_commit=revision,
                bundle_id="../escape",
                artifacts={"jar": "hash"},
            )
        )
    )
    with pytest.raises(ValueError, match="build variant"):
        engine_fork.read_lock(approved)


def test_only_installed_approved_fork_is_selected(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_fork, "HERE", tmp_path)
    legacy = tmp_path / "stock"
    assert engine_fork.selected_bundle(legacy) == legacy
    raw = json.dumps(
        dict(lock_version=1, fork_commit="a" * 40, artifacts={"jar": "hash"})
    ).encode()
    (tmp_path / "engine-lock.json").write_bytes(raw)
    assert engine_fork.selected_bundle(legacy) == legacy
    candidate = tmp_path / ".engines" / ("a" * 40)
    candidate.mkdir(parents=True)
    with pytest.raises(ValueError, match="not pinned"):
        engine_fork.selected_bundle(legacy)
    (candidate / "manaforge-engine-lock.json").write_bytes(raw)
    assert engine_fork.selected_bundle(legacy) == candidate


def test_private_launch_uses_selected_engine_pin(tmp_path, monkeypatch):
    from mtg_play.launch_manifest import export_launch_manifest
    from mtg_play.contracts import GameSetup, MatchSeat
    from generate_launch_fixtures import native_deck
    from mtg_play.gateway_bootstrap import frame_gateway_manifest

    bundle, app = tmp_path / "bundle", tmp_path / "app"
    bundle.mkdir()
    app.mkdir()
    monkeypatch.setattr(engine_fork, "HERE", app)
    raw = json.dumps(
        {"engine": "1.4.62-V1", "fork_commit": "test", "artifacts": {}}
    ).encode()
    (bundle / "manaforge-engine-lock.json").write_bytes(raw)
    (app / "engine-lock.json").write_bytes(raw)
    setup = GameSetup(
        (MatchSeat("human", "Human"), MatchSeat("ai", "AI", "engine_ai")), "freeform"
    )
    document = native_deck(False)
    payload = export_launch_manifest(
        setup,
        {"human": document, "ai": document},
        manaforge_version="test-alpha.1",
        engine_bundle=bundle,
    )
    assert (
        json.loads(payload)["engine"]["artifact_manifest_sha256"]
        == hashlib.sha256(raw).hexdigest()
    )
    assert frame_gateway_manifest(payload)
