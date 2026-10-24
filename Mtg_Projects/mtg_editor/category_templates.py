"""Reusable category names/order; applying a template never changes card assignments."""
import json
import os
from pathlib import Path
import tempfile
import uuid

from PyQt6 import QtWidgets as W
from mtg_core.decks import DeckCategory

COMMANDER = ('Ramp', 'Draw', 'Removal', 'Board Wipes', 'Protection', 'Recursion',
             'Win Conditions', 'Lands')
BUILTIN_NAME = 'Commander essentials'


def category_names(names):
    if not isinstance(names, (list, tuple)) or any(not isinstance(n, str) for n in names):
        raise ValueError('Category names must be a list of text values.')
    result, seen = [], set()
    for name in names:
        name = name.strip()
        if name and name.casefold() not in seen:
            result.append(name)
            seen.add(name.casefold())
    return result


def apply_template(document, names):
    names = category_names(names)
    categories = document.deck.categories
    existing = {c.name.casefold() for c in categories}
    order = max((c.sort_order for c in categories), default=-1) + 1
    for name in names:
        if name.casefold() not in existing:
            categories.append(DeckCategory(str(uuid.uuid4()), name, order))
            existing.add(name.casefold())
            order += 1


class TemplateStore:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(raw, dict) or raw.get('version') != 1 or not isinstance(raw.get('templates'), dict):
            raise ValueError('Unsupported category template file.')
        return {name: category_names(names) for name, names in raw['templates'].items()}

    def save(self, name, names):
        name = name.strip()
        names = category_names(names)
        if not name or not names:
            raise ValueError('A template needs a name and at least one category.')
        if name.casefold() == BUILTIN_NAME.casefold():
            raise ValueError('Use another name for your custom template.')
        templates = self.load()
        key = next((n for n in templates if n.casefold() == name.casefold()), name)
        templates[key] = names
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.category-templates-', suffix='.tmp', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump({'version': 1, 'templates': templates}, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class CategoryTemplates(W.QDialog):
    def __init__(self, document, store, parent=None):
        super().__init__(parent)
        self.store, self.document = store, document
        self.setWindowTitle('Category templates')
        self.resize(420, 440)
        layout = W.QVBoxLayout(self)
        note = W.QLabel('Apply adds missing categories. Existing categories, their order, and card assignments are preserved.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.templates = {BUILTIN_NAME: list(COMMANDER), **store.load()}
        self.selector = W.QComboBox()
        self.selector.addItems(self.templates)
        layout.addWidget(self.selector)
        self.preview = W.QListWidget()
        layout.addWidget(self.preview, 1)
        self.selector.currentTextChanged.connect(self.refresh)
        self.refresh()
        save = W.QPushButton('Save current deck categories as template…')
        save.setEnabled(bool(document.deck.categories))
        save.clicked.connect(self.save_current)
        layout.addWidget(save)
        buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Apply | W.QDialogButtonBox.StandardButton.Close)
        buttons.button(W.QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def refresh(self, *_):
        self.preview.clear()
        self.preview.addItems(self.selected_names())

    def selected_names(self):
        return list(self.templates.get(self.selector.currentText(), []))

    def save_current(self):
        name, ok = W.QInputDialog.getText(self, 'Save category template',
                                        'Template name (an existing name updates that template):')
        if not ok:
            return
        names = [c.name for c in sorted(self.document.deck.categories, key=lambda c: c.sort_order)]
        try:
            self.store.save(name, names)
            self.templates = {BUILTIN_NAME: list(COMMANDER), **self.store.load()}
        except (OSError, ValueError) as exc:
            W.QMessageBox.warning(self, 'Could not save template', str(exc))
            return
        self.selector.clear()
        self.selector.addItems(self.templates)
        key = next(n for n in self.templates if n.casefold() == name.strip().casefold())
        self.selector.setCurrentText(key)
