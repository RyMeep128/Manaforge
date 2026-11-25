"""Disk retention must never remove an active or unconfirmed engine workspace."""

import json

from mtg_play import session_storage as storage


def session(root, number, *, reaped=True, database=True):
    path = root / f"20261124-120000-{number:08x}"
    path.mkdir(parents=True)
    result = {
        "success": False,
        "compiler": {"started": False},
        "bridge": {"started": True, "reaped": reaped},
        "server": {"started": True, "reaped": reaped},
    }
    (path / "result.json").write_text(json.dumps(result))
    (path / "classes").mkdir()
    (path / "classes/Bridge.class").write_bytes(b"compiled")
    if database:
        (path / "server/db").mkdir(parents=True)
        (path / "server/db/cards.h2.mv.db").write_bytes(b"database")
    (path / "bridge.log").write_bytes(b"old log contents\nfinal error")
    return path


def test_bounds_diagnostics_and_keeps_only_latest_initialized_catalog(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(storage, "MAX_SESSIONS", 2)
    monkeypatch.setattr(storage, "MAX_LOG_BYTES", 11)
    old = session(tmp_path, 1)
    catalog = session(tmp_path, 2)
    latest = session(tmp_path, 3, database=False)
    (latest / "private-bootstrap.json").write_text("secret")

    assert storage.prune_sessions(tmp_path) == []
    assert not old.exists()
    assert (catalog / "server/db/cards.h2.mv.db").read_bytes() == b"database"
    assert not (catalog / "classes").exists()
    assert not (latest / "private-bootstrap.json").exists()
    assert (latest / "bridge.log").read_bytes() == b"final error"
    assert json.loads((latest / "result.json").read_text())["success"] is False
    assert storage.prune_sessions(tmp_path) == []

    newer = session(tmp_path, 4)
    assert storage.prune_sessions(tmp_path) == []
    assert not catalog.exists()
    assert (newer / "server/db/cards.h2.mv.db").is_file()


def test_preserves_unfinished_uncertain_malformed_and_unknown_directories(tmp_path):
    unfinished = session(tmp_path, 1)
    (unfinished / "result.json").unlink()
    uncertain = session(tmp_path, 2, reaped=False)
    malformed = session(tmp_path, 3)
    (malformed / "result.json").write_text("not json")
    missing_state = session(tmp_path, 4)
    (missing_state / "result.json").write_text('{"success":true}')
    unknown = tmp_path / "installed"
    unknown.mkdir()
    (unknown / "payload").write_bytes(b"keep")

    assert storage.prune_sessions(tmp_path) == [str(malformed)]
    for path in (unfinished, uncertain, malformed, missing_state):
        assert (path / "server/db/cards.h2.mv.db").is_file()
    assert (unknown / "payload").read_bytes() == b"keep"


def test_peer_shutdown_must_also_be_confirmed(tmp_path):
    path = session(tmp_path, 1)
    result = json.loads((path / "result.json").read_text())
    result["peer_0"] = {"started": True, "reaped": False}
    (path / "result.json").write_text(json.dumps(result))
    assert storage.prune_sessions(tmp_path) == []
    assert (path / "classes/Bridge.class").is_file()


def test_legacy_completed_runs_without_compiler_record_are_maintained(tmp_path):
    path = session(tmp_path, 1)
    result = json.loads((path / "result.json").read_text())
    del result["compiler"]
    (path / "result.json").write_text(json.dumps(result))
    assert storage.prune_sessions(tmp_path) == []
    assert not (path / "classes").exists()
    assert (path / "server/db/cards.h2.mv.db").is_file()


def test_storage_failure_is_reported_without_discarding_result(tmp_path, monkeypatch):
    path = session(tmp_path, 1)
    original = storage._remove

    def locked(target, parent):
        if target.name == "classes":
            raise PermissionError("locked")
        original(target, parent)

    monkeypatch.setattr(storage, "_remove", locked)
    assert storage.prune_sessions(tmp_path) == [str(path)]
    assert (path / "result.json").is_file()


def test_does_not_follow_session_or_child_links(tmp_path):
    import pytest

    root = tmp_path / "sessions"
    root.mkdir()
    external = session(tmp_path / "external", 1)
    linked = root / external.name
    try:
        linked.symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks is unavailable")
    assert storage.prune_sessions(root) == []
    assert (external / "classes/Bridge.class").is_file()
    owned = session(root, 2)
    (owned / "private").symlink_to(external, target_is_directory=True)
    assert storage.prune_sessions(root) == [str(owned)]
    assert (external / "classes/Bridge.class").is_file()
