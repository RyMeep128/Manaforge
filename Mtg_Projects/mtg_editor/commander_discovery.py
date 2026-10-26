"""Image-first commander discovery over local rules and explicit EDHREC themes."""

import json

from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.commander_discovery import search_commanders
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_core.edhrec_discovery import DiscoveryStore
from mtg_core.paths import core_data_root

from .canvas import CardCanvas
from .card_drop import CardDropPanel, CardSearchEdit
from .commander_selection import commanders, select_commander
from .organization import card_facts, update_candidate_quantities
from .search import SearchCache, SearchController, SearchWorker


class DiscoverySearch:
    """Snapshot adapter sharing debounce, caching, and cancellation with local search."""
    def __init__(self, service):
        self.service = service
        self.store = None
        self.metadata = None

    def search_editor_cards(self, query, *, should_cancel=None):
        from mtg_core.discovery_starter import ensure_starter_catalog, snapshot_path
        import sqlite3
        root = core_data_root() / 'recommendations'
        try:
            ensure_starter_catalog(self.service, should_cancel=should_cancel)
            path = snapshot_path(root, 'edhrec-discovery.sqlite3')
        except (OSError, ValueError, sqlite3.DatabaseError):
            path = root / 'edhrec-discovery.sqlite3'
        self.store = DiscoveryStore(path)
        if self.metadata is None:
            database = getattr(self.service, 'database', None)
            reader = getattr(database, 'discovery_metadata', None)
            self.metadata = reader(should_cancel=should_cancel) if callable(reader) else {}
        return search_commanders(self.service, json.loads(query), self.store,
                                 metadata=self.metadata, should_cancel=should_cancel)


class DiscoveryWorker(SearchWorker):
    """Discovery returns a catalog/result snapshot, rather than SearchCardResult pages."""
    def run(self):
        from mtg_core.search.cancellation import SearchCancelled, check_cancelled
        try:
            check_cancelled(self.cancelled.is_set)
            snapshot = None if self.refresh else self.cache.get(self.query)
            if snapshot is None:
                if self.refresh:
                    self.service.metadata = None
                snapshot = self.service.search_editor_cards(self.query, should_cancel=self.cancelled.is_set)
                check_cancelled(self.cancelled.is_set)
                self.cache.put(self.query, snapshot)
            check_cancelled(self.cancelled.is_set)
            self.completed.emit(self.query, snapshot, '')
        except SearchCancelled:
            pass
        except Exception as exc:
            if not self.cancelled.is_set():
                self.completed.emit(self.query, {}, str(exc))


class DiscoveryController(SearchController):
    worker_type = DiscoveryWorker

    def search(self, query=None, *, refresh=False, append=False):
        if refresh:
            self.cache = SearchCache()
        super().search(query, refresh=refresh, append=append)

    def _completed(self, query, snapshot, error):
        worker = self.sender()
        if (worker is self.worker and not worker.cancelled.is_set()
                and not self.closing and query == self.query):
            self.resultsReady.emit(query, snapshot, error)


class DiscoveryCanvas(CardCanvas):
    commanderRequested = C.pyqtSignal(str)

    def __init__(self, document, thumbnails, parent):
        super().__init__(document, thumbnails, parent, search=True)
        self.theme_name = ""

    def mouseDoubleClickEvent(self, event):
        if event.button() != C.Qt.MouseButton.LeftButton:
            return
        item = self.hit(event.position().toPoint())
        if self.activate_quantity(item, event.position().toPoint()):
            return
        if item:
            self.commanderRequested.emit(item[0].entry_id)


class CommanderDiscovery(CardDropPanel):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.rows = {}
        self.limit = 50
        self.loaded_query = None
        self.result_status = ""
        self.context = None
        self.theme_slug = ""
        self.theme_catalog = []
        self.theme_options = {}
        self.controller = DiscoveryController(DiscoverySearch(editor.service), self)
        layout = W.QVBoxLayout(self)
        theme_row = W.QHBoxLayout()
        theme_label = W.QLabel("Theme")
        theme_label.setProperty("role", "title")
        theme_row.addWidget(theme_label)
        self.theme = W.QComboBox()
        self.theme.setEditable(True)
        self.theme.setInsertPolicy(W.QComboBox.InsertPolicy.NoInsert)
        self.theme.addItem("All themes / local discovery", "")
        self.theme.setMinimumWidth(220)
        self.theme.setToolTip("Type to find a theme, or use Browse themes to open the full dropdown.")
        self.theme.completer().setFilterMode(C.Qt.MatchFlag.MatchContains)
        self.theme.completer().setCaseSensitivity(C.Qt.CaseSensitivity.CaseInsensitive)
        self.theme.completer().setCompletionMode(W.QCompleter.CompletionMode.PopupCompletion)
        theme_row.addWidget(self.theme, 1)
        self.browse_themes = W.QPushButton("Browse themes ▾")
        self.browse_themes.setToolTip("Open the full list of imported themes.")
        self.browse_themes.setEnabled(False)
        self.browse_themes.clicked.connect(self.show_themes)
        theme_row.addWidget(self.browse_themes)
        refresh = W.QPushButton("Refresh local data")
        refresh.clicked.connect(lambda: self.search(refresh=True))
        theme_row.addWidget(refresh)
        layout.addLayout(theme_row)
        self.theme_status = W.QLabel("EDHREC themes load from the local snapshot. No collection runs in the editor.")
        self.theme_status.setWordWrap(True)
        layout.addWidget(self.theme_status)
        self.import_themes_button = W.QPushButton("Import cached themes")
        self.import_themes_button.setToolTip("Build the theme index from previously collected EDHREC responses. No downloads.")
        self.import_themes_button.clicked.connect(self.import_themes)
        layout.addWidget(self.import_themes_button, 0, C.Qt.AlignmentFlag.AlignLeft)
        fields = W.QHBoxLayout()
        self.name = CardSearchEdit()
        self.name.setPlaceholderText("Commander name")
        self.type = CardSearchEdit()
        self.type.setPlaceholderText("Type / creature type")
        self.text = CardSearchEdit()
        self.text.setPlaceholderText("Oracle text contains…")
        for field in (self.name, self.type, self.text):
            field.setClearButtonEnabled(True)
            fields.addWidget(field, 1)
            field.textChanged.connect(self.filters_changed)
        layout.addLayout(fields)
        options = W.QGridLayout()
        self.capability = W.QComboBox()
        for label, value in [("Any capability", ""), ("Partner / Partner with", "partner"),
                             ("Friends Forever", "friends forever"), ("Choose a Background", "choose a background"),
                             ("Background cards", "background"), ("Doctor's companion", "doctor's companion")]:
            self.capability.addItem(label, value)
        self.browse_mode = W.QComboBox()
        self.browse_mode.addItem('Commander Browser', 'all')
        self.browse_mode.addItem('Top Commanders (cached coverage)', 'top')
        self.browse_mode.model().item(1).setEnabled(False)
        self.browse_mode.currentIndexChanged.connect(self.filters_changed)
        options.addWidget(self.browse_mode, 0, 0)
        options.addWidget(self.capability, 1, 0)
        from .discovery_options import color_combo
        self.identity = color_combo()
        self.identity.currentIndexChanged.connect(self.filters_changed)
        options.addWidget(self.identity, 0, 1)
        self.legal = W.QCheckBox("Legal cards only")
        self.legal.setAccessibleDescription('Use deck format and commander color identity defaults')
        self.legal.setChecked(True)
        options.addWidget(self.legal, 1, 1)
        layout.addLayout(options)
        pairing = W.QHBoxLayout()
        self.partner = W.QCheckBox("Compatible with current commander")
        self.partner.setToolTip("Use existing pairing rules. With a theme selected, require explicit membership for this exact pair.")
        pairing.addWidget(self.partner)
        pairing.addStretch()
        self.cancel = W.QPushButton("Cancel")
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.controller.cancel)
        pairing.addWidget(self.cancel)
        layout.addLayout(pairing)
        self.status = W.QLabel("Browse local commanders, or choose an imported theme.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.canvas = DiscoveryCanvas(DeckDocument(), editor.thumbnails, self)
        self.canvas.card_width = 190
        self.canvas.setAccessibleName("Commander discovery results")
        self.canvas.setToolTip("Double-click to set as commander and browse recommendations.")
        self.canvas.quantityRequested.connect(self.change_quantity)
        self.canvas.commanderRequested.connect(self.set_commander)
        self.canvas.selectionChanged.connect(self.selection_changed)
        self.canvas.menuRequested.connect(self.card_menu)
        self.canvas.detailsRequested.connect(lambda key: editor.candidate_details(self.canvas, key))
        layout.addWidget(self.canvas, 1)
        self.details = W.QLabel("Choose a commander to start building.")
        self.details.setTextFormat(C.Qt.TextFormat.PlainText)
        self.details.setWordWrap(True)
        self.details.setMaximumHeight(100)
        layout.addWidget(self.details)
        actions = W.QHBoxLayout()
        self.set_button = W.QPushButton("Set as Commander")
        self.set_button.setProperty("buttonRole", "primary")
        self.set_button.clicked.connect(lambda: self.set_commander())
        actions.addWidget(self.set_button)
        self.second_button = W.QPushButton("Add as Second Commander")
        self.second_button.clicked.connect(lambda: self.set_commander(second=True))
        actions.addWidget(self.second_button)
        actions.addStretch()
        layout.addLayout(actions)
        secondary = W.QHBoxLayout()
        checks = W.QPushButton("Commander / deck checks")
        checks.clicked.connect(editor.commander_checks)
        secondary.addWidget(checks)
        manual = W.QPushButton('Build Manually')
        manual.clicked.connect(lambda: self.editor.add_card_tabs.setCurrentWidget(self.editor.add_cards_workspace.card_search))
        secondary.addWidget(manual)
        secondary.addStretch()
        self.more = W.QPushButton("Show more")
        self.more.clicked.connect(self.show_more)
        self.more.hide()
        secondary.addWidget(self.more)
        layout.addLayout(secondary)
        self.theme.currentIndexChanged.connect(self.theme_selected)
        self.theme.activated.connect(self.theme_selected)
        self.theme.completer().activated[str].connect(self.complete_theme)
        self.capability.currentIndexChanged.connect(self.filters_changed)
        self.partner.toggled.connect(self.filters_changed)
        self.legal.toggled.connect(lambda checked: editor.set_include_illegal(not checked))
        self.controller.resultsReady.connect(self.completed)
        self.controller.statusChanged.connect(self.status.setText)
        self.controller.busyChanged.connect(self.cancel.setEnabled)
        self.selection_changed()
        self.preference_deck = None
        self.theme_search = CardSearchEdit()
        self.theme_search.setPlaceholderText("Search cached themes, typal strategies, or companions")
        self.theme_search.setClearButtonEnabled(True)
        self.theme_search.textChanged.connect(self.populate_themes)
        self.theme_group = W.QComboBox()
        self.theme_group.addItems(["Mechanics", "Strategies", "Archetypes", "Typal", "Companions"])
        self.theme_group.currentTextChanged.connect(self.populate_themes)
        self.theme_list = W.QListWidget()
        self.theme_list.setMaximumHeight(145)
        self.theme_list.setFlow(W.QListView.Flow.LeftToRight)
        self.theme_list.setWrapping(True)
        self.theme_list.itemClicked.connect(lambda item: self.theme.setCurrentIndex(self.theme.findData(item.data(C.Qt.ItemDataRole.UserRole))))
        browser = W.QHBoxLayout()
        browser.addWidget(self.theme_group)
        browser.addWidget(self.theme_search, 1)
        clear = W.QPushButton("Clear theme")
        clear.clicked.connect(lambda: self.theme.setCurrentIndex(0))
        browser.addWidget(clear)
        layout.insertLayout(0, browser)
        layout.insertWidget(1, self.theme_list)
        # Keep the full theme catalog beside a large commander grid.
        layout.removeItem(browser)
        browser.removeWidget(self.theme_search)
        layout.removeWidget(self.theme_list)
        sidebar = W.QWidget()
        sidebar.setMinimumWidth(220)
        sidebar.setMaximumWidth(300)
        sidebar_layout = W.QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 8, 0)
        sidebar_layout.addLayout(browser)
        sidebar_layout.addWidget(self.theme_search)
        self.theme_list.setMaximumHeight(16777215)
        self.theme_list.setFlow(W.QListView.Flow.TopToBottom)
        self.theme_list.setWrapping(False)
        self.theme_list.setSpacing(5)
        sidebar_layout.addWidget(self.theme_list, 1)
        self.theme.hide()
        self.browse_themes.hide()
        theme_label.setText('Discover Deck Ideas')
        main = W.QWidget()
        main_layout = W.QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                main_layout.addWidget(item.widget(), 1 if item.widget() is self.canvas else 0)
            elif item.layout() is not None:
                main_layout.addLayout(item.layout())
        workspace = W.QHBoxLayout()
        workspace.addWidget(sidebar)
        workspace.addWidget(main, 1)
        layout.addLayout(workspace, 1)
        self.populate_themes()

    def populate_themes(self, *_):
        self.theme_list.clear()
        group = self.theme_group.currentText()
        needle = self.theme_search.text().strip().casefold()
        for slug, name in self.theme_catalog:
            option = self.theme_options.get(slug, {})
            if (needle and needle in name.casefold()) or (not needle and option.get('group', 'Themes') == group):
                item = W.QListWidgetItem(name)
                item.setData(C.Qt.ItemDataRole.UserRole, slug)
                item.setToolTip('Cached EDHREC commander associations' if option.get('origin') == 'edhrec'
                                else 'Local card mechanics / type search')
                self.theme_list.addItem(item)
        if not self.theme_list.count():
            item = W.QListWidgetItem('No matching themes. Try local type or Oracle text search below.')
            item.setFlags(C.Qt.ItemFlag.NoItemFlags)
            self.theme_list.addItem(item)

    def save_preferences(self):
        value = dict(self.editor.document.editor_preferences.get('discovery', {}),
                     theme=self.theme_slug, identity=self.identity.currentData(),
                     theme_option=self.theme_options.get(self.theme_slug, {}))
        if self.editor.document.editor_preferences.get('discovery') != value:
            self.editor.document.editor_preferences.update(discovery=value)
            self.editor.changed()

    def filters(self):
        from mtg_core.card_pool import pool_context
        format_name, deck_identity, include_illegal = pool_context(self.editor.document)
        selected = commanders(self.editor.document)
        return dict(theme=self.theme_slug, browse=self.browse_mode.currentData(), identity=self.identity.currentData(), name=self.name.text(), type=self.type.text(),
                    text=self.text.text(), capability=self.capability.currentData(),
                    legal_only=not include_illegal, deck_format=format_name, deck_identity=deck_identity, limit=self.limit,
                    partner_card_id=selected[0].card_id if self.partner.isChecked() and len(selected) == 1 else None)

    def query(self):
        return json.dumps(self.filters(), sort_keys=True)

    def theme_selected(self, index):
        if index < 0:
            return
        slug = self.theme.itemData(index) or ""
        if slug != self.theme_slug:
            self.theme_slug = slug
            if slug:
                with C.QSignalBlocker(self.browse_mode):
                    self.browse_mode.setCurrentIndex(0)
            self.sync_theme_selection()
            self.filters_changed()

    def sync_theme_selection(self):
        for index in range(self.theme_list.count()):
            item = self.theme_list.item(index)
            item.setSelected(item.data(C.Qt.ItemDataRole.UserRole) == self.theme_slug)

    def complete_theme(self, text):
        index = self.theme.findText(text, C.Qt.MatchFlag.MatchFixedString)
        if index >= 0:
            self.theme.setCurrentIndex(index)
            self.theme_selected(index)

    def show_themes(self):
        self.theme.completer().popup().hide()
        self.theme.setFocus()
        self.theme.showPopup()

    def import_themes(self):
        from threading import Event
        from mtg_core.edhrec_discovery_ingest import import_cached_discovery

        if self.editor.closing or self.editor.task is not None:
            return
        self.controller.cancel()
        self.loaded_query = None
        cancelled = Event()
        progress = W.QProgressDialog("Importing cached EDHREC themes…", "Cancel", 0, 0, self.editor)
        progress.canceled.connect(cancelled.set)
        self.editor.task_runner.failed.connect(progress.close)
        self.editor.task_runner.failed.connect(progress.deleteLater)
        progress.show()

        def imported(result):
            progress.close()
            progress.deleteLater()
            # Replace rather than mutate a cache an exiting search worker may
            # still hold. All subsequent searches see the newly published data.
            from .search import SearchCache

            self.controller.cache = SearchCache()
            if result["status"] == "cancelled":
                self.editor.statusBar().showMessage("Theme import cancelled. The previous snapshot is preserved.")
            else:
                self.editor.statusBar().showMessage(
                    f"Imported {result['themes']} themes from {result['cohorts']} commander cohorts.")
            self.search(refresh=True)

        self.editor.run_task(lambda: import_cached_discovery(should_cancel=cancelled.is_set), imported)
        self.editor.statusBar().showMessage("Importing cached EDHREC themes…")

    def filters_changed(self, *_):
        self.save_preferences()
        self.limit = 50
        self.loaded_query = None
        self.rows.clear()
        self.canvas.document.deck.entries.clear()
        self.more.hide()
        self.canvas.refresh()
        self.selection_changed()
        if self.isVisible():
            self.controller.change_query(self.query())

    def search(self, *, refresh=False):
        if self.isVisible() and not self.editor.closing:
            self.controller.search(self.query(), refresh=refresh)

    def completed(self, query, snapshot, error):
        if not self.isVisible() or self.editor.closing or query != self.query():
            return
        if error:
            self.status.setText("Commander discovery failed. Refresh local data to retry.")
            self.status.setToolTip(error)
            return
        self.loaded_query = query
        self.theme_options = {theme['slug']: theme for theme in snapshot['themes']}
        self.browse_mode.model().item(1).setEnabled(bool(snapshot.get('ranked')) and not self.theme_slug)
        catalog = [(theme["slug"], theme["name"]) for theme in snapshot["themes"]]
        if catalog != self.theme_catalog:
            typed = self.theme.currentText()
            editing = typed != self.theme.itemText(self.theme.currentIndex())
            with C.QSignalBlocker(self.theme):
                self.theme.clear()
                self.theme.addItem("All themes / local discovery", "")
                for slug, name in catalog:
                    self.theme.addItem(name, slug)
                self.theme.setCurrentIndex(max(0, self.theme.findData(self.theme_slug)))
                if editing:
                    self.theme.setEditText(typed)
            self.theme_catalog = catalog
            self.populate_themes()
        self.theme.setEnabled(bool(snapshot["themes"]))
        self.browse_themes.setEnabled(bool(snapshot["themes"]))
        prefix = 'Limited bundled starter snapshot. ' if snapshot.get('coverage') == 'starter' else ''
        self.theme_status.setText(prefix + f"{snapshot.get('cards', 0):,} local cards; "
                                  f"{len(snapshot['themes'])} themes and typal options.")
        self.theme_status.setToolTip(snapshot['status'] + "\n" + f"{snapshot.get('cards', 0):,} local cards; "
                                    f"{snapshot.get('cohorts', 0):,} cached commander cohorts.")
        if self.theme_slug and self.theme.findData(self.theme_slug) < 0:
            # A removed/unavailable snapshot must not leave a hidden theme filter
            # blocking the local fallback.
            self.theme_slug = ""
            self.filters_changed()
            return
        self.sync_theme_selection()
        if self.theme_slug:
            self.save_preferences()
        self.canvas.theme_name = dict(catalog).get(self.theme_slug, "")
        self.rows = {}
        entries = []
        for row in snapshot["results"]:
            card = row["card"]
            entry = DeckEntry(card.card_id, card.name, card_id=card.card_id, oracle_id=card.oracle_id,
                              set_code=card.set_code, collector_number=card.collector_number, pre_cropped=True,
                              extras={"facts": card_facts(card.payload or {})})
            self.rows[entry.entry_id] = dict(row, entry=entry)
            entries.append(entry)
        position = self.canvas.verticalScrollBar().value()
        self.canvas.document.deck.entries = entries
        update_candidate_quantities(self.editor.document, self.canvas)
        self.canvas.refresh()
        self.canvas.verticalScrollBar().setValue(position)
        self.status.setToolTip("")
        if entries:
            if snapshot["more"]:
                suffix = "More matches are available."
            else:
                suffix = "Select a card to inspect or set as commander."
            self.status.setText(f"{len(entries)} commanders / Backgrounds. {suffix}")
        else:
            self.status.setText("No commanders match these filters. Try broader text or a different theme.")
        self.more.setVisible(snapshot["more"])
        self.result_status = self.status.text()
        self.selection_changed()

    def selected(self):
        return next((self.rows[key] for key in self.canvas.selected if key in self.rows), None)

    def selection_changed(self):
        row = self.selected()
        self.set_button.setEnabled(row is not None)
        self.second_button.setEnabled(row is not None and len(commanders(self.editor.document)) == 1)
        if not row:
            self.details.setText("Choose a commander to start building.")
            return
        entry = row["entry"]
        self.details.setText(entry.name)
        self.details.setToolTip('Companion deck restrictions must be checked separately.'
                                if self.theme_options.get(self.theme_slug, {}).get('group') == 'Companions' else '')

    def change_quantity(self, entry_id, delta):
        row = self.rows.get(entry_id)
        if row and delta > 0:
            self.set_commander(entry_id)

    def set_commander(self, entry_id=None, _delta=1, *, second=False):
        row = self.rows.get(entry_id) if entry_id else self.selected()
        if row:
            self.canvas.preview.hide()
            select_commander(self.editor, row["entry"], second=second,
                             on_selected=lambda: self.editor.add_card_tabs.setCurrentWidget(self.editor.recommendation_panel))

    def card_menu(self, entry_id, position):
        menu = W.QMenu(self)
        menu.addAction("Inspect card", lambda: self.editor.candidate_details(self.canvas, entry_id))
        entry = self.rows[entry_id]["entry"]
        menu.addAction("Discover similar cards / popular commanders", lambda: self.editor.discover_card(entry))
        if self.canvas.face_count(entry) > 1:
            menu.addAction("Flip preview", lambda: self.canvas.flip_entry(entry))
        menu.addAction("Set as Commander", lambda: self.set_commander(entry_id))
        second = menu.addAction("Add as Second Commander", lambda: self.set_commander(entry_id, second=True))
        second.setEnabled(len(commanders(self.editor.document)) == 1)
        menu.exec(position)

    def show_more(self):
        self.limit += 50
        self.search()

    def deck_changed(self):
        from mtg_core.card_pool import pool_context
        pool = pool_context(self.editor.document)
        pool_changed = getattr(self, '_pool', None) != pool
        self._pool = pool
        with C.QSignalBlocker(self.legal):
            self.legal.setChecked(not pool[2])
        deck_id = self.editor.document.deck.deck_id
        saved = self.editor.document.editor_preferences.get('discovery', {})
        preferences_changed = (self.preference_deck != deck_id or self.theme_slug != saved.get('theme', '')
                or self.identity.currentData() != saved.get('identity'))
        if preferences_changed:
            self.preference_deck = deck_id
            saved = self.editor.document.editor_preferences.get('discovery', {})
            self.theme_slug = saved.get('theme', '')
            with C.QSignalBlocker(self.identity):
                self.identity.setCurrentIndex(max(0, self.identity.findData(saved.get('identity'))))
            with C.QSignalBlocker(self.theme):
                self.theme.setCurrentIndex(max(0, self.theme.findData(self.theme_slug)))
            self.loaded_query = None
            self.sync_theme_selection()
        selected = commanders(self.editor.document)
        context = (self.editor.document.deck.deck_id, tuple((e.entry_id, e.card_id) for e in selected))
        changed = context != self.context
        self.context = context
        if pool_changed or preferences_changed:
            self.controller.cancel()
            self.rows.clear()
            self.canvas.document.deck.entries.clear()
            self.canvas.refresh()
            self.loaded_query = None
        self.partner.setEnabled(len(selected) == 1 and bool(selected[0].card_id))
        if not self.partner.isEnabled():
            self.partner.setChecked(False)
        update_candidate_quantities(self.editor.document, self.canvas)
        self.selection_changed()
        if changed and self.partner.isChecked():
            self.filters_changed()
        elif (preferences_changed or pool_changed) and self.isVisible():
            self.controller.change_query(self.query())

    def showEvent(self, event):
        super().showEvent(event)
        self.deck_changed()
        if self.loaded_query != self.query():
            self.search()
        else:
            self.status.setText(self.result_status)

    def hideEvent(self, event):
        self.controller.cancel()
        super().hideEvent(event)
