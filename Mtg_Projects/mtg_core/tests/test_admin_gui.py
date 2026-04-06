from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox

from mtg_core.admin_service import CardAdminService
from mtg_core.db import CardDatabase
from mtg_core_gui.window import CoreAdminMainWindow


def _app():
    return QApplication.instance() or QApplication([])


def _window(tmp_path):
    database = CardDatabase(str(tmp_path / "gui.sqlite3"))
    service = CardAdminService(database=database)
    service.create_card(
        oracle_id="oracle-bolt",
        name="Lightning Bolt",
        layout="normal",
    )
    service.create_print(
        card_id="print-bolt",
        oracle_id="oracle-bolt",
        name="Lightning Bolt",
        set_code="lea",
        collector_number="161",
    )
    return CoreAdminMainWindow(service), service


def test_admin_window_opens_and_cards_tab_populates(tmp_path):
    app = _app()
    window, _service = _window(tmp_path)

    window.show()
    app.processEvents()

    assert window.cards_tab.table.rowCount() == 1
    assert window.prints_tab.table.rowCount() == 1
    assert "DB:" in window._db_label.text()


def test_selecting_and_saving_cards_and_prints_refreshes_forms(tmp_path, monkeypatch):
    app = _app()
    window, service = _window(tmp_path)

    window.cards_tab.table.selectRow(0)
    app.processEvents()
    assert window.cards_tab.name_edit.text() == "Lightning Bolt"

    window.cards_tab._new_card()
    window.cards_tab.name_edit.setText("Opt")
    window.cards_tab.oracle_id_edit.setText("oracle-opt")
    window.cards_tab.layout_edit.setText("normal")
    window.cards_tab._save_card()
    app.processEvents()
    assert any(card.oracle_id == "oracle-opt" for card in service.list_cards())

    window.prints_tab.table.selectRow(0)
    app.processEvents()
    assert window.prints_tab.card_id_edit.text() == "print-bolt"

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window.prints_tab._delete_print()
    app.processEvents()
    assert service.get_print("print-bolt") is None
