from __future__ import annotations

import json

from PyQt6.QtCore import QObject, QThread, QTimer, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mtg_core.admin_service import CardAdminService
from mtg_core.models import CardRecord, ImageAssetRecord, ImageManifestView, PrintRecord, SyncMetadata
from mtg_core.services import FIXED_CATALOG_QUERY


class BulkDownloadWorker(QObject):
    progress = pyqtSignal(object)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, admin_service: CardAdminService, query: str) -> None:
        super().__init__()
        self.admin_service = admin_service
        self.query = query
        self._pause_requested = False

    def request_pause(self) -> None:
        self._pause_requested = True

    @pyqtSlot()
    def run(self) -> None:
        try:
            while True:
                status = self.admin_service.process_bulk_download_chunk(
                    query=self.query,
                    should_pause=lambda: self._pause_requested
                )
                self.progress.emit(status)
                if status.status in {"completed", "failed", "paused"}:
                    self.finished.emit(status)
                    return
        except Exception as exc:  # pragma: no cover - defensive GUI guard
            self.failed.emit(str(exc))


class OracleTagSyncWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, admin_service: CardAdminService) -> None:
        super().__init__()
        self.admin_service = admin_service

    @pyqtSlot()
    def run(self) -> None:
        try:
            self.finished.emit(self.admin_service.sync_oracle_tags())
        except Exception as exc:  # pragma: no cover - defensive GUI guard
            self.failed.emit(str(exc))


class CardsTab(QWidget):
    HEADERS = ["Oracle ID", "Name", "Normalized", "Layout"]
    PAGE_SIZE = 100

    def __init__(self, admin_service: CardAdminService, status_fn) -> None:
        super().__init__()
        self.admin_service = admin_service
        self.status_fn = status_fn
        self._selected_oracle_id: str | None = None
        self._building_form = False
        self._page = 1
        self._total_pages = 1
        self._total_count = 0
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search cards")
        self.search_edit.textChanged.connect(self._reset_and_refresh)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._load_selected_row)

        self.oracle_id_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.normalized_name_edit = QLineEdit()
        self.layout_edit = QLineEdit()

        form = QFormLayout()
        form.addRow("Oracle ID", self.oracle_id_edit)
        form.addRow("Name", self.name_edit)
        form.addRow("Normalized", self.normalized_name_edit)
        form.addRow("Layout", self.layout_edit)

        new_button = QPushButton("New")
        save_button = QPushButton("Save")
        delete_button = QPushButton("Delete")
        refresh_button = QPushButton("Refresh")
        new_button.clicked.connect(self._new_card)
        save_button.clicked.connect(self._save_card)
        delete_button.clicked.connect(self._delete_card)
        refresh_button.clicked.connect(self.refresh_table)

        buttons = QHBoxLayout()
        buttons.addWidget(new_button)
        buttons.addWidget(save_button)
        buttons.addWidget(delete_button)
        buttons.addWidget(refresh_button)
        buttons.addStretch(1)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.addLayout(form)
        detail_layout.addLayout(buttons)
        self.prev_button = QPushButton("Prev")
        self.prev_button.clicked.connect(self._previous_page)
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self._next_page)
        self.page_label = QLabel()
        pagination = QHBoxLayout()
        pagination.addWidget(self.prev_button)
        pagination.addWidget(self.next_button)
        pagination.addWidget(self.page_label)
        pagination.addStretch(1)
        detail_layout.addLayout(pagination)

        splitter = QSplitter()
        splitter.addWidget(self.table)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        self._loaded = False
        layout = QVBoxLayout(self)
        layout.addWidget(self.search_edit)
        layout.addWidget(splitter)

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        self.refresh_table()

    def refresh_table(self) -> None:
        cards = self.admin_service.list_cards(
            self.search_edit.text(),
            page=self._page,
            page_size=self.PAGE_SIZE,
        )
        self._page = cards.page
        self._total_pages = cards.total_pages
        self._total_count = cards.total_count
        self.table.setRowCount(len(cards.items))
        for row_index, card in enumerate(cards.items):
            values = [card.oracle_id, card.name, card.normalized_name, card.layout or ""]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, card.oracle_id)
                self.table.setItem(row_index, column, item)
        self.table.resizeColumnsToContents()
        self.page_label.setText(
            f"Page {self._page} of {self._total_pages} • {self._total_count} cards"
        )
        self.prev_button.setEnabled(self._page > 1)
        self.next_button.setEnabled(self._page < self._total_pages)
        self.status_fn(f"Cards: {len(cards.items)} loaded")

    def _reset_and_refresh(self) -> None:
        self._page = 1
        self.refresh_table()

    def _previous_page(self) -> None:
        if self._page <= 1:
            return
        self._page -= 1
        self.refresh_table()

    def _next_page(self) -> None:
        if self._page >= self._total_pages:
            return
        self._page += 1
        self.refresh_table()

    def _load_selected_row(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        oracle_id = items[0].data(Qt.ItemDataRole.UserRole)
        card = self.admin_service.get_card(oracle_id)
        if card is None:
            return
        self._selected_oracle_id = card.oracle_id
        self._building_form = True
        self.oracle_id_edit.setText(card.oracle_id)
        self.oracle_id_edit.setReadOnly(True)
        self.name_edit.setText(card.name)
        self.normalized_name_edit.setText(card.normalized_name)
        self.layout_edit.setText(card.layout or "")
        self._building_form = False
        self.status_fn(f"Selected card: {card.name}")

    def _new_card(self) -> None:
        self._selected_oracle_id = None
        self._building_form = True
        self.oracle_id_edit.clear()
        self.oracle_id_edit.setReadOnly(False)
        self.name_edit.clear()
        self.normalized_name_edit.clear()
        self.layout_edit.clear()
        self._building_form = False
        self.status_fn("Creating new card")

    def _save_card(self) -> None:
        try:
            if self._selected_oracle_id:
                card = self.admin_service.update_card(
                    self._selected_oracle_id,
                    name=self.name_edit.text(),
                    normalized_name=self.normalized_name_edit.text(),
                    layout=self.layout_edit.text(),
                )
                self.status_fn(f"Updated card: {card.name}")
            else:
                card = self.admin_service.create_card(
                    oracle_id=self.oracle_id_edit.text(),
                    name=self.name_edit.text(),
                    normalized_name=self.normalized_name_edit.text(),
                    layout=self.layout_edit.text(),
                )
                self._selected_oracle_id = card.oracle_id
                self.oracle_id_edit.setText(card.oracle_id)
                self.oracle_id_edit.setReadOnly(True)
                self.status_fn(f"Created card: {card.name}")
        except Exception as exc:  # pragma: no cover - QWidget flow
            QMessageBox.critical(self, "Save Card", str(exc))
            return
        self.refresh_table()

    def _delete_card(self) -> None:
        oracle_id = self._selected_oracle_id or self.oracle_id_edit.text().strip()
        if not oracle_id:
            return
        if (
            QMessageBox.question(
                self,
                "Delete Card",
                f"Delete card '{oracle_id}' and its prints/manifests?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        deleted = self.admin_service.delete_card(oracle_id)
        if deleted:
            self._new_card()
            self.refresh_table()
            self.status_fn(f"Deleted card: {oracle_id}")


class PrintsTab(QWidget):
    HEADERS = ["Card ID", "Name", "Set", "Collector #", "Oracle ID", "Released"]
    PAGE_SIZE = 100

    def __init__(self, admin_service: CardAdminService, status_fn) -> None:
        super().__init__()
        self.admin_service = admin_service
        self.status_fn = status_fn
        self._selected_card_id: str | None = None
        self._page = 1
        self._total_pages = 1
        self._total_count = 0

        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText('Local query: t:creature o:"draw a card" mv<=3')
        self.syntax_checkbox = QCheckBox('Scryfall syntax')
        self.syntax_checkbox.setChecked(True)
        self.syntax_checkbox.setToolTip('Search locally stored rules text, Oracle tags, and card properties. Regex is not supported.')
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._reset_and_refresh)
        self.syntax_checkbox.toggled.connect(self._reset_and_refresh)
        self.set_code_edit = QLineEdit()
        self.set_code_edit.setPlaceholderText("Set code")
        self.oracle_filter_edit = QLineEdit()
        self.oracle_filter_edit.setPlaceholderText("Oracle ID")
        self.query_edit.textChanged.connect(self._schedule_refresh)
        self.set_code_edit.textChanged.connect(self._reset_and_refresh)
        self.oracle_filter_edit.textChanged.connect(self._reset_and_refresh)

        filter_row = QHBoxLayout()
        filter_row.addWidget(self.query_edit)
        filter_row.addWidget(self.syntax_checkbox)
        filter_row.addWidget(self.set_code_edit)
        filter_row.addWidget(self.oracle_filter_edit)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._load_selected_row)

        self.card_id_edit = QLineEdit()
        self.oracle_id_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.set_code_field = QLineEdit()
        self.set_name_edit = QLineEdit()
        self.collector_edit = QLineEdit()
        self.released_edit = QLineEdit()
        self.image_url_edit = QLineEdit()
        self.thumbnail_url_edit = QLineEdit()
        self.preview_url_edit = QLineEdit()
        self.double_faced_checkbox = QCheckBox("Double faced")
        self.payload_edit = QPlainTextEdit()
        self.payload_edit.setReadOnly(True)
        self.rules_edit = QPlainTextEdit()
        self.rules_edit.setReadOnly(True)

        form = QFormLayout()
        form.addRow("Card ID", self.card_id_edit)
        form.addRow("Oracle ID", self.oracle_id_edit)
        form.addRow("Name", self.name_edit)
        form.addRow("Set Code", self.set_code_field)
        form.addRow("Set Name", self.set_name_edit)
        form.addRow("Collector #", self.collector_edit)
        form.addRow("Released", self.released_edit)
        form.addRow("Image URL", self.image_url_edit)
        form.addRow("Thumbnail URL", self.thumbnail_url_edit)
        form.addRow("Preview URL", self.preview_url_edit)
        form.addRow("", self.double_faced_checkbox)
        form.addRow("Payload JSON", self.payload_edit)
        form.addRow("Card text (all faces)", self.rules_edit)

        new_button = QPushButton("New")
        save_button = QPushButton("Save")
        delete_button = QPushButton("Delete")
        refresh_button = QPushButton("Refresh")
        new_button.clicked.connect(self._new_print)
        save_button.clicked.connect(self._save_print)
        delete_button.clicked.connect(self._delete_print)
        refresh_button.clicked.connect(self.refresh_table)

        buttons = QHBoxLayout()
        buttons.addWidget(new_button)
        buttons.addWidget(save_button)
        buttons.addWidget(delete_button)
        buttons.addWidget(refresh_button)
        buttons.addStretch(1)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.addLayout(form)
        detail_layout.addLayout(buttons)
        self.prev_button = QPushButton("Prev")
        self.prev_button.clicked.connect(self._previous_page)
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self._next_page)
        self.page_label = QLabel()
        pagination = QHBoxLayout()
        pagination.addWidget(self.prev_button)
        pagination.addWidget(self.next_button)
        pagination.addWidget(self.page_label)
        pagination.addStretch(1)
        detail_layout.addLayout(pagination)

        splitter = QSplitter()
        splitter.addWidget(self.table)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        self._loaded = False
        layout = QVBoxLayout(self)
        layout.addLayout(filter_row)
        layout.addWidget(splitter)

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        self.refresh_table()

    def refresh_table(self) -> None:
        try:
            prints = self.admin_service.list_prints(
                query=self.query_edit.text(),
                set_code=self.set_code_edit.text(),
                oracle_id=self.oracle_filter_edit.text(),
                page=self._page,
                page_size=self.PAGE_SIZE,
                syntax=self.syntax_checkbox.isChecked(),
            )
        except ValueError as exc:
            self.table.setRowCount(0)
            self.page_label.setText(str(exc))
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)
            self.status_fn(str(exc))
            return
        self._page = prints.page
        self._total_pages = prints.total_pages
        self._total_count = prints.total_count
        self.table.setRowCount(len(prints.items))
        for row_index, print_record in enumerate(prints.items):
            values = [
                print_record.card_id,
                print_record.name,
                print_record.set_code or "",
                print_record.collector_number or "",
                print_record.oracle_id,
                print_record.released_at or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, print_record.card_id)
                self.table.setItem(row_index, column, item)
        self.table.resizeColumnsToContents()
        self.page_label.setText(
            f"Page {self._page} of {self._total_pages} • {self._total_count} prints"
        )
        self.prev_button.setEnabled(self._page > 1)
        self.next_button.setEnabled(self._page < self._total_pages)
        self.status_fn(f"Prints: {len(prints.items)} loaded")

    def _reset_and_refresh(self) -> None:
        self._page = 1
        self.refresh_table()

    def _schedule_refresh(self) -> None:
        self._search_timer.start()

    def _previous_page(self) -> None:
        if self._page <= 1:
            return
        self._page -= 1
        self.refresh_table()

    def _next_page(self) -> None:
        if self._page >= self._total_pages:
            return
        self._page += 1
        self.refresh_table()

    def _load_selected_row(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        card_id = items[0].data(Qt.ItemDataRole.UserRole)
        print_record = self.admin_service.get_print(card_id)
        if print_record is None:
            return
        self._selected_card_id = print_record.card_id
        self.card_id_edit.setText(print_record.card_id)
        self.card_id_edit.setReadOnly(True)
        self.oracle_id_edit.setText(print_record.oracle_id)
        self.name_edit.setText(print_record.name)
        self.set_code_field.setText(print_record.set_code or "")
        self.set_name_edit.setText(print_record.set_name or "")
        self.collector_edit.setText(print_record.collector_number or "")
        self.released_edit.setText(print_record.released_at or "")
        self.image_url_edit.setText(print_record.image_url or "")
        self.thumbnail_url_edit.setText(print_record.thumbnail_url or "")
        self.preview_url_edit.setText(print_record.preview_url or "")
        self.double_faced_checkbox.setChecked(print_record.is_double_faced)
        self.payload_edit.setPlainText(json.dumps(print_record.payload, indent=2, sort_keys=True))
        from mtg_core.search import card_rules_text
        self.rules_edit.setPlainText(card_rules_text(print_record.payload))
        self.status_fn(f"Selected print: {print_record.name} ({print_record.card_id})")

    def _new_print(self) -> None:
        self._selected_card_id = None
        self.card_id_edit.clear()
        self.card_id_edit.setReadOnly(False)
        self.oracle_id_edit.clear()
        self.name_edit.clear()
        self.set_code_field.clear()
        self.set_name_edit.clear()
        self.collector_edit.clear()
        self.released_edit.clear()
        self.image_url_edit.clear()
        self.thumbnail_url_edit.clear()
        self.preview_url_edit.clear()
        self.double_faced_checkbox.setChecked(False)
        self.payload_edit.clear()
        self.rules_edit.clear()
        self.status_fn("Creating new print")

    def _save_print(self) -> None:
        fields = dict(
            oracle_id=self.oracle_id_edit.text(),
            name=self.name_edit.text(),
            set_code=self.set_code_field.text(),
            set_name=self.set_name_edit.text(),
            collector_number=self.collector_edit.text(),
            released_at=self.released_edit.text(),
            image_url=self.image_url_edit.text(),
            thumbnail_url=self.thumbnail_url_edit.text(),
            preview_url=self.preview_url_edit.text(),
            is_double_faced=self.double_faced_checkbox.isChecked(),
        )
        try:
            if self._selected_card_id:
                print_record = self.admin_service.update_print(self._selected_card_id, **fields)
                self.status_fn(f"Updated print: {print_record.card_id}")
            else:
                print_record = self.admin_service.create_print(
                    card_id=self.card_id_edit.text(),
                    **fields,
                )
                self._selected_card_id = print_record.card_id
                self.card_id_edit.setText(print_record.card_id)
                self.card_id_edit.setReadOnly(True)
                self.status_fn(f"Created print: {print_record.card_id}")
            self.payload_edit.setPlainText(json.dumps(print_record.payload, indent=2, sort_keys=True))
        except Exception as exc:  # pragma: no cover - QWidget flow
            QMessageBox.critical(self, "Save Print", str(exc))
            return
        self.refresh_table()

    def _delete_print(self) -> None:
        card_id = self._selected_card_id or self.card_id_edit.text().strip()
        if not card_id:
            return
        if (
            QMessageBox.question(
                self,
                "Delete Print",
                f"Delete print '{card_id}' and related image-manifest rows?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        deleted = self.admin_service.delete_print(card_id)
        if deleted:
            self._new_print()
            self.refresh_table()
            self.status_fn(f"Deleted print: {card_id}")


class ImagesTab(QWidget):
    MANIFEST_HEADERS = ["Card", "Variant", "Asset", "Status", "Source", "Checksum"]
    ASSET_HEADERS = ["Asset", "Mime", "Source", "Checksum", "Bytes", "Updated"]
    PAGE_SIZE = 100

    def __init__(self, admin_service: CardAdminService, status_fn) -> None:
        super().__init__()
        self.admin_service = admin_service
        self.status_fn = status_fn
        self._asset_records: dict[str, ImageAssetRecord] = {}
        self._manifest_page = 1
        self._manifest_total_pages = 1
        self._manifest_total_count = 0
        self._asset_page = 1
        self._asset_total_pages = 1
        self._asset_total_count = 0

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_views)

        self.manifest_table = QTableWidget(0, len(self.MANIFEST_HEADERS))
        self.manifest_table.setHorizontalHeaderLabels(self.MANIFEST_HEADERS)
        self.manifest_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.assets_table = QTableWidget(0, len(self.ASSET_HEADERS))
        self.assets_table.setHorizontalHeaderLabels(self.ASSET_HEADERS)
        self.assets_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.assets_table.itemSelectionChanged.connect(self._refresh_asset_preview)

        self.manifest_prev_button = QPushButton("Prev Manifests")
        self.manifest_prev_button.clicked.connect(self._previous_manifest_page)
        self.manifest_next_button = QPushButton("Next Manifests")
        self.manifest_next_button.clicked.connect(self._next_manifest_page)
        self.manifest_page_label = QLabel()
        self.asset_prev_button = QPushButton("Prev Assets")
        self.asset_prev_button.clicked.connect(self._previous_asset_page)
        self.asset_next_button = QPushButton("Next Assets")
        self.asset_next_button.clicked.connect(self._next_asset_page)
        self.asset_page_label = QLabel()

        self.asset_meta = QPlainTextEdit()
        self.asset_meta.setReadOnly(True)
        self.asset_preview = QLabel("Select an asset to preview")
        self.asset_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.asset_preview.setMinimumHeight(220)

        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.addWidget(self.asset_preview)
        preview_layout.addWidget(self.asset_meta)

        manifest_controls = QWidget()
        manifest_controls_layout = QHBoxLayout(manifest_controls)
        manifest_controls_layout.addWidget(self.manifest_prev_button)
        manifest_controls_layout.addWidget(self.manifest_next_button)
        manifest_controls_layout.addWidget(self.manifest_page_label)
        manifest_controls_layout.addStretch(1)

        asset_controls = QWidget()
        asset_controls_layout = QHBoxLayout(asset_controls)
        asset_controls_layout.addWidget(self.asset_prev_button)
        asset_controls_layout.addWidget(self.asset_next_button)
        asset_controls_layout.addWidget(self.asset_page_label)
        asset_controls_layout.addStretch(1)

        tables = QSplitter(Qt.Orientation.Vertical)
        manifest_panel = QWidget()
        manifest_panel_layout = QVBoxLayout(manifest_panel)
        manifest_panel_layout.addWidget(manifest_controls)
        manifest_panel_layout.addWidget(self.manifest_table)
        assets_panel = QWidget()
        assets_panel_layout = QVBoxLayout(assets_panel)
        assets_panel_layout.addWidget(asset_controls)
        assets_panel_layout.addWidget(self.assets_table)
        tables.addWidget(manifest_panel)
        tables.addWidget(assets_panel)
        tables.setStretchFactor(0, 1)
        tables.setStretchFactor(1, 1)

        body = QSplitter()
        body.addWidget(tables)
        body.addWidget(preview_panel)
        body.setStretchFactor(0, 2)
        body.setStretchFactor(1, 1)

        self._loaded = False
        layout = QVBoxLayout(self)
        layout.addWidget(self.refresh_button)
        layout.addWidget(body)
        
    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        self.refresh_views()

    def refresh_views(self) -> None:
        manifests = self.admin_service.list_image_manifest(
            page=self._manifest_page,
            page_size=self.PAGE_SIZE,
        )
        assets = self.admin_service.list_image_assets(
            page=self._asset_page,
            page_size=self.PAGE_SIZE,
        )
        self._manifest_page = manifests.page
        self._manifest_total_pages = manifests.total_pages
        self._manifest_total_count = manifests.total_count
        self._asset_page = assets.page
        self._asset_total_pages = assets.total_pages
        self._asset_total_count = assets.total_count
        self._asset_records = {asset.asset_id: asset for asset in assets.items}

        self.manifest_table.setRowCount(len(manifests.items))
        for row_index, manifest in enumerate(manifests.items):
            values = [
                manifest.card_name or manifest.card_id,
                manifest.variant,
                manifest.asset_id or "",
                manifest.status,
                manifest.source or "",
                manifest.checksum or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                self.manifest_table.setItem(row_index, column, item)

        self.assets_table.setRowCount(len(assets.items))
        for row_index, asset in enumerate(assets.items):
            values = [
                asset.asset_id,
                asset.mime_type or "",
                asset.source or "",
                asset.checksum,
                str(asset.payload_size or 0),
                str(asset.updated_at or ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, asset.asset_id)
                self.assets_table.setItem(row_index, column, item)
        self.manifest_table.resizeColumnsToContents()
        self.assets_table.resizeColumnsToContents()
        self.manifest_page_label.setText(
            f"Page {self._manifest_page} of {self._manifest_total_pages} • {self._manifest_total_count} manifests"
        )
        self.asset_page_label.setText(
            f"Page {self._asset_page} of {self._asset_total_pages} • {self._asset_total_count} assets"
        )
        self.manifest_prev_button.setEnabled(self._manifest_page > 1)
        self.manifest_next_button.setEnabled(self._manifest_page < self._manifest_total_pages)
        self.asset_prev_button.setEnabled(self._asset_page > 1)
        self.asset_next_button.setEnabled(self._asset_page < self._asset_total_pages)
        self.status_fn(f"Images: {len(manifests.items)} manifests, {len(assets.items)} assets")

    def _previous_manifest_page(self) -> None:
        if self._manifest_page <= 1:
            return
        self._manifest_page -= 1
        self.refresh_views()

    def _next_manifest_page(self) -> None:
        if self._manifest_page >= self._manifest_total_pages:
            return
        self._manifest_page += 1
        self.refresh_views()

    def _previous_asset_page(self) -> None:
        if self._asset_page <= 1:
            return
        self._asset_page -= 1
        self.refresh_views()

    def _next_asset_page(self) -> None:
        if self._asset_page >= self._asset_total_pages:
            return
        self._asset_page += 1
        self.refresh_views()

    def _refresh_asset_preview(self) -> None:
        items = self.assets_table.selectedItems()
        if not items:
            return
        asset_id = items[0].data(Qt.ItemDataRole.UserRole)
        asset = self.admin_service.get_image_asset(asset_id)
        if asset is None:
            return
        pixmap = QPixmap()
        pixmap.loadFromData(asset.payload)
        if not pixmap.isNull():
            scaled = pixmap.scaled(
                280,
                280,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.asset_preview.setText("")
            self.asset_preview.setPixmap(scaled)
        else:
            self.asset_preview.clear()
            self.asset_preview.setText("Preview unavailable for this asset")
        self.asset_meta.setPlainText(
            json.dumps(
                {
                    "asset_id": asset.asset_id,
                    "checksum": asset.checksum,
                    "extension": asset.extension,
                    "mime_type": asset.mime_type,
                    "source": asset.source,
                    "source_url": asset.source_url,
                    "payload_bytes": asset.payload_size or len(asset.payload),
                    "created_at": asset.created_at,
                    "updated_at": asset.updated_at,
                },
                indent=2,
                sort_keys=True,
            )
        )
        self.status_fn(f"Selected asset: {asset.asset_id}")


class SyncTab(QWidget):
    close_ready = pyqtSignal()
    HEADERS = ["Source", "Version", "Last Sync"]

    def __init__(self, admin_service: CardAdminService, status_fn) -> None:
        super().__init__()
        self.admin_service = admin_service
        self.status_fn = status_fn
        self._thread: QThread | None = None
        self._worker: BulkDownloadWorker | None = None
        self._tag_thread: QThread | None = None
        self._tag_worker: OracleTagSyncWorker | None = None
        self._close_requested = False
        self._loaded = False
        self._query_initialized = False
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(1000)
        self._status_timer.timeout.connect(self._refresh_download_status)
        self.query_edit = QLineEdit(FIXED_CATALOG_QUERY)
        self.query_edit.setPlaceholderText("Scryfall search query")
        self.query_edit.textChanged.connect(lambda _text: self._refresh_download_status())
        self.job_status_label = QLabel()
        self.chunk_status_label = QLabel()
        self.counts_label = QLabel()
        self.next_page_label = QLabel()
        self.last_error_label = QLabel()
        self.updated_label = QLabel()
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self._start_download_job)
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self._pause_download_job)
        self.resume_button = QPushButton("Resume")
        self.resume_button.clicked.connect(self._resume_download_job)
        self.refresh_status_button = QPushButton("Refresh Status")
        self.refresh_status_button.clicked.connect(self._refresh_download_status)
        self.oracle_tags_button = QPushButton("Update Oracle Tags")
        self.oracle_tags_button.clicked.connect(self._start_oracle_tag_sync)
        self.oracle_tags_label = QLabel("Not updated this session")

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._load_payload)
        self.payload_edit = QPlainTextEdit()
        self.payload_edit.setReadOnly(True)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_view)

        controls = QWidget()
        controls_layout = QGridLayout(controls)
        controls_layout.addWidget(QLabel("Scryfall Query"), 0, 0)
        controls_layout.addWidget(self.query_edit, 0, 1, 1, 3)
        controls_layout.addWidget(QLabel("Job Status"), 1, 0)
        controls_layout.addWidget(self.job_status_label, 1, 1)
        controls_layout.addWidget(QLabel("Chunk"), 1, 2)
        controls_layout.addWidget(self.chunk_status_label, 1, 3)
        controls_layout.addWidget(QLabel("Counts"), 2, 0)
        controls_layout.addWidget(self.counts_label, 2, 1, 1, 3)
        controls_layout.addWidget(QLabel("Next Page"), 3, 0)
        controls_layout.addWidget(self.next_page_label, 3, 1, 1, 3)
        controls_layout.addWidget(QLabel("Last Error"), 4, 0)
        controls_layout.addWidget(self.last_error_label, 4, 1, 1, 3)
        controls_layout.addWidget(QLabel("Updated"), 5, 0)
        controls_layout.addWidget(self.updated_label, 5, 1, 1, 3)
        controls_layout.addWidget(self.start_button, 6, 0)
        controls_layout.addWidget(self.pause_button, 6, 1)
        controls_layout.addWidget(self.resume_button, 6, 2)
        controls_layout.addWidget(self.refresh_status_button, 6, 3)
        controls_layout.addWidget(refresh_button, 7, 0)
        controls_layout.addWidget(self.oracle_tags_button, 8, 0)
        controls_layout.addWidget(self.oracle_tags_label, 8, 1, 1, 3)
        controls_layout.setColumnStretch(1, 1)

        splitter = QSplitter()
        splitter.addWidget(self.table)
        splitter.addWidget(self.payload_edit)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(controls)
        layout.addWidget(splitter)

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        self._refresh_download_status()
        self.refresh_view()

    def refresh_view(self) -> None:
        rows = self.admin_service.list_sync_state()
        self.table.setRowCount(len(rows))
        for row_index, sync_row in enumerate(rows):
            values = [sync_row.source, sync_row.version or "", str(sync_row.last_sync_at or "")]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, sync_row.payload or {})
                self.table.setItem(row_index, column, item)
        self.table.resizeColumnsToContents()
        self.status_fn(f"Sync rows: {len(rows)} loaded")
        self._refresh_download_status()

    def _load_payload(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        payload = items[0].data(Qt.ItemDataRole.UserRole)
        self.payload_edit.setPlainText(json.dumps(payload, indent=2, sort_keys=True))

    def _refresh_download_status(self) -> None:
        status = self.admin_service.get_bulk_download_status()
        self._apply_download_status(status)

    def _apply_download_status(self, status) -> None:
        display_status = self._display_status(status)
        if not self._query_initialized:
            self._query_initialized = True
            self.query_edit.setText(status.query)
        self.job_status_label.setText(display_status)
        self.chunk_status_label.setText(str(status.chunk_number))
        self.counts_label.setText(
            f"scanned={status.total_scanned}  downloaded={status.total_downloaded}  "
            f"skipped={status.total_skipped}  failed={status.total_failed}"
        )
        self.next_page_label.setText(status.current_page_url or "Completed / none pending")
        self.last_error_label.setText(status.last_error or "None")
        self.updated_label.setText("" if status.last_sync_at is None else str(status.last_sync_at))
        self._sync_buttons(status)

    def _query_text(self) -> str:
        return self.query_edit.text().strip()

    def _display_status(self, status) -> str:
        if not self.is_download_running() and status.status == "running":
            return "paused"
        return status.status

    def _sync_buttons(self, status) -> None:
        running = self.is_download_running()
        stale_running = (not running) and status.status == "running"
        query_changed = self._query_text() != status.query
        self.start_button.setEnabled(
            not running and (query_changed or status.status in {"idle", "completed", "failed"})
        )
        self.pause_button.setEnabled(running)
        self.resume_button.setEnabled(not running and not query_changed and (status.can_resume or stale_running))
        if running:
            if not self._status_timer.isActive():
                self._status_timer.start()
        elif self._status_timer.isActive():
            self._status_timer.stop()

    def is_download_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def request_pause_for_close(self) -> bool:
        if self._tag_thread is not None and self._tag_thread.isRunning():
            self._close_requested = True
            return False
        if not self.is_download_running():
            status = self.admin_service.get_bulk_download_status()
            if status.status == "running" and not status.completed:
                self.admin_service.pause_bulk_download(query=status.query)
            return True
        self._close_requested = True
        self._pause_download_job()
        return False

    def _start_download_job(self) -> None:
        if self.is_download_running():
            return
        query = self._query_text()
        if not query:
            QMessageBox.warning(self, "Scryfall Query Required", "Enter a Scryfall search query before starting sync.")
            return
        self._close_requested = False
        try:
            status = self.admin_service.reset_bulk_download_status(query=query)
        except ValueError as exc:
            QMessageBox.warning(self, "Scryfall Query Required", str(exc))
            return
        self._apply_download_status(status)
        self._launch_worker(query)

    def _resume_download_job(self) -> None:
        if self.is_download_running():
            return
        status = self.admin_service.get_bulk_download_status()
        query = status.query.strip()
        if not query:
            QMessageBox.warning(self, "Scryfall Query Required", "Enter a Scryfall search query before resuming sync.")
            return
        self.query_edit.setText(query)
        self._close_requested = False
        self._launch_worker(query)

    def _pause_download_job(self) -> None:
        if self._worker is None:
            status = self.admin_service.get_bulk_download_status()
            if status.status == "running" and not status.completed:
                status = self.admin_service.pause_bulk_download(query=status.query)
            self._apply_download_status(status)
            return
        self._worker.request_pause()
        self.pause_button.setEnabled(False)
        self.status_fn("Pausing after current chunk...")

    def _launch_worker(self, query: str) -> None:
        self._thread = QThread(self)
        self._worker = BulkDownloadWorker(self.admin_service, query)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.failed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()
        self._apply_download_status(self.admin_service.get_bulk_download_status())
        self.status_fn("Sync download started")

    def _start_oracle_tag_sync(self) -> None:
        if self._tag_thread is not None and self._tag_thread.isRunning():
            return
        self.oracle_tags_button.setEnabled(False)
        self.oracle_tags_label.setText('Downloading Oracle Tags…')
        self._tag_thread = QThread(self)
        self._tag_worker = OracleTagSyncWorker(self.admin_service)
        self._tag_worker.moveToThread(self._tag_thread)
        self._tag_thread.started.connect(self._tag_worker.run)
        self._tag_worker.finished.connect(self._on_oracle_tags_finished)
        self._tag_worker.failed.connect(self._on_oracle_tags_failed)
        self._tag_worker.finished.connect(self._tag_thread.quit)
        self._tag_worker.failed.connect(self._tag_thread.quit)
        self._tag_worker.finished.connect(self._tag_worker.deleteLater)
        self._tag_worker.failed.connect(self._tag_worker.deleteLater)
        self._tag_thread.finished.connect(self._tag_thread.deleteLater)
        self._tag_thread.start()

    def _on_oracle_tags_finished(self, result) -> None:
        self.oracle_tags_label.setText(
            f"{result['tags']} tags • {result['taggings']} card assignments")
        self.oracle_tags_button.setEnabled(True)
        self._tag_worker = None
        self._tag_thread = None
        self.refresh_view()
        self.status_fn('Oracle Tags updated')
        if self._close_requested:
            self._close_requested = False
            self.close_ready.emit()

    def _on_oracle_tags_failed(self, message: str) -> None:
        self.oracle_tags_label.setText(f'Update failed: {message}')
        self.oracle_tags_button.setEnabled(True)
        self._tag_worker = None
        self._tag_thread = None
        self.status_fn('Oracle Tags update failed')
        if self._close_requested:
            self._close_requested = False
            self.close_ready.emit()

    def _on_worker_progress(self, status) -> None:
        self._apply_download_status(status)
        self.status_fn(f"Sync download: {status.status} after chunk {status.chunk_number}")

    def _on_worker_finished(self, status) -> None:
        self._apply_download_status(status)
        self.status_fn(f"Sync download finished with status: {status.status}")
        self._worker = None
        self._thread = None
        self._refresh_download_status()
        if self._close_requested:
            self._close_requested = False
            self.close_ready.emit()

    def _on_worker_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Sync Download", message)
        self.status_fn("Sync download failed")
        self._worker = None
        self._thread = None
        self._refresh_download_status()


class CoreAdminMainWindow(QMainWindow):
    def __init__(self, admin_service: CardAdminService | None = None) -> None:
        super().__init__()
        self.admin_service = admin_service or CardAdminService()
        self.setWindowTitle("MTG Core Database Admin")
        self.resize(1360, 820)

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self._db_label = QLabel(f"DB: {self.admin_service.database.db_path}")
        status_bar.addPermanentWidget(self._db_label)

        tabs = QTabWidget()
        self.cards_tab = CardsTab(self.admin_service, self._set_status)
        self.prints_tab = PrintsTab(self.admin_service, self._set_status)
        self.images_tab = ImagesTab(self.admin_service, self._set_status)
        self.sync_tab = SyncTab(self.admin_service, self._set_status)
        self._allow_close_after_pause = False
        self.sync_tab.close_ready.connect(self._close_after_pause)
        tabs.addTab(self.cards_tab, "Cards")
        tabs.addTab(self.prints_tab, "Prints")
        tabs.addTab(self.images_tab, "Images")
        tabs.addTab(self.sync_tab, "Sync")
        tabs.currentChanged.connect(self._load_current_tab)
        self.setCentralWidget(tabs)
        self._set_status("Ready")
        self._load_current_tab(tabs.currentIndex())

    def _set_status(self, message: str) -> None:
        self.statusBar().showMessage(message, 6000)

    def _load_current_tab(self, _index: int) -> None:
        current = self.centralWidget().currentWidget()
        if hasattr(current, "ensure_loaded"):
            current.ensure_loaded()

    def _close_after_pause(self) -> None:
        self._allow_close_after_pause = True
        self._set_status("Sync download paused; closing app")
        QTimer.singleShot(0, self.close)

    def closeEvent(self, event) -> None:  # pragma: no cover - GUI interaction
        if self._allow_close_after_pause:
            event.accept()
            return
        if self.sync_tab.request_pause_for_close():
            event.accept()
            return
        self._set_status("Finishing current chunk before closing...")
        event.ignore()
