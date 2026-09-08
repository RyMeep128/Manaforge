import json
from pathlib import Path

import project_library


def _set_project_library_roots(monkeypatch, tmp_path):
    monkeypatch.setattr(project_library, "cwd", str(tmp_path))
    monkeypatch.setattr(project_library, "app_dir", str(tmp_path))


def _seed_test_back(tmp_path):
    test_images_dir = tmp_path / "test_Images"
    test_images_dir.mkdir()
    (test_images_dir / "__back.jpg").write_bytes(b"shared-back")


def test_create_project_adds_library_entry_with_db_backed_default_back(monkeypatch, tmp_path):
    _set_project_library_roots(monkeypatch, tmp_path)
    _seed_test_back(tmp_path)

    entry = project_library.create_project("Alpha Project")

    assert entry["display_name"] == "Alpha Project"
    assert (tmp_path / "projects" / "library.json").exists()
    project_data = json.loads(Path(entry["path"]).read_text(encoding="utf-8"))
    assert project_data["backside_default"] == "__back.jpg"
    assert "image_dir" not in project_data
    assert project_data["backside_default_asset_id"].startswith("img-")

    projects = project_library.list_projects()
    assert len(projects) == 1
    assert projects[0]["id"] == entry["id"]


def test_draft_workspace_is_seeded_and_detects_user_content(monkeypatch, tmp_path):
    _set_project_library_roots(monkeypatch, tmp_path)
    _seed_test_back(tmp_path)

    draft = project_library.create_draft_project_dict()

    assert Path(draft["image_dir"]).name == "tmp_images"
    assert (Path(draft["image_dir"]) / "__back.jpg").exists()
    assert project_library.draft_has_user_content() is False

    (Path(draft["image_dir"]) / "card-a.png").write_bytes(b"front")
    assert project_library.draft_has_user_content() is True


def test_draft_project_state_can_be_saved_and_recovered(monkeypatch, tmp_path):
    _set_project_library_roots(monkeypatch, tmp_path)
    _seed_test_back(tmp_path)
    draft = project_library.create_draft_project_dict()
    state = {**draft, "cards": {"card-a.png": 3}, "bleed_edge": "0.1"}

    project_library.save_draft_project(state)
    recovered = project_library.load_draft_project_dict()

    recovered_entries = {entry["front_name"]: entry["count"]
                         for entry in recovered["card_entries"]}
    assert recovered_entries == {"card-a.png": 3}
    assert recovered["bleed_edge"] == "0.1"
    assert recovered["image_dir"] == draft["image_dir"]
    assert recovered["img_cache"] == draft["img_cache"]


def test_image_only_legacy_draft_is_recoverable(monkeypatch, tmp_path):
    _set_project_library_roots(monkeypatch, tmp_path)
    _seed_test_back(tmp_path)
    draft = project_library.create_draft_project_dict()
    (Path(draft["image_dir"]) / "card-a.png").write_bytes(b"front")

    recovered = project_library.load_draft_project_dict()

    assert recovered["cards"] == {"card-a.png": 1}


def test_materialize_draft_project_persists_db_backed_references(monkeypatch, tmp_path):
    _set_project_library_roots(monkeypatch, tmp_path)
    _seed_test_back(tmp_path)

    draft = project_library.create_draft_project_dict()
    draft_root = Path(draft["image_dir"])
    (draft_root / "card-a.png").write_bytes(b"front")
    (draft_root / "crop" / "card-a.png").write_bytes(b"cropped")
    Path(draft["img_cache"]).write_text("{}", encoding="utf-8")

    print_dict = {
        "image_dir": str(draft_root),
        "img_cache": str(draft_root / "img.cache"),
        "backside_default": "__back.jpg",
        "cards": {"card-a.png": 1},
    }

    entry = project_library.materialize_draft_project(
        "Saved Draft",
        print_dict,
        thumbnail_card="card-a.png",
    )

    saved_project = json.loads(Path(entry["path"]).read_text(encoding="utf-8"))
    assert "image_dir" not in saved_project
    assert saved_project["backside_default_asset_id"].startswith("img-")
    assert saved_project["card_entries"][0]["front_name"] == "card-a.png"
    assert saved_project["card_entries"][0]["image_asset_id"].startswith("img-")
    assert entry["thumbnail_card"] == "card-a.png"

    assert (Path(project_library.draft_root()) / "crop").exists()
    assert not (Path(project_library.draft_root()) / "card-a.png").exists()
    assert project_library.draft_has_user_content() is False


def test_list_projects_uses_thumbnail_override_then_first_playable(monkeypatch, tmp_path):
    _set_project_library_roots(monkeypatch, tmp_path)
    _seed_test_back(tmp_path)

    entry = project_library.create_project("Thumb Test")
    project_path = Path(entry["path"])
    project_data = json.loads(project_path.read_text(encoding="utf-8"))
    core = project_library.get_default_card_service()
    front_a_asset = core.store_image_bytes(b"a", extension="png", source="test")
    front_b_asset = core.store_image_bytes(b"b", extension="png", source="test")
    project_path.write_text(
        json.dumps(
            {
                **project_data,
                "card_entries": [
                    {"entry_id": "front-a.png", "front_name": "front-a.png", "count": 1, "image_asset_id": front_a_asset, "metadata": {}},
                    {"entry_id": "front-b.png", "front_name": "front-b.png", "count": 1, "image_asset_id": front_b_asset, "metadata": {}},
                ],
            }
        ),
        encoding="utf-8",
    )

    first = project_library.get_project(entry["id"])
    assert first["thumbnail_card_resolved"] == "front-a.png"

    project_library.set_thumbnail_card(entry["id"], "front-b.png")
    second = project_library.get_project(entry["id"])
    assert second["thumbnail_card_resolved"] == "front-b.png"
    thumbnail_path = Path(second["thumbnail_path"])
    assert thumbnail_path.exists()
    assert "front-b" in thumbnail_path.name
    assert front_b_asset in thumbnail_path.name
    assert thumbnail_path.read_bytes() == b"b"


def test_import_project_copies_external_project_into_library(monkeypatch, tmp_path):
    _set_project_library_roots(monkeypatch, tmp_path)
    external = tmp_path / "outside.json"
    external.write_text(json.dumps({"cards": {"card-a.png": 2}}), encoding="utf-8")

    entry = project_library.import_project(str(external))

    assert entry["display_name"] == "outside"
    managed_path = tmp_path / "projects"
    assert str(managed_path) in entry["path"]
    assert json.loads(Path(entry["path"]).read_text(encoding="utf-8")) == {
        "cards": {"card-a.png": 2}
    }
    assert entry["card_count"] == 1
    assert entry["print_count"] == 2


def test_remove_project_deletes_project_file(monkeypatch, tmp_path):
    _set_project_library_roots(monkeypatch, tmp_path)
    _seed_test_back(tmp_path)
    entry = project_library.create_project("Delete Me")
    project_path = Path(entry["path"])

    assert project_library.remove_project(entry["id"]) is True
    assert project_library.list_projects() == []
    assert not project_path.exists()


def test_rename_and_duplicate_project(monkeypatch, tmp_path):
    _set_project_library_roots(monkeypatch, tmp_path)
    _seed_test_back(tmp_path)
    source = project_library.create_project("Original")
    Path(source["path"]).write_text(json.dumps({"cards": {"card.png": 2}}), encoding="utf-8")
    project_library.set_thumbnail_card(source["id"], "card.png")

    renamed = project_library.rename_project(source["id"], "Renamed")
    duplicate = project_library.duplicate_project(source["id"], "Renamed Copy")

    assert renamed["display_name"] == "Renamed"
    assert duplicate["id"] != source["id"]
    assert duplicate["display_name"] == "Renamed Copy"
    assert json.loads(Path(duplicate["path"]).read_text(encoding="utf-8")) == {
        "cards": {"card.png": 2}
    }


def test_remove_project_succeeds_when_project_artifacts_are_already_missing(
    monkeypatch, tmp_path
):
    _set_project_library_roots(monkeypatch, tmp_path)
    _seed_test_back(tmp_path)
    entry = project_library.create_project("Missing Files")
    project_path = Path(entry["path"])

    project_path.unlink()

    assert project_library.remove_project(entry["id"]) is True
    assert project_library.list_projects() == []


def test_remove_project_keeps_library_entry_when_delete_fails(monkeypatch, tmp_path):
    _set_project_library_roots(monkeypatch, tmp_path)
    _seed_test_back(tmp_path)
    entry = project_library.create_project("Fail Delete")

    def fail_remove(_path):
        raise OSError("boom")

    monkeypatch.setattr(project_library.os, "remove", fail_remove)

    try:
        project_library.remove_project(entry["id"])
    except OSError as exc:
        assert str(exc) == "boom"
    else:
        raise AssertionError("Expected remove_project to raise OSError")

    remaining = project_library.list_projects()
    assert len(remaining) == 1
    assert remaining[0]["id"] == entry["id"]
