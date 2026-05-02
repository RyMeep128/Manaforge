from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mtg_editor.models import DEFAULT_FORMAT, DeckProject


class ProjectStoreError(ValueError):
    pass


def create_project(
    path: str | Path,
    deck_name: str,
    format: str = DEFAULT_FORMAT,
) -> DeckProject:
    project = DeckProject.new(deck_name=deck_name, format=format)
    save_project(path, project)
    return project


def load_project(path: str | Path) -> DeckProject:
    project_path = Path(path)
    try:
        with project_path.open("r", encoding="utf-8") as handle:
            data: Any = json.load(handle)
    except OSError as exc:
        raise ProjectStoreError(f"Could not read deck project: {project_path}") from exc
    except json.JSONDecodeError as exc:
        raise ProjectStoreError(f"Deck project is not valid JSON: {project_path}") from exc

    if not isinstance(data, dict):
        raise ProjectStoreError("Deck project root must be a JSON object")
    try:
        return DeckProject.from_dict(data)
    except (TypeError, ValueError) as exc:
        raise ProjectStoreError(f"Deck project is invalid: {exc}") from exc


def save_project(path: str | Path, project: DeckProject) -> None:
    if not isinstance(project, DeckProject):
        raise TypeError("project must be a DeckProject")
    project_path = Path(path)
    project_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = project_path.with_name(f".{project_path.name}.tmp")
    payload = json.dumps(project.to_dict(), indent=2, ensure_ascii=False)
    temp_path.write_text(payload + "\n", encoding="utf-8")
    temp_path.replace(project_path)
