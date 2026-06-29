from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

PyQt6 = pytest.importorskip("PyQt6")
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication

from mtg_editor.decklist_io import read_decklist_file
from mtg_editor.gui import DeckEditorWidget, DeckEditorWindow
from mtg_editor.models import DeckProject


_QT_APP = None


@dataclass(frozen=True)
class FakeSearchResult:
    card_id: str
    oracle_id: str
    name: str
    set_code: str | None
    set_name: str | None
    collector_number: str | None
    preview_url: str | None
    thumbnail_url: str | None
    payload: dict


class FakeDatabase:
    def get_image_record(self, card_id, variant="default"):
        return SimpleNamespace(path=f"cache/{card_id}.png", asset_id=f"asset-{card_id}")


class FakeCardService:
    def __init__(self):
        self.database = FakeDatabase()

    def get_print(self, *, set_code, collector_number):
        return None

    def get_card(self, *, exact_name=None, oracle_id=None, card_id=None):
        if exact_name == "Opt":
            return _payload("sf-opt", "Opt", set_code="eld", collector_number="59")
        if exact_name == "Lightning Bolt":
            return _payload("sf-bolt", "Lightning Bolt", set_code="clu", collector_number="141")
        return None

    def search_cards(self, query, filters=None):
        if query == "Bolt":
            return [
                FakeSearchResult(
                    card_id="sf-bolt-clu",
                    oracle_id="oracle-bolt",
                    name="Lightning Bolt",
                    set_code="clu",
                    set_name="CLU Set",
                    collector_number="141",
                    preview_url=None,
                    thumbnail_url=None,
                    payload=_payload("sf-bolt-clu", "Lightning Bolt", set_code="clu", collector_number="141"),
                ),
                FakeSearchResult(
                    card_id="sf-bolt-2xm",
                    oracle_id="oracle-bolt",
                    name="Lightning Bolt",
                    set_code="2xm",
                    set_name="2XM Set",
                    collector_number="129",
                    preview_url=None,
                    thumbnail_url=None,
                    payload=_payload("sf-bolt-2xm", "Lightning Bolt", set_code="2xm", collector_number="129"),
                ),
            ]
        return []


def _qt_app():
    global _QT_APP
    app = QApplication.instance()
    if app is None:
        _QT_APP = QApplication([])
        return _QT_APP
    return app


def test_deck_editor_widget_renders_new_project_defaults():
    _qt_app()

    widget = DeckEditorWidget()

    assert widget.deck_name_edit.text() == "Untitled Deck"
    assert widget.format_edit.text() == "Custom"
    assert "Unique: 0" in widget.header_summary.text()
    assert "Copies: 0" in widget.header_summary.text()
    assert widget.table.rowCount() == 0
    assert widget.visual_view_checkbox.isChecked()
    assert widget.project.preferences.view_mode == "grid"
    assert widget.content_stack.currentWidget() is widget.visual_scroll
    assert widget.search_edit.placeholderText() == "Search local catalog"
    assert widget.objectName() == "deckEditorRoot"
    assert widget.deck_name_edit.objectName() == "deckBannerInput"
    assert widget.format_edit.objectName() == "deckBannerInput"
    assert widget.quick_add_edit.objectName() == "deckBannerInput"
    assert widget.quick_add_button.objectName() == "deckBannerPrimaryButton"
    assert widget.new_button.objectName() == "deckBannerButton"
    assert "QFrame#deckBanner" in widget.styleSheet()
    assert widget.stat_labels["unique"].text() == "Unique 0"
    assert widget.workspace_splitter.count() == 3
    assert widget.workspace_splitter.widget(1) is widget.content_stack
    assert widget.right_panel_tabs.count() == 2
    assert widget.right_panel_tabs.tabText(0) == "Inspect"
    assert widget.right_panel_tabs.tabText(1) == "Playtest"
    assert widget.visual_board_widget.objectName() == "visualBoard"
    assert widget.text_filter_edit.objectName() == "softInput"
    assert widget.search_edit.objectName() == "softInput"
    assert widget.status_label.objectName() == "statusPill"
    assert "#edf1f7" in widget.styleSheet()
    assert "#dbeafe" in widget.styleSheet()


def test_view_mode_toggle_switches_between_visual_and_text():
    _qt_app()
    widget = DeckEditorWidget()

    widget.visual_view_checkbox.setChecked(False)

    assert widget.project.preferences.view_mode == "text"
    assert widget.content_stack.currentWidget() is widget.table

    widget.visual_view_checkbox.setChecked(True)

    assert widget.project.preferences.view_mode == "grid"
    assert widget.content_stack.currentWidget() is widget.visual_scroll


def test_quick_add_updates_project_stats_and_table():
    _qt_app()
    widget = DeckEditorWidget(card_service=FakeCardService())

    widget.quick_add_edit.setText("4 Opt")
    widget.quick_add_button.click()

    assert len(widget.project.cards) == 1
    card = widget.project.cards[0]
    assert card.name == "Opt"
    assert card.quantity == 4
    assert card.catalog_card_id == "sf-opt"
    assert card.type_line == "Instant"
    assert widget.table.rowCount() == 1
    assert list(widget.visual_card_tiles) == [card.card_id]
    assert list(widget.visual_columns) == ["all"]
    assert widget.table.item(0, 1).text() == "4"
    assert widget.table.item(0, 2).text() == "Opt"
    assert "Copies: 4" in widget.header_summary.text()


def test_ambiguous_quick_add_populates_search_without_mutating_project():
    _qt_app()
    widget = DeckEditorWidget(card_service=FakeCardService())

    widget.quick_add_edit.setText("Bolt")
    widget.quick_add_button.click()

    assert widget.project.cards == []
    assert len(widget.search_candidates) == 2
    assert len(widget.search_result_rows) == 2
    assert "Choose one from Search" in widget.status_label.text()


def test_search_candidate_adds_card_and_selects_visual_tile():
    _qt_app()
    widget = DeckEditorWidget(card_service=FakeCardService())

    widget.search_edit.setText("Bolt")
    widget.search_button.click()
    widget.search_result_rows[0].candidateSelected.emit(widget.search_candidates[0])

    assert len(widget.project.cards) == 1
    card = widget.project.cards[0]
    assert card.name == "Lightning Bolt"
    assert card.catalog_card_id == "sf-bolt-clu"
    assert widget.selected_card_id == card.card_id
    assert card.card_id in widget.visual_card_tiles


def test_import_export_and_save_load_round_trip(tmp_path):
    _qt_app()
    widget = DeckEditorWidget(card_service=FakeCardService())
    decklist_path = tmp_path / "import.txt"
    export_path = tmp_path / "export.txt"
    project_path = tmp_path / "deck.json"
    decklist_path.write_text("2 Lightning Bolt", encoding="utf-8")

    widget.import_decklist_path(decklist_path)
    widget.visual_view_checkbox.setChecked(False)
    widget.save_project_file(project_path)
    widget.new_project("Other")
    widget.load_project_file(project_path)
    widget.export_decklist_path(export_path)

    assert widget.project_path == project_path
    assert widget.project.preferences.view_mode == "text"
    assert not widget.visual_view_checkbox.isChecked()
    assert widget.content_stack.currentWidget() is widget.table
    assert widget.project.cards[0].name == "Lightning Bolt"
    assert widget.project.cards[0].quantity == 2
    assert read_decklist_file(export_path) == "\n".join(
        [
            "Mainboard:",
            "2 Lightning Bolt (CLU) 141",
        ]
    )


def test_group_sort_and_filter_controls_change_visible_rows_without_quantities():
    _qt_app()
    project = DeckProject.new()
    project.add_card("Zebra", quantity=2, card_id="zebra", mana_value=3, colors=["G"], color_identity=["G"])
    project.add_card("Alpha", quantity=4, card_id="alpha", mana_value=1, colors=["R"], color_identity=["R"])
    widget = DeckEditorWidget(project=project)
    before = [(card.card_id, card.quantity) for card in widget.project.cards]

    widget.sort_combo.setCurrentIndex(widget.sort_combo.findData("mana_value"))
    widget.group_combo.setCurrentIndex(widget.group_combo.findData("color"))
    widget.text_filter_edit.setText("alpha")

    assert widget.table.rowCount() == 1
    assert widget.table.item(0, 0).text() == "Red"
    assert widget.table.item(0, 2).text() == "Alpha"
    assert widget.visible_card_ids == ["alpha"]
    assert list(widget.visual_card_tiles) == ["alpha"]
    assert list(widget.visual_columns) == ["red"]
    assert [(card.card_id, card.quantity) for card in widget.project.cards] == before


def test_selected_card_controls_update_quantity_section_category_and_tags():
    _qt_app()
    project = DeckProject.new()
    card_id = project.add_card("Opt", quantity=1, card_id="opt")
    category_id = project.create_category("Draw")
    widget = DeckEditorWidget(project=project)

    widget.visual_card_tiles[card_id].cardSelected.emit(card_id)
    widget.quantity_spin.setValue(3)
    widget.section_combo.setCurrentText("sideboard")
    widget.category_combo.setCurrentIndex(widget.category_combo.findData(category_id))
    widget.tags_edit.setText("Cantrip, Instant")
    widget.apply_card_button.click()

    card = widget.project.get_card(card_id)
    assert card.quantity == 3
    assert card.section == "sideboard"
    assert card.primary_category == category_id
    assert card.tags == ["Cantrip", "Instant"]
    assert widget.selected_card_id == card_id


def test_visual_tile_and_inspector_quantity_and_remove_actions():
    _qt_app()
    project = DeckProject.new()
    card_id = project.add_card("Opt", quantity=2, card_id="opt")
    widget = DeckEditorWidget(project=project)

    tile = widget.visual_card_tiles[card_id]
    tile.incrementRequested.emit(card_id)
    assert widget.project.get_card(card_id).quantity == 3

    widget.visual_card_tiles[card_id].decrementRequested.emit(card_id)
    assert widget.project.get_card(card_id).quantity == 2

    widget.visual_card_tiles[card_id].cardSelected.emit(card_id)
    widget.decrement_selected_button.click()
    assert widget.project.get_card(card_id).quantity == 1

    widget.remove_selected_button.click()
    assert widget.project.get_card(card_id) is None
    assert widget.selected_card_id is None


def test_visual_board_moves_cards_between_category_and_section_columns():
    _qt_app()
    project = DeckProject.new()
    card_id = project.add_card("Opt", quantity=1, card_id="opt")
    category_id = project.create_category("Draw")
    widget = DeckEditorWidget(project=project)

    widget.group_combo.setCurrentIndex(widget.group_combo.findData("category"))
    widget._move_card_to_group(card_id, category_id)

    card = widget.project.get_card(card_id)
    assert card.primary_category == category_id
    assert category_id in widget.visual_columns

    widget.group_combo.setCurrentIndex(widget.group_combo.findData("section"))
    widget._move_card_to_group(card_id, "sideboard")

    assert widget.project.get_card(card_id).section == "sideboard"
    assert "sideboard" in widget.visual_columns


def test_board_category_create_and_rename_helpers():
    _qt_app()
    widget = DeckEditorWidget()

    category_id = widget.create_category_from_board("Ramp")
    widget.rename_category_from_board(category_id, "Mana")

    assert widget.group_combo.currentData() == "category"
    assert widget._category_label(category_id) == "Mana"


def test_visual_tile_uses_local_image_when_available(tmp_path):
    _qt_app()
    image_path = tmp_path / "card.png"
    pixmap = QPixmap(32, 44)
    pixmap.fill(Qt.GlobalColor.red)
    assert pixmap.save(str(image_path))
    project = DeckProject.new()
    card_id = project.add_card("Image Card", quantity=1, card_id="image-card", local_image_path=str(image_path))

    widget = DeckEditorWidget(project=project)

    tile = widget.visual_card_tiles[card_id]
    assert tile.image_label.pixmap() is not None


def test_playtest_panel_actions_do_not_mutate_project_cards():
    _qt_app()
    project = DeckProject.new()
    project.add_card("Island", quantity=8, card_id="island", image_uri="https://img.test/island.png")
    widget = DeckEditorWidget(project=project)
    before = [(card.card_id, card.quantity, card.section) for card in widget.project.cards]

    widget.start_playtest_button.click()
    assert widget.playtest_hand_list.count() == 7
    assert "Hand: 7" in widget.playtest_summary_label.text()

    widget.draw_one_button.click()
    assert widget.playtest_hand_list.count() == 8
    assert "Drawn: 1" in widget.playtest_summary_label.text()

    widget.reset_playtest_button.click()
    assert widget.playtest_hand_list.count() == 7
    assert [(card.card_id, card.quantity, card.section) for card in widget.project.cards] == before


def test_deck_editor_window_hosts_editor_widget():
    _qt_app()

    window = DeckEditorWindow()

    assert isinstance(window.editor, DeckEditorWidget)
    assert window.windowTitle() == "MTG Deck Editor"


def _payload(card_id, name, *, set_code, collector_number):
    return {
        "id": card_id,
        "oracle_id": f"oracle-{card_id}",
        "name": name,
        "set": set_code,
        "set_name": f"{set_code.upper()} Set",
        "collector_number": collector_number,
        "type_line": "Instant",
        "mana_cost": "{U}",
        "cmc": 1,
        "colors": ["U"],
        "color_identity": ["U"],
        "image_uris": {
            "png": f"https://img.test/{card_id}.png",
            "normal": f"https://img.test/{card_id}-normal.jpg",
            "small": f"https://img.test/{card_id}-small.jpg",
        },
    }
