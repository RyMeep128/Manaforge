"""Saved-game lifetime regressions; no native server or renderer."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mtg_play.live_game import LiveGameError, LiveGameLaunch
from mtg_play.live_game import (
    project_launch,
    validate_close_report,
    validate_scenario_close_report,
)
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


def test_focused_scenario_requires_matching_native_certificate_and_clean_shutdown():
    closed = dict(
        outcome=None, viewer_cleared=True, cleanup_confirmed=True, uncertain=0
    )
    certificate = dict(
        scenario="grave-decline", native_commander_scenario_verified=True
    )
    validate_scenario_close_report(closed, certificate, "grave-decline")
    with pytest.raises(LiveGameError, match="ENDED_WITHOUT_RESULT"):
        validate_close_report(closed)
    for proof, report in (
        (dict(certificate, scenario="other"), closed),
        (dict(certificate, native_commander_scenario_verified=False), closed),
        (certificate, dict(closed, uncertain=1)),
    ):
        with pytest.raises(LiveGameError, match="SCENARIO_UNPROVEN"):
            validate_scenario_close_report(report, proof, "grave-decline")


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


def test_commander_launch_preserves_paired_designations_and_rejects_companions():
    from mtg_core.decks import DeckEntry

    setup = GameSetup(
        (MatchSeat("human", "Human"), MatchSeat("ai", "AI", "engine_ai")), "commander"
    )
    document = native_deck(False)
    document.deck.entries[0].name = "Forest"
    for name in ("One", "Two"):
        document.deck.entries.append(
            DeckEntry(
                name,
                name,
                1,
                section="commander",
                set_code="SYN",
                collector_number=name,
                card_id=name,
            )
        )
    document.deck.commander_entry_ids = ["One", "Two"]
    before = json.dumps(document.to_dict(), sort_keys=True)
    value = json.loads(
        project_launch(setup, {"human": document, "ai": document}, "test-alpha.1")
    )
    assert value["seats"][0]["document"]["deck"]["commander_entry_ids"] == [
        "One",
        "Two",
    ]
    assert json.dumps(document.to_dict(), sort_keys=True) == before
    document.deck.entries.append(
        DeckEntry(
            "companion",
            "Companion",
            1,
            section="sideboard",
            set_code="SYN",
            collector_number="C",
            card_id="C",
        )
    )
    document.deck.extras["companion_entry_id"] = "companion"
    with pytest.raises(LiveGameError, match="SETUP_UNSUPPORTED"):
        project_launch(setup, {"human": document, "ai": document}, "test-alpha.1")
