"""Editor document lifecycle and persistence, independent of Qt."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import uuid

from mtg_core.decks import DeckDocument, DeckHistory, DeckStore


class DeckSession:
    """Own one document and its history; callers decide when to save or prompt.

    Failed reads and writes leave the active document, path, and saved snapshot
    intact. UI preferences and the linked print project survive history moves.
    """

    def __init__(self, root: Path, *, store: DeckStore | None = None):
        self.root = Path(root)
        self.store = store if store is not None else DeckStore()
        self.new()

    @property
    def dirty(self) -> bool:
        return self.document.to_dict() != self.saved

    def replace_document(self, document: DeckDocument, path: Path | None = None):
        self.document = document
        self.path = Path(path) if path is not None else None
        self.history = DeckHistory(document)
        self.saved = document.to_dict()

    def new(self):
        self.replace_document(DeckDocument())

    def edit(self, action) -> bool:
        return self.history.execute(action)

    def _move_history(self, action) -> bool:
        preferences = deepcopy(self.document.editor_preferences)
        link = self.document.extras.get('proxy_project_id')
        changed = action()
        self.document.editor_preferences = preferences
        if link:
            self.document.extras['proxy_project_id'] = link
        return changed

    def undo(self) -> bool:
        return self._move_history(self.history.undo)

    def redo(self) -> bool:
        return self._move_history(self.history.redo)

    def save(self) -> Path:
        if not self.dirty and self.path is not None:
            return self.path
        destination = self.path or self.root / f'{self.document.deck.deck_id}.manaforge.json'
        self.store.save(destination, self.document)
        self.path = destination
        self.saved = self.document.to_dict()
        return destination

    def open(self, path: Path):
        path = Path(path)
        raw = json.loads(path.read_text(encoding='utf-8'))
        if 'schema_version' in raw and 'deck' in raw:
            document, destination = DeckDocument.from_dict(raw), path
        else:
            document = DeckDocument.from_legacy_proxy(raw, name=path.stem)
            if isinstance(raw.get('deck_document'), dict):
                document = DeckDocument.from_dict(raw['deck_document'])
                document.print_settings['proxy_project'] = raw
            destination = None
        self.replace_document(document, destination)

    def recovery_paths(self) -> list[Path]:
        return self.store.recovery_paths(self.path) if self.path else []

    def recover(self, path: Path):
        document = self.store.load(path)
        document.deck.deck_id = str(uuid.uuid4())
        document.deck.name += ' (Recovered)'
        document.extras.pop('proxy_project_id', None)
        self.replace_document(document)
