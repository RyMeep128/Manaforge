from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QMimeData, Qt, pyqtSignal
from PyQt6.QtGui import QDrag, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from mtg_editor.catalog import CatalogCardCandidate
from mtg_editor.decklist_io import (
    export_decklist,
    import_decklist,
    import_decklist_file,
    write_decklist_file,
)
from mtg_editor.models import DEFAULT_CATEGORY_ID, DEFAULT_FORMAT, DeckCard, DeckProject
from mtg_editor.playtest import (
    PlaytestSession,
    append_playtest_note,
    draw_cards,
    mulligan,
    reset_playtest,
    start_playtest,
)
from mtg_editor.project_store import load_project, save_project
from mtg_editor.quick_add import add_catalog_candidate, quick_add_card, search_printings
from mtg_editor.services import CardFilters, compute_deck_stats, filter_cards, group_cards


GROUP_MODES = [
    ("None", "none"),
    ("Category", "category"),
    ("Section", "section"),
    ("Import Section", "import_section"),
    ("Card Type", "card_type"),
    ("Mana Value", "mana_value"),
    ("Color", "color"),
]

SORT_MODES = [
    ("Alphabetical A-Z", "alphabetical_az"),
    ("Alphabetical Z-A", "alphabetical_za"),
    ("Quantity", "quantity"),
    ("Import Order", "import_order"),
    ("Mana Value", "mana_value"),
    ("Color", "color"),
]

SECTION_OPTIONS = ["main", "sideboard", "maybeboard", "commander", "companion", "excluded"]
TABLE_HEADERS = [
    "Group",
    "Qty",
    "Name",
    "Section",
    "Category",
    "Type",
    "MV",
    "Color",
    "Set",
    "No.",
    "Status",
    "Image",
]
CARD_MIME_TYPE = "application/x-mtg-editor-card-id"
EDITOR_STYLE = """
QWidget#deckEditorRoot {
    background: #f4f6fb;
    color: #202631;
}
QFrame#deckBanner {
    background: #edf1f7;
    border: 1px solid #cdd5e1;
    border-radius: 10px;
}
QLineEdit#deckBannerInput {
    background: #f9fafb;
    border: 1px solid #b8c2cf;
    border-radius: 5px;
    color: #202631;
    padding: 5px 7px;
    selection-background-color: #8fb7ff;
}
QLineEdit#deckBannerInput:focus {
    background: #ffffff;
    border: 1px solid #3f6fb5;
}
QPushButton#deckBannerButton {
    background: #eef2f7;
    border: 1px solid #c3ccd9;
    border-radius: 5px;
    color: #202631;
    padding: 5px 9px;
}
QPushButton#deckBannerButton:hover {
    background: #e2e8f0;
}
QPushButton#deckBannerPrimaryButton {
    background: #dbeafe;
    border: 1px solid #93c5fd;
    border-radius: 5px;
    color: #17324d;
    padding: 5px 10px;
    font-weight: 600;
}
QPushButton#deckBannerPrimaryButton:hover {
    background: #bfdbfe;
}
QLabel#headerSummary {
    color: #334155;
}
QLabel#deckTitleLabel {
    color: #1f2937;
    font-size: 15px;
    font-weight: 700;
}
QLabel#mutedLabel {
    color: #64748b;
}
QLabel#statChip {
    background: #f8fafc;
    border: 1px solid #d1d8e5;
    border-radius: 8px;
    color: #1f2937;
    padding: 5px 8px;
}
QFrame#controlPanel {
    background: #eef2f7;
    border: 1px solid #ccd6e2;
    border-radius: 9px;
}
QLineEdit#softInput {
    background: #f8fafc;
    border: 1px solid #c3ccd9;
    border-radius: 5px;
    color: #202631;
    padding: 5px 7px;
}
QComboBox {
    background: #f8fafc;
    border: 1px solid #c3ccd9;
    border-radius: 5px;
    padding: 4px 7px;
}
QPushButton {
    background: #eef2f7;
    border: 1px solid #c3ccd9;
    border-radius: 5px;
    color: #202631;
    padding: 5px 8px;
}
QPushButton:hover {
    background: #e2e8f0;
}
QGroupBox {
    background: #f7f8fb;
    border: 1px solid #d1d8e5;
    border-radius: 9px;
    margin-top: 8px;
    padding-top: 9px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: #374151;
}
QScrollArea {
    background: #eef2f6;
    border: 1px solid #d1d8e5;
}
QWidget#visualBoard {
    background: #eef2f6;
}
QTabWidget::pane {
    background: #f7f8fb;
    border: 1px solid #d1d8e5;
    border-radius: 8px;
}
QTabBar::tab {
    background: #e2e8f0;
    border: 1px solid #d1d8e5;
    border-bottom: 0;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    color: #374151;
    padding: 6px 10px;
}
QTabBar::tab:selected {
    background: #f8fafc;
    font-weight: 600;
}
QLabel#statusPill {
    background: #e0ecff;
    border: 1px solid #b8cdf8;
    border-radius: 8px;
    color: #1e3a5f;
    padding: 6px 10px;
}
QFrame#searchResultRow {
    background: #f8fafc;
    border: 1px solid #d1d8e5;
    border-radius: 6px;
}
"""


class VisualCardTile(QFrame):
    cardSelected = pyqtSignal(str)
    incrementRequested = pyqtSignal(str)
    decrementRequested = pyqtSignal(str)
    removeRequested = pyqtSignal(str)

    def __init__(
        self,
        card: DeckCard,
        *,
        category_label: str,
        color_label: str,
        image_path: Path | None,
        selected: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.card_id = card.card_id
        self.setObjectName("visualCardTile")
        self.setProperty("selected", selected)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedWidth(178)
        self.setStyleSheet(
            """
            QFrame#visualCardTile {
                background: #fbfbf9;
                border: 1px solid #c7cbd1;
                border-radius: 7px;
            }
            QFrame#visualCardTile[selected="true"] {
                background: #eaf2ff;
                border: 2px solid #3b82f6;
            }
            QLabel#visualCardImage {
                background: #f1f3f5;
                border: 1px solid #d4d8de;
                border-radius: 6px;
                color: #334155;
                padding: 8px;
            }
            QLabel#visualCardName {
                font-weight: 600;
            }
            QLabel#visualCardMeta {
                color: #64748b;
            }
            QLabel#visualCardBadge {
                background: #e8eef8;
                border-radius: 5px;
                color: #223046;
                padding: 2px 6px;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(4)

        badge_row = QHBoxLayout()
        self.quantity_badge = QLabel(f"{card.quantity}x")
        self.quantity_badge.setObjectName("visualCardBadge")
        self.mana_badge = QLabel(self._mana_label(card))
        self.mana_badge.setObjectName("visualCardBadge")
        self.status_badge = QLabel(card.catalog_status or "manual")
        self.status_badge.setObjectName("visualCardBadge")
        badge_row.addWidget(self.quantity_badge)
        badge_row.addWidget(self.mana_badge)
        badge_row.addWidget(self.status_badge)
        badge_row.addStretch(1)
        layout.addLayout(badge_row)

        self.image_label = QLabel()
        self.image_label.setObjectName("visualCardImage")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setWordWrap(True)
        self.image_label.setFixedSize(158, 220)
        self._set_image_or_placeholder(card, image_path)
        layout.addWidget(self.image_label)

        title = QLabel(card.name)
        title.setObjectName("visualCardName")
        title.setWordWrap(True)
        layout.addWidget(title)

        type_text = card.type_line or "Unknown type"
        details = QLabel(f"{card.section} | {category_label}\n{color_label} | {type_text}")
        details.setObjectName("visualCardMeta")
        details.setWordWrap(True)
        layout.addWidget(details)

        print_parts = []
        if card.set_code:
            print_parts.append(card.set_code.upper())
        if card.collector_number:
            print_parts.append(card.collector_number)
        print_text = " ".join(print_parts) or "No print"
        footer = QLabel(print_text)
        footer.setObjectName("visualCardMeta")
        footer.setWordWrap(True)
        layout.addWidget(footer)

        action_row = QHBoxLayout()
        self.decrement_button = QPushButton("-")
        self.increment_button = QPushButton("+")
        self.remove_button = QPushButton("Remove")
        self.decrement_button.setFixedWidth(28)
        self.increment_button.setFixedWidth(28)
        self.decrement_button.setToolTip("Decrease quantity")
        self.increment_button.setToolTip("Increase quantity")
        self.remove_button.setToolTip("Remove from deck")
        self.decrement_button.clicked.connect(lambda: self.decrementRequested.emit(self.card_id))
        self.increment_button.clicked.connect(lambda: self.incrementRequested.emit(self.card_id))
        self.remove_button.clicked.connect(lambda: self.removeRequested.emit(self.card_id))
        action_row.addWidget(self.decrement_button)
        action_row.addWidget(self.increment_button)
        action_row.addWidget(self.remove_button)
        layout.addLayout(action_row)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.cardSelected.emit(self.card_id)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.buttons() & Qt.MouseButton.LeftButton:
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(CARD_MIME_TYPE, self.card_id.encode("utf-8"))
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.MoveAction)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def _set_image_or_placeholder(self, card: DeckCard, image_path: Path | None) -> None:
        if image_path is not None:
            pixmap = QPixmap(str(image_path))
            if not pixmap.isNull():
                self.image_label.setPixmap(
                    pixmap.scaled(
                        self.image_label.size(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                return
        self.image_label.setText(f"{card.name}\n\n{card.type_line or card.section}")

    def _mana_label(self, card: DeckCard) -> str:
        if card.mana_value is None:
            return "MV ?"
        return f"MV {str(card.mana_value).rstrip('0').rstrip('.')}"


class DeckBoardColumn(QFrame):
    cardDropped = pyqtSignal(str, str)
    renameRequested = pyqtSignal(str)

    def __init__(
        self,
        *,
        group_key: str,
        label: str,
        unique_count: int,
        total_copies: int,
        accepts_drop: bool,
        can_rename: bool,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.group_key = group_key
        self.setAcceptDrops(accepts_drop)
        self.setObjectName("deckBoardColumn")
        self.setMinimumWidth(218)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(
            """
            QFrame#deckBoardColumn {
                background: #f8fafc;
                border: 1px solid #d5dbe5;
                border-radius: 8px;
            }
            QLabel#columnTitle {
                font-weight: 700;
            }
            QLabel#columnMeta {
                color: #64748b;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 9, 9, 9)
        layout.setSpacing(7)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title = QLabel(label)
        title.setObjectName("columnTitle")
        title.setWordWrap(True)
        meta = QLabel(f"{unique_count} unique | {total_copies} copies")
        meta.setObjectName("columnMeta")
        title_block.addWidget(title)
        title_block.addWidget(meta)
        header.addLayout(title_block, stretch=1)
        if can_rename:
            rename_button = QPushButton("Rename")
            rename_button.clicked.connect(lambda: self.renameRequested.emit(self.group_key))
            header.addWidget(rename_button)
        layout.addLayout(header)

        drop_label = QLabel("Drop cards here" if accepts_drop else "")
        drop_label.setObjectName("columnMeta")
        drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(drop_label)

        self.card_layout = QVBoxLayout()
        self.card_layout.setSpacing(8)
        layout.addLayout(self.card_layout)
        layout.addStretch(1)

    def add_tile(self, tile: VisualCardTile) -> None:
        self.card_layout.addWidget(tile)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.acceptDrops() and event.mimeData().hasFormat(CARD_MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not self.acceptDrops() or not event.mimeData().hasFormat(CARD_MIME_TYPE):
            super().dropEvent(event)
            return
        card_id = bytes(event.mimeData().data(CARD_MIME_TYPE)).decode("utf-8")
        self.cardDropped.emit(card_id, self.group_key)
        event.acceptProposedAction()


class SearchResultRow(QFrame):
    candidateSelected = pyqtSignal(object)

    def __init__(self, candidate: CatalogCardCandidate, parent: QWidget | None = None):
        super().__init__(parent)
        self.candidate = candidate
        self.setObjectName("searchResultRow")
        self.setStyleSheet(
            """
            QFrame#searchResultRow {
                background: #f8fafc;
                border: 1px solid #d1d8e5;
                border-radius: 6px;
            }
            """
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(7, 7, 7, 7)
        details = QVBoxLayout()
        name = QLabel(candidate.name)
        name.setStyleSheet("font-weight: 600;")
        name.setWordWrap(True)
        print_bits = [bit for bit in [candidate.set_code.upper() if candidate.set_code else None, candidate.collector_number] if bit]
        meta = QLabel(" ".join(print_bits) or "Unknown print")
        meta.setStyleSheet("color: #64748b;")
        details.addWidget(name)
        details.addWidget(meta)
        layout.addLayout(details, stretch=1)
        add_button = QPushButton("Add")
        add_button.clicked.connect(lambda: self.candidateSelected.emit(self.candidate))
        layout.addWidget(add_button)


class DeckEditorWidget(QWidget):
    def __init__(
        self,
        project: DeckProject | None = None,
        *,
        project_path: str | Path | None = None,
        card_service: Any | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.project = project or DeckProject.new()
        self.project_path = None if project_path is None else Path(project_path)
        self.card_service = card_service
        self.playtest_session: PlaytestSession | None = None
        self.visible_card_ids: list[str] = []
        self.selected_card_id: str | None = None
        self.visual_card_tiles: dict[str, VisualCardTile] = {}
        self.visual_columns: dict[str, DeckBoardColumn] = {}
        self.search_candidates: list[CatalogCardCandidate] = []
        self.search_result_rows: list[SearchResultRow] = []
        self.stat_labels: dict[str, QLabel] = {}
        self._refreshing = False

        self._build_ui()
        self.refresh_view()

    def new_project(self, deck_name: str = "Untitled Deck", format: str = DEFAULT_FORMAT) -> None:
        self.project = DeckProject.new(deck_name=deck_name, format=format)
        self.project_path = None
        self.playtest_session = None
        self.selected_card_id = None
        self.refresh_view()

    def load_project_file(self, path: str | Path) -> DeckProject:
        self.project = load_project(path)
        self.project_path = Path(path)
        self.playtest_session = None
        self.selected_card_id = None
        self.refresh_view()
        return self.project

    def save_project_file(self, path: str | Path | None = None) -> None:
        target = Path(path) if path is not None else self.project_path
        if target is None:
            raise ValueError("project path is required")
        self._sync_project_metadata_from_fields()
        save_project(target, self.project)
        self.project_path = target
        self.status_label.setText(f"Saved {target.name}")
        self.refresh_view()

    def import_decklist_path(self, path: str | Path) -> None:
        result = import_decklist_file(self.project, path, card_service=self.card_service)
        self.status_label.setText(
            f"Imported {len(result.added_card_ids)} new, updated {len(result.updated_card_ids)}."
        )
        self.refresh_view()

    def export_decklist_path(self, path: str | Path) -> None:
        write_decklist_file(path, self.project, include_set_info=True)
        self.status_label.setText(f"Exported {Path(path).name}")

    def refresh_view(self) -> None:
        self._refreshing = True
        try:
            self.deck_name_edit.setText(self.project.metadata.deck_name)
            self.format_edit.setText(self.project.metadata.format)
            self._populate_category_combo()
            self._sync_view_controls_from_preferences()
            self._refresh_header()
            self._refresh_card_views()
            self._refresh_selected_controls()
            self._refresh_playtest_panel()
        finally:
            self._refreshing = False

    def _build_ui(self) -> None:
        self.setObjectName("deckEditorRoot")
        self.setStyleSheet(EDITOR_STYLE)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        root.addWidget(self._build_deck_banner())
        root.addWidget(self._build_controls_panel())

        self.content_stack = QStackedWidget()

        self.visual_scroll = QScrollArea()
        self.visual_scroll.setWidgetResizable(True)
        self.visual_board_widget = QWidget()
        self.visual_board_widget.setObjectName("visualBoard")
        self.visual_grid = QHBoxLayout(self.visual_board_widget)
        self.visual_grid.setContentsMargins(10, 10, 10, 10)
        self.visual_grid.setSpacing(10)
        self.visual_scroll.setWidget(self.visual_board_widget)

        self.table = QTableWidget(0, len(TABLE_HEADERS))
        self.table.setHorizontalHeaderLabels(TABLE_HEADERS)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        self.content_stack.addWidget(self.visual_scroll)
        self.content_stack.addWidget(self.table)
        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.addWidget(self._build_search_panel())
        self.workspace_splitter.addWidget(self.content_stack)
        self.workspace_splitter.addWidget(self._build_side_panel())
        self.workspace_splitter.setStretchFactor(0, 1)
        self.workspace_splitter.setStretchFactor(1, 4)
        self.workspace_splitter.setStretchFactor(2, 1)
        self.workspace_splitter.setSizes([260, 760, 300])
        root.addWidget(self.workspace_splitter, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusPill")
        self.status_label.setText("Ready")
        root.addWidget(self.status_label)

    def _build_deck_banner(self) -> QWidget:
        banner = QFrame()
        banner.setObjectName("deckBanner")
        layout = QVBoxLayout(banner)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_label = QLabel("Deck Workspace")
        title_label.setObjectName("deckTitleLabel")
        self.deck_name_edit = QLineEdit()
        self.deck_name_edit.setObjectName("deckBannerInput")
        self.deck_name_edit.setPlaceholderText("Deck name")
        self.deck_name_edit.setToolTip("Name for this deck project.")
        self.deck_name_edit.editingFinished.connect(self._on_metadata_changed)
        self.format_edit = QLineEdit()
        self.format_edit.setObjectName("deckBannerInput")
        self.format_edit.setPlaceholderText("Format")
        self.format_edit.setToolTip("Format label, such as Commander, Modern, or Custom.")
        self.format_edit.editingFinished.connect(self._on_metadata_changed)
        self.header_summary = QLabel("")
        self.header_summary.setObjectName("headerSummary")
        title_row.addWidget(title_label)
        title_row.addWidget(self.deck_name_edit, stretch=2)
        format_label = QLabel("Format")
        format_label.setObjectName("mutedLabel")
        title_row.addWidget(format_label)
        title_row.addWidget(self.format_edit, stretch=1)
        stat_row = QHBoxLayout()
        for key, label in [
            ("unique", "Unique 0"),
            ("copies", "Copies 0"),
            ("unresolved", "Unresolved 0"),
            ("missing", "Missing Images 0"),
        ]:
            chip = QLabel(label)
            chip.setObjectName("statChip")
            self.stat_labels[key] = chip
            stat_row.addWidget(chip)
        stat_row.addStretch(1)
        title_row.addLayout(stat_row, stretch=3)
        self.header_summary.setVisible(False)
        title_row.addWidget(self.header_summary)
        layout.addLayout(title_row)

        action_row = QHBoxLayout()
        self.new_button = QPushButton("New")
        self.open_button = QPushButton("Open")
        self.save_button = QPushButton("Save")
        self.import_button = QPushButton("Import")
        self.export_button = QPushButton("Export")
        self.quick_add_edit = QLineEdit()
        self.quick_add_edit.setObjectName("deckBannerInput")
        self.quick_add_edit.setPlaceholderText("Quick add or search, e.g. 4 Lightning Bolt")
        self.quick_add_edit.setToolTip("Type a card name or quantity plus name. Ambiguous matches appear in Search.")
        self.quick_add_button = QPushButton("Add")
        self.quick_add_button.setObjectName("deckBannerPrimaryButton")
        self.new_button.setToolTip("Start a new native deck editor project.")
        self.open_button.setToolTip("Open a saved native deck project JSON file.")
        self.save_button.setToolTip("Save this deck project.")
        self.import_button.setToolTip("Import a pasted or saved decklist file.")
        self.export_button.setToolTip("Export the current deck to a text decklist.")
        self.quick_add_button.setToolTip("Add the quick-add card to the deck.")

        self.new_button.clicked.connect(lambda: self.new_project())
        self.open_button.clicked.connect(self._choose_load_project)
        self.save_button.clicked.connect(self._choose_save_project)
        self.import_button.clicked.connect(self._choose_import_decklist)
        self.export_button.clicked.connect(self._choose_export_decklist)
        self.quick_add_button.clicked.connect(self._on_quick_add)
        self.quick_add_edit.returnPressed.connect(self._on_quick_add)

        for widget in [
            self.new_button,
            self.open_button,
            self.save_button,
            self.import_button,
            self.export_button,
        ]:
            widget.setObjectName("deckBannerButton")
            action_row.addWidget(widget)
        action_row.addWidget(self.quick_add_edit, stretch=1)
        action_row.addWidget(self.quick_add_button)
        layout.addLayout(action_row)
        return banner

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        self.deck_name_edit = QLineEdit()
        self.deck_name_edit.setPlaceholderText("Deck name")
        self.deck_name_edit.editingFinished.connect(self._on_metadata_changed)
        self.format_edit = QLineEdit()
        self.format_edit.setPlaceholderText("Format")
        self.format_edit.editingFinished.connect(self._on_metadata_changed)
        self.header_summary = QLabel("")

        layout.addWidget(QLabel("Name"))
        layout.addWidget(self.deck_name_edit, stretch=2)
        layout.addWidget(QLabel("Format"))
        layout.addWidget(self.format_edit, stretch=1)
        layout.addWidget(self.header_summary, stretch=3)
        return layout

    def _build_actions(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        self.new_button = QPushButton("New")
        self.open_button = QPushButton("Open")
        self.save_button = QPushButton("Save")
        self.import_button = QPushButton("Import")
        self.export_button = QPushButton("Export")
        self.quick_add_edit = QLineEdit()
        self.quick_add_edit.setPlaceholderText("Quick add, e.g. 4 Lightning Bolt")
        self.quick_add_button = QPushButton("Add")

        self.new_button.clicked.connect(lambda: self.new_project())
        self.open_button.clicked.connect(self._choose_load_project)
        self.save_button.clicked.connect(self._choose_save_project)
        self.import_button.clicked.connect(self._choose_import_decklist)
        self.export_button.clicked.connect(self._choose_export_decklist)
        self.quick_add_button.clicked.connect(self._on_quick_add)
        self.quick_add_edit.returnPressed.connect(self._on_quick_add)

        for widget in [
            self.new_button,
            self.open_button,
            self.save_button,
            self.import_button,
            self.export_button,
        ]:
            layout.addWidget(widget)
        layout.addWidget(self.quick_add_edit, stretch=1)
        layout.addWidget(self.quick_add_button)
        return layout

    def _build_controls_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("controlPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(9, 8, 9, 8)
        layout.setSpacing(6)
        heading_row = QHBoxLayout()
        heading = QLabel("Board View")
        heading.setObjectName("deckTitleLabel")
        hint = QLabel("Group, sort, filter, and organize the current visual board.")
        hint.setObjectName("mutedLabel")
        heading_row.addWidget(heading)
        heading_row.addWidget(hint, stretch=1)
        layout.addLayout(heading_row)
        layout.addLayout(self._build_controls())
        return panel

    def _build_controls(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        self.group_combo = QComboBox()
        self._populate_combo(self.group_combo, GROUP_MODES)
        self.group_combo.setToolTip("Choose how cards are stacked on the visual board.")
        self.sort_combo = QComboBox()
        self._populate_combo(self.sort_combo, SORT_MODES)
        self.sort_combo.setToolTip("Choose the order inside each group.")
        self.text_filter_edit = QLineEdit()
        self.text_filter_edit.setObjectName("softInput")
        self.text_filter_edit.setPlaceholderText("Filter cards")
        self.text_filter_edit.setToolTip("Filter visible cards by name, type, set, tag, and other text.")
        self.status_filter_combo = QComboBox()
        self._populate_combo(
            self.status_filter_combo,
            [
                ("All statuses", ""),
                ("Resolved", "resolved"),
                ("Unresolved", "unresolved"),
                ("Missing Image", "missing_image"),
            ],
        )
        self.status_filter_combo.setToolTip("Limit visible cards by catalog or image status.")
        self.visual_view_checkbox = QCheckBox("Visual")
        self.visual_view_checkbox.setChecked(self.project.preferences.view_mode != "text")
        self.visual_view_checkbox.setToolTip("Switch between visual board and dense table view.")
        self.new_category_button = QPushButton("New Category")
        self.rename_group_button = QPushButton("Rename Group")
        self.new_category_button.setToolTip("Create a deck category and switch to category grouping.")
        self.rename_group_button.setToolTip("Rename the selected card's custom category.")

        self.group_combo.currentIndexChanged.connect(self._on_view_controls_changed)
        self.sort_combo.currentIndexChanged.connect(self._on_view_controls_changed)
        self.text_filter_edit.textChanged.connect(self._on_view_controls_changed)
        self.status_filter_combo.currentIndexChanged.connect(self._on_view_controls_changed)
        self.visual_view_checkbox.stateChanged.connect(self._on_view_mode_changed)
        self.new_category_button.clicked.connect(self._create_category_from_prompt)
        self.rename_group_button.clicked.connect(self._rename_selected_category_from_prompt)

        layout.addWidget(self.visual_view_checkbox)
        layout.addWidget(QLabel("Group"))
        layout.addWidget(self.group_combo)
        layout.addWidget(QLabel("Sort"))
        layout.addWidget(self.sort_combo)
        layout.addWidget(self.text_filter_edit, stretch=1)
        layout.addWidget(self.status_filter_combo)
        layout.addWidget(self.new_category_button)
        layout.addWidget(self.rename_group_button)
        return layout

    def _build_search_panel(self) -> QWidget:
        group = QGroupBox("Search")
        layout = QVBoxLayout(group)
        helper = QLabel("Local catalog results stay here so adding printings is a one-click action.")
        helper.setObjectName("mutedLabel")
        helper.setWordWrap(True)
        layout.addWidget(helper)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("softInput")
        self.search_edit.setPlaceholderText("Search local catalog")
        self.search_edit.setToolTip("Search the local card database before any remote lookup.")
        self.search_button = QPushButton("Search")
        self.search_button.setToolTip("Find matching local card printings.")
        self.search_button.clicked.connect(self._on_search)
        self.search_edit.returnPressed.connect(self._on_search)

        search_row = QHBoxLayout()
        search_row.addWidget(self.search_edit, stretch=1)
        search_row.addWidget(self.search_button)
        layout.addLayout(search_row)

        self.search_results_scroll = QScrollArea()
        self.search_results_scroll.setWidgetResizable(True)
        self.search_results_widget = QWidget()
        self.search_results_layout = QVBoxLayout(self.search_results_widget)
        self.search_results_layout.setContentsMargins(4, 4, 4, 4)
        self.search_results_layout.setSpacing(6)
        self.search_results_layout.addStretch(1)
        self.search_results_scroll.setWidget(self.search_results_widget)
        layout.addWidget(self.search_results_scroll, stretch=1)
        return group

    def _build_side_panel(self) -> QWidget:
        self.right_panel_tabs = QTabWidget()
        self.right_panel_tabs.setObjectName("rightPanelTabs")
        self.right_panel_tabs.addTab(self._build_selected_card_group(), "Inspect")
        self.right_panel_tabs.addTab(self._build_playtest_group(), "Playtest")
        return self.right_panel_tabs

    def _build_selected_card_group(self) -> QGroupBox:
        group = QGroupBox("Card Inspector")
        layout = QFormLayout(group)
        self.selected_name_label = QLabel("None")
        self.quantity_spin = QSpinBox()
        self.quantity_spin.setRange(0, 999)
        self.section_combo = QComboBox()
        self.section_combo.addItems(SECTION_OPTIONS)
        self.category_combo = QComboBox()
        self.tags_edit = QLineEdit()
        self.apply_card_button = QPushButton("Apply")
        self.increment_selected_button = QPushButton("+1")
        self.decrement_selected_button = QPushButton("-1")
        self.remove_selected_button = QPushButton("Remove")
        self.apply_card_button.setToolTip("Apply the inspector edits to the selected card.")
        self.increment_selected_button.setToolTip("Increase selected card quantity.")
        self.decrement_selected_button.setToolTip("Decrease selected card quantity.")
        self.remove_selected_button.setToolTip("Remove selected card from the deck.")
        self.apply_card_button.clicked.connect(self._apply_selected_card_edits)
        self.increment_selected_button.clicked.connect(lambda: self._adjust_selected_quantity(1))
        self.decrement_selected_button.clicked.connect(lambda: self._adjust_selected_quantity(-1))
        self.remove_selected_button.clicked.connect(self._remove_selected_card)

        action_row = QHBoxLayout()
        action_row.addWidget(self.decrement_selected_button)
        action_row.addWidget(self.increment_selected_button)
        action_row.addWidget(self.remove_selected_button)

        layout.addRow("Card", self.selected_name_label)
        layout.addRow("Quantity", self.quantity_spin)
        layout.addRow("Section", self.section_combo)
        layout.addRow("Category", self.category_combo)
        layout.addRow("Tags", self.tags_edit)
        layout.addRow(action_row)
        layout.addRow(self.apply_card_button)
        return group

    def _build_playtest_group(self) -> QGroupBox:
        group = QGroupBox("Playtest")
        layout = QVBoxLayout(group)
        button_row = QHBoxLayout()
        self.start_playtest_button = QPushButton("Start")
        self.mulligan_button = QPushButton("Mulligan")
        self.draw_one_button = QPushButton("Draw 1")
        self.draw_many_button = QPushButton("Draw 3")
        self.reset_playtest_button = QPushButton("Reset")

        self.start_playtest_button.clicked.connect(self._start_playtest)
        self.mulligan_button.clicked.connect(self._mulligan_playtest)
        self.draw_one_button.clicked.connect(lambda: self._draw_playtest_cards(1))
        self.draw_many_button.clicked.connect(lambda: self._draw_playtest_cards(3))
        self.reset_playtest_button.clicked.connect(self._reset_playtest)

        for widget in [
            self.start_playtest_button,
            self.mulligan_button,
            self.draw_one_button,
            self.draw_many_button,
            self.reset_playtest_button,
        ]:
            button_row.addWidget(widget)
        layout.addLayout(button_row)

        self.playtest_summary_label = QLabel("No playtest session")
        self.playtest_hand_list = QListWidget()
        self.playtest_warning_label = QLabel("")
        self.playtest_notes_edit = QTextEdit()
        self.playtest_notes_edit.setPlaceholderText("Playtest note")
        self.playtest_notes_edit.setFixedHeight(64)
        self.add_note_button = QPushButton("Add Note")
        self.add_note_button.clicked.connect(self._append_playtest_note)

        layout.addWidget(self.playtest_summary_label)
        layout.addWidget(self.playtest_hand_list)
        layout.addWidget(self.playtest_warning_label)
        layout.addWidget(self.playtest_notes_edit)
        layout.addWidget(self.add_note_button)
        return group

    def _populate_combo(self, combo: QComboBox, entries: list[tuple[str, str]]) -> None:
        for label, value in entries:
            combo.addItem(label, value)

    def _populate_category_combo(self) -> None:
        current = self.category_combo.currentData() if hasattr(self, "category_combo") else None
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        for category in self.project.categories:
            self.category_combo.addItem(category.name, category.id)
        index = self.category_combo.findData(current)
        if index >= 0:
            self.category_combo.setCurrentIndex(index)
        self.category_combo.blockSignals(False)

    def _sync_view_controls_from_preferences(self) -> None:
        self._set_combo_data_without_signal(self.group_combo, self.project.preferences.group_mode)
        self._set_combo_data_without_signal(self.sort_combo, self.project.preferences.sort_mode)
        self.visual_view_checkbox.blockSignals(True)
        self.visual_view_checkbox.setChecked(self.project.preferences.view_mode != "text")
        self.visual_view_checkbox.blockSignals(False)
        self._apply_view_mode()

    def _set_combo_data_without_signal(self, combo: QComboBox, value: str) -> None:
        combo.blockSignals(True)
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _refresh_header(self) -> None:
        stats = compute_deck_stats(self.project)
        summary_parts = [
            f"Unique: {stats['total_unique_cards']}",
            f"Copies: {stats['total_copies']}",
            f"Unresolved: {stats['unresolved_count']}",
            f"Missing Images: {stats['missing_image_count']}",
        ]
        self.header_summary.setText(" | ".join(summary_parts))
        self.stat_labels["unique"].setText(f"Unique {stats['total_unique_cards']}")
        self.stat_labels["copies"].setText(f"Copies {stats['total_copies']}")
        self.stat_labels["unresolved"].setText(f"Unresolved {stats['unresolved_count']}")
        self.stat_labels["missing"].setText(
            f"Missing Images {stats['missing_image_count']}"
        )

    def _refresh_card_views(self) -> None:
        self._sync_project_metadata_from_fields()
        group_mode = self.group_combo.currentData() or "none"
        self.project.preferences.group_mode = group_mode
        self.project.preferences.sort_mode = self.sort_combo.currentData() or "alphabetical_az"

        columns = self._grouped_visible_columns(group_mode)
        rows = [
            (group_label, card)
            for _group_key, group_label, cards in columns
            for card in cards
        ]
        self.visible_card_ids = [card.card_id for _group, card in rows]
        if self.selected_card_id and self.project.get_card(self.selected_card_id) is None:
            self.selected_card_id = None
        self._refresh_table(rows)
        self._refresh_visual_grid(columns)
        self._apply_view_mode()

    def _grouped_visible_rows(self, group_mode: str) -> list[tuple[str, DeckCard]]:
        return [
            (group_label, card)
            for _group_key, group_label, cards in self._grouped_visible_columns(group_mode)
            for card in cards
        ]

    def _grouped_visible_columns(self, group_mode: str) -> list[tuple[str, str, list[DeckCard]]]:
        visible_cards = self._visible_cards()
        visible_ids = {card.card_id for card in visible_cards}
        card_by_id = {card.card_id: card for card in visible_cards}
        columns: list[tuple[str, str, list[DeckCard]]] = []
        for group in group_cards(self.project, group_mode):
            cards: list[DeckCard] = []
            for card_id in group.card_ids:
                if card_id in visible_ids:
                    cards.append(card_by_id[card_id])
            if cards:
                columns.append((group.key, group.label, cards))
        return columns

    def _refresh_table(self, rows: list[tuple[str, DeckCard]] | None = None) -> None:
        if rows is None:
            self._sync_project_metadata_from_fields()
            group_mode = self.group_combo.currentData() or "none"
            self.project.preferences.group_mode = group_mode
            self.project.preferences.sort_mode = self.sort_combo.currentData() or "alphabetical_az"
            rows = self._grouped_visible_rows(group_mode)
            self.visible_card_ids = [card.card_id for _group, card in rows]
        self.table.setRowCount(len(rows))
        for row, (group_label, card) in enumerate(rows):
            values = [
                group_label,
                str(card.quantity),
                card.name,
                card.section,
                self._category_label(card.primary_category),
                card.type_line or "",
                "" if card.mana_value is None else str(card.mana_value).rstrip("0").rstrip("."),
                self._color_label(card),
                card.set_code or "",
                card.collector_number or "",
                card.catalog_status or "",
                "Ready" if self._has_image(card) else "Missing",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, card.card_id)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self._select_table_row(self.selected_card_id)

    def _refresh_visual_grid(self, columns: list[tuple[str, str, list[DeckCard]]]) -> None:
        self._clear_layout(self.visual_grid)
        self.visual_card_tiles = {}
        self.visual_columns = {}

        if not columns:
            empty_label = QLabel("No cards match the current view.")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("color: #64748b; padding: 24px;")
            self.visual_grid.addWidget(empty_label)
            self.visual_grid.addStretch(1)
            return

        group_mode = self.group_combo.currentData() or "none"
        accepts_drop = group_mode in {"category", "section", "import_section"}
        for group_key, group_label, cards in columns:
            total_copies = sum(max(0, card.quantity) for card in cards)
            can_rename = group_mode == "category" and group_key != DEFAULT_CATEGORY_ID
            column = DeckBoardColumn(
                group_key=group_key,
                label=group_label,
                unique_count=len(cards),
                total_copies=total_copies,
                accepts_drop=accepts_drop,
                can_rename=can_rename,
            )
            column.cardDropped.connect(self._move_card_to_group)
            column.renameRequested.connect(self._rename_category_from_prompt)
            self.visual_columns[group_key] = column
            for card in cards:
                tile = VisualCardTile(
                    card,
                    category_label=self._category_label(card.primary_category),
                    color_label=self._color_label(card),
                    image_path=self._local_image_file(card),
                    selected=card.card_id == self.selected_card_id,
                )
                tile.cardSelected.connect(self._select_card_id)
                tile.incrementRequested.connect(lambda card_id: self._adjust_card_quantity(card_id, 1))
                tile.decrementRequested.connect(lambda card_id: self._adjust_card_quantity(card_id, -1))
                tile.removeRequested.connect(self._remove_card_id)
                self.visual_card_tiles[card.card_id] = tile
                column.add_tile(tile)
            self.visual_grid.addWidget(column)
        self.visual_grid.addStretch(1)

    def _visible_cards(self) -> list[DeckCard]:
        status_filter = self.status_filter_combo.currentData()
        missing_image = True if status_filter == "missing_image" else None
        catalog_status = None if status_filter in {"", "missing_image"} else status_filter
        return filter_cards(
            self.project,
            CardFilters(
                text=self.text_filter_edit.text().strip() or None,
                catalog_status=catalog_status,
                missing_image=missing_image,
            ),
        )

    def _refresh_selected_controls(self) -> None:
        card = self._selected_card()
        enabled = card is not None
        for widget in [
            self.quantity_spin,
            self.section_combo,
            self.category_combo,
            self.tags_edit,
            self.apply_card_button,
            self.increment_selected_button,
            self.decrement_selected_button,
            self.remove_selected_button,
        ]:
            widget.setEnabled(enabled)
        if card is None:
            self.selected_name_label.setText("None")
            self.quantity_spin.setValue(0)
            self.tags_edit.clear()
            return
        self.selected_name_label.setText(card.name)
        self.quantity_spin.setValue(card.quantity)
        section_index = self.section_combo.findText(card.section)
        if section_index >= 0:
            self.section_combo.setCurrentIndex(section_index)
        category_index = self.category_combo.findData(card.primary_category)
        if category_index >= 0:
            self.category_combo.setCurrentIndex(category_index)
        self.tags_edit.setText(", ".join(card.tags))

    def _refresh_playtest_panel(self) -> None:
        self.playtest_hand_list.clear()
        if self.playtest_session is None:
            self.playtest_summary_label.setText("No playtest session")
            self.playtest_warning_label.setText("")
            return
        session = self.playtest_session
        self.playtest_summary_label.setText(
            f"Hand: {len(session.hand)} | Library: {len(session.library)} | Drawn: {len(session.draw_history)}"
        )
        for card in session.hand:
            self.playtest_hand_list.addItem(f"{card.name} #{card.copy_number}")
        self.playtest_warning_label.setText(" | ".join(session.warnings))

    def _selected_card(self) -> DeckCard | None:
        if not self.selected_card_id:
            return None
        return self.project.get_card(self.selected_card_id)

    def _sync_project_metadata_from_fields(self) -> None:
        if not hasattr(self, "deck_name_edit"):
            return
        self.project.metadata.deck_name = self.deck_name_edit.text().strip() or "Untitled Deck"
        self.project.metadata.format = self.format_edit.text().strip() or DEFAULT_FORMAT

    def _on_metadata_changed(self) -> None:
        if self._refreshing:
            return
        self._sync_project_metadata_from_fields()
        self._refresh_header()

    def _on_view_controls_changed(self) -> None:
        if self._refreshing:
            return
        self._refresh_card_views()

    def _on_view_mode_changed(self, *_args: object) -> None:
        if self._refreshing:
            return
        self.project.preferences.view_mode = "grid" if self.visual_view_checkbox.isChecked() else "text"
        self._apply_view_mode()
        self._refresh_visual_selection()

    def _on_selection_changed(self) -> None:
        if self._refreshing:
            return
        selected_items = self.table.selectedItems()
        if selected_items:
            self.selected_card_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
        else:
            self.selected_card_id = None
        self._refresh_visual_selection()
        self._refresh_selected_controls()

    def _on_quick_add(self) -> None:
        text = self.quick_add_edit.text().strip()
        result = quick_add_card(self.project, text, card_service=self.card_service)
        if result.status == "added":
            self.quick_add_edit.clear()
            self.selected_card_id = result.card_id
        elif result.status == "needs_selection":
            self.search_edit.setText(result.query.name if result.query else text)
            self._populate_search_results(result.candidates)
            self.status_label.setText(f"{len(result.candidates)} printings found. Choose one from Search.")
            return
        self.status_label.setText(result.message or result.status)
        self.refresh_view()

    def _on_search(self) -> None:
        query = self.search_edit.text().strip()
        candidates = search_printings(query, card_service=self.card_service, limit=30)
        self._populate_search_results(candidates)
        if candidates:
            self.status_label.setText(f"{len(candidates)} local printings found.")
        else:
            self.status_label.setText("No local printings found.")

    def _populate_search_results(self, candidates: list[CatalogCardCandidate]) -> None:
        self.search_candidates = list(candidates)
        self.search_result_rows = []
        self._clear_layout(self.search_results_layout)
        if not candidates:
            empty = QLabel("Search results appear here.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #64748b; padding: 12px;")
            self.search_results_layout.addWidget(empty)
            self.search_results_layout.addStretch(1)
            return
        for candidate in candidates:
            row = SearchResultRow(candidate)
            row.candidateSelected.connect(self._add_search_candidate)
            self.search_result_rows.append(row)
            self.search_results_layout.addWidget(row)
        self.search_results_layout.addStretch(1)

    def _add_search_candidate(self, candidate: CatalogCardCandidate) -> None:
        result = add_catalog_candidate(self.project, candidate)
        if result.status == "added":
            self.selected_card_id = result.card_id
        self.status_label.setText(result.message or result.status)
        self.refresh_view()

    def _apply_selected_card_edits(self) -> None:
        card = self._selected_card()
        if card is None:
            return
        self.project.set_quantity(card.card_id, self.quantity_spin.value())
        self.project.set_section(card.card_id, self.section_combo.currentText())
        category_id = self.category_combo.currentData() or DEFAULT_CATEGORY_ID
        self.project.assign_category(card.card_id, category_id)
        card.tags = [
            tag.strip()
            for tag in self.tags_edit.text().split(",")
            if tag.strip()
        ]
        self.status_label.setText(f"Updated {card.name}")
        self.refresh_view()

    def _adjust_selected_quantity(self, delta: int) -> None:
        card = self._selected_card()
        if card is not None:
            self._adjust_card_quantity(card.card_id, delta)

    def _adjust_card_quantity(self, card_id: str, delta: int) -> None:
        card = self.project.get_card(card_id)
        if card is None:
            return
        self.project.set_quantity(card_id, max(0, card.quantity + delta))
        self.selected_card_id = card_id
        self.status_label.setText(f"Updated {card.name}")
        self.refresh_view()

    def _remove_selected_card(self) -> None:
        card = self._selected_card()
        if card is not None:
            self._remove_card_id(card.card_id)

    def _remove_card_id(self, card_id: str) -> None:
        card = self.project.get_card(card_id)
        if card is None:
            return
        self.project.remove_card(card_id)
        self.selected_card_id = None
        self.status_label.setText(f"Removed {card.name}")
        self.refresh_view()

    def _move_card_to_group(self, card_id: str, group_key: str) -> None:
        card = self.project.get_card(card_id)
        if card is None:
            return
        group_mode = self.group_combo.currentData() or "none"
        if group_mode == "category":
            self.project.assign_category(card_id, group_key)
        elif group_mode == "section":
            self.project.set_section(card_id, group_key)
        elif group_mode == "import_section":
            self.project.set_import_section(card_id, group_key)
        else:
            return
        self.selected_card_id = card_id
        self.status_label.setText(f"Moved {card.name} to {self._group_target_label(group_key)}")
        self.refresh_view()

    def create_category_from_board(self, name: str) -> str:
        category_id = self.project.create_category(name)
        self.project.preferences.group_mode = "category"
        self._set_combo_data_without_signal(self.group_combo, "category")
        self.status_label.setText(f"Created category {name.strip()}")
        self.refresh_view()
        return category_id

    def rename_category_from_board(self, category_id: str, name: str) -> None:
        self.project.rename_category(category_id, name)
        self.status_label.setText(f"Renamed category to {name.strip()}")
        self.refresh_view()

    def _create_category_from_prompt(self) -> None:
        name, accepted = QInputDialog.getText(self, "New Category", "Category name")
        if accepted and name.strip():
            self.create_category_from_board(name)

    def _rename_selected_category_from_prompt(self) -> None:
        card = self._selected_card()
        if card is None or card.primary_category == DEFAULT_CATEGORY_ID:
            self.status_label.setText("Select a card in a custom category first.")
            return
        self._rename_category_from_prompt(card.primary_category)

    def _rename_category_from_prompt(self, category_id: str) -> None:
        current_name = self._category_label(category_id)
        name, accepted = QInputDialog.getText(self, "Rename Category", "Category name", text=current_name)
        if accepted and name.strip():
            self.rename_category_from_board(category_id, name)

    def _start_playtest(self) -> None:
        self.playtest_session = start_playtest(self.project)
        self._refresh_playtest_panel()

    def _mulligan_playtest(self) -> None:
        if self.playtest_session is None:
            self._start_playtest()
            return
        next_size = max(1, len(self.playtest_session.hand) - 1)
        self.playtest_session = mulligan(self.playtest_session, next_size)
        self._refresh_playtest_panel()

    def _draw_playtest_cards(self, count: int) -> None:
        if self.playtest_session is None:
            self._start_playtest()
        if self.playtest_session is not None:
            draw_cards(self.playtest_session, count)
            self._refresh_playtest_panel()

    def _reset_playtest(self) -> None:
        if self.playtest_session is None:
            self._start_playtest()
            return
        self.playtest_session = reset_playtest(self.playtest_session)
        self._refresh_playtest_panel()

    def _append_playtest_note(self) -> None:
        append_playtest_note(self.project, self.playtest_notes_edit.toPlainText())
        self.playtest_notes_edit.clear()
        self.status_label.setText("Playtest note added.")

    def _choose_load_project(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Open Deck Project", "", "Deck Projects (*.json)")
        if path:
            self.load_project_file(path)

    def _choose_save_project(self) -> None:
        path = str(self.project_path) if self.project_path else ""
        if not path:
            path, _filter = QFileDialog.getSaveFileName(self, "Save Deck Project", "", "Deck Projects (*.json)")
        if path:
            self.save_project_file(path)

    def _choose_import_decklist(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Import Decklist",
            "",
            "Decklists (*.txt *.csv *.dek *.dck *.mtga);;All Files (*)",
        )
        if path:
            self.import_decklist_path(path)

    def _choose_export_decklist(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(self, "Export Decklist", "", "Text Decklists (*.txt)")
        if path:
            self.export_decklist_path(path)

    def _category_label(self, category_id: str) -> str:
        for category in self.project.categories:
            if category.id == category_id:
                return category.name
        return category_id

    def _group_target_label(self, group_key: str) -> str:
        group_mode = self.group_combo.currentData() or "none"
        if group_mode == "category":
            return self._category_label(group_key)
        if group_mode == "section":
            return group_key.title()
        return group_key

    def _color_label(self, card: DeckCard) -> str:
        colors = card.color_identity or card.colors
        return "".join(colors) if colors else "Colorless"

    def _has_image(self, card: DeckCard) -> bool:
        return any(
            [
                card.image_path,
                card.image_uri,
                card.image_asset_id,
                card.local_image_path,
                card.preview_uri,
                card.thumbnail_uri,
            ]
        )

    def _select_card_id(self, card_id: str) -> None:
        if self.project.get_card(card_id) is None:
            return
        self.selected_card_id = card_id
        self._select_table_row(card_id)
        self._refresh_visual_selection()
        self._refresh_selected_controls()

    def _select_table_row(self, card_id: str | None) -> None:
        self.table.blockSignals(True)
        self.table.clearSelection()
        if card_id:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item is not None and item.data(Qt.ItemDataRole.UserRole) == card_id:
                    self.table.selectRow(row)
                    break
        self.table.blockSignals(False)

    def _refresh_visual_selection(self) -> None:
        for card_id, tile in self.visual_card_tiles.items():
            tile.set_selected(card_id == self.selected_card_id)

    def _apply_view_mode(self) -> None:
        visual = self.project.preferences.view_mode != "text"
        self.visual_view_checkbox.blockSignals(True)
        self.visual_view_checkbox.setChecked(visual)
        self.visual_view_checkbox.blockSignals(False)
        self.content_stack.setCurrentWidget(self.visual_scroll if visual else self.table)

    def _local_image_file(self, card: DeckCard) -> Path | None:
        for raw_path in [card.local_image_path, card.image_path]:
            if not raw_path or "://" in raw_path:
                continue
            path = Path(raw_path)
            candidates = [path] if path.is_absolute() else [Path.cwd() / path]
            if self.project_path is not None and not path.is_absolute():
                candidates.insert(0, self.project_path.parent / path)
            for candidate in candidates:
                if candidate.is_file():
                    return candidate
        return None

    def _clear_layout(self, layout: Any) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()


class DeckEditorWindow(QMainWindow):
    def __init__(self, project: DeckProject | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("MTG Deck Editor")
        self.editor = DeckEditorWidget(project=project)
        self.setCentralWidget(self.editor)
        self.resize(1280, 760)


def run_editor(argv: list[str] | None = None) -> int:
    args = sys.argv if argv is None else argv
    app = QApplication.instance() or QApplication(args)
    window = DeckEditorWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run_editor())
