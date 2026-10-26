"""Real filesystem fixtures for reviewed, path-preserving artwork cleanup."""

from contextlib import closing
import os
from pathlib import Path
import threading
import subprocess

import pytest

from mtg_core import artwork_storage as storage
from mtg_core.artwork_storage import ArtworkStorage
from mtg_core.downloads import DownloadCancelled
from mtg_core.services import CardService


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "images"
    service = CardService(
        db_path=str(tmp_path / "cards.sqlite3"),
        image_root=str(root),
        fetch_bytes_fn=lambda url: b"artwork",
    )
    service.database.image_storage_root = root / "assets"
    service.database.upsert_card_payload(
        dict(id="card", name="Card", set="tst", collector_number="1")
    )
    asset_id = service.store_image_bytes(b"artwork", source="scryfall")
    canonical = Path(service.materialize_image_asset(asset_id))
    legacy = Path(
        service.materialize_image_asset(
            asset_id, output_root=str(root / "mtg_core_cache")
        )
    )
    asset = service.database.get_image_asset(asset_id)
    service.database.upsert_image_record(
        "card",
        asset_id=asset_id,
        path=str(legacy),
        status="ready",
        source="scryfall",
        checksum=asset.checksum,
    )
    return service, canonical, legacy, ArtworkStorage(service.database, root)


def audit(manager):
    return manager.audit(cancel=threading.Event(), report=lambda value: None)


def reclaim(manager):
    return manager.reclaim(cancel=threading.Event(), report=lambda value: None)


def test_verified_duplicate_becomes_link_and_old_saved_path_stays_readable(library):
    service, canonical, legacy, manager = library
    result = audit(manager)
    assert result["duplicates"] == 1
    assert result["reclaimable_bytes"] == len(b"artwork")
    assert result["logical_bytes"] == result["unique_bytes"] == 2 * len(b"artwork")
    result = reclaim(manager)
    assert result["reclaimed_bytes"] == len(b"artwork")
    assert os.path.samefile(canonical, legacy)
    assert legacy.read_bytes() == b"artwork"  # Saved project path still works offline.
    assert service.get_image_path("card") == str(canonical)
    second = audit(manager)
    assert second["reclaimable_bytes"] == 0
    assert second["already_linked"] == 1
    assert second["unique_bytes"] == len(b"artwork")
    assert reclaim(manager)["reclaimed_bytes"] == 0


def test_normal_browsing_and_faces_do_not_recreate_full_cache(library):
    service, canonical, legacy, _ = library
    legacy.unlink()
    for variant in ("default", "face-1", "back"):
        service.database.upsert_image_record(
            "card",
            variant=variant,
            asset_id=canonical.stem,
            path=str(legacy),
            status="ready",
            source="scryfall",
        )
        assert service.get_image_path("card", variant) == str(canonical)
        assert not legacy.exists()
    assert service.ensure_image("card", allow_remote=False) == str(canonical)


def test_explicit_exports_are_independent_files(library, tmp_path):
    service, canonical, _, _ = library
    export = Path(
        service.materialize_image_asset(
            canonical.stem, output_root=str(tmp_path / "export")
        )
    )
    assert export.read_bytes() == canonical.read_bytes()
    assert not os.path.samefile(canonical, export)


def test_repair_restores_manifest_path_without_a_cache_copy_or_downloader(library):
    from types import SimpleNamespace
    from mtg_core.repair import RepairService

    service, canonical, legacy, _ = library
    legacy.unlink()
    engine = SimpleNamespace(service=service)
    RepairService(engine).artwork(threading.Event(), lambda progress: None, repair=True)
    assert service.database.get_image_record("card").path == str(canonical)
    assert not legacy.exists()
    assert canonical.read_bytes() == b"artwork"


@pytest.mark.parametrize("target", ["canonical", "legacy"])
@pytest.mark.parametrize("failure", ["missing", "corrupt"])
def test_missing_or_corrupt_artwork_is_preserved(library, target, failure):
    _, canonical, legacy, manager = library
    path = canonical if target == "canonical" else legacy
    if failure == "missing":
        path.unlink()
    else:
        path.write_bytes(b"custom or damaged")
    before = legacy.read_bytes() if legacy.exists() else None
    result = audit(manager)
    assert result["reclaimable_bytes"] == 0
    assert result["problems"]
    assert reclaim(manager)["reclaimed_bytes"] == 0
    assert (legacy.read_bytes() if legacy.exists() else None) == before


def test_custom_and_unknown_files_are_not_cleanup_candidates(library):
    service, _, legacy, manager = library
    with closing(service.database.connect()) as db, db:
        db.execute("UPDATE image_manifest SET source='custom'")
    unknown = legacy.with_name("unknown.jpg")
    unknown.write_bytes(b"original")
    result = audit(manager)
    assert result["duplicates"] == 0
    assert result["unknown_files"] == 1
    assert result["preserved"] == 1
    reclaim(manager)
    assert unknown.read_bytes() == b"original"
    assert legacy.read_bytes() == b"artwork"


def test_ownership_change_after_review_is_preserved(library):
    service, canonical, legacy, manager = library
    audit(manager)
    with closing(service.database.connect()) as db, db:
        db.execute("UPDATE image_manifest SET source='custom'")
    assert reclaim(manager)["reclaimed_bytes"] == 0
    assert not os.path.samefile(canonical, legacy)


def test_cancel_and_restart_reuses_verified_hashes(library, monkeypatch):
    _, canonical, _, manager = library
    cancel = threading.Event()
    original = storage.digest
    hashed = []

    def digest(path, event):
        result = original(path, event)
        hashed.append(path)
        if path == canonical:
            cancel.set()
        return result

    monkeypatch.setattr(storage, "digest", digest)
    with pytest.raises(DownloadCancelled):
        manager.audit(cancel=cancel, report=lambda value: None)

    def resumed_digest(path, event):
        hashed.append(path)
        return original(path, event)

    monkeypatch.setattr(storage, "digest", resumed_digest)
    assert audit(manager)["duplicates"] == 1
    assert hashed.count(canonical) == 1


@pytest.mark.parametrize("operation", ["link", "replace"])
def test_unsupported_link_or_locked_destination_keeps_original(
    library, monkeypatch, operation
):
    _, canonical, legacy, manager = library
    audit(manager)

    def fail(*args, **kwargs):
        raise PermissionError("locked or unsupported")

    monkeypatch.setattr(storage.os, operation, fail)
    result = reclaim(manager)
    assert result["reclaimed_bytes"] == 0
    assert not os.path.samefile(canonical, legacy)
    assert legacy.read_bytes() == b"artwork"
    assert not list(legacy.parent.glob("*.dedup-*"))


def test_race_before_replace_preserves_changed_legacy_file(library, monkeypatch):
    _, canonical, legacy, manager = library
    audit(manager)
    original = os.link

    def change_after_link(source, target):
        original(source, target)
        legacy.write_bytes(b"changed artwork")

    monkeypatch.setattr(storage.os, "link", change_after_link)
    assert reclaim(manager)["reclaimed_bytes"] == 0
    assert legacy.read_bytes() == b"changed artwork"
    assert canonical.read_bytes() == b"artwork"


def test_interruption_after_atomic_replace_recovers_without_deleting_paths(library):
    _, canonical, legacy, manager = library
    audit(manager)
    temporary = legacy.with_name(legacy.name + ".dedup-recovery")
    with closing(manager.connect()) as db, db:
        db.execute("UPDATE pairs SET status='prepared',temporary=?", (str(temporary),))
    os.link(canonical, temporary)
    os.replace(temporary, legacy)  # Simulates interruption before journal completion.
    assert audit(manager)["already_linked"] == 1
    assert legacy.read_bytes() == b"artwork"
    assert reclaim(manager)["reclaimed_bytes"] == 0


def test_cannot_reclaim_without_completed_audit(library):
    _, _, _, manager = library
    with pytest.raises(ValueError, match="review"):
        reclaim(manager)


def test_writing_canonical_asset_does_not_modify_existing_hard_link(library):
    service, canonical, legacy, manager = library
    audit(manager)
    reclaim(manager)
    assert os.path.samefile(canonical, legacy)
    # Immutable publication replaces a directory entry, never writes into a link.
    service.database._write_verified_image_asset_file(
        canonical, b"artwork", service.database.get_image_record("card").checksum
    )
    assert canonical.read_bytes() == legacy.read_bytes() == b"artwork"
    assert not os.path.samefile(canonical, legacy)


def test_existing_root_junction_maps_old_paths_to_physical_library(library, tmp_path):
    service, canonical, legacy, manager = library
    alias = tmp_path / "old-images"
    if os.name == "nt":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(alias), str(manager.root)],
            check=True,
            capture_output=True,
        )
    else:
        alias.symlink_to(manager.root, target_is_directory=True)
    try:
        old_legacy = alias / legacy.relative_to(manager.root)
        old_canonical = alias / canonical.relative_to(manager.root)
        with closing(service.database.connect()) as db, db:
            db.execute("UPDATE image_manifest SET path=?", (str(old_legacy),))
            db.execute("UPDATE image_assets SET storage_path=?", (str(old_canonical),))
        assert audit(manager)["duplicates"] == 1
        assert reclaim(manager)["reclaimed_bytes"] == len(b"artwork")
        assert old_legacy.read_bytes() == b"artwork"
        assert os.path.samefile(old_legacy, canonical)
    finally:
        if os.name == "nt":
            alias.rmdir()  # Remove the junction only, never its target.
        else:
            alias.unlink()


def test_additional_legacy_hard_links_are_not_claimed_as_savings(library):
    _, canonical, legacy, manager = library
    other = legacy.with_name("another-path.png")
    os.link(legacy, other)
    result = audit(manager)
    assert result["reclaimable_bytes"] == 0
    assert result["unique_bytes"] == 2 * len(b"artwork")
    assert reclaim(manager)["reclaimed_bytes"] == 0
    assert not os.path.samefile(canonical, legacy)


def test_serializes_canonical_publication_with_cleanup(library):
    from mtg_core.artwork_storage_lock import storage_lock

    _, canonical, _, manager = library
    entered, finished = threading.Event(), threading.Event()

    def writer():
        entered.set()
        with storage_lock(manager.root):
            finished.set()

    with storage_lock(manager.root):
        worker = threading.Thread(target=writer)
        worker.start()
        assert entered.wait(5)
        assert not finished.wait(0.05)
        assert canonical.read_bytes() == b"artwork"
    worker.join(5)
    assert finished.is_set()


def test_unsigned_windows_identifiers_are_preserved_exactly(library, monkeypatch):
    from types import SimpleNamespace

    _, canonical, legacy, manager = library
    original = Path.stat
    device = 11121873872395515817  # Actual unsigned volume ID from the E: library.

    def large_identifiers(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        if path not in (canonical, legacy):
            return info
        return SimpleNamespace(
            st_dev=device,
            st_ino=2**100 + info.st_ino,
            st_mode=info.st_mode,
            st_size=info.st_size,
            st_mtime_ns=info.st_mtime_ns,
            st_nlink=info.st_nlink,
        )

    monkeypatch.setattr(Path, "stat", large_identifiers)
    result = audit(manager)
    assert result["duplicates"] == 1
    assert result["unique_bytes"] == 2 * len(b"artwork")
    with closing(manager.connect()) as db:
        rows = db.execute("SELECT device,inode,typeof(device) FROM files").fetchall()
        assert all(row[0] == str(device) and row[2] == "text" for row in rows)
        assert all(int(row[1]) >= 2**100 for row in rows)


def test_existing_journal_migrates_without_losing_verified_progress(library):
    _, _, _, manager = library
    audit(manager)
    with closing(manager.connect()) as db, db:
        before = [
            tuple(r)
            for r in db.execute(
                "SELECT path,checksum,signature FROM files ORDER BY path"
            )
        ]
        db.execute("ALTER TABLE files RENAME TO files_new")
        db.execute("""CREATE TABLE files (
            path TEXT PRIMARY KEY, signature TEXT, device INTEGER, inode TEXT,
            bytes INTEGER, links INTEGER, checksum TEXT, seen TEXT, role TEXT)""")
        db.execute("INSERT INTO files SELECT * FROM files_new")
        db.execute("DROP TABLE files_new")
    with closing(manager.connect()) as db:
        columns = {r["name"]: r["type"] for r in db.execute("PRAGMA table_info(files)")}
        assert columns["device"] == "TEXT"
        after = [
            tuple(r)
            for r in db.execute(
                "SELECT path,checksum,signature FROM files ORDER BY path"
            )
        ]
        assert before == after
    assert audit(manager)["duplicates"] == 1
