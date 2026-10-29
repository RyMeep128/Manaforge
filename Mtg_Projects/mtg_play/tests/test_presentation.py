"""Qt offscreen coverage of the public scripted-session presentation boundary."""

from dataclasses import replace
import threading
import time
from types import SimpleNamespace

import pytest
from PyQt6 import QtCore as C, QtWidgets as W

from mtg_core.decks import DeckDocument, DeckEntry, DeckStore
from mtg_play.contracts import (
    ChoiceOption,
    ChoiceRequest,
    CommandResult,
    GameSetup,
    GameSnapshot,
    MatchSeat,
    PlayerView,
)
from mtg_play.fake import ScriptedGameSession
from mtg_play.presentation import SessionController
from mtg_play.setup import SavedDeck, saved_decks
from mtg_play.workspace import PlayWorkspace


@pytest.fixture
def app():
    return W.QApplication.instance() or W.QApplication([])


def drain(app, predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.001)
    assert predicate()


def snapshot(viewer="one", revision=1):
    return GameSnapshot(
        session_id="local",
        viewer_id=viewer,
        revision=revision,
        status="playing",
        turn=1,
        phase="Beginning",
        step="Upkeep",
        active_player_id="one",
        priority_player_id="one",
        players=(
            PlayerView("one", "First", 20, 7, 53, False),
            PlayerView("two", "Second", 20, 7, 53, False),
        ),
        objects=(),
        actions=(),
        decision=ChoiceRequest(
            "opening",
            viewer,
            "boolean",
            "Keep your hand?",
            (ChoiceOption("keep", "Keep"), ChoiceOption("mulligan", "Mulligan")),
        ),
    )


class Owner:
    def __init__(self, session):
        self.session = session
        self.calls = []
        self.closed = False

    def __enter__(self):
        self.calls.append(("enter", C.QThread.currentThread()))
        return self

    def create_game(self, setup, decks, **kwargs):
        self.calls.append(("create", C.QThread.currentThread()))
        self.setup, self.decks = setup, decks
        return self.session

    def close(self):
        self.calls.append(("close", C.QThread.currentThread()))
        self.closed = True


def setup():
    return GameSetup((MatchSeat("one", "First"), MatchSeat("two", "Second")))


def close(app, controller):
    controller.stop()
    drain(app, lambda: not controller.active and not controller.busy)


def test_saved_documents_retain_printings_commanders_and_extras(tmp_path):
    doc = DeckDocument()
    doc.deck.entries = [
        DeckEntry(entry_id="forest", name="Forest", card_id="printing", quantity=12)
    ]
    doc.deck.commander_entry_ids = [doc.deck.entries[0].entry_id]
    doc.deck.extras["custom_configuration"] = {"untouched": True}
    path = tmp_path / "decks" / "deck.manaforge.json"
    DeckStore().save(path, doc)
    before = path.read_bytes()
    decks, errors = saved_decks(tmp_path)
    assert not errors
    assert decks[0].document.to_dict() == doc.to_dict()
    assert decks[0].commanders == ("Forest",)
    assert path.read_bytes() == before


def test_start_is_lazy_and_all_engine_calls_are_off_ui_thread(app):
    session = ScriptedGameSession((snapshot(), snapshot("two")))
    owner = Owner(session)
    controller = SessionController(adapter_factory=lambda: owner)
    views = []
    controller.snapshotChanged.connect(views.append)
    assert not owner.calls
    documents = (DeckDocument(), DeckDocument())
    assert controller.start(setup(), documents)
    drain(app, lambda: bool(views) and not controller.busy)
    assert owner.decks is documents
    assert owner.setup == setup()
    assert all(view.viewer_id == "one" for view in views)
    close(app, controller)
    assert owner.closed
    assert all(thread != app.thread() for _, thread in owner.calls)


def test_switch_discards_an_old_seat_reply_and_clears_immediately(app):
    entered, release = threading.Event(), threading.Event()

    class Delayed(ScriptedGameSession):
        delay = False

        def snapshot(self, player_id):
            if self.delay and player_id == "one":
                entered.set()
                release.wait(4)
            return super().snapshot(player_id)

    session = Delayed((snapshot(), snapshot("two")))
    controller = SessionController(adapter_factory=lambda: Owner(session))
    views, cleared = [], []
    controller.snapshotChanged.connect(views.append)
    controller.viewCleared.connect(lambda: cleared.append(True))
    controller.start(setup(), (DeckDocument(), DeckDocument()))
    drain(app, lambda: bool(views) and not controller.busy)
    controller.timer.stop()
    session.delay = True
    controller.refresh()
    drain(app, entered.is_set)
    views.clear()
    controller.reveal("two")
    assert cleared and controller._snapshot is None
    release.set()
    drain(app, lambda: bool(views) and not controller.busy)
    assert all(view.viewer_id == "two" for view in views)
    close(app, controller)


def test_snapshot_not_ready_removes_the_previous_view(app):
    class NotReady(RuntimeError):
        code = "SNAPSHOT_NOT_READY"

    class Session(ScriptedGameSession):
        ready = True

        def snapshot(self, player_id):
            if not self.ready:
                raise NotReady()
            return super().snapshot(player_id)

    session = Session((snapshot(),))
    controller = SessionController(adapter_factory=lambda: Owner(session))
    views, clears = [], []
    controller.snapshotChanged.connect(views.append)
    controller.viewCleared.connect(lambda: clears.append(True))
    controller.start(setup(), (DeckDocument(), DeckDocument()))
    drain(app, lambda: bool(views) and not controller.busy)
    controller.timer.stop()
    session.ready = False
    controller.refresh()
    drain(app, lambda: not controller.busy)
    assert clears and controller._snapshot is None
    close(app, controller)


def test_submitted_decision_cannot_be_sent_twice_or_treated_as_resolution(app):
    class Acknowledged(ScriptedGameSession):
        submissions = 0

        def choose(self, *args):
            self.submissions += 1
            return CommandResult("receipt", "submitted")

    session = Acknowledged((snapshot(),))
    controller = SessionController(adapter_factory=lambda: Owner(session))
    views = []
    controller.snapshotChanged.connect(views.append)
    controller.start(setup(), (DeckDocument(), DeckDocument()))
    drain(app, lambda: bool(views) and not controller.busy)
    controller.timer.stop()
    displayed = views[-1]
    assert controller.submit(displayed, "choose", "keep")
    assert not controller.submit(displayed, "choose", "keep")
    drain(app, lambda: not controller.busy)
    controller.refresh()
    drain(app, lambda: not controller.busy)
    assert session.submissions == 1
    assert controller._snapshot is None
    assert not controller.submit(displayed, "choose", "keep")
    session.publish(replace(snapshot(), revision=2, decision=None))
    controller.refresh()
    drain(app, lambda: not controller.busy)
    assert controller._snapshot.revision == 2
    close(app, controller)


def test_stop_during_start_cleans_up_after_start_and_drops_start_reply(app):
    entered, release = threading.Event(), threading.Event()

    class SlowOwner(Owner):
        def create_game(self, *args, **kwargs):
            entered.set()
            release.wait(4)
            return super().create_game(*args, **kwargs)

    owner = SlowOwner(ScriptedGameSession((snapshot(),)))
    controller = SessionController(adapter_factory=lambda: owner)
    views = []
    controller.snapshotChanged.connect(views.append)
    controller.start(setup(), (DeckDocument(), DeckDocument()))
    drain(app, entered.is_set)
    controller.stop()
    release.set()
    drain(app, lambda: not controller.active and not controller.busy)
    assert owner.closed and not views and not controller.timer.isActive()


def test_missing_runtime_is_recoverable_without_raw_engine_errors(app):
    def missing():
        raise RuntimeError("java UUID secret protocol payload")

    controller = SessionController(adapter_factory=missing)
    messages = []
    controller.statusChanged.connect(messages.append)
    controller.start(setup(), (DeckDocument(), DeckDocument()))
    drain(app, lambda: not controller.busy)
    assert not controller.active
    assert "runtime" in messages[-1]
    assert "secret" not in messages[-1]
    controller.adapter_factory = lambda: Owner(ScriptedGameSession((snapshot(),)))
    assert controller.start(setup(), (DeckDocument(), DeckDocument()))
    drain(app, lambda: not controller.busy)
    close(app, controller)


def test_workspace_selects_existing_documents_without_starting_runtime_on_open(
    app, tmp_path
):
    documents = (DeckDocument(), DeckDocument())
    for document in documents:
        document.deck.entries = [
            DeckEntry("commander", "Isamaru, Hound of Konda", section="commander")
        ]
        document.deck.commander_entry_ids = ["commander"]
    documents[0].deck.extras["preserve"] = ["selected printing"]
    owner = Owner(ScriptedGameSession((snapshot("one"),)))
    entries = tuple(
        SavedDeck(tmp_path / str(i), doc, ("Isamaru, Hound of Konda",))
        for i, doc in enumerate(documents)
    )
    workspace = PlayWorkspace(
        SimpleNamespace(database=object()),
        lambda: None,
        adapter_factory=lambda: owner,
        deck_provider=lambda: (entries, ()),
    )
    drain(app, lambda: not workspace.catalog_jobs.busy)
    assert not owner.calls and not workspace.start_button.isEnabled()
    for index, selector in enumerate(workspace.selectors):
        selector.setCurrentIndex(index + 1)
    workspace.format.setCurrentIndex(1)
    assert workspace.start_button.isEnabled()
    workspace.start_game()
    drain(app, lambda: not workspace.session.busy)
    assert owner.setup.format == "commander"
    assert tuple(doc.to_dict() for doc in owner.decks) == tuple(
        doc.to_dict() for doc in documents
    )
    assert owner.decks[0] is not documents[0]
    close(app, workspace.session)
    workspace.close()


def test_obsolete_handlers_cannot_answer_a_new_decision(app):
    session = ScriptedGameSession((snapshot(),))
    controller = SessionController(adapter_factory=lambda: Owner(session))
    views = []
    controller.snapshotChanged.connect(views.append)
    controller.start(setup(), (DeckDocument(), DeckDocument()))
    drain(app, lambda: bool(views) and not controller.busy)
    controller.timer.stop()
    old = views[-1]
    session.publish(
        replace(old, revision=2, decision=replace(old.decision, decision_id="new"))
    )
    controller.refresh()
    drain(app, lambda: not controller.busy)
    assert not controller.submit(old, "choose", "keep")
    assert controller.submit(views[-1], "choose", "keep")
    drain(app, lambda: not controller.busy)
    close(app, controller)


def test_uncertain_outcome_cannot_be_retried_or_cleared_by_seat_switch(app):
    class Uncertain(ScriptedGameSession):
        def choose(self, *args):
            return CommandResult("receipt", "uncertain")

    session = Uncertain((snapshot(), snapshot("two")))
    controller = SessionController(adapter_factory=lambda: Owner(session))
    views = []
    controller.snapshotChanged.connect(views.append)
    controller.start(setup(), (DeckDocument(), DeckDocument()))
    drain(app, lambda: bool(views) and not controller.busy)
    controller.timer.stop()
    assert controller.submit(views[-1], "choose", "keep")
    drain(app, lambda: not controller.busy)
    controller.reveal("two")
    controller.refresh()
    assert not controller.timer.isActive()
    assert not controller.submit(views[-1], "choose", "keep")
    close(app, controller)


def test_failed_runtime_with_confirmed_cleanup_can_return_to_setup(app):
    from mtg_play.contracts import RuntimeReport

    class RuntimeFailed(RuntimeError):
        code = "ENGINE_RUNTIME_FAILED"

    class FailedOwner(Owner):
        result = RuntimeReport(
            False, None, (("server", 1),), False, "ENGINE_RUNTIME_FAILED"
        )

        def __enter__(self):
            raise RuntimeFailed()

        def close(self):
            self.closed = True
            raise RuntimeFailed()

    owner = FailedOwner(None)
    controller = SessionController(adapter_factory=lambda: owner)
    controller.start(setup(), (DeckDocument(), DeckDocument()))
    drain(app, lambda: not controller.busy)
    assert owner.closed and not controller.active


def test_home_preview_is_lazy_persistent_and_disabled_for_installed_builds(
    app, monkeypatch
):
    from mtg_home.home import HomeWindow
    from mtg_home.launcher import ModuleController
    from mtg_home.modules import MODULES, module_available
    import sys

    monkeypatch.delenv("MANAFORGE_ENABLE_LOCAL_PLAY", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    play = next(module for module in MODULES if module.key == "play")
    assert module_available(play)
    home = HomeWindow()
    created = []

    def factory():
        workspace = PlayWorkspace(
            object(),
            lambda: controller.show_home(),
            adapter_factory=lambda: pytest.fail("Engine must remain lazy"),
            deck_provider=lambda: ((), ()),
        )
        created.append(workspace)
        return workspace

    controller = ModuleController(home, service=object(), factories={"play": factory})
    assert home.tiles["play"].isEnabled() and not created
    controller.open_module("play")
    drain(app, lambda: not created[0].catalog_jobs.busy)
    assert home.current_workspace == "play"
    controller.show_home()
    controller.open_module("play")
    assert len(created) == 1
    assert not created[0].isWindow()
    monkeypatch.setenv("MANAFORGE_ENABLE_LOCAL_PLAY", "1")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert not module_available(play)
    assert home.close()


def test_uncertain_inflight_command_blocks_both_seats_after_handoff(app):
    entered, release = threading.Event(), threading.Event()

    class DelayedCommand(ScriptedGameSession):
        def choose(self, *args):
            entered.set()
            release.wait(4)
            return CommandResult("receipt", "uncertain")

    controller = SessionController(
        adapter_factory=lambda: Owner(DelayedCommand((snapshot(), snapshot("two"))))
    )
    views, messages = [], []
    controller.snapshotChanged.connect(views.append)
    controller.statusChanged.connect(messages.append)
    controller.start(setup(), (DeckDocument(), DeckDocument()))
    drain(app, lambda: bool(views) and not controller.busy)
    controller.timer.stop()
    assert controller.submit(views[-1], "choose", "keep")
    drain(app, entered.is_set)
    controller.reveal("two")
    release.set()
    drain(app, lambda: not controller.busy)
    assert "unknown" in messages[-1]
    assert not controller.timer.isActive()
    assert controller._snapshot is None
    close(app, controller)


def test_cleanup_failure_preserves_owner_until_explicit_retry(app):
    class SlowCleanup(Owner):
        attempts = 0

        def close(self):
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("cleanup not confirmed")
            super().close()

    owner = SlowCleanup(ScriptedGameSession((snapshot(),)))
    controller = SessionController(adapter_factory=lambda: owner)
    controller.start(setup(), (DeckDocument(), DeckDocument()))
    drain(app, lambda: not controller.busy)
    controller.stop()
    drain(app, lambda: not controller.busy)
    assert controller.active and not controller.closing
    assert not owner.closed
    close(app, controller)
    assert owner.closed and owner.attempts == 2
