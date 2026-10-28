"""Persistent, image-first recommendation browsing over the existing ranking engine."""

from copy import deepcopy
import sqlite3
from threading import Event

from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_core.decks import DeckDocument
from mtg_core.recommendation_scoring import settings
from mtg_ui.theme import COLORS

from .canvas import CardCanvas
from .card_drop import CardDropPanel, CardSearchEdit
from .commander_selection import commanders
from .organization import in_deck_entries, update_candidate_quantities
from .recommendation_categories import (
    CATEGORIES,
    TYPE_CATEGORIES_ORDER,
    card_types,
    matches,
)
from .recommendations import load_recommendations
from .tasks import Task

CARD_TYPES = (
    "Artifact",
    "Battle",
    "Creature",
    "Enchantment",
    "Instant",
    "Land",
    "Planeswalker",
    "Sorcery",
)


def context_key(document):
    from mtg_core.categorization import is_manual

    return (
        dict(
            deck_id=document.deck.deck_id,
            format=document.deck.format,
            tags=list(document.deck.tags),
            commander_entry_ids=list(document.deck.commander_entry_ids),
            categories=[category.to_dict() for category in document.deck.categories],
            entries=[
                dict(
                    entry_id=e.entry_id,
                    card_id=e.card_id,
                    oracle_id=e.oracle_id,
                    name=e.name,
                    quantity=e.quantity,
                    section=e.section,
                    facts=deepcopy(e.extras.get("facts")),
                    category_ids=list(e.category_ids),
                    tags=list(e.tags),
                    manual=is_manual(e),
                )
                for e in document.deck.entries
            ],
        ),
        deepcopy(document.editor_preferences.get("guidance")),
        deepcopy(document.editor_preferences.get("manual_themes")),
        deepcopy(document.editor_preferences.get("recommendations")),
        deepcopy(document.artwork_preferences),
        deepcopy(document.editor_preferences.get("discovery", {})),
        document.editor_preferences.get("edhrec_cohort", "inherit"),
    )


def source_key(document, signature=()):
    """Changes requiring new sources/printings rather than just cached-candidate ranking."""
    from mtg_core.card_pool import pool_context

    return (
        document.deck.deck_id,
        pool_context(document),
        tuple(document.deck.tags),
        tuple((e.entry_id, e.oracle_id, e.card_id) for e in commanders(document)),
        deepcopy(document.artwork_preferences),
        deepcopy(document.editor_preferences.get("discovery", {}).get("theme_option")),
        document.editor_preferences.get("discovery", {}).get("theme"),
        document.editor_preferences.get("edhrec_cohort", "inherit"),
        signature,
    )


class CompactLabel(W.QLabel):
    """Keep context and status to one line, with the complete text in a tooltip."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.full_text = ""
        self.setTextFormat(C.Qt.TextFormat.PlainText)
        self.setSizePolicy(W.QSizePolicy.Policy.Ignored, W.QSizePolicy.Policy.Fixed)
        self.setMaximumHeight(24)
        self.setText(text)

    def setText(self, text):
        self.full_text = text
        self.setToolTip(text)
        self.elide()

    def elide(self):
        super().setText(
            self.fontMetrics().elidedText(
                self.full_text, C.Qt.TextElideMode.ElideRight, max(0, self.width())
            )
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.elide()


class RecommendationCanvas(CardCanvas):
    def __init__(self, thumbnails, parent=None):
        super().__init__(DeckDocument(), thumbnails, parent, search=True)
        self.card_width = 270
        self.minimum_search_card_width = 180
        self.card_aspect_ratio = 88 / 63
        self.empty_message = (
            "Choose a commander or browse local cards to start building."
        )
        self.setAccessibleName("Recommended cards")

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if (
            event.button() == C.Qt.MouseButton.LeftButton
            and not event.modifiers()
            and self.press_position is not None
        ):
            item = self.hit(event.position().toPoint())
            if item:
                self.detail_entry = item[0].entry_id

    def mouseDoubleClickEvent(self, event):
        self.detail_timer.stop()
        self.detail_entry = None
        self.press_position = None
        if event.button() != C.Qt.MouseButton.LeftButton:
            return
        item = self.hit(event.position().toPoint())
        if not self.activate_quantity(item, event.position().toPoint()) and item:
            self.detailsRequested.emit(item[0].entry_id)

    def paintEvent(self, event):
        if self.document.deck.entries or self.discovery_drop:
            super().paintEvent(event)
        else:
            painter = G.QPainter(self.viewport())
            painter.fillRect(self.viewport().rect(), G.QColor(COLORS["canvas"]))
            painter.setPen(G.QColor(COLORS["text_secondary"]))
            painter.drawText(
                self.viewport().rect().adjusted(20, 20, -20, -20),
                C.Qt.AlignmentFlag.AlignCenter | C.Qt.TextFlag.TextWordWrap,
                self.empty_message,
            )
            painter.end()
            self.thumbnails.set_visible(id(self), [])

    def hideEvent(self, event):
        self.hover_timer.stop()
        self.preview.hide()
        self.thumbnails.set_visible(id(self), [])
        super().hideEvent(event)


class RecommendationPanel(CardDropPanel):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.worker = None
        self.page_worker = None
        self.role_page = 0
        self.generation = self.page_generation = 0
        self.key = self.loaded_key = self.loaded_source_key = None
        self.rows, self.category_scroll = [], {}
        self.selected_category = "Top Cards"
        self.browse_mode = "types"
        self.mode_categories = {"types": "Top Cards", "roles": "Top Cards"}
        self.available_roles = []
        self.audience_generation = 0
        self.audience_signature = None
        self.audience_worker = None
        self.restore_category_position = None
        self.pages = None
        self.shown_limit = 50
        self.pending_page = self.pending = False
        self.cancelled, self.page_cancelled = Event(), Event()
        self.coverage = ""
        self.edhrec_status = ""
        self.load_error = ""
        self.theme_option = None
        self.last_discovery_identity = None
        self.preference_deck = None
        self.view_snapshot = None
        self.saving_view = False
        self.expanded = False
        self.timer = C.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(750)
        self.timer.timeout.connect(self.refresh)
        layout = W.QVBoxLayout(self)
        self.content = W.QWidget()
        body = W.QVBoxLayout(self.content)
        body.setContentsMargins(0, 0, 0, 0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        body.setSpacing(4)
        self.commander_header = CompactLabel("Discover Deck Ideas")
        body.addWidget(self.commander_header)
        self.controls_grid = W.QGridLayout()
        self.controls_grid.setContentsMargins(0, 0, 0, 0)
        self.controls_grid.setSpacing(4)
        self.text_filter = CardSearchEdit()
        self.text_filter.setPlaceholderText("Search recommendations")
        self.text_filter.setClearButtonEnabled(True)
        self.text_filter.setMinimumHeight(32)
        self.text_filter.setMinimumWidth(0)
        self.text_filter.textChanged.connect(self.filter_rows)
        self.audience = W.QComboBox()
        self.audience.setAccessibleName("Recommendation audience")
        self.audience.setMinimumWidth(0)
        self.audience.setSizeAdjustPolicy(
            W.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.audience.addItem("Audience: Automatic", "auto")
        self.audience.addItem("Audience: General", "general")
        self.audience.addItem("Audience: Follow global setting", "inherit")
        self.audience.currentIndexChanged.connect(self.change_audience)
        self.browse_modes = W.QTabBar()
        self.browse_modes.addTab("Card Types")
        self.browse_modes.addTab("Card Roles")
        self.browse_modes.setExpanding(False)
        self.browse_modes.setAccessibleName("Recommendation browsing mode")
        self.browse_modes.currentChanged.connect(self.change_mode)
        self.filters_button = W.QToolButton()
        self.filters_button.setText("Filters")
        self.filters_button.setCheckable(True)
        self.advanced_button = W.QToolButton()
        self.advanced_button.setText("More")
        self.advanced_button.setPopupMode(
            W.QToolButton.ToolButtonPopupMode.InstantPopup
        )
        menu = W.QMenu(self.advanced_button)
        menu.addAction("Change Commander / Theme", self.open_discovery)
        menu.addAction("Local Card Search", self.open_search)
        menu.addAction("Refresh cached recommendations", self.request_refresh)
        self.advanced_button.setMenu(menu)
        body.addLayout(self.controls_grid)
        body.addWidget(self.browse_modes)
        self.filter_box = W.QWidget()
        self.filter_layout = W.QGridLayout(self.filter_box)
        self.filter_layout.setContentsMargins(0, 0, 0, 0)
        self.type_filter = W.QComboBox()
        self.type_filter.setAccessibleName("Recommendation card type")
        self.type_filter.addItems(["All Card Types", *CARD_TYPES])
        self.type_filter.currentTextChanged.connect(self.filter_rows)
        self.membership = W.QComboBox()
        self.membership.addItems(["All cards", "Not in deck", "In deck"])
        self.membership.setCurrentIndex(1)
        self.membership.currentIndexChanged.connect(self.filter_rows)
        self.role_filter = W.QComboBox()
        self.role_filter.addItem("All roles")
        self.role_filter.currentTextChanged.connect(self.filter_rows)
        self.special_category = W.QComboBox()
        self.special_category.setAccessibleName("Specialist recommendation category")
        self.special_category.addItem("All collections", "Top Cards")
        for label in CATEGORIES:
            if label not in TYPE_CATEGORIES_ORDER:
                self.special_category.addItem(label, label)
        self.special_category.currentIndexChanged.connect(self.filter_rows)
        from .discovery_options import color_combo

        self.identity = color_combo()
        self.identity.currentIndexChanged.connect(self.filter_rows)
        self.mana_value = W.QSpinBox()
        self.mana_value.setRange(-1, 30)
        self.mana_value.setValue(-1)
        self.mana_value.setSpecialValueText("Any mana value")
        self.mana_value.setPrefix("MV ")
        self.mana_value.setAccessibleName("Mana value")
        self.mana_value.valueChanged.connect(self.filter_rows)
        self.include_illegal = W.QCheckBox("Include illegal cards")
        self.include_illegal.toggled.connect(editor.set_include_illegal)
        self.audience.setMinimumWidth(160)
        self.filter_widgets = [
            self.audience,
            self.include_illegal,
            self.type_filter,
            self.membership,
            self.role_filter,
            self.special_category,
            self.identity,
            self.mana_value,
        ]
        self.reflow_filters()
        self.filters_button.toggled.connect(self.filter_box.setVisible)
        self.filter_box.hide()
        body.addWidget(self.filter_box)
        self.type_tabs = W.QTabBar()
        self.type_tabs.setExpanding(False)
        self.type_tabs.setElideMode(C.Qt.TextElideMode.ElideRight)
        self.type_tabs.setMinimumWidth(0)
        self.type_tabs.setUsesScrollButtons(True)
        self.type_tabs.setAccessibleName("Recommendation categories")
        self.type_tabs.currentChanged.connect(self.tab_category_changed)
        self.role_search = CardSearchEdit()
        self.role_search.setPlaceholderText("Search roles")
        self.role_search.setAccessibleName("Search card roles")
        self.role_search.setClearButtonEnabled(True)
        self.role_search.setMinimumWidth(80)
        self.role_search.setMaximumWidth(220)
        self.role_search.textChanged.connect(self.search_roles)
        self.previous_roles = W.QPushButton("<")
        self.next_roles = W.QPushButton(">")
        for button, label in (
            (self.previous_roles, "Previous roles"),
            (self.next_roles, "Next roles"),
        ):
            button.setAccessibleName(label)
            button.setToolTip(label)
            button.setFixedSize(36, 34)
        self.previous_roles.clicked.connect(lambda: self.move_roles(-1))
        self.next_roles.clicked.connect(lambda: self.move_roles(1))
        self.role_hint = W.QLabel()
        self.role_hint.setWordWrap(True)
        self.navigation = W.QGridLayout()
        self.navigation.setContentsMargins(0, 0, 0, 0)
        self.navigation.setSpacing(4)
        body.removeWidget(self.browse_modes)
        body.addLayout(self.navigation)
        body.addWidget(self.role_hint)
        self.category_combo = W.QComboBox()
        self.category_combo.setAccessibleName("Recommendation category")
        self.category_combo.currentIndexChanged.connect(
            lambda index: self.change_category(self.category_combo.itemData(index))
        )
        self.category_combo.setMinimumWidth(0)
        self.category_combo.setMaximumWidth(175)
        self.category_combo.setSizeAdjustPolicy(
            W.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.category_combo.setMinimumContentsLength(10)
        self.status = CompactLabel("Recommendations use local cached data.")
        results = W.QHBoxLayout()
        self.canvas = RecommendationCanvas(editor.thumbnails, self)
        self.canvas.quantityRequested.connect(self.add)
        self.canvas.detailsRequested.connect(self.inspect)
        self.canvas.menuRequested.connect(self.card_menu)
        self.canvas.verticalScrollBar().valueChanged.connect(self.near_bottom)
        results.addWidget(self.canvas, 1)
        body.addLayout(results, 1)
        footer = W.QHBoxLayout()
        self.more = W.QPushButton("Load More")
        self.more.hide()
        self.more.clicked.connect(self.load_more)
        footer.addWidget(self.status, 1)
        self.more.setMaximumWidth(100)
        footer.addWidget(self.more)
        top = W.QToolButton()
        top.setText("Top")
        top.setToolTip("Back to Top")
        top.clicked.connect(lambda: self.canvas.verticalScrollBar().setValue(0))
        footer.addWidget(top)
        body.addLayout(footer)
        layout.addWidget(self.content, 1)
        self.populate_navigation()
        self.reflow_controls()
        self.update_navigation()

    def reflow_filters(self):
        columns = 3 if self.width() >= 900 else 2 if self.width() >= 500 else 1
        for index, widget in enumerate(self.filter_widgets):
            self.filter_layout.removeWidget(widget)
            widget.setMinimumWidth(160 if widget is self.audience else 0)
            self.filter_layout.addWidget(widget, index // columns, index % columns)

    def reflow_controls(self):
        widgets = [
            self.text_filter,
            self.filters_button,
            self.advanced_button,
        ]
        for widget in widgets:
            self.controls_grid.removeWidget(widget)
        for column in range(5):
            self.controls_grid.setColumnStretch(column, 0)
        if self.width() < 600:
            self.controls_grid.addWidget(self.text_filter, 0, 0, 1, 4)
            for column, widget in enumerate(widgets[1:]):
                self.controls_grid.addWidget(widget, 1, column)
            self.controls_grid.setColumnStretch(1, 1)
        else:
            for column, widget in enumerate(widgets):
                self.controls_grid.addWidget(widget, 0, column)
            self.controls_grid.setColumnStretch(0, 1)

    def update_navigation(self):
        self.type_tabs.setVisible(True)
        self.category_combo.setVisible(False)
        roles = self.browse_mode == "roles"
        self.role_search.setVisible(roles)
        self.previous_roles.setVisible(roles)
        self.next_roles.setVisible(roles)
        widgets = (
            self.browse_modes,
            self.role_search,
            self.type_tabs,
            self.previous_roles,
            self.next_roles,
        )
        for widget in widgets:
            self.navigation.removeWidget(widget)
        for column in range(5):
            self.navigation.setColumnStretch(column, 0)
        if self.width() < 900:
            self.navigation.addWidget(self.browse_modes, 0, 0)
            self.navigation.addWidget(self.role_search, 0, 1, 1, 3)
            self.navigation.addWidget(self.type_tabs, 1, 0, 1, 2)
            self.navigation.addWidget(self.previous_roles, 1, 2)
            self.navigation.addWidget(self.next_roles, 1, 3)
            self.navigation.setColumnStretch(1, 1)
        else:
            for column, widget in enumerate(widgets):
                self.navigation.addWidget(widget, 0, column)
            self.navigation.setColumnStretch(2, 1)

    def role_page_size(self):
        available = self.width() - (590 if self.width() >= 900 else 190)
        return max(1, min(10, available // 120))

    def search_roles(self):
        self.role_page = 0
        self.populate_navigation()

    def move_roles(self, direction):
        self.role_page = max(0, self.role_page + direction)
        self.populate_navigation()

    def populate_navigation(self):
        roles_mode = self.browse_mode == "roles"
        if roles_mode:
            term = self.role_search.text().strip().casefold()
            roles = [role for role in self.available_roles if term in role.casefold()]
            size = self.role_page_size()
            self.role_page = min(self.role_page, max(0, (len(roles) - 1) // size))
            start = self.role_page * size
            choices = [
                ("Top Cards", "Top Cards"),
                *[(role, "Role: " + role) for role in roles[start : start + size]],
            ]
            self.previous_roles.setEnabled(start > 0)
            self.next_roles.setEnabled(start + size < len(roles))
            active = self.selected_category.removeprefix("Role: ")
            hidden_selection = (
                self.selected_category != "Top Cards"
                and active not in roles[start : start + size]
            )
            self.role_hint.setText(
                ("No roles match. " if not roles else "")
                + ("Selected: " + active if hidden_selection else "")
            )
            self.role_hint.setVisible(not roles or hidden_selection)
        else:
            choices = [(label, label) for label in TYPE_CATEGORIES_ORDER]
            self.role_hint.hide()
        self.type_tabs.setUsesScrollButtons(not roles_mode)
        with C.QSignalBlocker(self.type_tabs), C.QSignalBlocker(self.category_combo):
            while self.type_tabs.count():
                self.type_tabs.removeTab(0)
            self.category_combo.clear()
            for label, key in choices:
                index = self.type_tabs.addTab(label)
                self.type_tabs.setTabData(index, key)
                self.category_combo.addItem(label, key)
            selected = self.category_combo.findData(self.selected_category)
            self.type_tabs.setCurrentIndex(selected)
            self.category_combo.setCurrentIndex(selected)
        self.update_navigation()

    def tab_category_changed(self, index):
        self.change_category(self.type_tabs.tabData(index))

    def position_key(self, category=None):
        return self.browse_mode + ":" + (category or self.selected_category)

    def change_mode(self, index):
        mode = "roles" if index == 1 else "types"
        if mode == self.browse_mode:
            return
        self.category_scroll[self.position_key()] = (
            self.canvas.verticalScrollBar().value(),
            self.shown_limit,
        )
        self.mode_categories[self.browse_mode] = self.selected_category
        self.browse_mode = mode
        self.selected_category = self.mode_categories.get(mode, "Top Cards")
        self.restore_category_position, self.shown_limit = self.category_scroll.get(
            self.position_key(), (0, 50)
        )
        self.populate_navigation()
        self.filter_rows(reset=False)
        self.save_view()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow_filters()
        self.reflow_controls()
        self.populate_navigation()

    def open_discovery(self):
        self.editor.add_cards_workspace.open()
        self.editor.add_card_tabs.setCurrentWidget(
            self.editor.add_cards_workspace.discovery
        )

    def open_search(self):
        self.editor.add_cards_workspace.open()
        self.editor.add_card_tabs.setCurrentWidget(
            self.editor.add_cards_workspace.card_search
        )

    def change_category(self, category):
        if not category or category == self.selected_category:
            return
        self.category_scroll[self.position_key()] = (
            self.canvas.verticalScrollBar().value(),
            self.shown_limit,
        )
        self.selected_category = category
        self.mode_categories[self.browse_mode] = category
        self.populate_navigation()
        position, self.shown_limit = self.category_scroll.get(
            self.position_key(), (0, 50)
        )
        self.restore_category_position = position
        self.filter_rows(reset=False)
        self.save_view()

    def active(self):
        return self.isVisible() and not self.editor.closing

    def change_audience(self, index):
        value = self.audience.itemData(index)
        if value is None:
            return
        if value != self.editor.document.editor_preferences.get(
            "edhrec_cohort", "inherit"
        ):
            self.editor.edit(
                lambda document: document.editor_preferences.update(edhrec_cohort=value)
            )

    def sync_audience(self):
        selected = self.editor.document.editor_preferences.get(
            "edhrec_cohort", "inherit"
        )
        with C.QSignalBlocker(self.audience):
            if self.audience.findData(selected) < 0:
                self.audience.addItem(
                    "Audience: " + selected + " (unavailable)", selected
                )
            self.audience.setCurrentIndex(self.audience.findData(selected))

    def load_audiences(self, signature):
        from mtg_core.edhrec_cohorts import cohort_options
        from mtg_core.paths import core_data_root

        if self.audience_worker is not None or signature == self.audience_signature:
            self.sync_audience()
            return
        self.audience_signature = signature
        self.audience_generation += 1
        generation = self.audience_generation

        def show(options):
            if generation != self.audience_generation or self.editor.closing:
                return
            choices = [
                ("Audience: Automatic", "auto"),
                ("Audience: General", "general"),
                ("Audience: Follow global setting", "inherit"),
            ]
            with C.QSignalBlocker(self.audience):
                self.audience.clear()
                for label, value in choices:
                    self.audience.addItem(label, value)
                for kind in ("theme", "bracket", "budget"):
                    group = [
                        (value, label)
                        for option_kind, value, label in options
                        if option_kind == kind
                    ]
                    if group:
                        self.audience.insertSeparator(self.audience.count())
                    for value, label in group:
                        self.audience.addItem(
                            f"{kind.title()}: {label}", f"{kind}:{value}"
                        )
            self.sync_audience()

        def read():
            try:
                return cohort_options(
                    core_data_root() / "recommendations" / "edhrec-cohorts.sqlite3"
                )
            except (OSError, ValueError, sqlite3.DatabaseError):
                return []

        self.audience_worker = Task(read, self, operation="recommendation audiences")
        self.audience_worker.completed.connect(lambda result, error: show(result or []))
        self.audience_worker.finished.connect(self.audiences_finished)
        self.audience_worker.start()

    def audiences_finished(self):
        self.audience_worker.deleteLater()
        self.audience_worker = None

    def set_expanded(self, expanded):
        self.expanded = expanded
        self.reflow_filters()

    def save_view(self):
        if (
            self.saving_view
            or self.preference_deck != self.editor.document.deck.deck_id
        ):
            return
        positions = dict(self.category_scroll)
        positions[self.position_key()] = (
            self.canvas.verticalScrollBar().value(),
            self.shown_limit,
        )
        value = dict(
            self.editor.document.editor_preferences.get("recommendation_browse", {})
        )
        value.update(
            text=self.text_filter.text(),
            kind=self.type_filter.currentText(),
            role=self.role_filter.currentText(),
            membership=self.membership.currentIndex(),
            identity=self.identity.currentData(),
            mana_value=self.mana_value.value(),
            category=self.selected_category,
            mode=self.browse_mode,
            mode_categories=dict(
                self.mode_categories, **{self.browse_mode: self.selected_category}
            ),
            collection=self.special_category.currentData(),
            card_width=self.canvas.card_width,
            positions={key: list(item) for key, item in positions.items()},
        )
        self.view_snapshot = deepcopy(value)
        if (
            self.editor.document.editor_preferences.get("recommendation_browse")
            != value
        ):
            self.saving_view = True
            try:
                self.editor.document.editor_preferences.update(
                    recommendation_browse=value
                )
                self.editor.changed()
            finally:
                self.saving_view = False

    def restore_view(self):
        value = self.editor.document.editor_preferences.get("recommendation_browse", {})
        changed = (
            self.preference_deck != self.editor.document.deck.deck_id
            or self.view_snapshot != value
        )
        if not changed:
            return False
        self.preference_deck = self.editor.document.deck.deck_id
        self.view_snapshot = deepcopy(value)
        for widget, text in [
            (self.type_filter, value.get("kind", "All Card Types")),
            (self.role_filter, value.get("role", "All roles")),
        ]:
            with C.QSignalBlocker(widget):
                if widget.findText(text) < 0:
                    widget.addItem(text)
                widget.setCurrentText(text)
        with (
            C.QSignalBlocker(self.text_filter),
            C.QSignalBlocker(self.membership),
            C.QSignalBlocker(self.identity),
            C.QSignalBlocker(self.mana_value),
        ):
            self.text_filter.setText(value.get("text", ""))
            self.membership.setCurrentIndex(value.get("membership", 1))
            self.identity.setCurrentIndex(
                max(0, self.identity.findData(value.get("identity")))
            )
            self.mana_value.setValue(value.get("mana_value", -1))
        collection = value.get("collection", "Top Cards")
        legacy_category = value.get("category", "Top Cards")
        if "mode" not in value and legacy_category not in TYPE_CATEGORIES_ORDER:
            collection = legacy_category
            legacy_category = "Top Cards"
        with C.QSignalBlocker(self.special_category):
            if self.special_category.findData(collection) < 0:
                self.special_category.addItem(collection, collection)
            self.special_category.setCurrentIndex(
                self.special_category.findData(collection)
            )
        self.browse_mode = "roles" if value.get("mode") == "roles" else "types"
        self.mode_categories = dict(value.get("mode_categories") or {})
        with C.QSignalBlocker(self.browse_modes):
            self.browse_modes.setCurrentIndex(int(self.browse_mode == "roles"))
        self.canvas.card_width = max(100, min(360, int(value.get("card_width", 270))))
        workspace = getattr(self.editor, "add_cards_workspace", None)
        if workspace is not None and workspace.expanded:
            with C.QSignalBlocker(workspace.zoom):
                workspace.zoom.setValue(self.canvas.card_width)
            workspace.resize_cards()
        self.selected_category = legacy_category
        self.category_scroll = {
            (key if key.startswith(("types:", "roles:")) else "types:" + key): tuple(
                item
            )
            for key, item in value.get("positions", {}).items()
            if isinstance(item, (list, tuple)) and len(item) == 2
        }
        self.restore_category_position, self.shown_limit = self.category_scroll.get(
            self.position_key(),
            self.category_scroll.get("types:" + collection, (0, 50)),
        )
        self.shown_limit = max(50, int(self.shown_limit))
        self.populate_navigation()
        return True

    def deck_changed(self):
        with C.QSignalBlocker(self.include_illegal):
            self.include_illegal.setChecked(
                self.editor.document.editor_preferences.get(
                    "include_illegal_cards", False
                )
            )
        if self.saving_view:
            return
        restored = self.restore_view()
        selected = commanders(self.editor.document)
        saved = self.editor.document.editor_preferences.get("discovery", {})
        theme = saved.get("theme_option") or (
            {"slug": saved["theme"], "name": saved["theme"]}
            if saved.get("theme")
            else None
        )
        discovery_identity = saved.get("identity")
        identity_changed = discovery_identity != self.last_discovery_identity
        if identity_changed and (
            not restored
            or not self.editor.document.editor_preferences.get("recommendation_browse")
        ):
            with C.QSignalBlocker(self.identity):
                self.identity.setCurrentIndex(
                    max(0, self.identity.findData(discovery_identity))
                )
        self.last_discovery_identity = discovery_identity
        manual = self.editor.document.editor_preferences.get("manual_themes", [])
        if manual:
            # Deck intent is a ranking signal. Only an explicit browse filter
            # should exclude otherwise useful recommendations.
            theme = None
        theme_changed = theme != self.theme_option
        self.theme_option = deepcopy(theme)
        identities = [
            (e.extras.get("facts") or {}).get("color_identity") for e in selected
        ]
        identity = "".join(
            c
            for c in "WUBRG"
            if any(c in colors for colors in identities if colors is not None)
        )
        identity = identity or (
            "Colorless"
            if identities and all(colors is not None for colors in identities)
            else "Color identity unavailable"
        )
        self.commander_header.setText(
            (" + ".join(e.name for e in selected) or "Discover Deck Ideas")
            + (" | " + identity if selected else "")
            + (" | " + theme.get("name", theme.get("slug", "")) if theme else "")
        )
        from mtg_core.paths import core_data_root
        from mtg_core.recommendation_sources import source_signature

        signature = (
            source_signature(core_data_root() / "recommendations")
            if self.active()
            else (self.key[1][-1] if self.key is not None else ())
        )
        self.sync_audience()
        if self.active():
            self.load_audiences(signature)
        current_source = source_key(self.editor.document, signature)
        key = (context_key(self.editor.document), current_source)
        changed = key != self.key
        switched = (
            self.key is not None and key[0][0]["deck_id"] != self.key[0][0]["deck_id"]
        )
        if changed:
            previous_source = self.loaded_source_key
            self.key = key
            self.generation += 1
            self.cancelled.set()
            self.page_cancelled.set()
            self.load_error = ""

            def access(signature):
                if (
                    signature
                    and signature[-1][0] == "library-access"
                    and signature[-1][1]
                ):
                    return signature[-1][1][0]
                return ()

            unsafe = previous_source is not None and (
                previous_source[:-1] != current_source[:-1]
                or access(previous_source[-1]) != access(current_source[-1])
            )
            from mtg_core.diagnostics import get_logger

            get_logger(__name__).debug(
                "Recommendation invalidation: deck_switch=%s unsafe=%s sources_changed=%s",
                switched,
                unsafe,
                previous_source != current_source,
            )
            if switched or unsafe:
                self.pages, self.rows = None, []
                self.audience.setToolTip("Updating audience…")
                if not restored:
                    self.category_scroll.clear()
                    self.shown_limit = 50
                self.loaded_key = None
        if self.loaded_key != key:
            self.pending = True
        self.filter_rows(reset=(theme_changed or identity_changed) and not restored)
        if self.active() and self.loaded_key != key:
            self.pending = True
            self.timer.start()

    def request_refresh(self):
        self.audience_signature = None
        self.loaded_source_key = None
        self.loaded_key = None
        self.cancelled.set()
        self.page_cancelled.set()
        self.load_error = ""
        self.generation += 1
        self.deck_changed()

    def refresh(self):
        if not self.active():
            return
        if self.worker is not None:
            self.pending = True
            return
        if self.loaded_key == self.key:
            self.pending = False
            if self.pending_page:
                self.request_page()
            return
        self.timer.stop()
        self.pending = False
        generation, key = self.generation, deepcopy(self.key)
        document = deepcopy(self.editor.document)
        service = self.editor.service
        reuse = self.pages if self.loaded_source_key == key[1] else None
        self.page_cancelled.set()
        self.cancelled = Event()
        cancelled = self.cancelled
        coverage = self.coverage
        edhrec_status = self.edhrec_status

        def load():
            from .recommendation_pages import RecommendationPages

            if reuse is not None:
                from mtg_core.recommendation_sources import default_sources

                sources = default_sources(
                    self.editor.recommendation_store(), document=document
                )
                pages = reuse.reranked(
                    service, document, sources=sources, should_cancel=cancelled.is_set
                )
                label = coverage
                cohort_status = edhrec_status
            else:
                pages = RecommendationPages()
                snapshot = load_recommendations(
                    service,
                    document,
                    self.editor.recommendation_store(),
                    include_present=True,
                    sink=pages.append,
                    should_cancel=cancelled.is_set,
                )
                active = [
                    s
                    for s in snapshot.get("source_status", [])
                    if s.get("role") != "local" and s.get("state") == "active"
                ]
                cohort_status = next(
                    (
                        s["status"]
                        for s in snapshot.get("source_status", [])
                        if s["source"] == "edhrec"
                    ),
                    "EDHREC unavailable",
                )
                starter = any(
                    "starter" in s.get("status", "").casefold() for s in active
                )
                label = (
                    (
                        "Limited bundled starter coverage"
                        if starter
                        else "Cached " + " + ".join(s["source"].upper() for s in active)
                    )
                    if active
                    else "No cached recommendations for this deck. Local Card Search remains available."
                )
            from mtg_core.recommendation_sources import source_signature
            from mtg_core.paths import core_data_root

            return dict(
                signature=source_signature(core_data_root() / "recommendations"),
                pages=pages,
                roles=pages.roles(),
                categories=pages.available_categories(),
                coverage=label,
                edhrec_status=cohort_status,
            )

        self.status.setText(
            "Updating recommendations..."
            if self.rows
            else "Loading cached recommendations..."
        )
        self.more.setEnabled(False)
        self.worker = Task(load, self, operation="recommendation candidates")
        self.worker.completed.connect(
            lambda result, error: self.completed(generation, key, result, error)
        )
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def completed(self, generation, key, snapshot, error):
        if (
            generation != self.generation
            or key != self.key
            or key[0] != context_key(self.editor.document)
        ):
            return
        self.pending = False
        self.timer.stop()
        if error:
            self.load_error = (
                "Could not load recommendations. Refresh or use Local Card Search."
            )
            self.status.setText(self.load_error)
            self.status.setToolTip(error)
            return
        if "signature" in snapshot:
            # Initial starter materialization is already represented by these results.
            # Other concurrent dataset changes must still invalidate on the next check.
            local_created = any(
                str(item[0]).endswith("local.sqlite3") and item[1] is None
                for item in key[1][-1]
            )

            def without_starter(signature):
                return tuple(
                    item
                    for item in signature
                    if "starter" not in str(item[0]).replace("\\", "/").split("/")
                    and not (local_created and str(item[0]).endswith("local.sqlite3"))
                )

            if without_starter(key[1][-1]) == without_starter(snapshot["signature"]):
                key = (key[0], source_key(self.editor.document, snapshot["signature"]))
                self.key = key
        self.loaded_key = key
        self.loaded_source_key = key[1]
        self.pages = snapshot["pages"]
        self.coverage = snapshot.get("coverage", "")
        self.edhrec_status = snapshot.get("edhrec_status", "")
        self.audience.setToolTip(self.edhrec_status)
        self.status.setToolTip("")
        current = self.role_filter.currentText()
        roles = snapshot["roles"]
        self.available_roles = roles
        with C.QSignalBlocker(self.role_filter):
            self.role_filter.clear()
            self.role_filter.addItems(["All roles", *roles])
            if self.role_filter.findText(current) < 0:
                self.role_filter.addItem(current)
            self.role_filter.setCurrentText(current)
        available = snapshot.get("categories", {})
        with C.QSignalBlocker(self.special_category):
            selected = self.special_category.currentData()
            self.special_category.clear()
            self.special_category.addItem("All collections", "Top Cards")
            labels = [
                label for label in CATEGORIES if label not in TYPE_CATEGORIES_ORDER
            ]
            labels.extend(
                sorted(label for label in available if label.startswith("EDHREC: "))
            )
            for label in labels:
                self.special_category.addItem(label, label)
            if self.special_category.findData(selected) < 0:
                self.special_category.addItem(selected, selected)
            self.special_category.setCurrentIndex(
                self.special_category.findData(selected)
            )
        self.populate_navigation()
        self.filter_rows(reset=False)

    def finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.more.setEnabled(True)
        if self.pending and self.loaded_key != self.key:
            if self.active():
                self.timer.start()
            return
        self.pending = False
        if self.pending_page:
            self.request_page()

    def near_bottom(self, value):
        bar = self.canvas.verticalScrollBar()
        if (
            value > 0
            and bar.maximum() - value < bar.pageStep()
            and self.more.isVisible()
            and self.worker is None
        ):
            C.QTimer.singleShot(0, self.load_more)

    def load_more(self):
        if self.worker is not None or not self.active():
            return
        self.shown_limit += 50
        self.filter_rows(reset=False)

    def filter_rows(self, *_, reset=True):
        if reset:
            self.category_scroll.clear()
            self.restore_category_position = 0
            self.shown_limit = 50
        self.page_cancelled.set()
        self.page_generation += 1
        self.render_rows()
        if self.pending or (self.worker is not None and self.loaded_key != self.key):
            self.status.setText(
                "Updating recommendations..."
                if self.rows
                else "Loading cached recommendations..."
            )
            if self.pages is None:
                self.canvas.empty_message = "Loading cached recommendations…"
        elif self.load_error:
            self.status.setText(self.load_error)
            self.canvas.empty_message = self.load_error
        if self.pages is not None:
            self.pending_page = True
            self.request_page()
        if reset:
            self.save_view()

    def request_page(self):
        if (
            not self.active()
            or self.worker is not None
            or self.page_worker is not None
            or self.pages is None
            or self.pending
            or self.loaded_key != self.key
        ):
            return
        self.pending_page = False
        pages, generation = self.pages, self.page_generation
        document = deepcopy(self.editor.document)
        self.page_cancelled = Event()
        cancelled = self.page_cancelled
        options = dict(
            limit=self.shown_limit,
            kind=self.type_filter.currentText(),
            text=self.text_filter.text(),
            role=self.role_filter.currentText(),
            membership=self.membership.currentIndex(),
            dismissed=settings(document)["dismissed"],
            category=self.selected_category,
            collection=self.special_category.currentData(),
            identity=self.identity.currentData(),
            mana_value=self.mana_value.value(),
            theme=deepcopy(self.theme_option),
            should_cancel=cancelled.is_set,
        )
        self.more.setEnabled(False)
        self.page_worker = Task(
            lambda: pages.page(document, **options),
            self,
            operation="recommendation page",
        )

        def completed(result, error):
            if (
                generation != self.page_generation
                or pages is not self.pages
                or not self.active()
                or cancelled.is_set()
            ):
                return
            if error:
                self.status.setText("Could not load this category. Refresh to retry.")
                return
            position = self.restore_category_position
            if position is None:
                position = self.canvas.verticalScrollBar().value()
            self.restore_category_position = None
            rows, more = result
            previous = {row["oracle_id"]: row["entry"] for row in self.rows}
            for row in rows:
                old = previous.get(row["oracle_id"])
                if (
                    old is not None
                    and old.card_id == row["entry"].card_id
                    and old.extras.get("facts") == row["entry"].extras.get("facts")
                ):
                    row["entry"] = old
            self.rows = rows
            self.render_rows(more)
            self.canvas.verticalScrollBar().setValue(position)

        self.page_worker.completed.connect(completed)
        self.page_worker.finished.connect(self.page_finished)
        self.page_worker.start()

    def page_finished(self):
        self.page_worker.deleteLater()
        self.page_worker = None
        self.more.setEnabled(self.worker is None)
        if self.pending_page and self.active():
            self.request_page()

    def render_rows(self, more=None):
        from mtg_core.card_pool import in_card_pool

        position = self.canvas.verticalScrollBar().value()
        present = in_deck_entries(
            self.editor.document, [row["entry"] for row in self.rows]
        )
        text = self.text_filter.text().strip().casefold()
        kind, role = self.type_filter.currentText(), self.role_filter.currentText()
        membership = self.membership.currentIndex()
        dismissed = settings(self.editor.document)["dismissed"]
        entries = []
        permissions = {}
        from mtg_core.library.recommendations import shared_permitted

        for row in self.rows:
            shared = row.get("source_evidence", {}).get("library")
            if shared:
                token = (
                    shared.get("cache_file"),
                    shared.get("cache_token"),
                    shared.get("cache_mtime"),
                )
                if token not in permissions:
                    permissions[token] = shared_permitted(shared)
                if not permissions[token]:
                    continue
            entry = row["entry"]
            entry.extras["category_suggestion"] = row["roles"]
            if (
                row["oracle_id"] not in dismissed
                and in_card_pool(entry.extras.get("facts") or {}, self.editor.document)
                and matches(
                    row,
                    self.selected_category,
                    self.identity.currentData(),
                    self.mana_value.value(),
                    self.theme_option,
                )
                and matches(row, self.special_category.currentData())
                and (kind == "All Card Types" or kind in card_types(entry))
                and (
                    not text
                    or text
                    in (
                        entry.name
                        + " "
                        + str(
                            (entry.extras.get("facts") or {}).get("oracle_text") or ""
                        )
                    ).casefold()
                )
                and (
                    role == "All roles"
                    or any(item["name"] == role for item in row["roles"])
                )
                and (
                    membership == 0 or (entry.entry_id in present) == (membership == 2)
                )
            ):
                entries.append(entry)
        if more is None:
            more = len(entries) > self.shown_limit or (
                self.pages is not None and not self.more.isHidden()
            )
        self.canvas.document.deck.entries = entries[: self.shown_limit]
        self.more.setVisible(more)
        count = len(self.canvas.document.deck.entries)
        label = f"{self.selected_category.removeprefix('Role: ')} · {count} cards"
        if more:
            label += " · More available"
        if self.rows and all(row.get("fallback") for row in self.rows):
            label += " · Popular Cards"
        audience_status = self.edhrec_status.casefold()
        if "disabled" in audience_status:
            label += " · EDHREC disabled"
        elif "unavailable" in audience_status and "using" in audience_status:
            label += " · General audience fallback"
        elif any(
            value in audience_status
            for value in ("unavailable", "no exact cached", "no cached edhrec")
        ):
            label += " · Audience unavailable"
        self.status.setText(label)
        self.status.setToolTip(
            "\n".join(filter(None, (self.edhrec_status, self.coverage)))
        )
        self.canvas.empty_message = (
            "No matching cards in this category. Clear a filter, change the theme, or use Local Card Search."
            if self.pages is not None
            else "Discover Deck Ideas or use Local Card Search to start building."
        )
        self.update_quantities()
        self.canvas.refresh()
        self.canvas.verticalScrollBar().setValue(position)

    def update_quantities(self):
        update_candidate_quantities(self.editor.document, self.canvas)

    def add(self, entry_id, _delta=1):
        row = next((r for r in self.rows if r["entry"].entry_id == entry_id), None)
        if row:
            if (
                _delta > 0
                and self.membership.currentIndex() == 1
                and in_deck_entries(self.editor.document, [row["entry"]])
            ):
                return
            entry = deepcopy(row["entry"])
            entry.extras["category_suggestion"] = row["roles"]
            self.editor.change_candidate_quantity(entry, _delta)

    def inspect(self, entry_id):
        self.editor.candidate_details(self.canvas, entry_id)

    def card_menu(self, entry_id, position):
        self.editor.candidate_menu(
            self.canvas, entry_id, position, self.add, self.dismiss
        )

    def dismiss(self, entry_id):
        row = next(
            (row for row in self.rows if row["entry"].entry_id == entry_id), None
        )
        if row is not None:
            preferences = settings(self.editor.document)
            preferences["dismissed"] = sorted(
                set(preferences["dismissed"]) | {row["oracle_id"]}
            )
            self.editor.edit(
                lambda document: document.editor_preferences.update(
                    recommendations=preferences
                )
            )

    def suspend(self):
        self.cancelled.set()
        self.page_cancelled.set()
        self.page_generation += 1
        self.timer.stop()
        self.pending = False
        self.generation += 1
        self.canvas.preview.hide()
        self.editor.thumbnails.set_visible(id(self.canvas), [])

    def discover_if_empty(self):
        if self.active() and not self.editor.document.deck.entries:
            self.open_discovery()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.editor.document.deck.entries and getattr(
            getattr(self.editor, "add_cards_workspace", None), "expanded", False
        ):
            C.QTimer.singleShot(0, self.discover_if_empty)
            return
        self.deck_changed()

    def hideEvent(self, event):
        if not self.editor.closing:
            self.save_view()
        self.page_cancelled.set()
        self.page_generation += 1
        self.timer.stop()
        self.canvas.preview.hide()
        self.editor.thumbnails.set_visible(id(self.canvas), [])
        super().hideEvent(event)
