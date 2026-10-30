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
        assert all("Choose a commander" in label.text() for label in workspace.details)
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
