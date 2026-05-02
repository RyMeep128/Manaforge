from __future__ import annotations

import json

import pytest

from mtg_editor.models import DeckProject
from mtg_editor.project_store import (
    ProjectStoreError,
    create_project,
    load_project,
    save_project,
)


def test_create_project_saves_native_project_file(tmp_path):
    project_path = tmp_path / "decks" / "burn.json"

    project = create_project(project_path, "Burn", format="Modern")

    saved = json.loads(project_path.read_text(encoding="utf-8"))
    assert project.metadata.deck_name == "Burn"
    assert project.metadata.format == "Modern"
    assert saved["schema_version"] == 1
    assert saved["metadata"]["deck_name"] == "Burn"
    assert saved["cards"] == []


def test_save_and_load_project_round_trip(tmp_path):
    project_path = tmp_path / "deck.json"
    project = DeckProject.new("Cantrips")
    project.add_card("Opt", quantity=4, card_id="card-opt")
    project.notes = "Looks smooth."

    save_project(project_path, project)
    loaded = load_project(project_path)

    assert loaded.to_dict() == project.to_dict()


def test_load_project_rejects_invalid_json(tmp_path):
    project_path = tmp_path / "bad.json"
    project_path.write_text("{nope", encoding="utf-8")

    with pytest.raises(ProjectStoreError, match="not valid JSON"):
        load_project(project_path)


def test_load_project_rejects_malformed_project(tmp_path):
    project_path = tmp_path / "bad-project.json"
    project_path.write_text(json.dumps({"schema_version": 1, "cards": [{}]}), encoding="utf-8")

    with pytest.raises(ProjectStoreError, match="invalid"):
        load_project(project_path)


def test_save_project_rejects_wrong_project_type(tmp_path):
    with pytest.raises(TypeError):
        save_project(tmp_path / "deck.json", {"schema_version": 1})
