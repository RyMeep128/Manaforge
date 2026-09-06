import os
import re
import math
import json
import datetime
import functools
import subprocess

import PyQt6.QtCore as QtCore
from PyQt6.QtGui import QPixmap, QIntValidator, QPainter, QPainterPath, QCursor, QTransform, QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QLineEdit,
    QGridLayout,
    QVBoxLayout,
    QHBoxLayout,
    QStackedLayout,
    QStackedWidget,
    QScrollArea,
    QStyle,
    QCommonStyle,
    QSizePolicy,
    QGroupBox,
    QCheckBox,
    QTabWidget,
    QSplitter,
    QMessageBox,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QFileDialog,
    QToolTip,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QMenu,
    QToolButton,
    QInputDialog,
)

import pdf
import image
import project_library
import runtime_images
import fallback_image as fallback
import ui_theme
from config import CFG
from constants import (
    cwd,
    card_ratio,
    card_size_without_bleed_inch,
    low_dpi_warning_threshold,
    page_sizes,
)
from models import ProjectState, as_project_state
from util import inch_to_mm, mm_to_inch, open_folder, point_to_inch
from background_tasks import make_popup_print_fn, popup
from dialogs import (
    AddCardDialog,
    ComboBoxWithLabel,
    DeckImportDialog,
    FileDialogType,
    HighResPickerDialog,
    LineEditWithLabel,
    SettingsDialog,
    WidgetWithLabel,
    delete_project_with_confirmation,
    folder_dialog,
    image_file_dialog,
    project_file_dialog,
)
from services import deck_import_service, pdf_service, project_service, layout_service
from preview_interaction import PreviewOverlay, DragPageButton


def confirm_underfilled_export(parent, occupancy):
    underfilled = [page for page in occupancy if page['filled'] < page['capacity']]
    if not underfilled:
        return True
    dialog = QMessageBox(parent)
    dialog.setIcon(QMessageBox.Icon.Warning)
    dialog.setWindowTitle("Under-filled sheets")
    dialog.setText("Some sheets have unused card slots.")
    lines = [layout_service.occupancy_label(page) for page in underfilled]
    summary = "\n".join(lines[:8])
    if len(lines) > 8:
        summary += f"\n…and {len(lines) - 8} more sheets."
        dialog.setDetailedText("\n".join(lines))
    dialog.setInformativeText(
        summary + "\n\nFilled counts are slots; oversized cards use two. "
        "Backs are paired with their fronts. You can go back to fill the sheets "
        "or export this layout to print anyway.")
    go_back = dialog.addButton("Go Back", QMessageBox.ButtonRole.RejectRole)
    print_anyway = dialog.addButton("Print Anyway", QMessageBox.ButtonRole.AcceptRole)
    dialog.setDefaultButton(go_back)
    dialog.setEscapeButton(go_back)
    dialog.exec()
    return dialog.clickedButton() is print_anyway


def failed_cards_decklist_text(failed_cards):
    """Return failed imports in a format accepted by the decklist importer."""
    return "\n".join(f"1 {card}" for card in failed_cards)


def show_card_import_complete(parent, import_result):
    summary_lines = [
        f"Imported {len(import_result.imported)} unique cards "
        f"({import_result.imported_count} total copies)."
    ]
    if import_result.failed_cards:
        failed_count = len(import_result.failed_cards)
        summary_lines.append(f"Failed to import {failed_count} card(s).")
    if import_result.unmatched_lines:
        summary_lines.append(
            "Unmatched lines: " + ", ".join(import_result.unmatched_lines[:8])
        )

    message_box = QMessageBox(parent)
    message_box.setIcon(QMessageBox.Icon.Information)
    message_box.setWindowTitle("Card Import Complete")
    message_box.setText("\n\n".join(summary_lines))
    message_box.setInformativeText(
        "Next step: click 'Prepare Images' if needed, then check the Preview tab."
    )
    message_box.setStandardButtons(QMessageBox.StandardButton.Ok)

    copy_button = None
    if import_result.failed_cards:
        failed_text = failed_cards_decklist_text(import_result.failed_cards)
        message_box.setDetailedText(failed_text)
        copy_button = message_box.addButton(
            "Copy Failed Cards", QMessageBox.ButtonRole.ActionRole
        )

    message_box.exec()
    if copy_button is not None and message_box.clickedButton() is copy_button:
        QApplication.clipboard().setText(failed_text)


def project_thumbnail_pixmap(image_path, width=120, height=160):
    pixmap = QPixmap()
    if image_path and os.path.exists(image_path):
        pixmap.load(image_path)
    if pixmap.isNull():
        pixmap.loadFromData(fallback.data)
    return pixmap.scaled(
        width,
        height,
        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        QtCore.Qt.TransformationMode.SmoothTransformation,
    )


def cached_preview_bytes(entry, field="data"):
    if not isinstance(entry, dict):
        raise TypeError("cached preview entry must be a dictionary")
    return image.decode_cached_image_bytes(entry[field])


def autosave_managed_session():
    application = QApplication.instance()
    if application is not None and hasattr(application, "autosave_managed_session"):
        application.autosave_managed_session()


def _card_sort_label(state, card_name):
    metadata = state.get_card_metadata(card_name) or {}
    display_name = metadata.get("name")
    return display_name if display_name else card_name


class EditorPage(QWidget):
    def __init__(self, tabs, scroll_area, options_container, options, print_preview):
        super().__init__()

        actions = options._actions_widget
        back_button = actions._home_button
        back_button.setText("< Projects")
        save_button = actions._save_button
        save_button.setText("Save")
        add_button = QToolButton()
        add_button.setText("+ Add Cards")
        add_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        add_button.setProperty("buttonRole", "primary")
        add_menu = QMenu(add_button)
        add_menu.addAction("Import decklist or public link…", actions._import_button.click)
        add_menu.addAction("Add an individual card…", actions._add_card_button.click)
        add_menu.addAction("Use a local image folder…", actions._set_images_button.click)
        add_button.setMenu(add_menu)

        prepare_button = actions._cropper_button
        prepare_button.setText("Prepare Images")
        export_button = actions._render_button
        export_button.setText("Export PDF")
        export_button.setProperty("buttonRole", "primary")
        settings_button = QPushButton("Print Settings")
        settings_button.setCheckable(True)
        more_button = QToolButton()
        more_button.setText("More")
        more_button.setToolTip("More project actions")
        more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more_menu = QMenu(more_button)
        prepare_action = more_menu.addAction("Prepare images…", prepare_button.click)
        more_menu.addSeparator()
        more_menu.addAction("Open image folder", actions._open_images_button.click)
        more_menu.addAction("Import saved project…", actions._load_button.click)
        more_menu.addAction("Application settings…", actions._settings_button.click)
        more_menu.addSeparator()
        clean_action = more_menu.addAction("Clean image cache…", actions._clear_cards_button.click)
        more_button.setMenu(more_menu)

        project_label = QLabel("Project workspace")
        project_label.setProperty("role", "subtitle")
        project_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        project_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        readiness_label = QLabel()
        readiness_label.setProperty("role", "muted")

        header = QFrame()
        header.setProperty("role", "toolbar")
        header.setFixedHeight(54)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 9, 14, 9)
        header_layout.setSpacing(8)
        header_layout.addWidget(back_button)
        header_layout.addWidget(project_label, 1)
        header_layout.addWidget(readiness_label)
        header_layout.addWidget(save_button)
        header_layout.addSpacing(8)
        header_layout.addWidget(add_button)
        header_layout.addWidget(export_button)
        header_layout.addWidget(settings_button)
        header_layout.addWidget(more_button)

        splitter = QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(tabs)
        splitter.addWidget(options_container)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)

        sidebar_width = max(
            options.sizeHint().width(),
            options.minimumSizeHint().width(),
            320,
        )
        options_container.setMinimumWidth(min(sidebar_width, 420))
        options_container.setMaximumWidth(420)
        splitter.setSizes([max(sidebar_width * 2, 900), sidebar_width])
        options_container.hide()
        settings_button.toggled.connect(options_container.setVisible)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(splitter)
        self.setLayout(layout)

        self._tabs = tabs
        self._scroll_area = scroll_area
        self._options = options
        self._print_preview = print_preview
        self._project_label = project_label
        self._settings_button = settings_button
        self._readiness_label = readiness_label
        self._prepare_button = prepare_button
        self._prepare_action = prepare_action
        self._export_button = export_button
        self._shortcuts = [
            QShortcut(QKeySequence.StandardKey.Save, self),
            QShortcut(QKeySequence(QtCore.Qt.Key.Key_Escape), self),
        ]
        self._shortcuts[0].activated.connect(save_button.click)
        self._shortcuts[1].activated.connect(lambda: settings_button.setChecked(False))
        self._update_readiness(tabs._state)

    def set_project_name(self, name):
        self._project_label.setText(name or "Untitled Project")
        self._project_label.setToolTip(name or "Untitled Project")

    def _update_readiness(self, state):
        card_names = [name for name in state.cards if not name.startswith("__")]
        prints = sum(max(0, state.cards.get(name, 0)) for name in card_names)
        missing = [name for name in card_names if name not in self._tabs._img_dict]
        unprepared = [
            name for name in card_names
            if name in self._tabs._img_dict
            and not image.is_pre_cropped_image_name(name)
            and "uncropped" not in self._tabs._img_dict[name]
        ]
        low_res = [
            name for name in card_names
            if (self._tabs._img_dict.get(name) or {}).get("effective_dpi", low_dpi_warning_threshold)
            < low_dpi_warning_threshold
        ]
        has_cards = bool(card_names)
        self._prepare_button.setEnabled(has_cards)
        self._prepare_action.setEnabled(has_cards)
        ready = has_cards and prints > 0 and not missing and not unprepared
        self._export_button.setEnabled(ready)
        if not has_cards:
            status = "No cards yet"
        elif missing:
            status = f"{len(missing)} missing image{'s' if len(missing) != 1 else ''}"
        elif unprepared:
            status = f"{len(unprepared)} image{'s' if len(unprepared) != 1 else ''} need preparation"
        elif low_res:
            status = f"Ready · {len(low_res)} low-resolution warning{'s' if len(low_res) != 1 else ''}"
        else:
            status = f"Ready · {len(card_names)} cards / {prints} prints"
        self._readiness_label.setText(status)
        self._readiness_label.setToolTip(
            f"{len(card_names)} cards, {prints} prints, {len(missing)} missing, "
            f"{len(unprepared)} unprepared, {len(low_res)} low resolution"
        )

    def refresh_widgets(self, state):
        self._options.refresh_widgets(state)

    def refresh(self, state, img_dict):
        self._scroll_area.refresh(state, img_dict)
        self._options.refresh(state, img_dict)
        self.refresh_preview(state, img_dict)
        self._update_readiness(as_project_state(state))

    def refresh_preview(self, state, img_dict):
        if hasattr(self._tabs, "refresh_preview"):
            self._tabs.refresh_preview(state, img_dict)
        else:
            self._print_preview.refresh(state, img_dict)


class WorkflowGuideWidget(QGroupBox):
    def __init__(self):
        super().__init__()

        self.setTitle("Start Here")

        intro = QLabel(
            "For most projects, follow these steps from top to bottom."
        )
        intro.setWordWrap(True)

        steps = QLabel(
            "1. Import cards or choose your image folder.\n"
            "2. Prepare images after adding or changing card files.\n"
            "3. Check the Preview tab to confirm the pages look right.\n"
            "4. Save the project so you can come back later.\n"
            "5. Save PDF when you are ready to export."
        )
        steps.setWordWrap(True)

        layout = QVBoxLayout()
        layout.addWidget(intro)
        layout.addWidget(steps)
        self.setLayout(layout)


class CardImage(QLabel):
    clicked = QtCore.pyqtSignal()
    double_clicked = QtCore.pyqtSignal()

    def __init__(self, img_data, img_size, round_corners=True, rotation=False):
        super().__init__()

        raw_pixmap = QPixmap()
        raw_pixmap.loadFromData(img_data, "PNG")
        pixmap = raw_pixmap

        card_size_minimum_width_pixels = 130

        if round_corners:
            card_corner_radius_inch = 1 / 8
            card_corner_radius_pixels = (
                card_corner_radius_inch * img_size[0] / card_size_without_bleed_inch[0]
            )

            clipped_pixmap = QPixmap(int(img_size[0]), int(img_size[1]))
            clipped_pixmap.fill(QtCore.Qt.GlobalColor.transparent)

            path = QPainterPath()
            path.addRoundedRect(
                QtCore.QRectF(pixmap.rect()),
                card_corner_radius_pixels,
                card_corner_radius_pixels,
            )

            painter = QPainter(clipped_pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

            painter.setClipPath(path)
            painter.drawPixmap(0, 0, pixmap)
            del painter

            pixmap = clipped_pixmap

        if rotation is not None:
            match rotation:
                case image.Rotation.RotateClockwise_90:
                    rotation = 90
                case image.Rotation.RotateCounterClockwise_90:
                    rotation = -90
                case image.Rotation.Rotate_180:
                    rotation = 180
            transform = QTransform()
            transform.rotate(rotation)
            pixmap = pixmap.transformed(transform)

        self.setPixmap(pixmap)

        self.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding
        )
        self.setScaledContents(True)
        self.setMinimumWidth(card_size_minimum_width_pixels)

        self._rotated = rotation in [-90, 90]

    def heightForWidth(self, width):
        if self._rotated:
            return int(width * card_ratio)
        else:
            return int(width / card_ratio)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.double_clicked.emit()


class BacksideImage(CardImage):
    def __init__(self, backside_name, img_dict):
        if backside_name in img_dict:
            backside_data = cached_preview_bytes(img_dict[backside_name])
            backside_size = img_dict[backside_name]["size"]
        else:
            backside_data = fallback.data
            backside_size = fallback.size

        super().__init__(backside_data, backside_size)


class StackedCardBacksideView(QStackedWidget):
    _backside_reset = QtCore.pyqtSignal()
    _backside_clicked = QtCore.pyqtSignal()

    def __init__(self, img: QWidget, backside: QWidget):
        super().__init__()

        style = QCommonStyle()

        reset_button = QPushButton()
        reset_button.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogResetButton)
        )
        reset_button.setToolTip("Use the default card back")
        reset_button.setFixedWidth(20)
        reset_button.setFixedHeight(20)
        reset_button.clicked.connect(self._backside_reset)

        backside.setToolTip("Choose a custom back for this card")

        backside_layout = QHBoxLayout()
        backside_layout.addStretch()
        backside_layout.addWidget(
            reset_button, alignment=QtCore.Qt.AlignmentFlag.AlignBottom
        )
        backside_layout.addWidget(
            backside, alignment=QtCore.Qt.AlignmentFlag.AlignBottom
        )
        backside_layout.setContentsMargins(0, 0, 0, 0)

        backside_container = QWidget(self)
        backside_container.setLayout(backside_layout)

        img.setMouseTracking(True)
        backside.setMouseTracking(True)
        backside_container.setMouseTracking(True)
        self.setMouseTracking(True)

        self.addWidget(img)
        self.addWidget(backside_container)
        self.layout().setStackingMode(QStackedLayout.StackingMode.StackAll)
        self.layout().setAlignment(
            backside,
            QtCore.Qt.AlignmentFlag.AlignBottom | QtCore.Qt.AlignmentFlag.AlignRight,
        )

        self._img = img
        self._backside = backside
        self._backside_container = backside_container

    def refresh_backside(self, new_backside):
        new_backside.setMouseTracking(True)

        layout = self._backside_container.layout()
        self._backside.setParent(None)
        layout.addWidget(new_backside)
        layout.addWidget(new_backside, alignment=QtCore.Qt.AlignmentFlag.AlignBottom)
        self._backside = new_backside

        self.refresh_sizes(self.rect().size())

    def refresh_sizes(self, size):
        width = size.width()
        height = size.height()

        img_width = int(width * 0.9)
        img_height = int(height * 0.9)

        backside_width = int(width * 0.45)
        backside_height = int(height * 0.45)

        self._img.setFixedWidth(img_width)
        self._img.setFixedHeight(img_height)
        self._backside.setFixedWidth(backside_width)
        self._backside.setFixedHeight(backside_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_sizes(event.size())

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)

        x = event.pos().x()
        y = event.pos().y()

        neg_backside_width = self.rect().width() - self._backside.rect().size().width()
        neg_backside_height = (
            self.rect().height() - self._backside.rect().size().height()
        )

        if x >= neg_backside_width and y >= neg_backside_height:
            self.setCurrentWidget(self._backside_container)
        else:
            self.setCurrentWidget(self._img)

    def leaveEvent(self, event):
        super().leaveEvent(event)

        self.setCurrentWidget(self._img)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)

        if self.currentWidget() == self._backside_container:
            self._backside_clicked.emit()


class CardWidget(QWidget):
    selection_changed = QtCore.pyqtSignal(str, bool)

    def __init__(self, print_dict, img_dict, card_name):
        super().__init__()
        self.setMouseTracking(True)
        state = as_project_state(print_dict)
        runtime_images.ensure_preview_entry(state, img_dict, card_name)

        if card_name in img_dict:
            img_data = cached_preview_bytes(img_dict[card_name])
            img_size = img_dict[card_name]["size"]
        else:
            img_data = fallback.data
            img_size = fallback.size
        img = CardImage(img_data, img_size)
        img.setToolTip("Click to select · Double-click to replace artwork")

        def open_high_res_picker():
            dialog = HighResPickerDialog(self, state, img_dict, card_name)
            if dialog.exec() == QDialog.DialogCode.Accepted and dialog.was_applied():
                self.window().refresh(state, img_dict)
                autosave_managed_session()

        if card_name is not None:
            img.clicked.connect(self.toggle_selected)
            img.double_clicked.connect(open_high_res_picker)

        backside_enabled = state.backside_enabled
        oversized_enabled = state.oversized_enabled

        backside_img = None
        if backside_enabled:
            backside_name = (
                state.backsides[card_name]
                if card_name in state.backsides
                else state.backside_default
            )
            runtime_images.ensure_preview_entry(state, img_dict, backside_name)
            backside_img = BacksideImage(backside_name, img_dict)

        initial_number = state.cards[card_name] if card_name is not None else 1

        number_edit = QLineEdit()
        number_edit.setValidator(QIntValidator(0, 100, self))
        number_edit.setText(str(initial_number))
        number_edit.setFixedWidth(40)

        decrement_button = QPushButton("-")
        increment_button = QPushButton("+")
        decrement_button.setFixedWidth(32)
        increment_button.setFixedWidth(32)

        decrement_button.setToolTip("Remove one copy")
        increment_button.setToolTip("Add one copy")

        number_layout = QHBoxLayout()
        number_layout.addStretch()
        number_layout.addWidget(decrement_button)
        number_layout.addWidget(number_edit)
        number_layout.addWidget(increment_button)
        number_layout.addStretch()
        number_layout.setContentsMargins(0, 0, 0, 0)

        number_area = QWidget()
        number_area.setLayout(number_layout)
        number_area.setFixedHeight(34)

        thumbnail_button = QPushButton("Use as Project Cover")
        thumbnail_button.setToolTip("Use this card on the project list")
        thumbnail_button.setFixedHeight(24)

        def set_project_thumbnail():
            app = QApplication.instance()
            if app is not None and hasattr(app, "set_project_thumbnail"):
                app.set_project_thumbnail(card_name)

        thumbnail_button.clicked.connect(set_project_thumbnail)
        thumbnail_button.setEnabled(card_name is not None)

        delete_button = None
        if card_name is not None:
            delete_button = QPushButton("X", self)
            delete_button.setFixedSize(24, 24)
            delete_button.setToolTip("Remove this card from the project")
            delete_button.setStyleSheet(
                "QPushButton {"
                "background-color: #8d2d2d; color: white; font-weight: bold;"
                "border: 1px solid #b85555; border-radius: 12px;"
                "}"
                "QPushButton:hover { background-color: #a83a3a; }"
            )
            delete_button.hide()

            def delete_card():
                confirm = QMessageBox.question(
                    self,
                    "Remove Card",
                    (
                        f"Remove '{card_name}' from this project?\n\n"
                        "This removes the card from this project and clears any local project cache files. "
                        "The image stays in the card database."
                    ),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if confirm != QMessageBox.StandardButton.Yes:
                    return

                application = QApplication.instance()
                try:
                    project_service.delete_card_files(state, img_dict, card_name)
                except OSError as exc:
                    if application is not None and hasattr(application, "warn_nonfatal"):
                        application.warn_nonfatal(
                            "Remove Card Failed",
                            f"The card image could not be fully deleted from disk.\n\n{exc}",
                        )
                    else:
                        QMessageBox.warning(
                            self,
                            "Remove Card Failed",
                            f"The card image could not be fully deleted from disk.\n\n{exc}",
                        )
                    return
                window = self.window()
                if window is not None and hasattr(
                    window, "clear_project_thumbnail_if_matches"
                ):
                    window.clear_project_thumbnail_if_matches(card_name)
                self.window().refresh(state, img_dict)

            delete_button.clicked.connect(delete_card)

        effective_dpi = None
        if card_name in img_dict:
            effective_dpi = img_dict[card_name].get("effective_dpi")

        if effective_dpi is not None:
            rounded_dpi = round(effective_dpi)
            dpi_label = QLabel(f"{rounded_dpi} DPI")
            dpi_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            if effective_dpi < low_dpi_warning_threshold:
                dpi_label.setToolTip(
                    f"This image is approximately {rounded_dpi} DPI, below the warning threshold of {low_dpi_warning_threshold} DPI."
                )
                dpi_label.setStyleSheet(
                    "background-color: #7a1f1f; color: white; font-weight: bold; "
                    "border: 1px solid #b85555; border-radius: 4px; padding: 2px 6px;"
                )
            else:
                dpi_label.setToolTip(
                    f"This image is approximately {rounded_dpi} DPI."
                )
                dpi_label.setStyleSheet(
                    "background-color: #1f3c5a; color: white; font-weight: bold; "
                    "border: 1px solid #5b87b5; border-radius: 4px; padding: 2px 6px;"
                )
            dpi_label.setFixedHeight(22)
            self._dpi_label = dpi_label
        else:
            self._dpi_label = None

        if backside_img is not None:
            card_widget = StackedCardBacksideView(img, backside_img)

            def backside_reset():
                if card_name in state.backsides:
                    del state.backsides[card_name]
                    state._ensure_card_entry(card_name).backside_name = None
                    runtime_images.ensure_preview_entry(state, img_dict, state.backside_default)
                    new_backside_img = BacksideImage(
                        state.backside_default, img_dict
                    )
                    card_widget.refresh_backside(new_backside_img)

            def backside_choose():
                backside_choice = image_file_dialog(self, state.image_dir)
                if backside_choice is not None and (
                    card_name not in state.backsides
                    or backside_choice != state.backsides[card_name]
                ):
                    state.set_backside(card_name, backside_choice)
                    new_backside_img = BacksideImage(backside_choice, img_dict)
                    card_widget.refresh_backside(new_backside_img)

            card_widget._backside_reset.connect(backside_reset)
            card_widget._backside_clicked.connect(backside_choose)
        else:
            card_widget = img

        if backside_enabled or oversized_enabled:
            extra_options = []

            if oversized_enabled:
                is_oversized = (
                    state.oversized[card_name]
                    if card_name in state.oversized
                    else False
                )
                oversized_checkbox = QCheckBox("Oversized")
                oversized_checkbox.setToolTip(
                    "Turn this on if this card should be printed oversized"
                )
                oversized_checkbox.setChecked(is_oversized)

                oversized_checkbox.checkStateChanged.connect(
                    functools.partial(self.toggle_oversized, state)
                )

                extra_options.append(oversized_checkbox)

            if extra_options:
                extra_options_layout = QHBoxLayout()
                extra_options_layout.addStretch()
                for opt in extra_options:
                    extra_options_layout.addWidget(opt)
                extra_options_layout.addStretch()
                extra_options_layout.setContentsMargins(0, 0, 0, 0)

                extra_options_area = QWidget()
                extra_options_area.setLayout(extra_options_layout)
                extra_options_area.setFixedHeight(20)

                self._extra_options_area = extra_options_area
            else:
                self._extra_options_area = None
        else:
            self._extra_options_area = None

        display_name = _card_sort_label(state, card_name)
        name_label = QLabel(display_name)
        name_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        name_label.setToolTip(display_name)
        name_label.setProperty("role", "subtitle")

        layout = QVBoxLayout()
        layout.setContentsMargins(7, 7, 7, 9)
        layout.setSpacing(7)
        layout.addWidget(card_widget)
        if self._dpi_label is not None:
            layout.addWidget(self._dpi_label)
        layout.addWidget(name_label)
        layout.addWidget(number_area)
        self.setLayout(layout)
        self.setObjectName("cardTile")
        self.setStyleSheet(
            "QWidget#cardTile { background: #171b22; border: 1px solid #2d3541; border-radius: 9px; }"
            "QWidget#cardTile[selected=\"true\"] { background: #203b33; border: 3px solid #42c995; border-radius: 9px; }"
            "QWidget#cardTile:hover { border-color: #566273; }"
            "QWidget#cardTile[selected=\"true\"]:hover { border-color: #55dfaa; }"
        )

        self._img_widget = img
        self._number_area = number_area
        self._thumbnail_button = thumbnail_button
        self._delete_button = delete_button
        self._name_label = name_label
        self._selected = False

        number_edit.editingFinished.connect(
            functools.partial(self.edit_number, state)
        )
        decrement_button.clicked.connect(functools.partial(self.dec_number, state))
        increment_button.clicked.connect(functools.partial(self.inc_number, state))

        margins = self.layout().contentsMargins()
        minimum_img_width = img.minimumWidth()
        minimum_width = minimum_img_width + margins.left() + margins.right()
        self.setMinimumSize(minimum_width, self.heightForWidth(minimum_width))

        self._number_edit = number_edit
        self._card_name = card_name

        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)

        def show_card_menu(position):
            menu = QMenu(self)
            menu.addAction("Replace artwork…", open_high_res_picker)
            if backside_enabled:
                menu.addAction("Choose custom back…", backside_choose)
                if card_name in state.backsides:
                    menu.addAction("Use default back", backside_reset)
            menu.addAction("Use as project cover", set_project_thumbnail)
            if oversized_enabled:
                oversized_action = menu.addAction("Print oversized")
                oversized_action.setCheckable(True)
                oversized_action.setChecked(bool(state.oversized.get(card_name, False)))
                oversized_action.toggled.connect(
                    lambda checked: self.toggle_oversized(
                        state,
                        QtCore.Qt.CheckState.Checked if checked else QtCore.Qt.CheckState.Unchecked,
                    )
                )
            menu.addSeparator()
            menu.addAction("Remove from project", delete_card)
            menu.exec(self.mapToGlobal(position))

        self.customContextMenuRequested.connect(show_card_menu)

    def enterEvent(self, event):
        super().enterEvent(event)

    def leaveEvent(self, event):
        super().leaveEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def heightForWidth(self, width):
        margins = self.layout().contentsMargins()
        spacing = self.layout().spacing()

        img_width = width - margins.left() - margins.right()
        img_height = self._img_widget.heightForWidth(img_width)

        additional_widgets = self._number_area.height() + spacing
        additional_widgets += self._name_label.sizeHint().height() + spacing

        if self._dpi_label is not None:
            additional_widgets += self._dpi_label.height() + spacing

        return img_height + additional_widgets + margins.top() + margins.bottom()

    def toggle_selected(self):
        self.set_selected(not self._selected)

    def set_selected(self, selected):
        selected = bool(selected)
        if self._selected == selected:
            return
        self._selected = selected
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.selection_changed.emit(self._card_name, selected)

    def apply_number(self, state, number):
        self._number_edit.setText(str(number))
        # Keep the persisted entry in sync: preview/history serialization rebuilds
        # the legacy cards map from these entries.
        state.set_card_count(self._card_name, number)
        if hasattr(self.window(), 'project_changed'):
            self.window().project_changed()

    def edit_number(self, state):
        number = int(self._number_edit.text())
        number = max(number, 0)
        self.apply_number(state, number)

    def dec_number(self, state):
        number = state.cards[self._card_name] - 1
        number = max(number, 0)
        self.apply_number(state, number)

    def inc_number(self, state):
        number = state.cards[self._card_name] + 1
        number = min(number, 999)
        self.apply_number(state, number)

    def toggle_short_edge(self, state, s):
        short_edge_dict = state.backside_short_edge
        if s == QtCore.Qt.CheckState.Checked:
            short_edge_dict[self._card_name] = True
        elif self._card_name in short_edge_dict:
            del short_edge_dict[self._card_name]
        state._ensure_card_entry(self._card_name).backside_short_edge = bool(short_edge_dict.get(self._card_name))

    def toggle_oversized(self, state, s):
        oversized_dict = state.oversized
        if s == QtCore.Qt.CheckState.Checked:
            oversized_dict[self._card_name] = True
        elif self._card_name in oversized_dict:
            del oversized_dict[self._card_name]
        state._ensure_card_entry(self._card_name).oversized = bool(oversized_dict.get(self._card_name))


class DummyCardWidget(CardWidget):
    def __init__(self, print_dict, img_dict):
        QWidget.__init__(self)
        self._card_name = "__dummy"

        img = CardImage(fallback.data, fallback.size)
        sp_retain = img.sizePolicy()
        sp_retain.setRetainSizeWhenHidden(True)
        img.setSizePolicy(sp_retain)
        img.hide()

        number_area = QWidget()
        number_area.setFixedHeight(20)
        number_area.hide()

        thumbnail_button = QPushButton("Use as Project Cover")
        thumbnail_button.setFixedHeight(24)
        thumbnail_button.hide()

        name_label = QLabel("")
        name_label.hide()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(img)
        layout.addWidget(name_label)
        layout.addWidget(number_area)
        layout.addWidget(thumbnail_button)
        self.setLayout(layout)

        self._img_widget = img
        self._number_area = number_area
        self._thumbnail_button = thumbnail_button
        self._name_label = name_label
        self._dpi_label = None
        self._extra_options_area = None
        self._delete_button = None

        minimum_img_width = img.minimumWidth()
        self.setMinimumSize(minimum_img_width, self.heightForWidth(minimum_img_width))

    def apply_number(self, state, number):
        pass

    def edit_number(self, state):
        pass

    def dec_number(self, state):
        pass

    def inc_number(self, state):
        pass

    def toggle_oversized(self, state, s):
        pass


class CardGrid(QWidget):
    selection_changed = QtCore.pyqtSignal(int)

    def __init__(self, print_dict, img_dict):
        super().__init__()

        self._cards = {}
        self._selected_names = set()
        self._filter_text = ""
        self._zoom_percent = 100
        self._state = state = as_project_state(print_dict)
        self._img_dict = img_dict

        grid_layout = QGridLayout()
        grid_layout.setContentsMargins(9, 9, 9, 9)
        self.setLayout(grid_layout)
        self.refresh(state, img_dict)

    def totalWidthFromItemWidth(self, item_width):
        margins = self.layout().contentsMargins()
        spacing = self.layout().spacing()

        return (
            item_width * self._cols
            + margins.left()
            + margins.right()
            + spacing * (self._cols - 1)
        )

    def heightForWidth(self, width):
        margins = self.layout().contentsMargins()
        spacing = self.layout().spacing()

        item_width = int(
            (width - margins.left() - margins.right() - spacing * (self._cols - 1))
            / self._cols
        )
        item_height = self._first_item.heightForWidth(item_width)
        height = (
            item_height * self._rows
            + margins.top()
            + margins.bottom()
            + spacing * (self._rows - 1)
        )

        return int(height)

    def resizeEvent(self, event):
        width = event.size().width()
        height = self.heightForWidth(width)
        self.setFixedHeight(height)

    def refresh(self, print_dict, img_dict):
        state = as_project_state(print_dict)
        self._state = state
        self._img_dict = img_dict
        for card in self._cards.values():
            card.setParent(None)
        self._cards = {}

        grid_layout = self.layout()

        i = 0
        cols = max(1, round(CFG.DisplayColumns * 100 / self._zoom_percent))
        card_sort = getattr(state, "card_sort", "Alphabetical (A-Z)")
        card_names = list(state.cards.keys())
        if card_sort == "Alphabetical (A-Z)":
            card_names = sorted(
                card_names,
                key=lambda name: _card_sort_label(state, name).casefold(),
            )
        elif card_sort == "Alphabetical (Z-A)":
            card_names = sorted(
                card_names,
                key=lambda name: _card_sort_label(state, name).casefold(),
                reverse=True,
            )

        for card_name in card_names:
            if card_name.startswith("__"):
                continue
            runtime_images.ensure_preview_entry(state, img_dict, card_name)
            if card_name not in img_dict:
                continue

            card_widget = CardWidget(state, img_dict, card_name)
            card_widget.selection_changed.connect(self._card_selection_changed)
            if card_name in self._selected_names:
                card_widget.set_selected(True)
            self._cards[card_name] = card_widget

            x = i // cols
            y = i % cols
            grid_layout.addWidget(card_widget, x, y)
            i = i + 1

        for j in range(i, cols):
            card_widget = DummyCardWidget(state, img_dict)
            sp_retain = card_widget.sizePolicy()
            sp_retain.setRetainSizeWhenHidden(True)
            card_widget.setSizePolicy(sp_retain)
            card_widget.hide()

            self._cards[card_widget._card_name] = card_widget
            grid_layout.addWidget(card_widget, 0, j)
            i = i + 1

        self._first_item = list(self._cards.values())[0]
        self._cols = cols
        self._rows = math.ceil(i / cols)
        self._nested_resize = False

        self.setMinimumWidth(
            self.totalWidthFromItemWidth(self._first_item.minimumWidth())
        )
        self.setMinimumHeight(
            self._first_item.heightForWidth(self._first_item.minimumWidth())
        )
        self.apply_filter(self._filter_text)

    def _card_selection_changed(self, card_name, selected):
        if selected:
            self._selected_names.add(card_name)
        else:
            self._selected_names.discard(card_name)
        self.selection_changed.emit(len(self._selected_names))

    def selected_cards(self):
        return [self._cards[name] for name in self._selected_names if name in self._cards]

    def clear_selection(self):
        for card in self.selected_cards():
            card.set_selected(False)

    def select_all_visible(self):
        for name, card in self._cards.items():
            if not name.startswith("__") and card.isVisible():
                card.set_selected(True)

    def apply_filter(self, text):
        self._filter_text = (text or "").strip().casefold()
        for name, card in self._cards.items():
            if name.startswith("__"):
                continue
            label = card._name_label.text().casefold()
            card.setVisible(not self._filter_text or self._filter_text in label)

    def has_visible_cards(self):
        return any(not card_name.startswith("__") for card_name in self._cards.keys())

    def set_zoom(self, percent):
        percent = max(50, min(200, int(percent)))
        if percent == self._zoom_percent:
            return
        self._zoom_percent = percent
        self.refresh(self._state, self._img_dict)
        self.adjustSize()

class CardScrollArea(QScrollArea):
    def __init__(self, print_dict, img_dict, card_grid):
        super().__init__()
        state = as_project_state(print_dict)

        search_edit = QLineEdit()
        search_edit.setPlaceholderText("Search cards…")
        search_edit.setClearButtonEnabled(True)
        search_edit.setMaximumWidth(340)
        sort_combo = QComboBox()
        sort_options = [
            "Alphabetical (A-Z)",
            "Alphabetical (Z-A)",
            "Import Order",
        ]
        sort_combo.addItems(sort_options)
        if state.card_sort in sort_options:
            sort_combo.setCurrentText(state.card_sort)
        else:
            sort_combo.setCurrentText("Alphabetical (A-Z)")

        sort_combo.setToolTip("Sort cards")
        zoom_combo = QComboBox()
        zoom_combo.addItems(["75%", "90%", "100%", "110%", "125%", "150%"])
        zoom_combo.setCurrentText("100%")
        zoom_combo.setToolTip("Change card size")
        selection_label = QLabel("")
        selection_label.setProperty("role", "muted")
        decrement_button = QPushButton("-")
        increment_button = QPushButton("+")
        clear_selection_button = QPushButton("Clear")
        for button in (decrement_button, increment_button):
            button.setFixedWidth(34)
        decrement_button.setToolTip("Remove one copy from selected cards")
        increment_button.setToolTip("Add one copy to selected cards")
        clear_selection_button.setToolTip("Clear selection")

        global_number_layout = QHBoxLayout()
        global_number_layout.addWidget(search_edit, 1)
        global_number_layout.addWidget(sort_combo)
        global_number_layout.addWidget(QLabel("Zoom"))
        global_number_layout.addWidget(zoom_combo)
        global_number_layout.addStretch()
        global_number_layout.addWidget(selection_label)
        global_number_layout.addWidget(decrement_button)
        global_number_layout.addWidget(increment_button)
        global_number_layout.addWidget(clear_selection_button)
        global_number_layout.setContentsMargins(6, 0, 6, 0)

        global_number_widget = QWidget()
        global_number_widget.setLayout(global_number_layout)

        empty_state = QLabel(
            "Your deck is ready for cards\n\n"
            "Use Add Cards to import a deck link, paste a list, search for a card, or choose local images."
        )
        empty_state.setWordWrap(True)
        empty_state.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        empty_state.setFrameShape(QFrame.Shape.StyledPanel)
        empty_state.setStyleSheet("padding: 20px;")

        card_area_layout = QVBoxLayout()
        card_area_layout.addWidget(global_number_widget)
        card_area_layout.addWidget(empty_state)
        card_area_layout.addWidget(card_grid)
        card_area_layout.addStretch()
        card_area_layout.setSpacing(0)

        card_area = QWidget()
        card_area.setLayout(card_area_layout)

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidget(card_area)

        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        def dec_number():
            for card in card_grid.selected_cards():
                card.dec_number(state)

        def inc_number():
            for card in card_grid.selected_cards():
                card.inc_number(state)

        def change_sort(t):
            state.card_sort = t
            self.window().refresh(state, self._img_dict)

        decrement_button.clicked.connect(dec_number)
        increment_button.clicked.connect(inc_number)
        clear_selection_button.clicked.connect(card_grid.clear_selection)
        search_edit.textChanged.connect(card_grid.apply_filter)
        sort_combo.currentTextChanged.connect(change_sort)
        zoom_combo.currentTextChanged.connect(
            lambda text: card_grid.set_zoom(int(text.rstrip("%")))
        )

        def update_selection(count):
            selection_label.setText(f"{count} selected" if count else self._count_text(state))
            decrement_button.setVisible(count > 0)
            increment_button.setVisible(count > 0)
            clear_selection_button.setVisible(count > 0)

        card_grid.selection_changed.connect(update_selection)
        update_selection(0)

        self._card_grid = card_grid
        self._global_number_widget = global_number_widget
        self._empty_state = empty_state
        self._img_dict = img_dict
        self._sort_combo = sort_combo
        self._zoom_combo = zoom_combo
        self._search_edit = search_edit
        self._selection_label = selection_label
        self._selection_buttons = (decrement_button, increment_button, clear_selection_button)
        self._update_empty_state()

        QShortcut(QKeySequence.StandardKey.Find, self, activated=search_edit.setFocus)
        QShortcut(QKeySequence.StandardKey.SelectAll, self, activated=card_grid.select_all_visible)

    def computeMinimumWidth(self):
        margins = self.widget().layout().contentsMargins()
        return (
            self._card_grid.minimumWidth()
            + 2 * self.verticalScrollBar().width()
            + margins.left()
            + margins.right()
        )

    def showEvent(self, event):
        super().showEvent(event)
        self.setMinimumWidth(self.computeMinimumWidth())

    def refresh(self, state, img_dict):
        self._card_grid.refresh(state, img_dict)
        if self._sort_combo.findText(state.card_sort) >= 0:
            self._sort_combo.setCurrentText(state.card_sort)
        else:
            self._sort_combo.setCurrentText("Alphabetical (A-Z)")
        self._update_empty_state()
        self.setMinimumWidth(self.computeMinimumWidth())
        self._card_grid.adjustSize()  # forces recomputing size
        if not self._card_grid._selected_names:
            self._selection_label.setText(self._count_text(state))

    @staticmethod
    def _count_text(state):
        names = [name for name in state.cards if not name.startswith("__")]
        prints = sum(max(0, state.cards.get(name, 0)) for name in names)
        return f"{len(names)} cards  |  {prints} prints"

    def _update_empty_state(self):
        has_cards = self._card_grid.has_visible_cards()
        self._global_number_widget.setVisible(has_cards)
        self._empty_state.setVisible(not has_cards)
        self._card_grid.setVisible(has_cards)


class PageGrid(QWidget):
    def __init__(self, cards, backside, columns, rows, bleed_edge_mm, img_get):
        super().__init__()

        grid = QGridLayout()
        grid.setSpacing(0)
        grid.setContentsMargins(0, 0, 0, 0)

        left_to_right = not backside
        card_grid = pdf.distribute_cards_to_grid(cards, left_to_right, columns, rows)

        has_missing_preview = False

        for x in range(0, rows):
            for y in range(0, columns):
                if card := card_grid[x][y]:
                    (card_name, is_short_edge, is_oversized) = card
                    if card_name is None:
                        continue

                    img_data, img_size = img_get(card_name, bleed_edge_mm)
                    if img_data is None:
                        img_data, img_size = fallback.data, fallback.size
                        has_missing_preview = True

                    rotation = pdf.get_card_rotation(
                        backside, is_oversized, is_short_edge
                    )

                    img = CardImage(
                        img_data,
                        img_size,
                        round_corners=False,
                        rotation=rotation,
                    )

                    img.setMinimumSize(0, 0)
                    img.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
                    if is_oversized:
                        grid.addWidget(img, x, y, 1, 2)
                    else:
                        grid.addWidget(img, x, y)

        # Reserve every printable slot, including empty rows and wide-card coverage.
        for row in range(rows):
            for column in range(columns):
                if grid.itemAtPosition(row, column) is None:
                    spacer = QWidget()
                    grid.addWidget(spacer, row, column)

        for i in range(0, grid.columnCount()):
            grid.setColumnStretch(i, 1)
        for i in range(0, grid.rowCount()):
            grid.setRowStretch(i, 1)

        self.setLayout(grid)

        self._rows = rows
        self._cols = max(1, columns)
        bleed = mm_to_inch(bleed_edge_mm)
        self._card_ratio = ((card_size_without_bleed_inch[0] + 2 * bleed)
                            / (card_size_without_bleed_inch[1] + 2 * bleed))
        self._has_missing_preview = has_missing_preview

    def hasMissingPreviews(self):
        return self._has_missing_preview

    def heightForWidth(self, width):
        return int(width / self._card_ratio * (self._rows / self._cols))

    def resizeEvent(self, event):
        super().resizeEvent(event)

        width = event.size().width()
        height = self.heightForWidth(width)
        self.setFixedHeight(height)


class PagePreview(QWidget):
    def __init__(
        self,
        cards,
        backside,
        columns,
        rows,
        bleed_edge_mm,
        backside_offset_mm,
        page_size,
        img_get,
    ):
        super().__init__()

        grid = PageGrid(cards, backside, columns, rows, bleed_edge_mm, img_get)

        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(grid)
        layout.setAlignment(grid, QtCore.Qt.AlignmentFlag.AlignTop)

        self.setLayout(layout)

        palette = self.palette()
        palette.setColor(self.backgroundRole(), 0xFFFFFF)
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        self.setObjectName("printSheet")
        self.setStyleSheet("#printSheet { background: white; } #printSheet QWidget { background: transparent; }")

        (page_width, page_height) = page_size
        self._page_ratio = page_width / page_height
        self._page_width = page_width
        self._page_height = page_height

        bleed_edge = mm_to_inch(bleed_edge_mm)
        (card_width, card_height) = (
            v + 2 * bleed_edge for v in card_size_without_bleed_inch
        )
        self._card_width = card_width
        self._card_height = card_height

        self._padding_width = (page_width - columns * card_width) / 2
        self._padding_height = (page_height - rows * card_height) / 2
        self._backside_offset = mm_to_inch(backside_offset_mm) if backside else 0

        self._grid = grid

    def hasMissingPreviews(self):
        return self._grid.hasMissingPreviews()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QtCore.Qt.GlobalColor.white)

    def heightForWidth(self, width):
        return int(width / self._page_ratio)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        width = event.size().width()
        height = self.heightForWidth(width)
        self.setFixedHeight(height)

        padding_width_pixels = round(self._padding_width * width / self._page_width)
        padding_height_pixels = round(self._padding_height * height / self._page_height)
        backside_offset_pixels = int(self._backside_offset * width / self._page_width)
        self.setContentsMargins(
            max(0, padding_width_pixels + backside_offset_pixels),
            padding_height_pixels,
            max(0, padding_width_pixels - backside_offset_pixels),
            padding_height_pixels,
        )


class PrintPreview(QScrollArea):
    def __init__(self, print_dict, img_dict):
        super().__init__()
        self._zoom_percent = 75
        self._page_index = 0
        self._pages = []
        self._view_mode = "Continuous"
        self._fit_zoom = False
        self._selected_copy = None
        self._extra_pages = 0
        self._overlays = []
        self._drag_span = 1
        self._drag_active = False
        self._history = layout_service.LayoutHistory()
        self._layout_shortcuts = []
        for sequence, callback in ((QKeySequence.StandardKey.Undo, self.undo_layout),
                                   (QKeySequence.StandardKey.Redo, self.redo_layout),
                                   ("Ctrl+Shift+Z", self.redo_layout)):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
            self._layout_shortcuts.append(shortcut)
        self._drag_timer = QtCore.QTimer(self)
        self._drag_timer.setInterval(40)
        self._drag_timer.timeout.connect(self._scroll_drag)
        self.refresh(as_project_state(print_dict), img_dict)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

    def refresh(self, print_dict, img_dict, *, preserve_scroll=True):
        scroll_value = self.verticalScrollBar().value()
        horizontal_value = self.horizontalScrollBar().value()
        state = as_project_state(print_dict)
        self._state, self._img_dict = state, img_dict
        self._history.observe(state.to_dict())
        self._overlays = []
        bleed_edge = float(state.bleed_edge)
        bleed_edge_inch = mm_to_inch(bleed_edge)

        page_size = page_sizes[state.pagesize]
        if state.orient == "Landscape":
            page_size = tuple(page_size[::-1])
        page_size = tuple(point_to_inch(p) for p in page_size)
        (page_width, page_height) = page_size

        (card_width, card_height) = card_size_without_bleed_inch
        card_width = card_width + 2 * bleed_edge_inch
        card_height = card_height + 2 * bleed_edge_inch

        columns = int(page_width // card_width)
        rows = int(page_height // card_height)

        self._columns, self._rows = columns, rows
        try:
            self._placements, relocated = layout_service.resolve(state, columns, rows)
        except ValueError as exc:
            self._placements, self._pages = [], []
            self._zoom_combo = None
            self.setWidget(QLabel(str(exc)))
            return
        raw_pages = layout_service.pages_from_items(
            state, self._placements, columns, rows,
            max(1, self._extra_pages))
        self._history.baseline = state.to_dict()
        occupancy = layout_service.occupancy(self._placements, columns, rows, len(raw_pages))
        self._page_captions = []
        pages = pdf.make_render_page_sequence(state, raw_pages)

        @functools.cache
        def img_get(card_name, bleed_edge):
            card_img = runtime_images.ensure_preview_entry(state, img_dict, card_name)
            if card_img is None:
                return None, None
            if bleed_edge > 0 and "uncropped" in card_img:
                uncropped_data = cached_preview_bytes(card_img["uncropped"])
                img = image.image_from_bytes(uncropped_data)
                img_crop = image.crop_image(img, card_name, bleed_edge, None)
                img_data, img_size = image.to_bytes(img_crop)
            else:
                img_data = cached_preview_bytes(card_img)
                img_size = card_img["size"]
            return img_data, img_size

        img_get.cache_clear()

        page_widgets = []
        for page in pages:
            occupied = occupancy[page["front_page_number"] - 1]
            caption = layout_service.occupancy_label(occupied)
            if page["backside"]:
                caption += " (back)"
            if occupied['cards'] != occupied['filled']:
                caption += f" | {occupied['cards']} cards; oversized cards use two slots"
            if occupied['page'] > max((p['page'] + 1 for p in self._placements), default=0):
                caption += " | Empty editing sheet; not exported"
            label = QLabel(caption)
            label.setProperty("role", "subtitle")
            self._page_captions.append(label)
            widget = PagePreview(page["cards"], page["backside"], columns, rows,
                bleed_edge, float(state.backside_offset), page_size, img_get)
            page_widgets.append(widget)
            if not page["backside"] and columns > 0 and rows > 0:
                self._overlays.append(PreviewOverlay(widget._grid, self, page["front_page_number"] - 1))
        pages = page_widgets

        has_missing_previews = any([p.hasMissingPreviews() for p in pages])
        self._pages = pages
        self._page_index = min(self._page_index, max(0, len(pages) - 1))
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(8, 4, 8, 4)
        previous_button = DragPageButton("Previous", lambda: self._set_page(self._page_index - 1), self)
        next_button = DragPageButton("Next", lambda: self._set_page(self._page_index + 1), self)
        page_count = QLabel()
        page_count.setProperty("role", "subtitle")
        zoom_combo = QComboBox()
        zoom_combo.addItems(["Fit", "50%", "75%", "100%", "125%", "150%"])
        zoom_combo.setCurrentText("Fit" if self._fit_zoom else f"{self._zoom_percent}%")
        view_combo = QComboBox()
        view_combo.addItems(["Continuous", "Single Page"])
        view_combo.setCurrentText(self._view_mode)
        zoom_combo.currentTextChanged.connect(self._set_zoom)
        view_combo.currentTextChanged.connect(self._set_view_mode)
        header_layout.addWidget(previous_button)
        header_layout.addWidget(next_button)
        header_layout.addWidget(page_count)
        add_page = QPushButton("Add page")
        add_page.clicked.connect(self.add_page)
        reset_layout = QPushButton("Reset layout")
        reset_layout.setEnabled(state.manual_layout is not None)
        reset_layout.clicked.connect(self.reset_layout)
        header_layout.addWidget(add_page)
        header_layout.addWidget(reset_layout)
        self._undo_button = QPushButton("Undo")
        self._redo_button = QPushButton("Redo")
        self._undo_button.setToolTip("Undo preview edit (Ctrl+Z)")
        self._redo_button.setToolTip("Redo preview edit (Ctrl+Y / Ctrl+Shift+Z)")
        self._undo_button.setEnabled(bool(self._history.undo_entries))
        self._redo_button.setEnabled(bool(self._history.redo_entries))
        self._undo_button.clicked.connect(self.undo_layout)
        self._redo_button.clicked.connect(self.redo_layout)
        header_layout.addWidget(self._undo_button)
        header_layout.addWidget(self._redo_button)
        header_layout.addStretch()
        preview_note = QLabel(
            f"{relocated} copies moved to fit the sheet" if relocated else
            "Drag fronts to arrange | + to add | Save to keep layout")
        preview_note.setWordWrap(True)
        preview_note.setProperty("role", "muted")
        header_layout.addWidget(QLabel("View"))
        header_layout.addWidget(view_combo)
        header_layout.addWidget(QLabel("Zoom"))
        header_layout.addWidget(zoom_combo)
        if has_missing_previews:
            bleed_info = QLabel("Some images need preparation")
            bleed_info.setProperty("role", "warning")
            header_layout.addWidget(bleed_info)
        if CFG.VibranceBump:
            vibrance_info = QLabel("Color boost appears in export")
            vibrance_info.setProperty("role", "muted")
            header_layout.addWidget(vibrance_info)

        header = QWidget()
        header_stack = QVBoxLayout()
        header_stack.setContentsMargins(0, 0, 0, 0)
        header_stack.addLayout(header_layout)
        header_stack.addWidget(preview_note)
        header.setLayout(header_stack)
        header.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        layout = QVBoxLayout()
        layout.addWidget(header)
        for caption, page in zip(self._page_captions, pages):
            layout.addWidget(caption, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
            layout.addWidget(page, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        layout.setSpacing(22)
        layout.setContentsMargins(80, 24, 80, 40)
        pages_widget = QWidget()
        pages_widget.setLayout(layout)
        pages_widget.setObjectName("printPreviewWorkspace")
        pages_widget.setStyleSheet("#printPreviewWorkspace { background: #242a32; }")

        self.setWidget(pages_widget)
        self._page_label = page_count
        self._previous_button = previous_button
        self._next_button = next_button
        self._zoom_combo = zoom_combo
        self._view_combo = view_combo
        self._apply_preview_view(fit=self._fit_zoom)
        if preserve_scroll:
            def restore_scroll():
                self.verticalScrollBar().setValue(scroll_value)
                self.horizontalScrollBar().setValue(horizontal_value)
            restore_scroll()
            QtCore.QTimer.singleShot(0, restore_scroll)

    def update_overlays(self):
        for overlay in self._overlays:
            overlay.update()

    def refresh_after_edit(self):
        window = self.window()
        if window is not self and hasattr(window, "refresh"):
            window.refresh(self._state, self._img_dict)
        else:
            self.refresh(self._state, self._img_dict)

    def reset_layout(self):
        before = self.layout_snapshot()
        self._state.manual_layout = None
        self._extra_pages = 0
        self._selected_copy = None
        self._history.push(before, self.layout_snapshot())
        self.refresh_after_edit()

    def add_page(self):
        before = self.layout_snapshot()
        self._extra_pages = max(1, self._extra_pages, max((p['page'] + 1 for p in self._placements), default=0)) + 1
        self._history.push(before, self.layout_snapshot())
        self.refresh(self._state, self._img_dict, preserve_scroll=False)
        target = next((i for i, page in enumerate(self._pages)
                       if any(o.parentWidget() is page._grid and o.page == self._extra_pages - 1
                              for o in self._overlays)), len(self._pages) - 1)
        self._set_page(target)

    def add_at_slot(self, destination):
        actions = self.window().findChildren(ActionsWidget)
        if not actions:
            return
        history_before = self.layout_snapshot()
        before = layout_service.record(self._placements)
        old_ids = {p['copy_id'] for p in self._placements}
        def place_import(result):
            expected = layout_service.copies(self._state)
            new = [p for key, p in expected.items() if key not in old_ids and p['name'] == result.filename]
            if not new:
                raise ValueError("The import did not add a new printed copy.")
            candidate = dict(new[-1], **dict(zip(('page', 'row', 'column'), destination)))
            occupied = set().union(*(layout_service.cells(p) for p in self._placements))
            if not layout_service.fits(candidate, occupied, self._columns, self._rows):
                raise ValueError("This card does not fit here. Oversized cards need two adjacent empty slots.")
            self._state.manual_layout = before
            self._state.manual_layout['placements'].extend(layout_service.record([candidate])['placements'])
            self._selected_copy = candidate['copy_id']
            self._history.push(history_before, self.layout_snapshot())
        actions[0]._add_single_card(on_added=place_import)

    def layout_snapshot(self):
        return dict(project=self._state.to_dict(), extra_pages=self._extra_pages,
                    selected_copy=self._selected_copy)

    def commit_layout(self, placements):
        before = self.layout_snapshot()
        self._state.manual_layout = layout_service.record(placements)
        self._history.push(before, self.layout_snapshot())

    def _restore_layout(self, snapshot):
        if snapshot is None:
            return
        self._state.copy_from(ProjectState.from_dict(snapshot['project']))
        self._extra_pages = snapshot['extra_pages']
        self._selected_copy = snapshot['selected_copy']
        self.refresh_after_edit()

    def undo_layout(self):
        self._history.observe(self._state.to_dict())
        self._restore_layout(self._history.undo())

    def redo_layout(self):
        self._history.observe(self._state.to_dict())
        self._restore_layout(self._history.redo())

    def _scroll_drag(self):
        if self._view_mode != "Continuous":
            return
        point = self.viewport().mapFromGlobal(QCursor.pos())
        if not 0 <= point.x() < self.viewport().width():
            return
        direction = -1 if point.y() < 60 else 1 if point.y() > self.viewport().height() - 60 else 0
        bar = self.verticalScrollBar()
        bar.setValue(bar.value() + direction * 22)

    def _set_page(self, index):
        if not self._pages:
            return
        self._page_index = max(0, min(int(index), len(self._pages) - 1))
        self._apply_preview_view(fit=self._fit_zoom)
        if self._view_mode == "Continuous":
            self.ensureWidgetVisible(self._pages[self._page_index], 20, 20)

    def _set_view_mode(self, mode):
        self._view_mode = mode
        self._apply_preview_view(fit=self._zoom_combo.currentText() == "Fit")

    def _set_zoom(self, text):
        self._fit_zoom = text == "Fit"
        if text != "Fit":
            self._zoom_percent = int(text.rstrip("%"))
        self._apply_preview_view(fit=text == "Fit")

    def _apply_preview_view(self, fit=False):
        count = len(self._pages)
        for index, page in enumerate(self._pages):
            page.setVisible(self._view_mode == "Continuous" or index == self._page_index)
            self._page_captions[index].setVisible(page.isVisibleTo(self.widget()))
        self._page_label.setText(
            f"Page {self._page_index + 1} of {count}" if count else "No pages"
        )
        self._previous_button.setEnabled(self._page_index > 0)
        self._next_button.setEnabled(self._page_index + 1 < count)
        if not count:
            return
        available = max(320, self.viewport().width() - 180)
        width = available if fit else int(816 * self._zoom_percent / 100)
        for page in self._pages:
            page.setFixedWidth(width)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_zoom_combo", None) is not None and self._zoom_combo.currentText() == "Fit":
            self._apply_preview_view(fit=True)


class LazyPrintPreview(QWidget):
    def __init__(self, print_dict, img_dict):
        super().__init__()
        self._state = as_project_state(print_dict)
        self._img_dict = img_dict
        self._preview = None

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def is_loaded(self):
        return self._preview is not None

    def refresh(self, print_dict, img_dict, force=False):
        self._state = as_project_state(print_dict)
        self._img_dict = img_dict
        if self._preview is None:
            if not force:
                return
            self._preview = PrintPreview(self._state, self._img_dict)
            self.layout().addWidget(self._preview)
            return
        self._preview.refresh(self._state, self._img_dict)


class ActionsWidget(QGroupBox):
    def __init__(
        self,
        application,
        print_dict,
        img_dict,
    ):
        super().__init__()
        state = as_project_state(print_dict)

        self.setTitle("Main Actions")

        cropper_button = QPushButton("Prepare Images")
        render_button = QPushButton("Save PDF")
        home_button = QPushButton("Back to Projects")
        save_button = QPushButton("Save Project")
        load_button = QPushButton("Load Project")
        set_images_button = QPushButton("Choose Image Folder")
        open_images_button = QPushButton("Open Images")
        settings_button = QPushButton("Settings")
        add_card_button = QPushButton("Add Card")
        import_decklist_button = QPushButton("Import Cards")
        clear_cards_button = QPushButton("Remove Old Card Images")

        for button in [
            add_card_button,
            import_decklist_button,
            cropper_button,
            render_button,
            save_button,
            load_button,
            set_images_button,
            open_images_button,
            settings_button,
            clear_cards_button,
            home_button,
        ]:
            button.setMinimumHeight(30)

        primary_button_style = (
            "QPushButton {"
            "background-color: #1f6f4a; color: white; font-weight: bold;"
            "border: 1px solid #17563a; border-radius: 4px; padding: 6px 10px;"
            "}"
            "QPushButton:hover { background-color: #258457; }"
        )
        danger_button_style = (
            "QPushButton {"
            "background-color: #5f2626; color: white;"
            "border: 1px solid #7e3636; border-radius: 4px; padding: 6px 10px;"
            "}"
            "QPushButton:hover { background-color: #743131; }"
        )
        subtle_heading_style = "font-size: 13px; font-weight: bold;"
        subtle_description_style = "color: #666666;"

        add_card_button.setStyleSheet(primary_button_style)
        import_decklist_button.setStyleSheet(primary_button_style)
        cropper_button.setStyleSheet(primary_button_style)
        render_button.setStyleSheet(primary_button_style)
        clear_cards_button.setStyleSheet(danger_button_style)

        buttons = [
            cropper_button,
            render_button,
            home_button,
            save_button,
            load_button,
            set_images_button,
            open_images_button,
            settings_button,
            add_card_button,
            import_decklist_button,
            clear_cards_button,
        ]
        minimum_width = max(map(lambda x: x.sizeHint().width(), buttons))

        def section_title(text, description):
            title = QLabel(text)
            title.setStyleSheet(subtle_heading_style)
            body = QLabel(description)
            body.setWordWrap(True)
            body.setStyleSheet(subtle_description_style)

            wrapper = QWidget()
            wrapper_layout = QVBoxLayout()
            wrapper_layout.setContentsMargins(0, 0, 0, 0)
            wrapper_layout.setSpacing(2)
            wrapper_layout.addWidget(title)
            wrapper_layout.addWidget(body)
            wrapper.setLayout(wrapper_layout)
            return wrapper

        project_section = section_title(
            "1. Project",
            "Start a project, save your work, or return to the project list.",
        )
        cards_section = section_title(
            "2. Add And Prepare Cards",
            "Bring cards into the project, choose image files, and prepare them for printing.",
        )
        export_section = section_title(
            "3. Export",
            "Check the preview, then save the final PDF.",
        )
        more_section = section_title(
            "More Tools",
            "Less common actions for opening folders, changing app settings, or cleaning up old images.",
        )

        layout = QVBoxLayout()
        layout.setSpacing(12)

        project_grid = QGridLayout()
        project_grid.setColumnMinimumWidth(0, minimum_width + 10)
        project_grid.setColumnMinimumWidth(1, minimum_width + 10)
        project_grid.addWidget(home_button, 0, 0, 1, 2)
        project_grid.addWidget(save_button, 1, 0)
        project_grid.addWidget(load_button, 1, 1)

        cards_grid = QGridLayout()
        cards_grid.setColumnMinimumWidth(0, minimum_width + 10)
        cards_grid.setColumnMinimumWidth(1, minimum_width + 10)
        cards_grid.addWidget(add_card_button, 0, 0)
        cards_grid.addWidget(import_decklist_button, 0, 1)
        cards_grid.addWidget(set_images_button, 1, 0, 1, 2)
        cards_grid.addWidget(cropper_button, 2, 0, 1, 2)

        export_grid = QGridLayout()
        export_grid.setColumnMinimumWidth(0, minimum_width + 10)
        export_grid.setColumnMinimumWidth(1, minimum_width + 10)
        export_grid.addWidget(render_button, 0, 0, 1, 2)

        more_grid = QGridLayout()
        more_grid.setColumnMinimumWidth(0, minimum_width + 10)
        more_grid.setColumnMinimumWidth(1, minimum_width + 10)
        more_grid.addWidget(open_images_button, 0, 0, 1, 2)
        more_grid.addWidget(settings_button, 1, 0, 1, 2)
        more_grid.addWidget(clear_cards_button, 2, 0, 1, 2)

        layout.addWidget(project_section)
        layout.addLayout(project_grid)
        layout.addWidget(cards_section)
        layout.addLayout(cards_grid)
        layout.addWidget(export_section)
        layout.addLayout(export_grid)
        layout.addWidget(more_section)
        layout.addLayout(more_grid)

        self.setLayout(layout)

        def render():
            rgx = re.compile(r"\W")
            default_pdf_name = (
                f"{re.sub(rgx, '', state.filename)}.pdf"
                if len(state.filename) > 0
                else "_printme.pdf"
            )
            pdf_path = QFileDialog.getSaveFileName(
                self,
                "Save PDF",
                os.path.join(cwd, default_pdf_name),
                "PDF Files (*.pdf)",
            )[0]
            if pdf_path == "":
                return

            if not pdf_path.lower().endswith(".pdf"):
                pdf_path = pdf_path + ".pdf"

            sheet = page_sizes[state.pagesize]
            if state.orient == "Landscape":
                sheet = tuple(reversed(sheet))
            bleed = mm_to_inch(float(state.bleed_edge))
            cols = int(point_to_inch(sheet[0]) // (card_size_without_bleed_inch[0] + 2 * bleed))
            rows = int(point_to_inch(sheet[1]) // (card_size_without_bleed_inch[1] + 2 * bleed))
            try:
                placements, _ = layout_service.resolve(state, cols, rows)
            except ValueError as exc:
                application.warn_nonfatal("Cannot Export Layout", str(exc))
                return

            if not confirm_underfilled_export(self.window(), layout_service.occupancy(placements, cols, rows)):
                return

            state.filename = os.path.splitext(os.path.basename(pdf_path))[0]
            render_result = None

            def render_work():
                nonlocal render_result
                render_result = pdf_service.generate_pdf(
                    state,
                    page_sizes[state.pagesize],
                    pdf_path,
                    make_popup_print_fn(render_window),
                )
                make_popup_print_fn(render_window)("Saving PDF...")
                render_result.pages.save()
                if render_result.backside_pages is not None:
                    render_result.backside_pages.save()
                try:
                    subprocess.Popen([pdf_path], shell=True)
                except OSError as e:
                    application.warn_nonfatal(
                        "PDF Open Failed",
                        f"The PDF was saved, but the app could not open it automatically.\n\n{e}",
                    )

            self.window().setEnabled(False)
            render_window = popup(self.window(), "Saving PDF...", application._debug_mode)
            render_window.show_during_work(render_work)
            del render_window
            self.window().setEnabled(True)
            saved_paths = pdf_path
            if render_result is not None and render_result.backside_pdf_path:
                saved_paths += f"\n{render_result.backside_pdf_path}"
            QMessageBox.information(
                self,
                "PDF Saved",
                f"Your PDF was saved here:\n\n{saved_paths}\n\nThe app will try to open the front PDF for you automatically.",
            )

        def run_cropper():
            runtime_images.invalidate_all(state, img_dict)

            def refresh_work():
                card_names = [name for name in state.cards.keys() if not name.startswith("__")]
                runtime_images.warm_preview_entries(state, img_dict, card_names)

            self.window().setEnabled(False)
            crop_window = popup(self.window(), "Refreshing previews...", application._debug_mode)
            crop_window.show_during_work(refresh_work)
            del crop_window
            self.window().refresh(state, img_dict)
            self.window().setEnabled(True)
            if hasattr(application, "show_status"):
                application.show_status("Images prepared")

        def save_project():
            saved = application.save_active_project(state)
            if saved is None:
                return
            if hasattr(application, "show_status"):
                application.show_status(f"Saved {saved['display_name']}")

        def load_project():
            new_project_json = project_file_dialog(
                self, FileDialogType.Open, application.json_path()
            )
            if new_project_json is not None and os.path.exists(new_project_json):
                application.import_and_open_project(new_project_json)

        def set_images_folder():
            new_image_dir = folder_dialog(self)
            if new_image_dir is not None:
                state.image_dir = new_image_dir
                state.img_cache = os.path.join(new_image_dir, "img.cache")

                project_service.init_dict(state, img_dict, application.warn_nonfatal)
                runtime_images.invalidate_all(state, img_dict)
                self.window().refresh(state, img_dict)

        def open_images_folder():
            open_folder(state.image_dir)

        def open_settings():
            prior_values = {
                "DisplayColumns": CFG.DisplayColumns,
                "EnableUncrop": CFG.EnableUncrop,
                "VibranceBump": CFG.VibranceBump,
                "MaxDPI": CFG.MaxDPI,
                "DefaultPageSize": CFG.DefaultPageSize,
                "HighResBackendURL": CFG.HighResBackendURL,
                "HighResCacheTTLSeconds": CFG.HighResCacheTTLSeconds,
                "HighResSearchCacheMemoryMB": CFG.HighResSearchCacheMemoryMB,
                "HighResImageCacheMemoryMB": CFG.HighResImageCacheMemoryMB,
            }
            dialog = SettingsDialog(self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            dialog.apply()
            if prior_values["DisplayColumns"] != CFG.DisplayColumns:
                self.window().refresh(state, img_dict)
            elif (
                prior_values["VibranceBump"] != CFG.VibranceBump
                or prior_values["DefaultPageSize"] != CFG.DefaultPageSize
            ):
                self.window().refresh_preview(state, img_dict)

        def add_single_card(checked=False, *, on_added=None):
            dialog = AddCardDialog(self, state.image_dir)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            selected_card = dialog.selected_card()
            if selected_card is None:
                return

            snapshot = ProjectState.from_dict(state.to_dict()) if on_added else None
            workflow_result = None
            add_error = None

            def add_work():
                nonlocal workflow_result, add_error
                try:
                    workflow_result = deck_import_service.import_single_card_into_project(
                        state,
                        img_dict,
                        state.image_dir,
                        selected_card,
                        make_popup_print_fn(add_window),
                        warn_fn=application.warn_nonfatal,
                        art_candidate=dialog.selected_art_candidate(),
                        art_source=dialog.selected_art_source(),
                        backend_url=CFG.HighResBackendURL,
                    )
                except (OSError, ValueError) as exc:
                    add_error = exc

            self.window().setEnabled(False)
            add_window = popup(
                self.window(), "Adding card...", application._debug_mode
            )
            add_window.show_during_work(add_work)
            del add_window
            self.window().setEnabled(True)

            if on_added is not None:
                if workflow_result is not None and add_error is None:
                    try:
                        on_added(workflow_result)
                    except ValueError as exc:
                        add_error = exc
                if add_error is not None:
                    state.copy_from(snapshot)

            if workflow_result is not None or add_error is not None:
                self.window().refresh(state, img_dict)

            if add_error is not None:
                application.warn_nonfatal("Add Card Failed", str(add_error))
                return

            if workflow_result is None:
                return

            if on_added is not None:
                return
            autosave_managed_session()

            art_message = (
                "Custom art was applied."
                if workflow_result.art_candidate is not None
                else "Default Scryfall art was kept."
            )
            QMessageBox.information(
                self,
                "Card Added",
                (
                    f"Added `{workflow_result.selected_card.name}` with quantity 1.\n\n"
                    f"{art_message}\n\n"
                    "Next step: click 'Prepare Images' if needed, then check the Preview tab."
                ),
            )

        def import_decklist_images():
            dialog = DeckImportDialog(self, state.image_dir)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            deck_text = dialog.deck_text()
            deck_url = dialog.deck_url()
            import_result = None
            import_error = None

            def import_work():
                nonlocal import_result, import_error
                try:
                    workflow_result = deck_import_service.import_into_project(
                        state,
                        img_dict,
                        state.image_dir,
                        make_popup_print_fn(import_window),
                        deck_text=deck_text,
                        deck_url=deck_url,
                        warn_fn=application.warn_nonfatal,
                    )
                    import_result = workflow_result.import_result
                except (OSError, ValueError) as exc:
                    import_error = exc
                    return

            self.window().setEnabled(False)
            import_window = popup(
                self.window(), "Importing cards...", application._debug_mode
            )
            import_window.show_during_work(import_work)
            del import_window
            self.window().setEnabled(True)

            if import_error is not None:
                application.warn_nonfatal(
                    "Card Import Failed",
                    str(import_error),
                )
                return

            if import_result is None:
                return

            if import_result.imported:
                self.window().refresh(state, img_dict)
                if hasattr(application, "show_status"):
                    application.show_status(
                        f"Imported {import_result.imported_count} cards"
                    )

            if import_result.imported:
                show_card_import_complete(self, import_result)
            else:
                failure_lines = ["No cards were imported."]
                if import_result.failed_cards:
                    failure_lines.append(
                        f"Failed to import {len(import_result.failed_cards)} card(s):\n"
                        + failed_cards_decklist_text(import_result.failed_cards)
                    )
                if import_result.unmatched_lines:
                    failure_lines.append(
                        "Unmatched lines:\n" + "\n".join(import_result.unmatched_lines)
                    )
                application.warn_nonfatal(
                    "Card Import Failed", "\n\n".join(failure_lines)
                )

        def clear_old_cards():
            confirm = QMessageBox.question(
                self,
                "Remove Old Card Images",
                (
                    "Remove all card images from the current image folder and its crop folder?\n\n"
                    "This is meant for cleaning out an old batch before starting over.\n"
                    "The default card back will be kept."
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return

            try:
                project_service.clear_old_cards(state, img_dict)
            except OSError as exc:
                application.warn_nonfatal(
                    "Remove Old Card Images Failed",
                    f"The old card images could not be fully removed.\n\n{exc}",
                )
                return

            self.window().refresh(state, img_dict)
            QMessageBox.information(
                self,
                "Old Card Images Removed",
                "The old card images were removed.\n\nYou can now import cards or choose a different image folder.",
            )

        render_button.clicked.connect(render)
        cropper_button.clicked.connect(run_cropper)
        home_button.clicked.connect(application.show_home)
        save_button.clicked.connect(save_project)
        load_button.clicked.connect(load_project)
        set_images_button.clicked.connect(set_images_folder)
        open_images_button.clicked.connect(open_images_folder)
        settings_button.clicked.connect(open_settings)
        add_card_button.clicked.connect(add_single_card)
        import_decklist_button.clicked.connect(import_decklist_images)
        clear_cards_button.clicked.connect(clear_old_cards)

        self._cropper_button = cropper_button
        self._render_button = render_button
        self._home_button = home_button
        self._save_button = save_button
        self._load_button = load_button
        self._set_images_button = set_images_button
        self._open_images_button = open_images_button
        self._settings_button = settings_button
        self._add_card_button = add_card_button
        self._add_single_card = add_single_card
        self._import_button = import_decklist_button
        self._clear_cards_button = clear_cards_button
        self._rebuild_after_cropper = False
        self._img_dict = img_dict


class PrintOptionsWidget(QGroupBox):
    def __init__(self, print_dict, img_dict):
        super().__init__()
        state = as_project_state(print_dict)

        self.setTitle("PDF Settings")

        description = QLabel(
            "These settings control the PDF file name, paper size, page direction, and guide lines."
        )
        description.setWordWrap(True)

        print_output = LineEditWithLabel("PDF &Name", state.filename)
        paper_size = ComboBoxWithLabel(
            "&Paper Size", list(page_sizes.keys()), state.pagesize
        )
        orientation = ComboBoxWithLabel(
            "&Orientation", ["Landscape", "Portrait"], state.orient
        )
        guides_checkbox = QCheckBox("Extended Guides")
        guides_checkbox.setChecked(state.extended_guides)

        layout = QVBoxLayout()
        layout.addWidget(description)
        layout.addWidget(print_output)
        layout.addWidget(paper_size)
        layout.addWidget(orientation)
        layout.addWidget(guides_checkbox)

        self.setLayout(layout)

        def change_output(t):
            state.filename = t

        def change_papersize(t):
            state.pagesize = t
            self.window().refresh_preview(state, img_dict)

        def change_orientation(t):
            state.orient = t
            self.window().refresh_preview(state, img_dict)

        def change_guides(s):
            enabled = s == QtCore.Qt.CheckState.Checked
            state.extended_guides = enabled

        print_output._widget.textChanged.connect(change_output)
        paper_size._widget.currentTextChanged.connect(change_papersize)
        orientation._widget.currentTextChanged.connect(change_orientation)
        guides_checkbox.checkStateChanged.connect(change_guides)

        self._print_output = print_output._widget
        self._paper_size = paper_size._widget
        self._orientation = orientation._widget
        self._guides_checkbox = guides_checkbox

    def refresh_widgets(self, print_dict):
        state = as_project_state(print_dict)
        self._print_output.setText(state.filename)
        self._paper_size.setCurrentText(state.pagesize)
        self._orientation.setCurrentText(state.orient)
        self._guides_checkbox.setChecked(state.extended_guides)


class BacksidePreview(QWidget):
    def __init__(self, backside_name, img_dict):
        super().__init__()

        self.setLayout(QVBoxLayout())
        self.refresh(backside_name, img_dict)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def refresh(self, backside_name, img_dict):
        backside_default_image = BacksideImage(backside_name, img_dict)

        backside_width = 120
        backside_height = backside_default_image.heightForWidth(backside_width)
        backside_default_image.setFixedWidth(backside_width)
        backside_default_image.setFixedHeight(backside_height)

        backside_default_label = QLabel(backside_name)

        layout = self.layout()
        for i in reversed(range(layout.count())):
            layout.itemAt(i).widget().setParent(None)

        layout.addWidget(backside_default_image)
        layout.addWidget(backside_default_label)
        layout.setAlignment(
            backside_default_image, QtCore.Qt.AlignmentFlag.AlignHCenter
        )
        layout.setAlignment(
            backside_default_label, QtCore.Qt.AlignmentFlag.AlignHCenter
        )
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)


class CardOptionsWidget(QGroupBox):
    def __init__(self, print_dict, img_dict):
        super().__init__()
        state = as_project_state(print_dict)

        self.setTitle("Card Settings")

        description = QLabel(
            "Use these settings to adjust bleed, card backs, and oversized card handling."
        )
        description.setWordWrap(True)

        advanced_note = QLabel(
            "Most projects can leave these off. Turn them on only if your cards need backs or oversized printing."
        )
        advanced_note.setWordWrap(True)

        bleed_edge_spin = QDoubleSpinBox()
        bleed_edge_spin.setDecimals(2)
        bleed_edge_spin.setRange(0, inch_to_mm(0.12))
        bleed_edge_spin.setSingleStep(0.1)
        bleed_edge_spin.setSuffix("mm")
        bleed_edge_spin.setValue(float(state.bleed_edge))
        bleed_edge = WidgetWithLabel("&Bleed Edge", bleed_edge_spin)

        bleed_back_divider = QFrame()
        bleed_back_divider.setFrameShape(QFrame.Shape.HLine)
        bleed_back_divider.setFrameShadow(QFrame.Shadow.Sunken)

        backside_enabled = state.backside_enabled
        backside_checkbox = QCheckBox("Print Card Backs")
        backside_checkbox.setChecked(backside_enabled)
        backside_checkbox.setToolTip(
            "Turn this on only if you want separate back pages in the final PDF."
        )

        backside_pages_at_end_checkbox = QCheckBox("Put Back Pages At End")
        backside_pages_at_end_checkbox.setChecked(state.backside_pages_at_end)
        backside_pages_at_end_checkbox.setToolTip(
            "Put all front pages first, then all matching back pages in order."
        )

        backside_separate_file_checkbox = QCheckBox("Export Card Backs As Separate PDF")
        backside_separate_file_checkbox.setChecked(state.backside_separate_file)
        backside_separate_file_checkbox.setToolTip(
            "Save back pages to a second file ending in _backs.pdf."
        )

        backside_reverse_page_order_checkbox = QCheckBox("Reverse Back Page Order")
        backside_reverse_page_order_checkbox.setChecked(
            state.backside_reverse_page_order
        )
        backside_reverse_page_order_checkbox.setToolTip(
            "Export the last backside sheet first, which can help with manual duplex printing."
        )

        backside_default_button = QPushButton("Choose Default Back")
        backside_default_preview = BacksidePreview(
            state.backside_default, img_dict
        )
        backside_default_button.setToolTip(
            "Choose the back image used for cards that do not have a custom back."
        )

        backside_offset_spin = QDoubleSpinBox()
        backside_offset_spin.setDecimals(2)
        backside_offset_spin.setRange(-inch_to_mm(0.3), inch_to_mm(0.3))
        backside_offset_spin.setSingleStep(0.1)
        backside_offset_spin.setSuffix("mm")
        backside_offset_spin.setValue(float(state.backside_offset))
        backside_offset = WidgetWithLabel("Back &Offset", backside_offset_spin)
        backside_offset.setToolTip(
            "Adjust this only if front and back pages print slightly misaligned."
        )

        backside_default_button.setEnabled(backside_enabled)
        backside_default_preview.setEnabled(backside_enabled)
        backside_offset.setEnabled(backside_enabled)
        backside_pages_at_end_checkbox.setEnabled(backside_enabled)
        backside_separate_file_checkbox.setEnabled(backside_enabled)
        backside_reverse_page_order_checkbox.setEnabled(backside_enabled)

        back_over_divider = QFrame()
        back_over_divider.setFrameShape(QFrame.Shape.HLine)
        back_over_divider.setFrameShadow(QFrame.Shadow.Sunken)

        oversized_enabled = state.oversized_enabled
        oversized_checkbox = QCheckBox("Allow Oversized Cards")
        oversized_checkbox.setChecked(oversized_enabled)
        oversized_checkbox.setToolTip(
            "Turn this on only if some cards need a larger print size."
        )

        layout = QVBoxLayout()
        layout.addWidget(description)
        layout.addWidget(advanced_note)
        layout.addWidget(bleed_edge)
        layout.addWidget(bleed_back_divider)
        layout.addWidget(backside_checkbox)
        layout.addWidget(backside_pages_at_end_checkbox)
        layout.addWidget(backside_separate_file_checkbox)
        layout.addWidget(backside_reverse_page_order_checkbox)
        layout.addWidget(backside_default_button)
        layout.addWidget(backside_default_preview)
        layout.addWidget(backside_offset)
        layout.addWidget(back_over_divider)
        layout.addWidget(oversized_checkbox)

        layout.setAlignment(
            backside_default_preview, QtCore.Qt.AlignmentFlag.AlignHCenter
        )

        self.setLayout(layout)

        def change_bleed_edge(v):
            state.bleed_edge = v
            self.window().refresh_preview(state, img_dict)

        def switch_backside_enabled(s):
            enabled = s == QtCore.Qt.CheckState.Checked
            state.backside_enabled = enabled
            backside_default_button.setEnabled(enabled)
            backside_offset.setEnabled(enabled)
            backside_default_preview.setEnabled(enabled)
            backside_pages_at_end_checkbox.setEnabled(enabled)
            backside_separate_file_checkbox.setEnabled(enabled)
            backside_reverse_page_order_checkbox.setEnabled(enabled)
            self.window().refresh(state, img_dict)

        def switch_backside_pages_at_end(s):
            enabled = s == QtCore.Qt.CheckState.Checked
            state.backside_pages_at_end = enabled
            self.window().refresh_preview(state, img_dict)

        def switch_backside_separate_file(s):
            state.backside_separate_file = s == QtCore.Qt.CheckState.Checked

        def switch_backside_reverse_page_order(s):
            state.backside_reverse_page_order = (
                s == QtCore.Qt.CheckState.Checked
            )
            self.window().refresh_preview(state, img_dict)

        def pick_backside():
            default_backside_choice = image_file_dialog(self, state.image_dir)
            if default_backside_choice is not None:
                state.backside_default = default_backside_choice
                backside_default_preview.refresh(
                    state.backside_default, img_dict
                )
                self.window().refresh(state, img_dict)

        def change_backside_offset(v):
            state.backside_offset = v
            self.window().refresh_preview(state, img_dict)

        def switch_oversized_enabled(s):
            enabled = s == QtCore.Qt.CheckState.Checked
            state.oversized_enabled = enabled
            self.window().refresh(state, img_dict)

        bleed_edge_spin.valueChanged.connect(change_bleed_edge)
        backside_checkbox.checkStateChanged.connect(switch_backside_enabled)
        backside_pages_at_end_checkbox.checkStateChanged.connect(switch_backside_pages_at_end)
        backside_separate_file_checkbox.checkStateChanged.connect(switch_backside_separate_file)
        backside_reverse_page_order_checkbox.checkStateChanged.connect(
            switch_backside_reverse_page_order
        )
        backside_default_button.clicked.connect(pick_backside)
        backside_offset_spin.valueChanged.connect(change_backside_offset)
        oversized_checkbox.checkStateChanged.connect(switch_oversized_enabled)

        self._bleed_edge_spin = bleed_edge_spin
        self._backside_checkbox = backside_checkbox
        self._backside_pages_at_end_checkbox = backside_pages_at_end_checkbox
        self._backside_separate_file_checkbox = backside_separate_file_checkbox
        self._backside_reverse_page_order_checkbox = backside_reverse_page_order_checkbox
        self._backside_offset_spin = backside_offset_spin
        self._backside_default_preview = backside_default_preview
        self._oversized_checkbox = oversized_checkbox

    def refresh_widgets(self, print_dict):
        state = as_project_state(print_dict)
        self._bleed_edge_spin.setValue(float(state.bleed_edge))
        self._backside_checkbox.setChecked(state.backside_enabled)
        self._backside_pages_at_end_checkbox.setChecked(state.backside_pages_at_end)
        self._backside_pages_at_end_checkbox.setEnabled(state.backside_enabled)
        self._backside_offset_spin.setValue(float(state.backside_offset))
        self._oversized_checkbox.setChecked(state.oversized_enabled)

    def refresh(self, print_dict, img_dict):
        state = as_project_state(print_dict)
        self._backside_default_preview.refresh(state.backside_default, img_dict)


class GlobalOptionsWidget(QGroupBox):
    def __init__(self, print_dict, img_dict):
        super().__init__()
        state = as_project_state(print_dict)

        self.setTitle("App Settings")

        description = QLabel(
            f"Open the settings window to edit app-wide options stored in {os.path.join(cwd, 'config.ini')}."
        )
        description.setWordWrap(True)

        secondary_description = QLabel(
            "This is where you adjust how the app behaves overall, such as card grid size and image-processing defaults."
        )
        secondary_description.setWordWrap(True)

        open_settings_button = QPushButton("Open Settings")

        layout = QVBoxLayout()
        layout.addWidget(description)
        layout.addWidget(secondary_description)
        layout.addWidget(open_settings_button)
        self.setLayout(layout)

        def open_settings():
            prior_values = {
                "DisplayColumns": CFG.DisplayColumns,
                "VibranceBump": CFG.VibranceBump,
                "DefaultPageSize": CFG.DefaultPageSize,
            }
            dialog = SettingsDialog(self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            dialog.apply()
            if prior_values["DisplayColumns"] != CFG.DisplayColumns:
                self.window().refresh(state, img_dict)
            elif (
                prior_values["VibranceBump"] != CFG.VibranceBump
                or prior_values["DefaultPageSize"] != CFG.DefaultPageSize
            ):
                self.window().refresh_preview(state, img_dict)

        open_settings_button.clicked.connect(open_settings)


class OptionsWidget(QWidget):
    def __init__(
        self,
        application,
        print_dict,
        img_dict,
    ):
        super().__init__()
        state = as_project_state(print_dict)

        actions_widget = ActionsWidget(
            application,
            state,
            img_dict,
        )
        print_options = PrintOptionsWidget(state, img_dict)
        card_options = CardOptionsWidget(state, img_dict)
        global_options = GlobalOptionsWidget(state, img_dict)

        heading = QLabel("Print Settings")
        heading.setProperty("role", "title")
        helper = QLabel("Paper, backs, bleed, and application preferences.")
        helper.setProperty("role", "muted")
        helper.setWordWrap(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        # ActionsWidget owns the established workflow callbacks. Keep it in the
        # Qt parent hierarchy so self.window() continues to resolve to the app
        # shell, while its controls are presented by EditorPage's command bar.
        layout.addWidget(actions_widget)
        actions_widget.hide()
        layout.addWidget(heading)
        layout.addWidget(helper)
        layout.addWidget(print_options)
        layout.addWidget(card_options)
        layout.addWidget(global_options)
        layout.addStretch()

        self.setLayout(layout)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self._print_options = print_options
        self._card_options = card_options
        self._actions_widget = actions_widget

    def refresh_widgets(self, print_dict):
        self._print_options.refresh_widgets(print_dict)
        self._card_options.refresh_widgets(print_dict)

    def refresh(self, print_dict, img_dict):
        self._card_options.refresh(print_dict, img_dict)


class CardTabs(QTabWidget):
    def __init__(self, print_dict, img_dict, scroll_area, print_preview):
        super().__init__()
        self._state = as_project_state(print_dict)
        self._img_dict = img_dict
        self._print_preview = print_preview

        self.addTab(scroll_area, "Cards")
        self.addTab(print_preview, "Preview")

        def current_changed(i):
            if i == self.indexOf(self._print_preview):
                self._refresh_print_preview(force=True)

        self.currentChanged.connect(current_changed)

    def _refresh_print_preview(self, force=False):
        if isinstance(self._print_preview, LazyPrintPreview):
            self._print_preview.refresh(self._state, self._img_dict, force=force)
        elif force:
            self._print_preview.refresh(self._state, self._img_dict)

    def refresh_preview(self, print_dict, img_dict):
        self._state = as_project_state(print_dict)
        self._img_dict = img_dict
        if isinstance(self._print_preview, LazyPrintPreview):
            self._refresh_print_preview(
                force=self.currentIndex() == self.indexOf(self._print_preview)
            )
        else:
            self._print_preview.refresh(self._state, self._img_dict)


class ProjectTileWidget(QWidget):
    open_requested = QtCore.pyqtSignal(str)
    delete_requested = QtCore.pyqtSignal(str)
    rename_requested = QtCore.pyqtSignal(str)
    duplicate_requested = QtCore.pyqtSignal(str)

    def __init__(self, project_entry):
        super().__init__()
        self.setMouseTracking(True)
        self._project_id = project_entry.get("id")

        thumbnail = QLabel()
        thumbnail.setPixmap(project_thumbnail_pixmap(project_entry.get("thumbnail_path")))
        thumbnail.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        thumbnail.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        modified = project_entry.get("modified_at") or project_entry.get("last_opened_at")
        modified_text = "Unknown"
        if modified:
            try:
                modified_text = (
                    datetime.datetime.fromisoformat(modified).astimezone().strftime("%Y-%m-%d %H:%M")
                )
            except ValueError:
                modified_text = modified

        title = QLabel(project_entry.get("display_name", "Untitled Project"))
        title.setWordWrap(True)
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-weight: bold;")
        title.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        card_count = project_entry.get("card_count", 0)
        print_count = project_entry.get("print_count", 0)
        subtitle = QLabel(f"{card_count} cards  |  {print_count} prints\nUpdated {modified_text}")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        subtitle.setProperty("role", "muted")
        subtitle.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(thumbnail)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        self.setLayout(layout)
        self.setFixedSize(220, 252)
        self.setObjectName("projectTile")
        self.setStyleSheet(
            "QWidget#projectTile { background-color: #171b22; border: 1px solid #303743; border-radius: 9px; }"
            "QWidget#projectTile:hover { background-color: #1d222b; border-color: #566273; }"
        )

        delete_button = QPushButton("X", self)
        delete_button.setFixedSize(24, 24)
        delete_button.setToolTip("Delete this project")
        delete_button.setProperty("buttonRole", "danger")
        delete_button.hide()
        delete_button.clicked.connect(
            lambda: self.delete_requested.emit(self._project_id)
        )
        self._delete_button = delete_button
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

    def _show_menu(self, position):
        menu = QMenu(self)
        menu.addAction("Open project", lambda: self.open_requested.emit(self._project_id))
        menu.addAction("Rename…", lambda: self.rename_requested.emit(self._project_id))
        menu.addAction("Duplicate…", lambda: self.duplicate_requested.emit(self._project_id))
        menu.addSeparator()
        menu.addAction("Delete project…", lambda: self.delete_requested.emit(self._project_id))
        menu.exec(self.mapToGlobal(position))

    def enterEvent(self, event):
        super().enterEvent(event)
        self._delete_button.show()
        self._delete_button.raise_()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._delete_button.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._delete_button.move(self.width() - self._delete_button.width() - 6, 6)
        self._delete_button.raise_()

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.open_requested.emit(self._project_id)


class ProjectDashboardPage(QWidget):
    def __init__(self, application):
        super().__init__()

        self._application = application
        self._projects = []

        title = QLabel("Your projects")
        title.setProperty("role", "title")
        subtitle = QLabel(
            "Pick up where you left off or start a new print project."
        )
        subtitle.setWordWrap(True)

        empty_state = QLabel(
            "No projects yet\n\nStart a new project, then add a decklist or card images."
        )
        empty_state.setWordWrap(True)
        empty_state.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        empty_state.setFrameShape(QFrame.Shape.StyledPanel)
        empty_state.setStyleSheet("padding: 24px;")
        self._empty_state = empty_state

        project_list = QListWidget()
        project_list.setViewMode(QListWidget.ViewMode.IconMode)
        project_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        project_list.setMovement(QListWidget.Movement.Static)
        project_list.setSpacing(14)
        project_list.setIconSize(QtCore.QSize(120, 160))
        project_list.setGridSize(QtCore.QSize(234, 266))
        self._project_list = project_list

        import_button = QPushButton("Import Project")
        new_button = QPushButton("+ New Project")
        new_button.setProperty("buttonRole", "primary")
        new_button.setToolTip("Start a new project draft")

        import_button.clicked.connect(self.import_project)
        new_button.clicked.connect(application.open_blank_editor)

        top_row = QHBoxLayout()
        top_row.addWidget(title)
        top_row.addStretch()
        top_row.addWidget(import_button)
        top_row.addWidget(new_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(8)
        layout.addLayout(top_row)
        layout.addWidget(subtitle)
        layout.addSpacing(12)
        layout.addWidget(empty_state)
        layout.addWidget(project_list)
        self.setLayout(layout)

    def refresh_projects(self):
        self._projects = project_library.list_projects()
        self._project_list.clear()
        for project_entry in self._projects:
            item = QListWidgetItem()
            item.setData(QtCore.Qt.ItemDataRole.UserRole, project_entry.get("id"))
            item.setSizeHint(QtCore.QSize(234, 266))
            self._project_list.addItem(item)
            tile = ProjectTileWidget(project_entry)
            tile.open_requested.connect(self._application.open_managed_project)
            tile.delete_requested.connect(self.delete_project)
            tile.rename_requested.connect(self.rename_project)
            tile.duplicate_requested.connect(self.duplicate_project)
            self._project_list.setItemWidget(item, tile)

        has_projects = self._project_list.count() > 0
        self._empty_state.setVisible(not has_projects)
        self._project_list.setVisible(has_projects)

        if self._project_list.count() > 0:
            self._project_list.setCurrentRow(0)

    def selected_project_id(self):
        item = self._project_list.currentItem()
        if item is None:
            return None
        return item.data(QtCore.Qt.ItemDataRole.UserRole)

    def open_selected(self):
        project_id = self.selected_project_id()
        if project_id is None:
            return
        self._application.open_managed_project(project_id)

    def import_project(self):
        selected_path = project_file_dialog(
            self,
            FileDialogType.Open,
            project_library.projects_root(),
        )
        if selected_path is None or not os.path.exists(selected_path):
            return
        self._application.import_and_open_project(selected_path)
        self.refresh_projects()

    def delete_project(self, project_id):
        delete_project_with_confirmation(
            self, self._application, project_id, self.refresh_projects
        )

    def rename_project(self, project_id):
        entry = project_library.get_project(project_id)
        if entry is None:
            return
        name, accepted = QInputDialog.getText(
            self, "Rename Project", "Project name:", text=entry["display_name"]
        )
        if not accepted or not name.strip():
            return
        project_library.rename_project(project_id, name)
        self.refresh_projects()

    def duplicate_project(self, project_id):
        entry = project_library.get_project(project_id)
        if entry is None:
            return
        name, accepted = QInputDialog.getText(
            self,
            "Duplicate Project",
            "Name for the copy:",
            text=f"{entry['display_name']} Copy",
        )
        if not accepted or not name.strip():
            return
        project_library.duplicate_project(project_id, name)
        self.refresh_projects()



__all__ = [
    "ActionsWidget",
    "BacksidePreview",
    "CardGrid",
    "CardOptionsWidget",
    "CardScrollArea",
    "CardTabs",
    "CardWidget",
    "DummyCardWidget",
    "EditorPage",
    "GlobalOptionsWidget",
    "LazyPrintPreview",
    "OptionsWidget",
    "PageGrid",
    "PagePreview",
    "PrintOptionsWidget",
    "PrintPreview",
    "ProjectDashboardPage",
    "ProjectTileWidget",
    "WorkflowGuideWidget",
]
