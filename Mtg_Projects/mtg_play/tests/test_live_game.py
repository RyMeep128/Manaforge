"""Saved-game lifetime regressions; no native server or renderer."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mtg_play.live_game import LiveGameError, LiveGameLaunch
from mtg_play.live_game import project_launch, validate_close_report
from mtg_play.contracts import GameSetup, MatchSeat
from generate_launch_fixtures import native_deck


def test_owned_cleanup_preserves_only_bounded_result_and_safe_code():
    launch = LiveGameLaunch()
    launch.allocate()
    root = launch.root
    (root / "game-closed.json").write_text(
        json.dumps(dict(outcome="win", snapshots=4, private="never retain"))
    )
    (root / "game-unsupported.json").write_text(
        json.dumps(dict(code="UNSUPPORTED_GAME_SELECT_345"))
    )
    launch.close()
    assert not root.exists()
    assert launch.root is None
    assert launch.summary["outcome"] == "win"
    assert "private" not in launch.summary
    assert launch.last_error == "UNSUPPORTED_GAME_SELECT_345"
    launch.close()


def test_saved_launch_preserves_printings_quantities_and_owner():
    setup = GameSetup(
        (MatchSeat("human", "Human"), MatchSeat("ai", "AI", "engine_ai")), "freeform"
    )
    document = native_deck(False)
    document.deck.entries[0].name = "Forest"
    before = document.to_dict()
    value = json.loads(
        project_launch(
            setup,
            {"human": document, "ai": document},
            "0.5.211-alpha.1",
            {"ai": "lender"},
        )
    )
    assert document.to_dict() == before
    assert value["seats"][1]["deck_owner_id"] == "lender"
    assert (
        value["seats"][0]["document"]["deck"]["entries"][0]["quantity"]
        == document.deck.entries[0].quantity
    )


def test_unsupported_setup_and_unresolved_printing_fail_before_launch():
    seats = (MatchSeat("human", "Human"), MatchSeat("ai", "AI", "engine_ai"))
    document = native_deck(False)
    with pytest.raises(LiveGameError, match="SETUP_UNSUPPORTED"):
        project_launch(
            GameSetup(seats, "commander"),
            {"human": document, "ai": document},
            "0.5.211-alpha.1",
        )
    document.deck.entries[0].set_code = ""
    with pytest.raises(ValueError):
        project_launch(
            GameSetup(seats, "freeform"),
            {"human": document, "ai": document},
            "0.5.211-alpha.1",
        )


def test_unconfirmed_process_cleanup_retains_files_for_retry():
    launch = LiveGameLaunch()
    launch.allocate()
    root = launch.root
    launch.owner = SimpleNamespace(close=lambda: SimpleNamespace(confirmed=False))
    try:
        with pytest.raises(LiveGameError, match="CLEANUP_UNCONFIRMED"):
            launch.close()
        assert root.exists()
        launch.owner = None
        launch.close()
        assert not root.exists()
    finally:
        launch.owner = None
        launch.close()


def test_changed_root_identity_is_never_deleted():
    launch = LiveGameLaunch()
    launch.allocate()
    original = launch._identity
    launch._identity = (-1, -1)
    try:
        with pytest.raises(LiveGameError, match="FILES_CLEANUP_FAILED"):
            launch.close()
        assert launch.root.exists()
    finally:
        launch._identity = original
        launch.close()


def test_unexpected_disconnect_cannot_be_reported_as_a_clean_return():
    closed = dict(
        viewer_cleared=True, cleanup_confirmed=True, uncertain=0, outcome=None
    )
    with pytest.raises(LiveGameError, match="ENDED_WITHOUT_RESULT"):
        validate_close_report(closed)
    validate_close_report(dict(closed, user_requested=True))
    validate_close_report(dict(closed, outcome="win"))
    with pytest.raises(LiveGameError, match="RESULT_UNCERTAIN"):
        validate_close_report(dict(closed, user_requested=True, uncertain=1))


@pytest.mark.parametrize("diagnostic", ["{broken", '{"code":"raw secret value"}'])
def test_invalid_diagnostics_do_not_block_cleanup(diagnostic):
    launch = LiveGameLaunch()
    launch.allocate()
    root = launch.root
    (root / "game-error.json").write_text(diagnostic)
    launch.close()
    assert not root.exists()
    assert launch.last_error is None
