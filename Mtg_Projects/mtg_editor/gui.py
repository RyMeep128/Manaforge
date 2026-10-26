from __future__ import annotations

from mtg_core.sections import DeckSection
from mtg_core.artwork import HighResOverride

from pathlib import Path
import uuid

from PyQt6 import QtCore, QtGui, QtWidgets as W
from mtg_core.decks import DeckDocument, DeckEntry, ENTRY_PRINT_FIELDS
from mtg_editor.session import DeckSession
from mtg_core.paths import data_root
from mtg_core import get_default_card_service
from mtg_editor.card_views import Thumbnails
from mtg_editor.canvas import CardCanvas
from mtg_editor.card_drop import CardDropPanel, CardSearchEdit
from mtg_editor.organization import SECTIONS, GROUPS, SORTS, card_facts, assign, move_entries
from mtg_ui.theme import application_stylesheet
from copy import deepcopy
from mtg_core.categorization import classify, apply_categories
from mtg_editor.filtering import compile_filter, matches, HELP as FILTER_HELP
from mtg_editor.search import SearchController, SearchWorker
from mtg_editor.tasks import EditorTaskRunner, Task


class DeckTable(QtCore.QAbstractTableModel):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.document.deck.entries)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else 4

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role == QtCore.Qt.ItemDataRole.UserRole:
            return self.document.deck.entries[index.row()]
        if index.isValid() and role == QtCore.Qt.ItemDataRole.DisplayRole:
            entry = self.document.deck.entries[index.row()]
            return (entry.quantity, entry.name, entry.section, entry.set_code or '')[index.column()]

    def headerData(self, section, orientation, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if role == QtCore.Qt.ItemDataRole.DisplayRole and orientation == QtCore.Qt.Orientation.Horizontal:
            return ('Quantity', 'Card', 'Section', 'Set')[section]

    def refresh(self):
        self.beginResetModel()
        self.endResetModel()



class EditorWindow(W.QMainWindow):
    def __init__(self, service=None, root=None):
        super().__init__()
        from mtg_ui.tooltips import disable_hover_tooltips
        disable_hover_tooltips()
        self.service = service or get_default_card_service()
        self.root = Path(root) if root else data_root() / 'decks'
        self.session = DeckSession(self.root)
        self._has_active_deck = False
        self.closing = False
        self.task_runner = EditorTaskRunner(self)
        self.task_runner.busyChanged.connect(self.task_busy_changed)
        self.task_runner.failed.connect(self.task_failed)
        self.task_runner.settled.connect(self.task_settled)
        from .search import SearchDraft
        self.search_draft = SearchDraft(self)
        self._quick_add_armed = False
        self.search_controller = SearchController(self.service, self)
        self.thumbnails = Thumbnails(self.service, self)
        from .basic_lands import AutomaticBasicLands
        self.basic_lands = AutomaticBasicLands(self)
        self.setStyleSheet(application_stylesheet())
        self.setWindowIcon(QtGui.QIcon(str(Path(__file__).resolve().parents[1] / 'mtg_proxy' / 'proxy.png')))
        self.resize(1280, 820)
        self.setMinimumSize(640, 360)
        self.autosave = QtCore.QTimer(self)
        self.autosave.setSingleShot(True)
        self.autosave.setInterval(2000)
        self.autosave.timeout.connect(self.save)
        body = W.QWidget()
        layout = W.QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = W.QFrame()
        header.setProperty('role', 'toolbar')
        header.setSizePolicy(W.QSizePolicy.Policy.Expanding, W.QSizePolicy.Policy.Fixed)
        header_layout = W.QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        bar = W.QHBoxLayout()
        header_layout.addLayout(bar)
        self.header_extra_container = W.QWidget()
        self.header_extra = W.QHBoxLayout(self.header_extra_container)
        self.header_extra.setContentsMargins(14, 0, 14, 6)
        self.header_extra.addStretch(1)
        header_layout.addWidget(self.header_extra_container)
        self.header_extra_container.hide()
        self.header_bar = bar
        bar.setContentsMargins(14, 10, 14, 10)
        decks = W.QToolButton()
        decks.setText('< Projects')
        decks.setPopupMode(W.QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        decks.clicked.connect(self.project_browser)
        self.recent = W.QMenu(decks)
        self.recent.aboutToShow.connect(self.refresh_recent)
        decks.setMenu(self.recent)
        bar.addWidget(decks)
        self.decks_button = decks
        self.name = W.QLineEdit(self.document.deck.name)
        self.name.setMinimumWidth(130)
        self.name.setStyleSheet('font-size:13pt;font-weight:600;')
        self.name.editingFinished.connect(self.edit_metadata)
        bar.addWidget(self.name, 1)
        self.format = W.QComboBox()
        self.format.addItems(['Custom', 'Commander', 'Modern', 'Standard', 'Pauper', 'Legacy', 'Vintage'])
        self.format.currentTextChanged.connect(self.edit_metadata)
        bar.addWidget(self.format)
        self.count = W.QLabel('0 cards')
        bar.addWidget(self.count)
        self.save_status = W.QLabel('Saved')
        self.save_status.setProperty('role', 'muted')
        bar.addWidget(self.save_status)
        self.undo_button = self.button(bar, 'Undo', self.undo)
        self.redo_button = self.button(bar, 'Redo', self.redo)
        self.save_button = self.button(bar, 'Save', self.save)
        self.print_button = self.button(bar, 'Print Deck', self.print_deck, True)
        more = W.QToolButton()
        more.setText('More')
        more.setPopupMode(W.QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = W.QMenu(more)
        menu.addAction('Artwork preferences?', self.artwork_preferences)
        menu.addAction('Deck artwork preferences...', self.project_artwork_preferences)
        menu.addAction('Global printing defaults...', self.printing_preferences)
        menu.addAction('Deck guidance…', self.deck_guidance)
        menu.addAction('Recommendations…', self.recommendations)
        menu.addAction('Import recommendation decks…', self.import_recommendation_decks)
        from .recommendation_cache import manage_cache
        menu.addAction('Recommendation cache…', lambda: manage_cache(self))
        menu.addAction('Text view', self.show_table)
        menu.addAction('Deck themes...', self.edit_themes)
        menu.addAction('Deck insights…', self.deck_insights)
        menu.addAction('Opening-hand playtest…', self.playtest)
        menu.addAction('Print readiness…', self.print_readiness)
        menu.addAction('Export decklist…', self.export_decklist)
        menu.addAction('Commander / format deck checks…', self.commander_checks)
        menu.addAction('Manage Tags…', self.manage_categories)
        menu.addAction('Comprehensive Rules…', self.rules_reference)
        menu.addAction('Customize Quick Menu…', lambda: self.manage_categories(customize=True))
        menu.addAction('Quick Additional Tags', lambda: self.quick_tag(QtGui.QCursor.pos(), tags=True))
        tag_overflow = menu.addMenu('Other active roles / tags')
        tag_overflow.aboutToShow.connect(lambda: self.populate_tag_overflow(tag_overflow))
        menu.addAction('Category templates…', self.category_templates)
        menu.addAction('Auto Categorize…', self.auto_categorize)
        menu.addAction('Quick category / tags (hold T)', lambda: self.quick_tag(QtGui.QCursor.pos()))
        self.show_empty_categories = menu.addAction('Show empty categories')
        self.show_empty_categories.setCheckable(True)
        self.show_empty_categories.toggled.connect(self.toggle_empty_categories)
        menu.addAction('Deck description…', self.edit_description)
        menu.addAction('Restore recovery snapshot…', self.recover)
        menu.addAction('Open deck…', self.open)
        more.setMenu(menu)
        bar.addWidget(more)
        self.header_actions = [self.undo_button, self.redo_button, self.save_button, self.print_button, more]
        layout.addWidget(header)
        controls = W.QFrame()
        controls.setProperty('role', 'toolbar')
        controls.setSizePolicy(W.QSizePolicy.Policy.Expanding, W.QSizePolicy.Policy.Fixed)
        control_layout = W.QVBoxLayout(controls)
        control_layout.setContentsMargins(14, 6, 14, 8)
        control_layout.setSpacing(6)
        self.control_bar = W.QHBoxLayout()
        self.control_bar.setSpacing(10)
        control_layout.addLayout(self.control_bar)
        self.control_extra_container = W.QWidget()
        self.control_extra = W.QVBoxLayout(self.control_extra_container)
        self.control_extra.setContentsMargins(0, 0, 0, 0)
        self.control_extra.setSpacing(10)
        control_layout.addWidget(self.control_extra_container)
        self.control_extra_container.hide()

        add_group, add_row = self.toolbar_group('Add Cards')
        self.workspace_button = self.button(add_row, 'Card Search', self.open_add_cards, True)
        self.button(add_row, 'Themes', self.edit_themes)
        self.quick_add = CardSearchEdit()
        self.quick_add.setPlaceholderText('Quick Add')
        self.quick_add.setAccessibleName('Quick Add: Enter searches, then Enter adds a result')
        self.quick_add.setFixedWidth(120)
        self.quick_add.returnPressed.connect(self.quick_add_enter)
        add_row.addWidget(self.quick_add)
        self.import_button = self.button(add_row, 'Import', self.import_decklist)

        view_group, view_row = self.toolbar_group('View As')
        self.view_mode = W.QComboBox()
        self.view_mode.addItems(['Grid', 'Stacks', 'Expanded Stacks', 'Text'])
        view_row.addWidget(self.view_mode)
        group_group, group_row = self.toolbar_group('Group By')
        self.group = W.QComboBox()
        self.group.addItems(GROUPS)
        group_row.addWidget(self.group)
        sort_group, sort_row = self.toolbar_group('Sort By')
        self.sort = W.QComboBox()
        self.sort.addItems(SORTS)
        sort_row.addWidget(self.sort)
        filter_group, filter_row = self.toolbar_group('Local Filter')
        self.filter = CardSearchEdit()
        self.filter.setClearButtonEnabled(True)
        self.filter.setPlaceholderText('Filter this deck')
        self.filter.setMinimumWidth(140)
        self.filter.setMaximumWidth(200)
        filter_row.addWidget(self.filter)
        self.filter_help = W.QToolButton()
        self.filter_help.setText('?')
        self.filter_help.setAccessibleName('Filter syntax help')
        self.filter_help.setFixedWidth(28)
        self.filter_help.setStyleSheet('padding:0 4px;')
        self.filter_help.clicked.connect(lambda: W.QMessageBox.information(self, 'Deck filters', FILTER_HELP))
        filter_row.addWidget(self.filter_help)
        self.readiness_filter = W.QPushButton()
        self.readiness_filter.hide()
        self.readiness_filter.clicked.connect(self.clear_readiness_filter)
        filter_row.addWidget(self.readiness_filter)
        self.readiness_snapshot = None

        self.organization_overflow = W.QToolButton()
        self.organization_overflow.setText('Display / Tags')
        self.organization_overflow.setPopupMode(W.QToolButton.ToolButtonPopupMode.InstantPopup)
        organization_menu = W.QMenu(self.organization_overflow)
        self.add_tag_button = W.QPushButton('+ Add Tag')
        self.add_tag_button.clicked.connect(lambda: self.add_tag())
        add_action = W.QWidgetAction(organization_menu)
        add_action.setDefaultWidget(self.add_tag_button)
        organization_menu.addAction(add_action)
        self.quick_tag_button = W.QPushButton('Quick Tags')
        self.quick_tag_button.clicked.connect(lambda: self.quick_tag(QtGui.QCursor.pos()))
        self.compact_quick_tags = W.QWidgetAction(organization_menu)
        self.compact_quick_tags.setDefaultWidget(self.quick_tag_button)
        organization_menu.addAction(self.compact_quick_tags)
        organization_menu.addAction('Manage Tags', self.manage_categories)
        organization_menu.addAction('Customize Quick Menu', lambda: self.manage_categories(customize=True))
        organization_menu.addSeparator()
        zoom_widget = W.QWidget()
        zoom_row = W.QHBoxLayout(zoom_widget)
        zoom_row.addWidget(W.QLabel('Card size'))
        self.zoom = W.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.zoom.setRange(120, 260)
        self.zoom.setValue(180)
        self.zoom.setMaximumWidth(135)
        zoom_row.addWidget(self.zoom)
        zoom_action = W.QWidgetAction(organization_menu)
        zoom_action.setDefaultWidget(zoom_widget)
        organization_menu.addAction(zoom_action)
        self.organization_overflow.setMenu(organization_menu)
        self.add_lands_button = W.QPushButton('Add Lands')
        self.add_lands_button.setToolTip('Fill remaining deck slots with legal basic lands. Removing a land stops automatic filling.')
        self.add_lands_button.clicked.connect(self.add_lands)
        self.selection_label = W.QLabel('')
        self.control_groups = [add_group, view_group, group_group, sort_group, filter_group]
        self.control_overflow = self.control_groups
        for widget in [*self.control_groups, self.organization_overflow, self.add_lands_button, self.selection_label]:
            self.control_bar.addWidget(widget)
        self.control_bar.addStretch(1)
        self.control_extra_rows = []
        self.name.setMinimumHeight(34)
        for widget in (self.format, self.view_mode, self.group, self.sort, self.filter, self.quick_add,
                       self.filter_help, self.workspace_button, self.import_button, self.organization_overflow, self.add_lands_button,
                       *self.header_actions):
            # The theme's 32px content minimum also needs room for its borders.
            # Let Qt honor the styled size hint instead of clipping it at 32px.
            widget.setMinimumHeight(34)
        layout.addWidget(controls)
        self.splitter = W.QSplitter()
        self.search_panel = CardDropPanel(self)
        self.search_panel.setMinimumWidth(270)
        search_layout = W.QVBoxLayout(self.search_panel)
        search_header = W.QHBoxLayout()
        label = W.QLabel('Quick Add')
        self.search_heading = label
        label.setProperty('role', 'title')
        search_header.addWidget(label, 1)
        self.search_close = self.button(search_header, '×', self.toggle_search)
        search_layout.addLayout(search_header)
        self.add_card_tabs = W.QTabWidget()
        search_layout.addWidget(self.add_card_tabs, 1)
        self.syntax_search_page = W.QWidget()
        search_layout = W.QVBoxLayout(self.syntax_search_page)
        search_layout.setContentsMargins(0, 8, 0, 0)
        self.add_card_tabs.addTab(self.syntax_search_page, 'Syntax Search')
        self.query = CardSearchEdit()
        self.query.setPlaceholderText('Local search: o:flying c=g')
        self.query.textChanged.connect(self.search_draft.set_text)
        self.query.setMinimumHeight(38)
        self.query.returnPressed.connect(self.search)
        self.query.setClearButtonEnabled(True)
        search_layout.addWidget(self.query)
        search_controls = W.QHBoxLayout()
        self.syntax_search_button = self.button(search_controls, 'Search', self.search, True)
        self.cancel_search_button = self.button(search_controls, 'Cancel', self.cancel_search)
        self.cancel_search_button.setEnabled(False)
        self.refresh_search_button = self.button(search_controls, 'Refresh', self.refresh_results)
        self.refresh_search_button.setToolTip('Bypass recent results. Cached searches expire after 30 seconds.')
        self.syntax_membership = W.QComboBox()
        self.syntax_membership.addItems(['All cards', 'Not in deck', 'In deck'])
        self.syntax_membership.setCurrentIndex(1)
        self.syntax_membership.currentIndexChanged.connect(self.filter_syntax_results)
        self.syntax_all_entries = []
        self.syntax_error = ''
        search_layout.addLayout(search_controls)
        search_layout.addWidget(self.syntax_membership)
        self.include_illegal = W.QCheckBox('Include illegal cards')
        self.include_illegal.setAccessibleDescription('Ignore deck format and commander color identity defaults')
        self.include_illegal.toggled.connect(self.set_include_illegal)
        search_layout.addWidget(self.include_illegal)
        self.search_status = W.QLabel('Search by name or Scryfall syntax')
        self.search_status.setWordWrap(True)
        search_layout.addWidget(self.search_status)
        self.search_document = DeckDocument()
        self.results = CardCanvas(self.search_document, self.thumbnails, search=True)
        self.results.card_width = 130
        self.results.quantityRequested.connect(self.add_result)
        self.results.menuRequested.connect(self.search_menu)
        self.results.detailsRequested.connect(lambda key: self.candidate_details(self.results, key))
        search_layout.addWidget(self.results, 1)
        self.search_more = W.QPushButton('Load More')
        self.search_more.hide()
        self.search_more.clicked.connect(self.search_controller.load_more)
        self.search_controller.pageStateChanged.connect(self.search_more.setVisible)
        self.search_controller.busyChanged.connect(lambda busy: self.search_more.setEnabled(not busy))
        search_layout.addWidget(self.search_more)
        from .recommendation_panel import RecommendationPanel
        self.recommendation_panel = RecommendationPanel(self)
        self.add_card_tabs.addTab(self.recommendation_panel, 'Recommendations')
        self.add_card_tabs.currentChanged.connect(self.add_card_tab_changed)
        self.splitter.addWidget(self.search_panel)
        self.grid = CardCanvas(self.document, self.thumbnails)
        self.grid.selectionChanged.connect(self.selection_changed)
        self.grid.quantityRequested.connect(self.change_quantity)
        self.grid.artworkRequested.connect(self.replace_artwork)
        self.grid.detailsRequested.connect(self.card_details)
        self.grid.menuRequested.connect(self.card_menu)
        self.grid.quickTagRequested.connect(self.quick_tag)
        self.grid.setToolTip('Hold right mouse or T: quick category / tags. Right-click: card actions.')
        self.grid.moveRequested.connect(self.move_cards)
        self.grid.preferencesChanged.connect(self.preferences_changed)
        self.grid.addRequested.connect(self.open_add_cards)
        self.model = DeckTable(self.document, self)
        self.table = W.QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(W.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(W.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.selectionModel().selectionChanged.connect(self.table_selection_changed)
        self.table.installEventFilter(self)
        self.table.viewport().installEventFilter(self)
        from .quick_tags import HoldTagGesture
        from .tag_model import hold_delay
        self.tag_gestures = [HoldTagGesture(view,
            lambda position, v=view: self.select_tag_target(v, position),
            lambda entry_id, position: self.card_menu(entry_id, position), self.quick_tag,
            delay=lambda: hold_delay(self.document))
            for view in (self.grid, self.table)]
        self.table.setToolTip(self.grid.toolTip())
        self._refreshing_table = False
        self.table.horizontalHeader().setSectionResizeMode(1, W.QHeaderView.ResizeMode.Stretch)
        self.views = W.QStackedWidget()
        self.views.addWidget(self.grid)
        self.views.addWidget(self.table)
        from .text_view import TextDeckView
        self.text_view = TextDeckView(self)
        self.views.addWidget(self.text_view)
        self.view_scrolls = {}
        self._active_view = 'Stacks'
        self.splitter.addWidget(self.views)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([330, 920])
        self.splitter.splitterMoved.connect(self.preferences_changed)
        self.search_panel.hide()
        from .add_cards_workspace import AddCardsWorkspace
        self.workspace_stack = W.QStackedWidget()
        self.workspace_stack.addWidget(self.splitter)
        self.add_cards_workspace = AddCardsWorkspace(self, controls)
        self.workspace_stack.addWidget(self.add_cards_workspace)
        layout.addWidget(self.workspace_stack, 1)
        for canvas in (self.grid, *self.add_cards_workspace.canvases()):
            canvas.discoverRequested.connect(self.discover_card)
        from .project_browser import ProjectDashboard
        self.editor_body = body
        self.dashboard = ProjectDashboard(self.root, data_root() / 'projects', self.thumbnails, self)
        self.dashboard.newRequested.connect(self.new)
        self.dashboard.openRequested.connect(self.open_path)
        self.dashboard.resumeRequested.connect(self.resume_deck)
        self.project_stack = W.QStackedWidget()
        self.project_stack.addWidget(self.dashboard)
        self.project_stack.addWidget(body)
        self.setCentralWidget(self.project_stack)
        for combo in (self.view_mode, self.group, self.sort):
            combo.currentTextChanged.connect(self.preferences_changed)
        self.zoom.valueChanged.connect(self.preferences_changed)
        self.filter.textChanged.connect(self.filter_changed)
        self.shortcuts = []
        for sequence, callback in [('Ctrl+S', self.save), ('Ctrl+N', self.new), ('Ctrl+O', self.open),
                                   ('Ctrl+Z', self.undo), ('Ctrl+Y', self.redo), ('Ctrl+Shift+Z', self.redo),
                                   ('Ctrl+F', self.focus_filter), ('Ctrl+K', self.open_search)]:
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(sequence),
                                       self if sequence in ('Ctrl+S', 'Ctrl+N', 'Ctrl+O') else body)
            shortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
        from mtg_ui.keyboard import add_shortcuts_help
        add_shortcuts_help(self)
        self.search_draft.changed.connect(self.sync_search_draft)
        self.quick_add.textChanged.connect(self.search_draft.set_text)
        self.search_close.setToolTip('Close Quick Add (Esc)')
        self.sync_fields()
        self.changed()

        self.search_controller.resultsReady.connect(self.show_results)
        self.search_controller.cleared.connect(self.clear_search_results)
        self.search_controller.statusChanged.connect(self.search_status.setText)
        self.search_controller.busyChanged.connect(self.cancel_search_button.setEnabled)

    @property
    def task(self):
        return self.task_runner.task

    @property
    def worker(self):
        return self.search_controller.worker

    @property
    def search_timer(self):
        return self.search_controller.timer

    @property
    def pending_search(self):
        return self.search_controller.pending

    @property
    def search_cache(self):
        return self.search_controller.cache

    # Compatibility accessors keep existing widget and extension callers working.
    @property
    def document(self):
        return self.session.document

    @property
    def history(self):
        return self.session.history

    @property
    def store(self):
        return self.session.store

    @property
    def path(self):
        return self.session.path

    @property
    def saved(self):
        return self.session.saved

    @saved.setter
    def saved(self, value):
        self.session.saved = value

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, 'control_groups'):
            return
        short = self.height() < 560
        self.search_heading.setVisible(not short)
        self.search_close.setVisible(not short)
        self.search_status.setVisible(not short)
        self.reflow_toolbars()

    def reflow_toolbars(self):
        compact = self.height() < 650
        for group in self.control_groups:
            group.title_label.setVisible(not compact)
            group.layout().setSpacing(0 if compact else 2)
        available = max(300, self.width()-28)
        info = (self.decks_button.sizeHint().width() + self.name.minimumWidth() +
                self.format.sizeHint().width() + self.count.sizeHint().width() +
                self.save_status.sizeHint().width() + 36)
        wrap_header = info + sum(widget.sizeHint().width()+6 for widget in self.header_actions) > available
        target = self.header_extra if wrap_header else self.header_bar
        for widget in self.header_actions:
            if target.indexOf(widget) < 0:
                self.header_bar.removeWidget(widget)
                self.header_extra.removeWidget(widget)
                target.addWidget(widget)
        self.header_extra_container.setVisible(wrap_header)

        rows = [[]]
        used = 0
        widgets = [*self.control_groups, self.organization_overflow, self.add_lands_button, self.selection_label]
        for widget in widgets:
            width = widget.sizeHint().width() + 10
            if rows[-1] and used + width > available:
                rows.append([])
                used = 0
            rows[-1].append(widget)
            used += width
        while len(self.control_extra_rows) < len(rows)-1:
            row = W.QHBoxLayout()
            row.setSpacing(10)
            row.addStretch(1)
            self.control_extra.addLayout(row)
            self.control_extra_rows.append(row)
        layouts = [self.control_bar, *self.control_extra_rows]
        for row, row_widgets in zip(layouts, rows):
            for index, widget in enumerate(row_widgets):
                if row.indexOf(widget) != index:
                    for previous_row in layouts:
                        previous_row.removeWidget(widget)
                    row.insertWidget(index, widget)
        self.control_extra_container.setVisible(len(rows) > 1)

    def toolbar_group(self, title):
        frame = W.QFrame()
        name = 'deckTools' + title.replace(' ', '')
        frame.setObjectName(name)
        frame.setStyleSheet('QFrame#' + name + ' {border-right:1px solid #303743;}')
        frame.setSizePolicy(W.QSizePolicy.Policy.Fixed, W.QSizePolicy.Policy.Fixed)
        layout = W.QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 8, 2)
        layout.setSpacing(2)
        label = W.QLabel(title)
        frame.title_label = label
        frame.setAccessibleName(title)
        frame.setToolTip(title)
        label.setStyleSheet('font-size:9pt;color:#b5bdc9;')
        layout.addWidget(label)
        row = W.QHBoxLayout()
        row.setSpacing(6)
        layout.addLayout(row)
        return frame, row

    def sync_search_draft(self, text, syntax):
        panel = self.add_cards_workspace.card_search
        for field in (self.quick_add, self.query, panel.name):
            with QtCore.QSignalBlocker(field):
                field.setText(text)
        self._quick_add_armed = False
        self._quick_add_ready_query = None
        if self.syntax_search_page.isVisible():
            self.search_changed()
        else:
            self.cancel_search()
            self.clear_search_results()
        if panel.isVisible():
            panel.query_changed()
        else:
            panel.controller.cancel()
            panel.clear()

    def quick_add_enter(self):
        query = self.quick_add.text().strip()
        if not query:
            self.open_search()
            return
        if (self._quick_add_armed and getattr(self, '_quick_add_ready_query', None) == query
                and self.query.text().strip() == query
                and self.search_document.deck.entries):
            entry = next((entry for entry in self.search_document.deck.entries if entry.entry_id in self.results.selected),
                         self.search_document.deck.entries[0])
            self.add_result(entry.entry_id)
            self.quick_add.setFocus()
            return
        self._quick_add_armed = True
        self.search_draft.set_text(self.quick_add.text())
        self.open_search()
        self.quick_add.setFocus()
        self.statusBar().showMessage('Enter again after results load to add the selected or first match.', 4000)

    def button(self, layout, text, callback, primary=False):
        button = W.QPushButton(text)
        if primary:
            button.setProperty('buttonRole', 'primary')
        button.clicked.connect(lambda checked=False: callback())
        layout.addWidget(button)
        return button

    def discover_card(self, entry):
        from .card_discovery import CardDiscoveryDialog
        if not hasattr(self, 'card_discovery_dialog'):
            self.card_discovery_dialog = CardDiscoveryDialog(self)
        self.card_discovery_dialog.open_card(entry)

    def add_lands(self):
        from mtg_core.basic_lands import AUTOMATION
        if self.closing or self.task is not None:
            return
        self.basic_lands.retry_after.clear()
        self.edit(lambda document: document.deck.extras.update({AUTOMATION: True}))
        # Also retry when automation was already enabled and waiting for data.
        self.changed()
        self.statusBar().showMessage('Automatic basic lands enabled; waiting for legal colors or catalog data if needed.', 6000)

    def edit_themes(self):
        from .themes import edit_themes
        edit_themes(self)

    def artwork_preferences(self):
        from mtg_ui.artwork_preferences import edit_artwork_preferences
        edit_artwork_preferences(self, self.service)

    def printing_preferences(self):
        from mtg_ui.printing_preferences import edit_printing_preferences
        edit_printing_preferences(self, self.service)

    def project_artwork_preferences(self):
        from mtg_ui.artwork_preferences import choose_project_artwork_preferences
        accepted, rules = choose_project_artwork_preferences(self, self.service, self.document)
        if accepted:
            self.edit(lambda document: setattr(document, 'artwork_preferences', rules))

    def focus_filter(self):
        self.add_cards_workspace.back()
        self.filter.setFocus()
        self.filter.selectAll()

    def open_search(self):
        self.add_cards_workspace.back()
        self.search_panel.show()
        with QtCore.QSignalBlocker(self.add_card_tabs):
            self.add_card_tabs.setCurrentIndex(0)
        self.splitter.setSizes([self.document.editor_preferences.get('panel_width', 330), max(400, self.width()-330)])
        self.add_card_tab_changed(0)

    def open_add_cards(self):
        self._quick_add_armed = False
        self.add_cards_workspace.open()
        if self.search_draft.text.strip():
            target = self.syntax_search_page if self.search_draft.syntax else self.add_cards_workspace.card_search
            self.add_card_tabs.setCurrentWidget(target)
            field = self.query if self.search_draft.syntax else self.add_cards_workspace.card_search.name
            field.setFocus()

    def add_card_tab_changed(self, index):
        if self.add_card_tabs.widget(index) is self.syntax_search_page:
            self.query.setFocus()
            if (self.query.text().strip() and not self.search_document.deck.entries
                    and not self.pending_search
                    and (self.worker is None or self.worker.cancelled.is_set())):
                self.search()
            elif (self.search_document.deck.entries
                    and (self.worker is None or self.worker.cancelled.is_set())):
                self.search_status.setText(
                    f'{len(self.search_document.deck.entries)} local matches loaded. Double-click or + to add.')
        else:
            self.cancel_search()
            self.results.hover_timer.stop()
            self.results.preview.hide()
            self.thumbnails.set_visible(id(self.results), [])

    def toggle_search(self):
        if self.add_cards_workspace.expanded:
            self.open_search()
            return
        if self.search_panel.isHidden():
            self.open_search()
        else:
            self.search_panel.hide()
            self.cancel_search()
            self.results.preview.hide()
            self.thumbnails.set_visible(id(self.results), [])

    def filter_changed(self):
        try:
            compile_filter(self.filter.text())
        except ValueError as exc:
            self.filter.setStyleSheet('border: 1px solid #e0a040;')
            self.filter.setToolTip(f'{exc} Showing the last valid filter.\n\n{FILTER_HELP}')
            self.statusBar().showMessage(f'{exc} Showing the last valid filter.')
            return
        self.filter.setStyleSheet('')
        self.filter.setToolTip(FILTER_HELP)
        self.grid.query = self.filter.text()
        self.grid.relayout()
        self.text_view.refresh()
        visible = self.apply_table_filter()
        active = bool(self.grid.query) or self.grid.filtered_ids is not None
        self.statusBar().showMessage(f'{visible} of {len(self.document.deck.entries)} entries match' if active else 'Deck filter cleared')

    def apply_table_filter(self):
        terms = compile_filter(self.grid.query)
        categories = {c.category_id: c.name for c in self.document.deck.categories}
        visible_ids = set()
        for row, entry in enumerate(self.document.deck.entries):
            visible = matches(entry, terms, categories)
            if self.grid.filtered_ids is not None:
                visible = visible and entry.entry_id in self.grid.filtered_ids
            self.table.setRowHidden(row, not visible)
            if visible:
                visible_ids.add(entry.entry_id)
        self.grid.selected.intersection_update(visible_ids)
        self.restore_table_selection()
        self.selection_changed()
        return len(visible_ids)

    def view_scrollbar(self, mode):
        return self.text_view.rows.verticalScrollBar() if mode == 'Text' else self.grid.verticalScrollBar()

    def preferences_changed(self, *_):
        mode = self.view_mode.currentText()
        switched = mode != self._active_view
        if switched:
            self.view_scrolls[self._active_view] = self.view_scrollbar(self._active_view).value()
            self.grid.detail_timer.stop()
            self.grid.hover_timer.stop()
            self.grid.preview.hide()
        if mode != 'Text':
            self.grid.mode = mode
        self._active_view = mode
        self.grid.grouping = self.group.currentText()
        self.grid.sort = self.sort.currentText()
        self.grid.card_width = self.zoom.value()
        self.views.setCurrentWidget(self.text_view if mode == 'Text' else self.grid)
        self.document.editor_preferences.update(view=mode, group=self.grid.grouping,
            sort=self.grid.sort, card_width=self.grid.card_width, collapsed=sorted(self.grid.collapsed),
            view_scrolls=dict(self.view_scrolls))
        if not self.search_panel.isHidden():
            self.document.editor_preferences['panel_width'] = self.splitter.sizes()[0]
        self.changed()
        if switched:
            position = self.view_scrolls.get(mode, 0)
            self.view_scrollbar(mode).setValue(position)
            QtCore.QTimer.singleShot(0, lambda: self.view_scrollbar(mode).setValue(position)
                                    if self._active_view == mode else None)

    def selection_changed(self):
        count = len(self.grid.selected)
        self.selection_label.setText(f'{count} selected' if count else '')
        self.quick_tag_button.setEnabled(bool(count))
        self.compact_quick_tags.setEnabled(bool(count))
        self.text_view.rows.viewport().update()
        self.text_view.update_preview()

    def keyPressEvent(self, event):
        # Native popups and focused controls receive the event before it bubbles
        # here. Do not register an Escape shortcut that preempts them.
        if event.key() == QtCore.Qt.Key.Key_Escape and not event.modifiers():
            canvases = (self.grid, *self.add_cards_workspace.canvases())
            previews = [canvas for canvas in canvases if canvas.preview.isVisible()]
            if previews:
                for canvas in previews:
                    canvas.hover_timer.stop()
                    canvas.detail_timer.stop()
                    canvas.preview.hide()
            elif self.add_cards_workspace.expanded:
                self.add_cards_workspace.back()
                # Escape returns directly to the deck even if Quick Add was
                # visible before entering the full discovery workspace.
                if not self.search_panel.isHidden():
                    self.toggle_search()
                (self.text_view.rows if self.views.currentWidget() is self.text_view
                 else self.views.currentWidget()).setFocus()
            elif not self.search_panel.isHidden():
                self.toggle_search()
                (self.text_view.rows if self.views.currentWidget() is self.text_view
                 else self.views.currentWidget()).setFocus()
            event.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched, event):
        if watched in (self.table, self.table.viewport()):
            if (event.type() == QtCore.QEvent.Type.KeyPress
                    and event.key() in (QtCore.Qt.Key.Key_Delete, QtCore.Qt.Key.Key_Backspace)
                    and not event.modifiers()
                    and self.grid.selected
                    and self.table.state() != W.QAbstractItemView.State.EditingState):
                self.remove_selected()
                return True
            if (event.type() == QtCore.QEvent.Type.KeyPress and event.key() == QtCore.Qt.Key.Key_T
                    and not event.modifiers() and self.grid.selected):
                if not event.isAutoRepeat():
                    self.quick_tag(QtGui.QCursor.pos())
                return True
        return super().eventFilter(watched, event)

    def select_tag_target(self, view, position):
        self.grid.detail_timer.stop()
        view.setFocus()
        self.grid.hover_timer.stop()
        self.grid.preview.hide()
        point = view.viewport().mapFromGlobal(position)
        if view is self.table:
            index = self.table.indexAt(point)
            if not index.isValid():
                return None
            entry_id = self.document.deck.entries[index.row()].entry_id
            if entry_id not in self.grid.selected:
                self.table.selectRow(index.row())
        else:
            item = self.grid.hit(point)
            if not item:
                return None
            entry_id = item[0].entry_id
            if entry_id not in self.grid.selected:
                self.grid.selected = {entry_id}
            self.grid.selectionChanged.emit()
            self.grid.viewport().update()
        return entry_id

    def show_table(self):
        self.add_cards_workspace.back()
        if self.view_mode.currentText() == 'Text':
            self.views.setCurrentWidget(self.text_view)
        else:
            self.view_mode.setCurrentText('Text')

    def table_selection_changed(self, *_):
        if self._refreshing_table or self.views.currentWidget() is not self.table:
            return
        self.grid.selected = {self.document.deck.entries[index.row()].entry_id
                              for index in self.table.selectionModel().selectedRows()}
        self.selection_changed()

    def restore_table_selection(self):
        self._refreshing_table = True
        self.table.clearSelection()
        flags = QtCore.QItemSelectionModel.SelectionFlag.Select | QtCore.QItemSelectionModel.SelectionFlag.Rows
        for row, entry in enumerate(self.document.deck.entries):
            if entry.entry_id in self.grid.selected:
                index = self.model.index(row, 0)
                self.table.selectionModel().select(index, flags)
                self.table.selectionModel().setCurrentIndex(index, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)
        self._refreshing_table = False

    def edit(self, action):
        from .tag_model import retain_tag_definitions
        from mtg_core.basic_lands import land_quantities, stop_on_land_removal, reconcile_basic_lands
        def command(document):
            previous_lands = land_quantities(document)
            retain_tag_definitions(document)
            action(document)
            stop_on_land_removal(document, previous_lands)
            reconcile_basic_lands(document, self.basic_lands.templates)
            retain_tag_definitions(document)
        if self.session.edit(command):
            self._has_active_deck = True
            self.project_stack.setCurrentWidget(self.editor_body)
            self.changed()

    def changed(self):
        if not self._has_active_deck and (self.document.deck.entries or self.document.deck.categories):
            self._has_active_deck = True
            self.project_stack.setCurrentWidget(self.editor_body)
        self.basic_lands.changed()
        from mtg_core.basic_lands import AUTOMATION
        lands_active = self.document.deck.extras.get(AUTOMATION, False) is True
        self.add_lands_button.setText('Add Lands - Active' if lands_active else 'Add Lands')
        self.add_lands_button.setAccessibleName(self.add_lands_button.text())
        self.add_lands_button.setToolTip(
            'Automatic land filling is active, including while waiting for legal colors or catalog data. Removing a land stops it.'
            if lands_active else 'Fill remaining deck slots with legal basic lands. Removing a land stops automatic filling.')
        self.add_lands_button.setStyleSheet(
            'QPushButton { background-color: #237443; border-color: #39945b; color: white; }'
            'QPushButton:hover { background-color: #2b8750; }'
            'QPushButton:pressed { background-color: #1b5c35; }'
            'QPushButton:disabled { background-color: #294b36; color: #b3c8ba; }'
            if lands_active else '')
        deck_id = self.document.deck.deck_id
        from mtg_core.card_pool import pool_context
        pool_key = (deck_id, pool_context(self.document))
        if getattr(self, '_search_pool_key', None) != pool_key:
            self._search_pool_key = pool_key
            self.search_controller.change_query(self.effective_search_query())
            self.add_cards_workspace.card_search.query_changed()
        self._discovery_deck_id = deck_id
        with QtCore.QSignalBlocker(self.include_illegal):
            self.include_illegal.setChecked(self.document.editor_preferences.get('include_illegal_cards', False))
        if not self.name.isModified():
            self.name.setText(self.document.deck.name)
        for gesture in getattr(self, 'tag_gestures', []):
            gesture.cancel()
        previous = getattr(self, 'quick_menu', None)
        if previous is not None:
            previous.close()
        if hasattr(self, 'card_discovery_dialog'):
            self.card_discovery_dialog.deck_changed()
        self.update_search_membership()
        self.recommendation_panel.deck_changed()
        self.add_cards_workspace.discovery.deck_changed()
        self.add_cards_workspace.card_search.update_quantities()
        if self.readiness_snapshot is not None and self.document.to_dict() != self.readiness_snapshot:
            self.grid.filtered_ids = None
            self.readiness_snapshot = None
            self.readiness_filter.hide()
            self.statusBar().showMessage('Deck changed; readiness filter cleared. Run Print readiness again for updated results.')
        self._refreshing_table = True
        self.model.refresh()
        self._refreshing_table = False
        self.grid.refresh()
        self.apply_table_filter()
        self.text_view.refresh()
        if self.views.currentWidget() is self.table:
            self.restore_table_selection()
        dirty = self.session.dirty
        self.setWindowTitle(f'{self.document.deck.name}{"*" if dirty else ""} — Manaforge Deck Editor')
        total = sum(e.quantity for e in self.document.deck.entries if e.section in (DeckSection.MAINBOARD, DeckSection.COMMANDER))
        self.count.setText(f'{total} cards')
        self.save_status.setText('Unsaved' if dirty else 'Saved')
        self.undo_button.setEnabled(self.history.can_undo)
        self.redo_button.setEnabled(self.history.can_redo)
        self.add_cards_workspace.undo_button.setEnabled(self.history.can_undo)
        self.add_cards_workspace.redo_button.setEnabled(self.history.can_redo)
        self.selection_changed()
        self.reflow_toolbars()
        if dirty:
            self.autosave.start()

    def edit_metadata(self):
        name_edited = self.name.isModified()
        def action(document):
            document.deck.name = self.name.text().strip() or 'Untitled Deck'
            if name_edited:
                document.deck.extras['manual_name'] = bool(self.name.text().strip())
            document.deck.format = self.format.currentText()
        self.edit(action)
        self.name.setModified(False)
        self.name.setText(self.document.deck.name)

    def edit_description(self):
        text, ok = W.QInputDialog.getMultiLineText(self, 'Deck description', 'Description:', self.document.deck.description)
        if ok:
            self.edit(lambda d: setattr(d.deck, 'description', text))

    def clear_search_results(self):
        self.syntax_all_entries = []
        self.syntax_error = ''
        self.search_document.deck.entries.clear()
        self.results.refresh()

    def set_include_illegal(self, checked):
        self.edit(lambda d: d.editor_preferences.update(include_illegal_cards=checked))

    def effective_search_query(self):
        from mtg_core.card_pool import deck_query
        return deck_query(self.query.text(), self.document)

    def search_changed(self):
        self.search_controller.change_query(self.effective_search_query())

    def cancel_search(self):
        self.search_controller.cancel()

    def refresh_results(self):
        self.search_controller.search(self.effective_search_query(), refresh=True)

    def search(self):
        if not self.closing:
            self.search_controller.search(self.effective_search_query())

    def show_results(self, query, results, error):
        if query != self.effective_search_query():
            return
        self._quick_add_ready_query = self.query.text().strip() if not error else None
        self.syntax_error = error
        previous = {entry.card_id: entry for entry in self.syntax_all_entries}
        self.search_document.deck.entries = [previous.get(r.card_id) or DeckEntry(entry_id=r.card_id, name=r.name,
            card_id=r.card_id, oracle_id=r.oracle_id, set_code=r.set_code,
            collector_number=r.collector_number, pre_cropped=True, extras={'facts': card_facts(getattr(r, 'payload', {}) or {}),
                'category_suggestion': (getattr(r, 'payload', {}) or {}).get('_category_evidence',
                    classify(getattr(r, 'payload', {}) or {}))}) for r in results]
        self.results.refresh()
        self.syntax_all_entries = list(self.search_document.deck.entries)
        self.filter_syntax_results()
        self.search_status.setText(error or (f'Showing {len(self.search_document.deck.entries)} local matches. ' +
            ('Load More for additional results.' if self.search_controller.has_more else 'All available results loaded.')))

    def filter_syntax_results(self, *_):
        from .organization import in_deck_entries, update_candidate_quantities
        present = in_deck_entries(self.document, self.syntax_all_entries)
        membership = self.syntax_membership.currentIndex()
        self.search_document.deck.entries = [entry for entry in self.syntax_all_entries
            if membership == 0 or (entry.entry_id in present) == (membership == 2)]
        update_candidate_quantities(self.document, self.results)
        self.results.refresh()
        if self.syntax_all_entries and not self.syntax_error:
            self.search_status.setText(f'Showing {len(self.search_document.deck.entries)} local matches. ' +
                ('Load More for additional results.' if self.search_controller.has_more else 'All available results loaded.'))

    def update_search_membership(self):
        from .organization import update_candidate_quantities
        if self.syntax_membership.currentIndex() and self.syntax_all_entries:
            self.filter_syntax_results()
        update_candidate_quantities(self.document, self.results)

    def add_result(self, entry_id, delta=1):
        result = next((e for e in [*self.syntax_all_entries, *self.search_document.deck.entries]
                       if e.entry_id == entry_id), None)
        if result is None:
            return
        self.change_candidate_quantity(result, delta)

    def change_candidate_quantity(self, result, delta=1):
        if delta > 0:
            self.add_card(result)
            return
        if delta >= 0:
            return
        matches = [entry for entry in self.document.deck.entries
                   if entry.quantity > 0 and entry.section in (DeckSection.MAINBOARD, DeckSection.COMMANDER)
                   and ((result.card_id and entry.card_id == result.card_id)
                        or (result.oracle_id and entry.oracle_id == result.oracle_id)
                        or (entry.name.casefold() == result.name.casefold()
                            and (not result.oracle_id or not entry.oracle_id)))]
        if not matches:
            return
        # Prefer mainboard copies and the visible printing before alternatives.
        target = min(matches, key=lambda entry: (entry.section == DeckSection.COMMANDER,
                                                 entry.card_id != result.card_id, entry.sort_order))
        from .card_details import apply_quantity
        self.edit(lambda d: apply_quantity(d, target.entry_id, target.quantity-1))

    def add_card(self, result):
        """Shared Add Card command for search and recommendation discovery."""
        def action(document):
            existing = next((e for e in document.deck.entries if ((result.card_id and e.card_id == result.card_id)
                or (not result.card_id and not e.card_id and e.name.casefold() == result.name.casefold()))
                and e.section == DeckSection.MAINBOARD and not e.art_override), None)
            if existing:
                existing.quantity += 1
            else:
                entry = deepcopy(result)
                entry.quantity = 1
                entry.entry_id = str(uuid.uuid4())
                entry.sort_order = max((e.sort_order for e in document.deck.entries), default=-1)+1
                document.deck.entries.append(entry)
                apply_categories(document, {entry.entry_id: entry.extras.pop('category_suggestion', [])})
        self.edit(action)

    def change_quantity(self, entry_id, delta):
        if not entry_id and delta == 0:
            self.remove_selected()
            return
        ids = set(self.grid.selected) if entry_id in self.grid.selected else {entry_id}
        def action(document):
            for entry in document.deck.entries:
                if entry.entry_id in ids:
                    entry.quantity = max(0, entry.quantity+delta)
            removed = {entry.entry_id for entry in document.deck.entries
                       if entry.entry_id in ids and entry.quantity == 0}
            document.deck.entries = [entry for entry in document.deck.entries if entry.entry_id not in removed]
            document.deck.commander_entry_ids = [key for key in document.deck.commander_entry_ids if key not in removed]
        self.edit(action)

    def remove_selected(self):
        ids = set(self.grid.selected)
        def action(document):
            document.deck.entries = [e for e in document.deck.entries if e.entry_id not in ids]
            document.deck.commander_entry_ids = [i for i in document.deck.commander_entry_ids if i not in ids]
        self.edit(action)

    def move_cards(self, ids, target, before):
        self.edit(lambda d: move_entries(d, ids, self.grid.grouping, target, before))

    def quick_tag(self, position, *, hold=False, tags=None):
        from .quick_tags import QuickTagMenu, apply_quick_role
        ids = set(self.grid.selected) & {e.entry_id for e in self.document.deck.entries}
        if not ids:
            self.statusBar().showMessage('Select cards to categorize or tag.', 4000)
            return
        self.grid.hover_timer.stop()
        self.grid.preview.hide()
        previous = getattr(self, 'quick_menu', None)
        if previous is not None:
            previous.close()
            previous.deleteLater()
        self.quick_menu = QuickTagMenu(self.document, ids, self, hold=hold, tags=tags)
        target = self.grid.context_target or self.grid.hovered
        self.grid.pin_context_target(target if target in ids else next(iter(ids)))
        self.quick_menu.closed.connect(self.grid.release_context_target)
        snapshot = self.document.to_dict()
        def apply(name, tags):
            if self.document.to_dict() != snapshot:
                return
            self.edit(lambda d: apply_quick_role(d, ids, name, tags))
            self.statusBar().showMessage(f'Updated {len(ids)} cards: ' +
                ('secondary tags' if tags else 'manual primary category') + '. Undo is available.', 5000)
        self.quick_menu.chosen.connect(apply)
        self.quick_menu.popup(position)

    def populate_tag_overflow(self, menu):
        from .tag_model import radial_choices
        from .quick_tags import apply_quick_role
        menu.clear()
        ids = set(self.grid.selected) & {e.entry_id for e in self.document.deck.entries}
        snapshot = self.document.to_dict()
        def apply(name, tags):
            if ids and self.document.to_dict() == snapshot:
                self.edit(lambda d: apply_quick_role(d, ids, name, tags))
        for tags, title in ((False, 'Primary Roles'), (True, 'Additional Tags')):
            submenu = menu.addMenu(title)
            overflow = radial_choices(self.document, tags)[1]
            if not overflow:
                submenu.addAction('All active choices are in the ring').setEnabled(False)
            for choice in overflow:
                action = submenu.addAction(choice.name, lambda checked=False, n=choice.name, t=tags: apply(n, t))
                action.setEnabled(bool(ids))

    def card_menu(self, entry_id, position):
        ids = set(self.grid.selected) or {entry_id}
        entry = next(e for e in self.document.deck.entries if e.entry_id == entry_id)
        menu = W.QMenu(self)
        if self.grid.face_count(entry) > 1:
            menu.addAction('Flip preview', lambda: self.grid.flip_entry(entry))
        menu.addAction('Set Primary Role…', lambda: self.add_tag(tags=False))
        menu.addAction('Add / Remove Tags…', lambda: self.quick_tag(position, tags=True))
        menu.addAction('Customize Quick Menu…', lambda: self.manage_categories(customize=True))
        menu.addAction('Discover similar cards / popular commanders', lambda: self.discover_card(entry))
        self.add_reference_action(menu, entry)
        menu.addAction('Replace artwork…', lambda: self.replace_artwork(entry_id)).setEnabled(len(ids) == 1)
        menu.addAction('View Oracle tags…', lambda: self.view_tags(entry))
        menu.addAction('Advanced role memberships…', lambda: self.edit_roles(ids))
        sections = menu.addMenu('Move to section')
        for key, label in SECTIONS.items():
            sections.addAction(label, lambda checked=False, k=key: self.edit(lambda d: assign(d, ids, 'section', k)))
        menu.addAction('Make commander', lambda: self.edit(lambda d: assign(d, ids, 'section', DeckSection.COMMANDER)))
        owned_label = f'Owned copies ({entry.owned})...' if len(ids) == 1 else 'Set owned copies...'
        menu.addAction(owned_label, lambda: self.edit_owned_copies(ids))
        for label, field, value in [('Make oversized', 'oversized', True), ('Make normal size', 'oversized', False),
                                    ('Do not print', 'do_not_print', True), ('Include in printing', 'do_not_print', False)]:
            menu.addAction(label, lambda checked=False, f=field, v=value: self.edit(lambda d: assign(d, ids, f, v)))
        menu.addAction('Retry artwork', lambda: self.thumbnails.retry(entry.card_id, entry.image_asset_id))
        menu.addSeparator()
        menu.addAction(f'Remove {len(ids)} selected', self.remove_selected)
        self.grid.preview.hide()
        menu.exec(position)

    def search_menu(self, entry_id, position):
        self.candidate_menu(self.results, entry_id, position, self.add_result)

    def candidate_menu(self, canvas, entry_id, position, add, dismiss=None):
        entry = next((entry for entry in canvas.document.deck.entries if entry.entry_id == entry_id), None)
        if entry is None:
            return
        menu = W.QMenu(self)
        menu.addAction('Add card', lambda: add(entry_id))
        if canvas.face_count(entry) > 1:
            menu.addAction('Flip preview', lambda: canvas.flip_entry(entry))
        menu.addAction('Details / alternate printings', lambda: self.candidate_details(canvas, entry_id))
        if dismiss is not None:
            menu.addAction('Dismiss recommendation', lambda: dismiss(entry_id))
        menu.addAction('Discover similar cards / popular commanders', lambda: self.discover_card(entry))
        self.add_reference_action(menu, entry)
        menu.addAction('View Oracle tags?', lambda: self.view_tags(entry))
        menu.addAction('Retry artwork', lambda: self.thumbnails.retry(entry.card_id, entry.image_asset_id))
        canvas.preview.hide()
        menu.exec(position)

    def candidate_details(self, canvas, entry_id):
        from .card_details import CardDetails, apply_printing
        entry = next((entry for entry in canvas.document.deck.entries if entry.entry_id == entry_id), None)
        if entry is None:
            return
        previous = getattr(self, 'details_dialog', None)
        if previous is not None:
            previous.close()
            previous.deleteLater()
        document = self.document
        candidate = deepcopy(entry)
        self.details_dialog = CardDetails(self.service, candidate, self, face=canvas.faces.get(entry_id, 0))
        self.details_dialog.quantity.setReadOnly(True)
        self.details_dialog.apply_quantity_button.hide()
        self.details_dialog.use.setText('Add this printing')
        def add_printing(target, payload):
            if self.document is not document:
                return
            temporary = DeckDocument()
            temporary.deck.entries = [candidate]
            apply_printing(temporary, target, payload)
            self.change_candidate_quantity(candidate, 1)
        self.details_dialog.printingChosen.connect(add_printing)
        self.details_dialog.show()

    def add_reference_action(self, menu, entry):
        from mtg_ui.rulings import add_card_reference_action
        add_card_reference_action(menu, self.service, name=entry.name,
                                  oracle_id=entry.oracle_id, card_id=entry.card_id, parent=self)

    def edit_owned_copies(self, ids):
        entries = [entry for entry in self.document.deck.entries if entry.entry_id in ids]
        if not entries:
            return
        counts = {entry.owned for entry in entries}
        label = (f'Owned copies of {entries[0].name}:' if len(entries) == 1 else
                 f'Owned copies per entry (replaces counts on {len(entries)} selected entries):')
        if len(counts) > 1:
            label += '\nCurrent counts differ.'
        label += '\nUsed by Print only missing copies. Do not print remains a separate exclusion.'
        count, accepted = W.QInputDialog.getInt(
            self, 'Owned copies', label, min(entries[0].owned, 2147483647) if len(counts) == 1 else 0,
            0, 2147483647)
        if accepted:
            self.edit(lambda document: assign(document, ids, 'owned', count))

    def edit_tags(self, ids, tags):
        text, ok = W.QInputDialog.getText(self, 'User tags', 'Comma-separated tags (applies to selected cards):', text=', '.join(tags))
        if ok:
            self.edit(lambda d: assign(d, ids, 'tags', list(dict.fromkeys(t.strip() for t in text.split(',') if t.strip()))))

    def view_tags(self, entry):
        from mtg_ui.print_dialogs import CardTagsDialog
        def show(tags):
            dialog = CardTagsDialog(self, entry.name, tags)
            if dialog.exec() == W.QDialog.DialogCode.Accepted and dialog.selected_tag:
                self.open_search()
                from mtg_core.card_pool import oracle_tag_query
                self.query.setText(oracle_tag_query(dialog.selected_tag))
        self.run_task(lambda: self.service.get_oracle_tags(entry.oracle_id), show)

    def clear_readiness_filter(self):
        self.grid.filtered_ids = None
        self.readiness_snapshot = None
        self.readiness_filter.hide()
        self.filter_changed()

    def print_readiness(self):
        from .readiness import inspect_readiness, ReadinessDialog, LABELS
        snapshot = DeckDocument.from_dict(self.document.to_dict())
        def show(result):
            dialog = ReadinessDialog(result, self)
            def apply(key, ids):
                self.filter.clear()
                self.grid.filtered_ids = set(ids)
                self.readiness_snapshot = self.document.to_dict()
                self.readiness_filter.setText(f'{LABELS[key]} ×')
                self.readiness_filter.setToolTip('Clear readiness filter. Results are cleared when the deck changes.')
                self.readiness_filter.show()
                self.filter_changed()
            dialog.filterRequested.connect(apply)
            dialog.exec()
        self.run_task(lambda: inspect_readiness(snapshot, self.service), show)

    def playtest(self):
        from .playtest import PlaytestDialog
        dialog = PlaytestDialog(DeckDocument.from_dict(self.document.to_dict()), self)
        if dialog.exec() == W.QDialog.DialogCode.Accepted:
            def apply(document):
                document.deck.playtest_notes = dialog.notes.toPlainText()
            self.edit(apply)
            self.document.editor_preferences['playtest'] = dialog.settings()
            self.changed()

    def recommendation_store(self):
        from mtg_core.paths import core_data_root
        from mtg_core.recommendations import RecommendationStore
        return RecommendationStore(core_data_root() / 'recommendations' / 'local.sqlite3')

    def import_recommendation_decks(self):
        from threading import Event
        paths, _ = W.QFileDialog.getOpenFileNames(self, 'Import your Commander decks',
                                                 str(self.root), 'Manaforge decks (*.json)')
        if not paths:
            return
        cancelled = Event()
        progress = W.QProgressDialog('Importing local recommendation decks…', 'Cancel', 0, 0, self)
        progress.canceled.connect(cancelled.set)
        self.task_runner.failed.connect(progress.close)
        self.task_runner.failed.connect(progress.deleteLater)
        progress.show()
        def complete(result):
            progress.close()
            progress.deleteLater()
            W.QMessageBox.information(self, 'Recommendation import',
                f"Imported {result['imported']}; unchanged {result['unchanged']}; "
                f"entries missing Oracle identity {result['missing_identities']}.\n"
                f"Cancelled: {result['cancelled']}. Reimport the same files to resume.\n" +
                '\n'.join(result['errors']))
        self.run_task(lambda: self.recommendation_store().import_files(paths, should_cancel=cancelled.is_set), complete)

    def recommendations(self):
        self.open_add_cards()
        self.add_card_tabs.setCurrentWidget(self.recommendation_panel)

    def deck_guidance(self):
        from .guidance import GuidanceDialog
        snapshot = DeckDocument.from_dict(self.document.to_dict())
        def show(proposals):
            if self.document.to_dict() != snapshot.to_dict():
                self.statusBar().showMessage('Deck changed while loading guidance; please reopen it.', 6000)
                return
            dialog = GuidanceDialog(snapshot, proposals, self)
            if dialog.exec() == W.QDialog.DialogCode.Accepted:
                self.edit(lambda document: document.editor_preferences.update(
                    guidance=dialog.settings.to_dict()))
        self.run_task(lambda: self.service.analyze_entries(snapshot.deck.entries), show)

    def deck_insights(self):
        from .insights import InsightsDialog
        snapshot = DeckDocument.from_dict(self.document.to_dict())
        ids = {e.card_id for e in snapshot.deck.entries if e.card_id}
        def load():
            return {cid: self.service.get_card(card_id=cid) or {} for cid in ids}
        def show(records):
            previous = getattr(self, 'insights_dialog', None)
            if previous is not None:
                previous.close()
                previous.deleteLater()
            self.insights_dialog = InsightsDialog(snapshot, records, self)
            self.insights_dialog.show()
        self.run_task(load, show)

    def commander_checks(self):
        from .commander_dialog import CommanderDialog
        from mtg_core.commander import set_commanders
        entries = deepcopy(self.document.deck.entries)
        def show(records):
            dialog = CommanderDialog(self.document, records, self)
            if dialog.exec() == W.QDialog.DialogCode.Accepted:
                self.edit(dialog.apply_selections)
        self.run_task(lambda: self.service.get_deck_legality_data(entries), show)

    def import_decklist(self):
        from .decklist_dialogs import ImportDecklist
        from mtg_core.decklists import apply_decklist
        if self.task is not None:
            return
        dialog = ImportDecklist(self.service, self)
        if dialog.exec() == W.QDialog.DialogCode.Accepted and dialog.result:
            self.edit(lambda d: apply_decklist(d, dialog.result))
            self.group.setCurrentText('Category')
            self.statusBar().showMessage('Decklist imported and categorized. Undo is available.', 6000)

    def export_decklist(self):
        from .decklist_dialogs import ExportDecklist
        ExportDecklist(self.document, self).exec()

    def category_templates(self):
        from .category_templates import CategoryTemplates, TemplateStore, apply_template
        try:
            dialog = CategoryTemplates(self.document, TemplateStore(self.root / 'category_templates.json'), self)
        except (OSError, ValueError) as exc:
            W.QMessageBox.warning(self, 'Could not load templates', str(exc))
            return
        if dialog.exec() == W.QDialog.DialogCode.Accepted:
            names = dialog.selected_names()
            self.edit(lambda d: apply_template(d, names))
            self.group.setCurrentText('Category')
            self.statusBar().showMessage('Category template applied. Card assignments preserved; Undo is available.', 6000)

    def add_tag(self, *, tags=False):
        from .tag_management import TagPicker
        ids = set(self.grid.selected) & {e.entry_id for e in self.document.deck.entries}
        snapshot = self.document.to_dict()
        dialog = TagPicker(self.document, ids, self, tags=tags)
        accepted = dialog.exec() == W.QDialog.DialogCode.Accepted
        if dialog.manage_requested:
            self.manage_categories()
        elif accepted and self.document.to_dict() == snapshot:
            self.edit(dialog.apply)
            self.statusBar().showMessage('Organization updated. Undo is available.', 4000)

    def manage_categories(self, *, customize=False):
        from .tag_management import OrganizationManager
        snapshot = self.document.to_dict()
        dialog = OrganizationManager(self.document, self, customize=customize)
        if dialog.exec() == W.QDialog.DialogCode.Accepted:
            if self.document.to_dict() != snapshot:
                self.statusBar().showMessage('Deck changed; reopen Manage Tags.', 4000)
                return
            def apply(document):
                document.deck = deepcopy(dialog.draft.deck)
                document.editor_preferences = deepcopy(dialog.draft.editor_preferences)
            self.edit(apply)

    def edit_roles(self, ids):
        from .role_editor import RoleEditor
        from mtg_core.categorization import override_categories
        dialog = RoleEditor(self.document, ids, self)
        if dialog.exec() == W.QDialog.DialogCode.Accepted:
            choices = dialog.choices()
            if choices:
                self.edit(lambda document: override_categories(document, ids, choices))
                self.statusBar().showMessage('Deck roles updated. Undo is available.', 5000)

    def auto_categorize(self):
        from .category_review import CategoryReview
        entries = deepcopy(self.document.deck.entries)
        commander_ids = tuple(self.document.deck.commander_entry_ids)
        def review(proposals):
            from mtg_core.categorization import theme_priorities
            proposals = {key: theme_priorities(self.document, evidence) for key, evidence in proposals.items()}
            dialog = CategoryReview(self.document, proposals, self)
            if dialog.exec() == W.QDialog.DialogCode.Accepted:
                selected = dialog.selected_proposals()
                self.edit(lambda document: apply_categories(document, selected,
                          reconsider_manual=dialog.reconsider.isChecked()))
                self.group.setCurrentText('Category')
                self.statusBar().showMessage(f'Categorized {len(selected)} entries. Undo is available.', 8000)
        self.run_task(lambda: self.service.analyze_entries(entries,
                      commander_entry_ids=commander_ids), review)

    def run_task(self, work, callback):
        context = {'deck_id': self.document.deck.deck_id, 'path': str(self.path) if self.path else None}
        self.task_runner.start(work, callback, context=context)

    def task_busy_changed(self, busy):
        self.centralWidget().setEnabled(not busy)
        if busy:
            self.autosave.stop()
            self.statusBar().showMessage('Working?')

    def task_failed(self, error):
        self.statusBar().showMessage(error)
        W.QMessageBox.warning(self, 'Could not complete operation', error)

    def task_settled(self):
        if self.session.dirty:
            self.autosave.start()

    def rules_reference(self):
        from mtg_ui.rules_reference import RulesBrowser
        RulesBrowser(self.service, self).exec()

    def card_details(self, entry_id):
        from .card_details import CardDetails, apply_printing, apply_quantity
        entry = next((e for e in self.document.deck.entries if e.entry_id == entry_id), None)
        if entry is None:
            return
        previous = getattr(self, 'details_dialog', None)
        if previous is not None:
            previous.close()
            previous.deleteLater()
        document = self.document
        self.details_dialog = CardDetails(self.service, entry, self, face=self.grid.faces.get(entry_id, 0))
        def choose(target, payload):
            if self.document is document:
                self.edit(lambda d: apply_printing(d, target, payload))
        self.details_dialog.printingChosen.connect(choose)
        def quantity(target, value):
            if self.document is document:
                self.edit(lambda d: apply_quantity(d, target, value))
        self.details_dialog.quantityChosen.connect(quantity)
        self.details_dialog.show()

    def replace_artwork(self, entry_id):
        from .proxy_adapter import choose_art, apply_art
        selection = choose_art(self, self.document, entry_id)
        if selection is None:
            return
        def apply(result):
            def action(document):
                entry = next(e for e in document.deck.entries if e.entry_id == entry_id)
                entry.image_asset_id = result.pop('image_asset_id')
                for key, value in result.items():
                    if value is not None:
                        if key == "art_override":
                            entry.art_override = HighResOverride.from_dict(value)
                        elif key in ENTRY_PRINT_FIELDS:
                            setattr(entry, key, value)
                        else:
                            entry.extras[key] = value
            self.edit(action)
        self.run_task(lambda: apply_art(selection), apply)

    def print_deck(self):
        from mtg_core.diagnostics import get_logger
        try:
            self._print_deck()
        except Exception as exc:
            get_logger(__name__).exception('Could not start deck printing')
            self.task_failed(f'Could not print deck: {exc}')

    def _print_deck(self):
        from .proxy_adapter import (prepare_print, launch_print, print_token_suggestions,
                                    include_print_tokens, exclude_basic_lands, subtract_owned_copies)
        dialog = W.QDialog(self)
        dialog.setWindowTitle('Print Deck — sections')
        layout = W.QVBoxLayout(dialog)
        layout.addWidget(W.QLabel('Choose sections. Cards marked do not print are excluded.'))
        checks = {}
        for key, label in SECTIONS.items():
            check = W.QCheckBox(label)
            check.setChecked(key in (DeckSection.MAINBOARD, DeckSection.COMMANDER))
            layout.addWidget(check)
            checks[key] = check
        include_basics = W.QCheckBox('Include basic lands')
        include_basics.setChecked(True)
        include_basics.setToolTip('Uncheck to omit basic lands, including snow-covered basics and Wastes, from this print job.')
        layout.addWidget(include_basics)
        missing_only = W.QCheckBox('Print only missing copies')
        missing_only.setToolTip('Subtract owned copies from each included entry. Edit owned counts from the card context menu.')
        layout.addWidget(missing_only)
        buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Ok | W.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != W.QDialog.DialogCode.Accepted:
            return
        if not self.save():
            W.QMessageBox.warning(self, 'Could not print deck', self.statusBar().currentMessage())
            return
        snapshot = DeckDocument.from_dict(self.document.to_dict())
        sections = {key for key, check in checks.items() if check.isChecked()}
        print_basics = include_basics.isChecked()
        if missing_only.isChecked():
            subtract_owned_copies(snapshot, sections)
        def launch(project):
            self.document.extras['proxy_project_id'] = project['id']
            self.changed()
            if self.save():
                try:
                    handler = getattr(self, 'print_project_handler', None)
                    if handler is not None:
                        handler(project)
                    else:
                        launch_print(project)
                    relocated = project.get('relocated_copies', 0)
                    self.statusBar().showMessage('Deck opened in Proxy.' +
                        (f' {relocated} copies relocated to fit the sheet.' if relocated else ''))
                except OSError as exc:
                    W.QMessageBox.warning(self, 'Could not launch Proxy', str(exc))
        def choose_tokens(suggestions):
            from mtg_ui.print_dialogs import ComponentSuggestionsDialog
            if suggestions:
                chooser = ComponentSuggestionsDialog(self, suggestions)
                if chooser.exec() == W.QDialog.DialogCode.Accepted:
                    include_print_tokens(snapshot, chooser.selected_suggestions(), sections)
            def prepare():
                self.run_task(lambda: prepare_print(snapshot, self.service, sections), launch)
            # A modal chooser may already have delivered the worker's finished signal.
            if self.task is None:
                prepare()
            else:
                self.task.finished.connect(lambda: QtCore.QTimer.singleShot(0, prepare))
        def find_tokens():
            if not print_basics:
                exclude_basic_lands(snapshot, self.service, sections)
            return print_token_suggestions(snapshot, self.service, sections)
        self.run_task(find_tokens, choose_tokens)

    def undo(self):
        if self.task is not None:
            return
        self.session.undo()
        self.sync_fields()
        self.changed()

    def redo(self):
        if self.task is not None:
            return
        self.session.redo()
        self.sync_fields()
        self.changed()

    def toggle_empty_categories(self, visible):
        self.document.editor_preferences['show_empty_categories'] = visible
        self.changed()

    def sync_fields(self):
        same_deck = getattr(self, '_view_deck_id', None) == self.document.deck.deck_id
        previous_mode = self._active_view
        current_position = self.view_scrollbar(previous_mode).value()
        self._view_deck_id = self.document.deck.deck_id
        blockers = [QtCore.QSignalBlocker(w) for w in (self.name, self.format, self.view_mode, self.group, self.sort, self.zoom, self.show_empty_categories)]
        self.name.setText(self.document.deck.name)
        if self.format.findText(self.document.deck.format) < 0:
            self.format.addItem(self.document.deck.format)
        self.format.setCurrentText(self.document.deck.format)
        prefs = self.document.editor_preferences
        self.show_empty_categories.setChecked(prefs.get('show_empty_categories', False))
        self.view_mode.setCurrentText(prefs.get('view', 'Stacks'))
        self.group.setCurrentText(prefs.get('group', 'Category'))
        self.sort.setCurrentText(prefs.get('sort', 'Name'))
        self.zoom.setValue(prefs.get('card_width', 180))
        mode = self.view_mode.currentText()
        self.grid.mode = mode if mode != 'Text' else 'Grid'
        self.grid.grouping, self.grid.sort = self.group.currentText(), self.sort.currentText()
        self._active_view = mode
        self.view_scrolls = dict(prefs.get('view_scrolls', {}))
        self.text_view.rows.collapsed = set(prefs.get('text_collapsed', []))
        with QtCore.QSignalBlocker(self.text_view.preview_toggle):
            self.text_view.preview_toggle.setChecked(prefs.get('text_preview', True))
        self.text_view.preview.setVisible(self.text_view.preview_toggle.isChecked() and self.text_view.width() >= 900)
        self.views.setCurrentWidget(self.text_view if mode == 'Text' else self.grid)
        self.grid.card_width = self.zoom.value()
        self.grid.collapsed = set(prefs.get('collapsed', []))
        position = current_position if same_deck and previous_mode == mode else self.view_scrolls.get(mode, 0)
        QtCore.QTimer.singleShot(0, lambda: self.view_scrollbar(mode).setValue(position)
                                if self._active_view == mode else None)
        del blockers

    def save(self):
        if not self._has_active_deck:
            return True
        self.view_scrolls[self._active_view] = self.view_scrollbar(self._active_view).value()
        self.document.editor_preferences['view_scrolls'] = dict(self.view_scrolls)
        if (self.name.text().strip() or 'Untitled Deck') != self.document.deck.name or self.format.currentText() != self.document.deck.format:
            self.edit_metadata()
        self.autosave.stop()
        if not self.session.dirty and self.path:
            return True
        try:
            destination = self.session.save()
        except (OSError, ValueError, TypeError) as exc:
            self.statusBar().showMessage(f'Save failed; changes remain unsaved: {exc}')
            self.autosave.start(10000)
            return False
        self.changed()
        self.statusBar().showMessage(f'Saved: {destination}')
        return True

    def replace_document(self, document, path=None):
        self.session.replace_document(document, path)
        self._document_replaced()

    def _document_replaced(self):
        self._has_active_deck = True
        self.project_stack.setCurrentWidget(self.editor_body)
        document = self.document
        self.model.document = self.grid.document = document
        self.grid.selected.clear()
        self.grid.verticalScrollBar().setValue(0)
        self.sync_fields()
        self.edit(lambda document: None)
        self.changed()
        # Legacy entries have no grouping facts; hydrate local metadata off the UI thread.
        legacy_folder = document.print_settings.get('proxy_project', {}).get('image_dir')
        missing = [(e.entry_id, e.card_id, e.extras.get('proxy_front_name'), e.image_asset_id)
                   for e in document.deck.entries if (e.card_id and 'legalities' not in e.extras.get('facts', {})) or (legacy_folder and not e.image_asset_id)]
        uncategorized = [deepcopy(e) for e in document.deck.entries
                         if not e.category_ids and not e.extras.get('auto_categories')]
        analysis_context = deepcopy(document.deck.entries)
        commander_ids = tuple(document.deck.commander_entry_ids)
        can_analyze = callable(getattr(self.service, 'analyze_entries', None))
        if (missing and hasattr(self.service, 'get_card')) or (uncategorized and can_analyze):
            def resolve():
                result = {}
                for eid, cid, front_name, asset in missing:
                    facts = card_facts(self.service.get_card(card_id=cid) or {}) if cid and hasattr(self.service, 'get_card') else {}
                    if not asset and legacy_folder and front_name:
                        path = Path(legacy_folder) / Path(front_name).name
                        if path.is_file():
                            asset = self.service.store_image_bytes(path.read_bytes(),
                                extension=path.suffix.lstrip('.') or 'png', source='editor_legacy')
                    result[eid] = facts, asset
                proposals = self.service.analyze_entries(uncategorized, context_entries=analysis_context,
                    commander_entry_ids=commander_ids) if can_analyze else {}
                return result, proposals
            def apply(resolved):
                resolved, proposals = resolved
                for entry in self.document.deck.entries:
                    if entry.entry_id in resolved:
                        facts, asset = resolved[entry.entry_id]
                        entry.extras['facts'] = facts
                        entry.image_asset_id = asset
                self.edit(lambda d: apply_categories(d, proposals))
                self.changed()
            self.run_task(resolve, apply)

    def new(self):
        if self.task is not None or (self._has_active_deck and self.session.dirty and not self.save()):
            return
        self.session.new()
        self._document_replaced()

    def open(self):
        path, _ = W.QFileDialog.getOpenFileName(self, 'Open deck or proxy project', str(self.root), 'JSON projects (*.json)')
        if path:
            self.open_path(Path(path))

    def open_path(self, path):
        if self.task is not None or (self._has_active_deck and self.session.dirty and not self.save()):
            return
        try:
            self.session.open(path)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            W.QMessageBox.warning(self, 'Open failed', str(exc))
            return
        self._document_replaced()
        if self.path is None:
            self.save()

    def recover(self):
        if not self.path:
            return
        paths = self.session.recovery_paths()
        if not paths:
            W.QMessageBox.information(self, 'Recovery', 'No recovery snapshots yet.')
            return
        value, ok = W.QInputDialog.getItem(self, 'Recovery', 'Restore a snapshot into a new deck:', [p.name for p in paths], 0, False)
        if ok:
            if self.session.dirty and not self.save():
                return
            try:
                self.session.recover(next(p for p in paths if p.name == value))
            except (OSError, ValueError) as exc:
                W.QMessageBox.warning(self, 'Recovery failed', str(exc))
                return
            self._document_replaced()
            self.save()

    def refresh_recent(self):
        self.recent.clear()
        self.recent.addAction('Decks and print projects…', self.project_browser)
        self.recent.addAction('New deck', self.new)
        self.recent.addAction('Open deck / proxy project…', self.open)
        self.recent.addSeparator()
        paths = sorted(self.root.glob('*.manaforge.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:15]
        for path in paths:
            try:
                name = self.store.load(path).deck.name
            except (OSError, ValueError, TypeError):
                continue
            self.recent.addAction(name, lambda checked=False, p=path: self.open_path(p))

    def project_browser(self):
        if self.task is not None:
            return
        if self._has_active_deck and self.session.dirty and not self.save():
            return
        self.dashboard.resume_button.setVisible(self._has_active_deck)
        self.project_stack.setCurrentWidget(self.dashboard)
        self.grid.preview.hide()
        self.results.preview.hide()
        self.dashboard.refresh()
        self.dashboard.filter.setFocus()

    def resume_deck(self):
        if self._has_active_deck and self.task is None:
            self.project_stack.setCurrentWidget(self.editor_body)

    def closeEvent(self, event):
        self.closing = True
        self.basic_lands.stop()
        discovery = getattr(self, 'card_discovery_dialog', None)
        if discovery is not None:
            discovery.controller.shutdown()
            discovery.hide()
            discovery.canvas.preview.close()
        self.dashboard.stop()
        self.text_view.stopping = True
        self.search_controller.shutdown()
        self.add_cards_workspace.discovery.controller.shutdown()
        self.add_cards_workspace.card_search.controller.shutdown()
        self.recommendation_panel.suspend()
        if (self.worker is not None or self.task is not None or self.thumbnails.worker is not None
                or self.recommendation_panel.worker is not None or self.add_cards_workspace.discovery.controller.worker is not None
                or self.add_cards_workspace.card_search.controller.worker is not None or self.text_view.worker is not None
                or self.dashboard.worker is not None or self.basic_lands.worker is not None
                or (discovery is not None and discovery.controller.worker is not None)):
            self.thumbnails.stopping = True
            self.thumbnails.pending.clear()
            self.statusBar().showMessage('Finishing background work before closing…')
            QtCore.QTimer.singleShot(150, self.close)
            event.ignore()
            return
        if self.session.dirty and not self.save():
            self.thumbnails.stopping = False
            self.closing = False
            self.basic_lands.changed()
            self.dashboard.stopping = False
            self.dashboard.update_visible()
            self.text_view.stopping = False
            self.search_controller.resume()
            self.add_cards_workspace.discovery.controller.resume()
            self.add_cards_workspace.card_search.controller.resume()
            self.recommendation_panel.deck_changed()
            event.ignore()
            return
        self.autosave.stop()
        self.search_timer.stop()
        self.thumbnails.stop()
        self.grid.preview.close()
        self.results.preview.close()
        self.recommendation_panel.canvas.preview.close()
        self.add_cards_workspace.discovery.canvas.preview.close()
        self.add_cards_workspace.card_search.canvas.preview.close()
        super().closeEvent(event)


def main():
    app = W.QApplication.instance() or W.QApplication([])
    app.setApplicationName('Manaforge Deck Editor')
    app.setStyle('Fusion')
    app.setStyleSheet(application_stylesheet())
    window = EditorWindow()
    window.show()
    app.exec()
