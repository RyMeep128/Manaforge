"""Qt navigation regressions for CI. Opening Play must not start an engine."""

from types import SimpleNamespace as NS

import pytest
from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_play.setup import SavedDeck
from mtg_play.workspace import PlayWorkspace
from mtg_play.tests.test_presentation import drain


@pytest.fixture(scope="session")
def navigation_application():
    return W.QApplication.instance() or W.QApplication([])


@pytest.fixture
def app(navigation_application):
    application = navigation_application
    workspaces = application._navigation_workspaces = []
    yield application
    for workspace in workspaces:

        def stopped():
            ready = workspace.prepare_to_close()
            return ready and not workspace.busy

        drain(application, stopped)
        workspace.loading_timer.stop()
        workspace.close()
        workspace.deleteLater()
    application.sendPostedEvents(None, C.QEvent.Type.DeferredDelete)
    application.processEvents()
    del application._navigation_workspaces


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
    app._navigation_workspaces.append(workspace)
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


def test_randomize_gates_setup_until_verified_runtime_cleanup(app, tmp_path):
    from threading import Event

    workspace, calls = workspace_fixture(app, tmp_path)
    gate, entered = Event(), Event()
    closed = []

    def validate(document, format, **kwargs):
        entered.set()
        assert gate.wait(5)
        return True

    class Runtime:
        def __enter__(self):
            return self

        validate_deck = staticmethod(validate)

        def close(self):
            closed.append(True)

    workspace.opponents.factory = Runtime
    try:
        workspace.landing_page.offline_button.click()
        workspace.format.setCurrentIndex(workspace.format.findData("freeform"))
        workspace.format_continue.click()
        workspace.selectors[0].setCurrentIndex(1)
        workspace.selectors[1].setCurrentIndex(1)
        assert workspace.start_button.isEnabled()
        workspace.randomize.click()
        drain(app, entered.is_set)
        assert not workspace.start_button.isEnabled()
        assert not workspace.change_format.isEnabled()
        assert not workspace.reload.isEnabled()
        assert not any(selector.isEnabled() for selector in workspace.selectors)
        workspace._show_page(workspace.landing_page)
        assert workspace.pages.currentWidget() is workspace.loading_page
        assert "opponent" in workspace.loading_title.text().lower()
        assert workspace.loading_bar.maximum() == 0
        assert workspace.loading_cancel.isEnabled()
        gate.set()
        drain(app, lambda: not workspace.opponents.busy)
        assert workspace.selectors[1].currentData() == 1
        assert (
            workspace.lobby.seats[1].deck.deck_id
            == workspace._decks[1].document.deck.deck_id
        )
        assert closed and not calls and workspace.start_button.isEnabled()
    finally:
        gate.set()
        drain(app, lambda: not workspace.opponents.jobs.busy)
        workspace.close()


def test_missing_artwork_return_preserves_choices_and_continue_uses_frozen_service(
    app, tmp_path
):
    workspace, calls = workspace_fixture(app, tmp_path)
    starts = []
    workspace.session.start = lambda setup, decks, **kwargs: (
        starts.append((setup, decks)) or False
    )
    try:
        workspace.landing_page.offline_button.click()
        workspace.format.setCurrentIndex(workspace.format.findData("freeform"))
        workspace.format_continue.click()
        workspace.selectors[0].setCurrentIndex(1)
        workspace.selectors[1].setCurrentIndex(2)
        chosen = workspace.lobby.selected_documents()
        workspace.start_button.click()
        drain(
            app,
            lambda: (
                not workspace.asset_jobs.busy
                and not workspace.asset_continue.isHidden()
            ),
        )
        assert not starts and not calls and not workspace.start_button.isEnabled()
        assert "Forest" in workspace.asset_missing.toPlainText()
        workspace.asset_return.click()
        assert workspace.pages.currentWidget() is workspace.setup_page
        assert workspace.lobby.selected_documents() == chosen
        assert workspace.start_button.isEnabled()
        workspace.start_button.click()
        drain(
            app,
            lambda: (
                not workspace.asset_jobs.busy
                and not workspace.asset_continue.isHidden()
            ),
        )
        workspace.asset_continue.click()
        assert len(starts) == 1 and not calls
        assert tuple(doc.to_dict() for doc in starts[0][1]) == tuple(
            doc.to_dict() for doc in chosen
        )
        assert all(copy is not original for copy, original in zip(starts[0][1], chosen))
        assert workspace.table.artwork.service.get_image_path("unknown") is None
    finally:
        workspace._return_from_assets()
        drain(app, lambda: not workspace.asset_jobs.busy)
        workspace.close()


def test_fully_cached_artwork_starts_without_missing_warning(
    app, tmp_path, monkeypatch
):
    from mtg_play.tests.test_artwork_cache import source

    monkeypatch.setenv("PRINT_PROXY_PREP_DATA_DIR", str(tmp_path / "data"))
    workspace, calls = workspace_fixture(app, tmp_path)
    path = source(tmp_path / "front.png")
    workspace.service.get_image_path = lambda *args, **kwargs: str(path)
    workspace.service.get_card = lambda **kwargs: {"layout": "normal"}
    starts = []
    workspace.session.start = lambda *args, **kwargs: starts.append(args) or False
    try:
        workspace.landing_page.offline_button.click()
        workspace.format.setCurrentIndex(workspace.format.findData("freeform"))
        workspace.format_continue.click()
        workspace.selectors[0].setCurrentIndex(1)
        workspace.selectors[1].setCurrentIndex(2)
        workspace.start_button.click()
        drain(app, lambda: bool(starts) and not workspace.asset_jobs.busy)
        assert workspace.asset_continue.isHidden() and not calls
        assert workspace.table.artwork.service.get_image_path("selected-print") == str(
            path.resolve()
        )
    finally:
        workspace.close()


def test_cancelling_artwork_waits_for_worker_and_keeps_lobby_selection(
    app, tmp_path, monkeypatch
):
    from threading import Event

    workspace, calls = workspace_fixture(app, tmp_path)
    entered, release = Event(), Event()

    def prepare(documents, service, *, cancel, report):
        entered.set()
        assert release.wait(5)
        assert cancel.is_set()
        return None

    monkeypatch.setattr("mtg_play.workspace.prepare_assets", prepare)
    try:
        workspace.landing_page.offline_button.click()
        workspace.format.setCurrentIndex(workspace.format.findData("freeform"))
        workspace.format_continue.click()
        workspace.selectors[0].setCurrentIndex(1)
        workspace.selectors[1].setCurrentIndex(2)
        chosen = workspace.lobby.selected_documents()
        workspace.start_button.click()
        drain(app, entered.is_set)
        workspace.asset_return.click()
        assert workspace.busy and not workspace.start_button.isEnabled()
        release.set()
        drain(
            app,
            lambda: workspace._asset_pending is None and not workspace.asset_jobs.busy,
        )
        assert workspace.pages.currentWidget() is workspace.setup_page
        assert workspace.lobby.selected_documents() == chosen and not calls
    finally:
        release.set()
        drain(app, lambda: not workspace.asset_jobs.busy)
        workspace.close()


@pytest.mark.parametrize("maximized", [False, True])
def test_focused_view_restores_previous_window_mode(app, tmp_path, maximized):
    workspace, calls = workspace_fixture(app, tmp_path)
    workspace.resize(1000, 720)
    workspace.show()
    if maximized:
        workspace.showMaximized()
    app.processEvents()
    try:
        workspace._enter_focused_view()
        app.processEvents()
        assert workspace.isMaximized()
        assert workspace.intro.isHidden() and workspace.workspace_title.isHidden()
        workspace._leave_focused_view()
        app.processEvents()
        assert workspace.isMaximized() == maximized
        assert not workspace.intro.isHidden() and workspace._window_snapshot is None
        assert not calls
    finally:
        workspace.close()


def test_setup_actions_are_adjacent_and_start_explains_blocking_deck(app, tmp_path):
    from dataclasses import replace
    from mtg_play.readiness import DeckReadiness

    workspace, calls = workspace_fixture(app, tmp_path)
    try:
        workspace.landing_page.offline_button.click()
        workspace.resize(1280, 850)
        workspace.show()
        workspace.format.setCurrentIndex(workspace.format.findData("freeform"))
        app.processEvents()
        assert workspace.format_continue.mapTo(workspace, C.QPoint()).y() < 450
        workspace.format_continue.click()
        workspace.selectors[0].setCurrentIndex(1)
        bad = DeckReadiness(
            "freeform",
            "blocked",
            ("Unsupported deck sections: planar.",),
            ("UNSUPPORTED_SECTION",),
        )
        workspace._decks = (
            workspace._decks[0],
            replace(workspace._decks[1], checks=(bad,)),
        )
        workspace.selectors[1].setCurrentIndex(2)
        app.processEvents()
        assert not workspace.start_button.isEnabled()
        assert (
            "Opponent" in workspace.start_reason.text()
            and "planar" in workspace.start_reason.text()
        )
        assert workspace.start_button.toolTip() == workspace.start_reason.text()
        assert (
            workspace.start_button.mapTo(workspace, C.QPoint()).y()
            < workspace.height() - 100
        )
        assert not calls
    finally:
        workspace.close()


def test_match_loading_waits_for_authorized_opening_snapshot(app, tmp_path):
    from mtg_play.tests.test_presentation import snapshot

    workspace, calls = workspace_fixture(app, tmp_path)
    try:
        workspace.session.active = True
        workspace._show_loading("match", "Starting your match", "Starting engine...")
        workspace._status("Preparing opening hand...")
        assert workspace.pages.currentWidget() is workspace.loading_page
        assert workspace.loading_detail.text() == "Preparing opening hand..."
        workspace._show_snapshot(snapshot("two"))
        assert workspace.pages.currentWidget() is workspace.loading_page
        workspace._show_snapshot(snapshot(workspace.lobby.local_seat_id))
        assert workspace.pages.currentWidget() is workspace.game_page
        assert not workspace.loading_timer.isActive() and not calls
    finally:
        workspace.session.active = False
        workspace.table.clear()
        workspace.close()


def test_completed_game_return_skips_concession_confirmation_and_shows_cleanup(
    app, tmp_path, monkeypatch
):
    from mtg_play.tests.test_presentation import snapshot
    from dataclasses import replace

    workspace, calls = workspace_fixture(app, tmp_path)
    stops = []
    workspace.session.stop = lambda: stops.append(True)
    monkeypatch.setattr(
        W.QMessageBox,
        "question",
        lambda *args: pytest.fail("A finished match must not ask to concede"),
    )
    try:
        workspace.session.active = True
        workspace._show_snapshot(
            replace(
                snapshot(workspace.lobby.local_seat_id),
                result="did_not_win",
                decision=None,
            )
        )
        workspace.table.result_return.click()
        assert stops == [True] and not calls
        assert workspace.pages.currentWidget() is workspace.loading_page
        assert (
            workspace._loading_purpose == "close"
            and not workspace.loading_cancel.isEnabled()
        )
        workspace.session.closing = False
        workspace._engine_loading_idle()
        assert (
            workspace.loading_cancel.text() == "Retry cleanup"
            and workspace.loading_cancel.isEnabled()
        )
        workspace.loading_cancel.click()
        assert len(stops) == 2
    finally:
        workspace.session.active = False
        workspace.loading_timer.stop()
        workspace.table.clear()
        workspace.close()


def test_play_feedback_opens_existing_composer_without_auto_sending_or_deck_data(
    app, tmp_path, monkeypatch
):
    import json
    from mtg_ui import feedback

    workspace, calls = workspace_fixture(app, tmp_path)
    opened = []

    class Composer:
        def __init__(self, parent, **kwargs):
            opened.append(kwargs)

        def exec(self):
            opened.append("reviewed")

    monkeypatch.setattr(feedback, "FeedbackDialog", Composer)
    try:
        workspace.report_play_issue.click()
        assert opened[-1] == "reviewed" and not calls
        report = json.loads(opened[0]["diagnostics"])
        assert report["mode"] == "offline_ai"
        assert "Saved deck" not in opened[0]["diagnostics"]
        assert "screenshot" not in opened[0] and "report" not in opened[0]
    finally:
        workspace.close()


def test_uncertain_match_exposes_cleanup_only_recovery_without_replay(
    app, tmp_path, monkeypatch
):
    workspace, calls = workspace_fixture(app, tmp_path)
    stops = []
    workspace.session.stop = lambda: stops.append(True)
    monkeypatch.setattr(
        W.QMessageBox,
        "question",
        lambda *args: pytest.fail(
            "Explicit recovery must not add a second confirmation"
        ),
    )
    try:
        workspace.session.active = True
        workspace.session._blocked = True
        workspace._selection_changed()
        assert (
            not workspace.recover_button.isHidden()
            and workspace.recover_button.isEnabled()
        )
        workspace.recover_button.click()
        assert stops == [True] and not calls
        assert workspace._loading_purpose == "close"
    finally:
        workspace.session.active = False
        workspace.loading_timer.stop()
        workspace.close()
