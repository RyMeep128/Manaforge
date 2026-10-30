"""Qt navigation regressions for CI. Opening Play must not start an engine."""

from types import SimpleNamespace as NS

import pytest
from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_play.setup import SavedDeck
from mtg_play.workspace import PlayWorkspace
from mtg_play.tests.test_presentation import drain


@pytest.fixture
def app():
    return W.QApplication.instance() or W.QApplication([])


def workspace_fixture(app, tmp_path):
    calls = []
    documents = (DeckDocument(), DeckDocument())
    for index, document in enumerate(documents):
        document.deck.name = "Saved deck " + str(index)
        document.deck.entries = [
            DeckEntry("land", "Forest", 60, card_id="selected-print")
        ]
    entries = tuple(
        SavedDeck(tmp_path / str(index), document, ())
        for index, document in enumerate(documents)
    )

    def forbidden_runtime():
        calls.append("engine")
        raise AssertionError("Navigation must not construct the runtime")

    workspace = PlayWorkspace(
        NS(database=object()),
        lambda: calls.append("home"),
        adapter_factory=forbidden_runtime,
        deck_provider=lambda: (entries, ()),
    )
    drain(app, lambda: not workspace.catalog_jobs.busy)
    return workspace, calls


@pytest.mark.parametrize("entry", ["play", "offline"])
def test_both_play_entries_require_format_before_shared_lobby(app, tmp_path, entry):
    workspace, calls = workspace_fixture(app, tmp_path)
    try:
        assert workspace.pages.currentWidget() is workspace.landing_page
        assert all(not selector.isEnabled() for selector in workspace.selectors)
        assert not workspace.start_button.isEnabled()
        if entry == "play":
            workspace.landing_page.play_button.click()
            assert workspace.pages.currentWidget() is workspace.mode_page
            workspace.mode_page.offline_button.click()
        else:
            workspace.landing_page.offline_button.click()
        assert workspace.pages.currentWidget() is workspace.format_page
        assert not workspace.format_continue.isEnabled()
        workspace.format_continue.click()
        assert workspace.pages.currentWidget() is workspace.format_page
        workspace.format_back.click()
        if entry == "play":
            assert workspace.pages.currentWidget() is workspace.mode_page
            workspace.mode_page.offline_button.click()
        else:
            assert workspace.pages.currentWidget() is workspace.landing_page
            workspace.landing_page.offline_button.click()
        workspace.format.setCurrentIndex(workspace.format.findData("freeform"))
        workspace.format_continue.click()
        assert workspace.pages.currentWidget() is workspace.setup_page
        assert all(selector.isEnabled() for selector in workspace.selectors)
        assert not workspace.start_button.isEnabled()
        for index, selector in enumerate(workspace.selectors):
            selector.setCurrentIndex(index + 1)
        assert workspace.start_button.isEnabled()
        assert workspace.lobby.format == "freeform"
        assert [seat.deck.deck_id for seat in workspace.lobby.seats] == [
            deck.document.deck.deck_id for deck in workspace._decks
        ]
        assert not calls and not workspace.session.active
    finally:
        workspace.close()


def test_unavailable_networking_and_home_navigation_do_not_create_runtime(
    app, tmp_path
):
    workspace, calls = workspace_fixture(app, tmp_path)
    try:
        for button in (
            workspace.landing_page.host_button,
            workspace.landing_page.join_button,
        ):
            assert not button.isEnabled()
            assert "Coming soon" in button.toolTip()
            button.click()
        assert workspace.pages.currentWidget() is workspace.landing_page
        workspace.home_button.click()
        assert calls == ["home"] and not workspace.session.active
    finally:
        workspace.close()


def test_return_and_cancel_format_change_preserve_selected_decks(app, tmp_path):
    workspace, calls = workspace_fixture(app, tmp_path)
    try:
        workspace.landing_page.offline_button.click()
        workspace.format.setCurrentIndex(workspace.format.findData("freeform"))
        workspace.format_continue.click()
        for index, selector in enumerate(workspace.selectors):
            selector.setCurrentIndex(index + 1)
        selected = tuple(selector.currentData() for selector in workspace.selectors)
        workspace.change_format.click()
        workspace.format.setCurrentIndex(workspace.format.findData("commander"))
        workspace.format_back.click()
        assert workspace.pages.currentWidget() is workspace.setup_page
        assert (
            workspace.lobby.format == "freeform" and workspace.start_button.isEnabled()
        )
        assert (
            tuple(selector.currentData() for selector in workspace.selectors)
            == selected
        )
        workspace.lobby_back.click()
        assert workspace.pages.currentWidget() is workspace.landing_page
        assert not workspace.start_button.isEnabled()
        workspace.start_game()
        assert not calls
        workspace.landing_page.offline_button.click()
        workspace.format_continue.click()
        assert (
            tuple(selector.currentData() for selector in workspace.selectors)
            == selected
        )
        assert workspace.start_button.isEnabled()
        workspace.change_format.click()
        workspace.format.setCurrentIndex(workspace.format.findData("commander"))
        workspace.format_continue.click()
        assert not workspace.start_button.isEnabled()
        assert (
            tuple(selector.currentData() for selector in workspace.selectors)
            == selected
        )
        assert all(
            "Choose a commander" in label.text() for label in workspace.readiness_labels
        )
        assert not calls
    finally:
        workspace.close()


@pytest.mark.parametrize("width,height", [(1280, 720), (1024, 768)])
def test_landing_primary_controls_remain_visible_at_desktop_sizes(
    app, tmp_path, width, height
):
    workspace, calls = workspace_fixture(app, tmp_path)
    try:
        workspace.resize(width, height)
        workspace.show()
        app.processEvents()
        viewport = workspace.landing_page.viewport()
        for button in (
            workspace.landing_page.play_button,
            workspace.landing_page.offline_button,
        ):
            assert button.isVisible()
            position = button.mapTo(viewport, C.QPoint(0, 0))
            assert viewport.rect().contains(C.QRect(position, button.size()))
        assert not calls
    finally:
        workspace.close()


def test_lobby_readiness_is_async_blocks_known_errors_and_keeps_shared_ownership(
    app, tmp_path
):
    calls, threads = [], []
    invalid = DeckDocument()
    shared = DeckDocument()
    shared.deck.name = "Friend's deck"
    shared.deck.entries = [DeckEntry("land", "Forest", 60, card_id="selected-print")]
    before = shared.to_dict()
    rows = (
        SavedDeck(tmp_path / "invalid", invalid, ()),
        SavedDeck(
            None,
            shared,
            (),
            source_id="followed:server:deck",
            owner_id="friend-owner",
            source_label="Shared cache: Friends - friend",
        ),
    )

    def local_records(entries):
        threads.append(C.QThread.currentThread())
        return {}

    def forbidden_engine():
        calls.append("engine")
        raise AssertionError("Known bad decks must not launch the engine")

    workspace = PlayWorkspace(
        NS(database=object(), get_deck_legality_data=local_records),
        lambda: None,
        adapter_factory=forbidden_engine,
        deck_provider=lambda: (rows, ()),
        browse_library=lambda: calls.append("library"),
    )
    try:
        drain(app, lambda: not workspace.catalog_jobs.busy)
        assert threads and all(thread is not app.thread() for thread in threads)
        workspace.landing_page.offline_button.click()
        workspace.format.setCurrentIndex(workspace.format.findData("freeform"))
        workspace.format_continue.click()
        workspace.shared_decks.click()
        assert calls == ["library"]
        workspace.selectors[0].setCurrentIndex(1)
        workspace.selectors[1].setCurrentIndex(2)
        assert not workspace.start_button.isEnabled()
        assert "Not eligible" in workspace.readiness_labels[0].text()
        workspace.start_game()
        assert calls == ["library"]
        workspace.selectors[0].setCurrentIndex(2)
        assert workspace.start_button.isEnabled()
        assert all(
            seat.deck.owner_id == "friend-owner" for seat in workspace.lobby.seats
        )
        assert all(
            seat.deck.source_id == "followed:server:deck"
            for seat in workspace.lobby.seats
        )
        assert shared.to_dict() == before
        selected_keys = tuple(
            workspace._decks[selector.currentData()].key
            for selector in workspace.selectors
        )
        workspace.reload.click()
        drain(app, lambda: not workspace.catalog_jobs.busy)
        assert (
            tuple(
                workspace._decks[selector.currentData()].key
                for selector in workspace.selectors
            )
            == selected_keys
        )
        assert all(
            seat.deck.owner_id == "friend-owner" for seat in workspace.lobby.seats
        )
        assert calls == ["library"]
    finally:
        workspace.close()


def test_shared_browse_opens_existing_library_module_and_preserves_play(
    app, tmp_path, monkeypatch
):
    from mtg_home.home import HomeWindow
    from mtg_home.launcher import ModuleController

    monkeypatch.setenv("MANAFORGE_ENABLE_LOCAL_PLAY", "1")
    monkeypatch.setenv("PRINT_PROXY_PREP_DATA_DIR", str(tmp_path))
    home = HomeWindow()
    controller = ModuleController(
        home, service=NS(database=object()), factories={"library": W.QWidget}
    )
    try:
        controller.open_module("play")
        workspace = controller.windows["play"]
        drain(app, lambda: not workspace.catalog_jobs.busy)
        workspace.landing_page.offline_button.click()
        workspace.format.setCurrentIndex(workspace.format.findData("freeform"))
        workspace.format_continue.click()
        workspace.shared_decks.click()
        assert home.current_workspace == "library"
        assert "library" in controller.windows and not workspace.session.active
        controller.open_module("play")
        assert controller.windows["play"] is workspace
        assert workspace.pages.currentWidget() is workspace.setup_page
        assert workspace.lobby.format == "freeform"
    finally:
        home.close()
