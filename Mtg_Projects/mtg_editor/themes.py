"""Searchable deck-local manual themes, sharing the discovery theme catalog."""
from copy import deepcopy
from .card_drop import CardSearchEdit
from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.discovery_themes import theme_catalog, oracle_tag_theme, theme_matches


class ThemesDialog(W.QDialog):
    def __init__(self, document, catalog, inferred, parent, *, compact=False):
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
        self.current_themes = automatic
        layout.addWidget(automatic)
        self.search = CardSearchEdit()
        self.search.setPlaceholderText('Search themes by name')
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.group = W.QComboBox()
        self.group.addItems(['All groups', *sorted({'Commander Oracle Tags', *{t.get('group', 'Themes') for t in catalog}})])
        layout.addWidget(self.group)
        self.list = W.QListWidget()
        self.list.setStyleSheet("QListWidget::indicator { width: 18px; height: 18px; "
                                "border: 2px solid #a8b6cc; border-radius: 3px; } "
                                "QListWidget::indicator:checked { background: #729bea; "
                                "border-color: #dbe7ff; } "
                                "QListWidget::item { padding: 5px; }")
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
        from .commander_selection import commanders
        from mtg_core.categorization import classify
        rows = [{'entry': entry, 'roles': classify(entry.extras.get('facts') or {})} for entry in commanders(document)]
        suggested = {key for key, option in self.catalog.items() if any(theme_matches(row, option) for row in rows)}
        for key, option in sorted(self.catalog.items(), key=lambda pair: (pair[0] not in suggested, pair[1]['name'].casefold())):
            item = W.QListWidgetItem(option['name'] + (' · Suggested' if key in suggested else ''))
            item.setData(C.Qt.ItemDataRole.UserRole, key)
            item.setFlags(item.flags() | C.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(C.Qt.CheckState.Checked if key in checked else C.Qt.CheckState.Unchecked)
            item.setToolTip(option.get('group', 'Themes') + ' · Manual when checked')
            self.list.addItem(item)
        self.initial_selections = self.selections()
        tag_note = W.QLabel('Choose commander tags from the Commander Oracle Tags group, or enter any Oracle tag below.'
                           if any(t.get('oracle_tag') for t in catalog) else
                           'No commander Oracle tags are available locally. You can still enter an Oracle tag below.')
        tag_note.setWordWrap(True)
        layout.addWidget(tag_note)
        tag_row = W.QHBoxLayout()
        self.oracle_tag = CardSearchEdit()
        self.oracle_tag.setPlaceholderText('Oracle tag or otag:tag')
        self.oracle_tag.setAccessibleName('Custom theme Oracle tag')
        tag_row.addWidget(self.oracle_tag)
        add_theme = W.QPushButton('Add Theme')
        add_theme.setAutoDefault(False)
        add_theme.clicked.connect(self.add_oracle_theme)
        tag_row.addWidget(add_theme)
        layout.addLayout(tag_row)
        self.tag_status = W.QLabel()
        self.tag_status.setWordWrap(True)
        layout.addWidget(self.tag_status)
        clear = W.QPushButton('Remove all manual themes')
        clear.clicked.connect(self.clear)
        layout.addWidget(clear)
        buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Save | W.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.buttons = buttons
        if compact:
            automatic.setText('Current themes: ' + (', '.join(t['name'] for t in saved) or 'None'))
            for widget in (note, self.group, tag_note, self.oracle_tag,
                           add_theme, self.tag_status, clear):
                widget.hide()
        self.search.textChanged.connect(self.filter)
        self.group.currentTextChanged.connect(self.filter)

    def keyPressEvent(self, event):
        if not self.isWindow() and event.key() in (C.Qt.Key.Key_Return, C.Qt.Key.Key_Enter, C.Qt.Key.Key_Escape):
            event.ignore()
            return
        if (self.oracle_tag.hasFocus()
                and event.key() in (C.Qt.Key.Key_Return, C.Qt.Key.Key_Enter)):
            self.add_oracle_theme()
            event.accept()
            return
        super().keyPressEvent(event)

    def add_oracle_theme(self):
        try:
            option = oracle_tag_theme(self.oracle_tag.text())
        except ValueError as exc:
            self.tag_status.setText(str(exc))
            self.oracle_tag.setFocus()
            return
        key = option['slug']
        item = next((self.list.item(i) for i in range(self.list.count())
                     if self.list.item(i).data(C.Qt.ItemDataRole.UserRole) == key), None)
        if item is None:
            self.catalog[key] = option
            item = W.QListWidgetItem(option['name'])
            item.setData(C.Qt.ItemDataRole.UserRole, key)
            item.setFlags(item.flags() | C.Qt.ItemFlag.ItemIsUserCheckable)
            item.setToolTip(option['query'])
            self.list.addItem(item)
        item.setCheckState(C.Qt.CheckState.Checked)
        self.search.clear()
        self.group.setCurrentText('Commander Oracle Tags')
        self.filter()
        self.list.setCurrentItem(item)
        self.list.scrollToItem(item)
        self.oracle_tag.clear()
        self.tag_status.setText('Oracle tag theme selected. Save to apply it to this deck.')

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


def edit_themes(editor, *, commander_changed=False):
    if editor.task is not None or editor.closing:
        return
    snapshot = editor.document.deck.deck_id
    snapshot_data = editor.document.to_dict()
    cached = [t for t in editor.add_cards_workspace.discovery.theme_options.values() if t.get('origin') == 'edhrec']
    document = deepcopy(editor.document)
    def load():
        from mtg_core.guidance import guidance, GuidanceSettings
        reader = getattr(getattr(editor.service, 'database', None), 'discovery_metadata', None)
        catalog = theme_catalog(cached, reader() if callable(reader) else {})
        from .commander_selection import commanders
        from mtg_core.diagnostics import get_logger
        tags = set()
        for entry in commanders(document):
            if entry.quantity <= 0:
                continue
            tags.update((entry.extras.get('facts') or {}).get('oracle_tags') or [])
            try:
                oracle_id = entry.oracle_id
                if not oracle_id and entry.card_id:
                    oracle_id = (editor.service.get_card(card_id=entry.card_id) or {}).get('oracle_id')
                reader = getattr(editor.service, 'get_oracle_tags', None)
                if callable(reader) and oracle_id:
                    tags.update(reader(oracle_id) or [])
            except Exception:
                get_logger(__name__).exception('Could not load commander Oracle tags')
        catalog.extend(oracle_tag_theme(tag) for tag in sorted(tags))
        proposals = editor.service.analyze_entries(document.deck.entries)
        inferred = guidance(document, proposals, GuidanceSettings.from_document(document))
        return catalog, [row['id'][6:] for row in inferred['suggestions'] if row['id'].startswith('theme:')]
    def loaded(result):
        if snapshot != editor.document.deck.deck_id or snapshot_data != editor.document.to_dict():
            return
        catalog, inferred = result
        dialog = ThemesDialog(editor.document, catalog, inferred, editor, compact=commander_changed)
        if commander_changed:
            dialog.setWindowTitle('Update themes for your new commander?')
            dialog.buttons.button(W.QDialogButtonBox.StandardButton.Cancel).setText('Keep existing themes')
        if (dialog.exec() == W.QDialog.DialogCode.Accepted and snapshot == editor.document.deck.deck_id
                and snapshot_data == editor.document.to_dict()):
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
