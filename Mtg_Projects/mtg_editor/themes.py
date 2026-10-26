"""Searchable deck-local manual themes, sharing the discovery theme catalog."""
from copy import deepcopy
from .card_drop import CardSearchEdit
from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.discovery_themes import theme_catalog


class ThemesDialog(W.QDialog):
    def __init__(self, document, catalog, inferred, parent):
        super().__init__(parent)
        self.setWindowTitle('Deck themes')
        self.resize(520, 540)
        layout = W.QVBoxLayout(self)
        note = W.QLabel('Checked themes are manual selections saved with this deck. '
                        'They guide recommendations and role priorities. Inferred themes remain automatic; '
                        'changing themes preserves every card and manual category override.')
        note.setWordWrap(True)
        layout.addWidget(note)
        automatic = W.QLabel('Automatically inferred: ' + (', '.join(inferred) or 'No repeated theme detected yet.'))
        automatic.setWordWrap(True)
        layout.addWidget(automatic)
        self.search = CardSearchEdit()
        self.search.setPlaceholderText('Search themes by name')
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.group = W.QComboBox()
        self.group.addItems(['All groups', *sorted({t.get('group', 'Themes') for t in catalog})])
        layout.addWidget(self.group)
        self.list = W.QListWidget()
        layout.addWidget(self.list, 1)
        saved = list(document.editor_preferences.get('manual_themes', []))
        discovery = document.editor_preferences.get('discovery', {})
        legacy = discovery.get('theme_option') or next(
            (t for t in catalog if t['slug'] == discovery.get('theme')), None)
        if not legacy and discovery.get('theme'):
            legacy = dict(slug=discovery['theme'], name=discovery['theme'], group='Themes')
        if legacy and not legacy.get('companion') and not any(t['slug'] == legacy['slug'] for t in saved):
            saved.append(legacy)
        self.catalog = {t['slug']: t for t in [*catalog, *saved] if not t.get('companion')}
        checked = {t['slug'] for t in saved}
        for key, option in sorted(self.catalog.items(), key=lambda pair: pair[1]['name'].casefold()):
            item = W.QListWidgetItem(option['name'])
            item.setData(C.Qt.ItemDataRole.UserRole, key)
            item.setFlags(item.flags() | C.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(C.Qt.CheckState.Checked if key in checked else C.Qt.CheckState.Unchecked)
            item.setToolTip(option.get('group', 'Themes') + ' · Manual when checked')
            self.list.addItem(item)
        self.initial_selections = self.selections()
        clear = W.QPushButton('Remove all manual themes')
        clear.clicked.connect(self.clear)
        layout.addWidget(clear)
        buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Save | W.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.search.textChanged.connect(self.filter)
        self.group.currentTextChanged.connect(self.filter)

    def filter(self, *_):
        needle = self.search.text().casefold().strip()
        group = self.group.currentText()
        for i in range(self.list.count()):
            item = self.list.item(i)
            option = self.catalog[item.data(C.Qt.ItemDataRole.UserRole)]
            item.setHidden(needle not in option['name'].casefold() or
                           (group != 'All groups' and option.get('group', 'Themes') != group))

    def clear(self):
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(C.Qt.CheckState.Unchecked)

    def selections(self):
        return [deepcopy(self.catalog[self.list.item(i).data(C.Qt.ItemDataRole.UserRole)])
                for i in range(self.list.count()) if self.list.item(i).checkState() == C.Qt.CheckState.Checked]


def edit_themes(editor):
    if editor.task is not None or editor.closing:
        return
    snapshot = editor.document.deck.deck_id
    cached = [t for t in editor.add_cards_workspace.discovery.theme_options.values() if t.get('origin') == 'edhrec']
    document = deepcopy(editor.document)
    def load():
        from mtg_core.guidance import guidance, GuidanceSettings
        reader = getattr(getattr(editor.service, 'database', None), 'discovery_metadata', None)
        catalog = theme_catalog(cached, reader() if callable(reader) else {})
        proposals = editor.service.analyze_entries(document.deck.entries)
        inferred = guidance(document, proposals, GuidanceSettings.from_document(document))
        return catalog, [row['id'][6:] for row in inferred['suggestions'] if row['id'].startswith('theme:')]
    def loaded(result):
        if snapshot != editor.document.deck.deck_id:
            return
        catalog, inferred = result
        dialog = ThemesDialog(editor.document, catalog, inferred, editor)
        if dialog.exec() == W.QDialog.DialogCode.Accepted and snapshot == editor.document.deck.deck_id:
            themes = dialog.selections()
            if themes == dialog.initial_selections:
                return
            def apply(document):
                document.editor_preferences['manual_themes'] = themes
                discovery = document.editor_preferences.setdefault('discovery', {})
                discovery.update(theme=themes[0]['slug'] if themes else '',
                                 theme_option=themes[0] if themes else {})
            editor.edit(apply)
    editor.run_task(load, loaded)
