"""Editor document lifecycle and persistence, independent of Qt."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import uuid

from mtg_core.decks import DeckDocument, DeckHistory, DeckStore

UNDOABLE_PREFERENCES = frozenset({'manual_themes', 'discovery', 'include_illegal_cards',
                                 'edhrec_cohort', 'recommendations', 'guidance'})

def update_default_name(document):
    """Follow the commander/first-added card until the user supplies a name."""
    deck = document.deck
    record = deck.extras.get('default_name', {})
    if deck.extras.get('manual_name') or (deck.name.strip() not in ('', 'Untitled Deck')
                                         and deck.name != record.get('value')):
        return
    entries = [entry for entry in deck.entries if entry.quantity > 0]
    first = next((entry for entry in entries if entry.entry_id == record.get('first_entry_id')), None)
    first = first or next(iter(entries), None)
    commander = next((entry for key in deck.commander_entry_ids for entry in entries if entry.entry_id == key), None)
    commander = commander or next((entry for entry in entries if entry.section == 'commander'), None)
    source = commander or first
    if source is not None:
        deck.name = source.name
        deck.extras['default_name'] = {'value': deck.name, 'first_entry_id': first.entry_id}
    elif record:
        deck.name = 'Untitled Deck'
        deck.extras.pop('default_name', None)


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
        update_default_name(document)

    def new(self):
        self.replace_document(DeckDocument(editor_preferences={'edhrec_cohort': 'auto'}))

    def edit(self, action) -> bool:
        def command(document):
            action(document)
            update_default_name(document)
        return self.history.execute(command)

    def _move_history(self, action) -> bool:
        preferences = deepcopy(self.document.editor_preferences)
        link = self.document.extras.get('proxy_project_id')
        changed = action()
        # Keep presentation state, but restore the history snapshot's deck intent.
        semantic = {key: value for key, value in self.document.editor_preferences.items()
                    if key in UNDOABLE_PREFERENCES}
        self.document.editor_preferences = {key: value for key, value in preferences.items()
                                            if key not in UNDOABLE_PREFERENCES}
        self.document.editor_preferences.update(semantic)
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
