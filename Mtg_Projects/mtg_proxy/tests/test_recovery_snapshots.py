import json
import os

import project_library
from models import ProjectState


def test_save_keeps_bounded_recovery_snapshots(tmp_path, monkeypatch):
    project_path = tmp_path / 'deck.json'
    project_path.write_text(json.dumps({'project_version': 2, 'card_entries': []}))
    library = {'projects': [{'id': 'deck-id', 'path': str(project_path),
                             'display_name': 'Deck'}]}
    monkeypatch.setattr(project_library, 'load_library', lambda: library)
    monkeypatch.setattr(project_library, 'save_library', lambda _data: None)
    monkeypatch.setattr(project_library, 'get_project', lambda _id: library['projects'][0])
    monkeypatch.setattr(project_library, 'recovery_root', lambda: str(tmp_path / 'recovery'))

    for count in range(1, 8):
        project_library.save_project(
            'deck-id', ProjectState.from_dict({'cards': {'card.png': count}}))

    snapshots = project_library.recovery_snapshots('deck-id')
    assert len(snapshots) == 5
    assert all(os.path.exists(path) for path in snapshots)
    recovered = project_library.load_recovery_snapshot(snapshots[0])
    assert recovered['card_entries'][0]['count'] == 6
