"""Unity launcher regression coverage for GitHub Actions."""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from PyQt6 import QtWidgets as W
from mtg_core.decks import DeckDocument
from mtg_play.setup import SavedDeck
from mtg_play.readiness import DeckReadiness
from mtg_play import workspace as module


@pytest.fixture
def launcher(monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    monkeypatch.setattr(module.PlayWorkspace, "load_decks", lambda self: None)
    widget = module.PlayWorkspace(None, lambda: None)
    decks = tuple(
        SavedDeck(None, DeckDocument(), (), source_id=str(i)) for i in range(2)
    )
    widget._catalog_loaded("catalog", "completed", (decks, ()))
    yield widget
    widget.deleteLater()
    app.processEvents()


def select_decks(widget):
    widget.selectors[0].setCurrentIndex(1)
    widget.selectors[1].setCurrentIndex(2)


def test_only_start_button_launches_unity_with_selected_decks(launcher, monkeypatch):
    assert [b.text() for b in launcher.findChildren(W.QPushButton)] == ["Start Game"]
    assert not launcher.start_button.isEnabled()
    select_decks(launcher)
    launch = Mock()
    launch.root = None
    monkeypatch.setattr(module, "LiveGameLaunch", lambda: launch)
    run = Mock(return_value={"outcome": "win"})
    monkeypatch.setattr(module, "run_live_game", run)
    queued = []
    monkeypatch.setattr(
        launcher.native_jobs, "submit", lambda work, **kw: queued.append(work)
    )
    launcher.start_button.click()
    assert len(queued) == 1
    queued[0](None, None)
    setup, documents, _, _ = run.call_args.args
    assert setup.format == "freeform"
    assert set(documents) == {"one", "two"}
    assert run.call_args.kwargs["launch"] is launch


def test_blocked_deck_disables_start_and_explains_reason(launcher):
    blocked = DeckReadiness("freeform", "blocked", ("Deck needs review",))
    launcher._decks = (
        replace(launcher._decks[0], checks=(blocked,)),
        launcher._decks[1],
    )
    select_decks(launcher)
    assert not launcher.start_button.isEnabled()
    assert "Deck needs review" in launcher.status.text()


def test_application_shutdown_cancels_owned_unity_job(launcher, monkeypatch):
    monkeypatch.setattr(type(launcher.native_jobs), "busy", property(lambda self: True))
    cancel = Mock()
    monkeypatch.setattr(launcher.native_jobs, "cancel_all", cancel)
    assert not launcher.prepare_to_close()
    cancel.assert_called_once()


@pytest.mark.parametrize("remove_opponent", [False, True])
def test_reload_tracks_deck_identity_and_clears_removed_selection(
    launcher, remove_opponent
):
    select_decks(launcher)
    original = launcher._decks
    refreshed = (original[0],) if remove_opponent else tuple(reversed(original))
    launcher._catalog_loaded("reload", "completed", (refreshed, ()))
    selected = [
        launcher._decks[selector.currentData()].key
        if selector.currentData() is not None
        else None
        for selector in launcher.selectors
    ]
    assert selected == [original[0].key, None if remove_opponent else original[1].key]
    assert launcher.start_button.isEnabled() is not remove_opponent
