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


@pytest.fixture(autouse=True)
def isolated_session_logs(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "mtg_play.session_logs.core_data_root", lambda: tmp_path / "core"
    )


def test_player_log_survives_cleanup_without_private_launch_files(tmp_path):
    launch = LiveGameLaunch()
    launch.allocate()
    root = launch.root
    (root / "player.log").write_text("NullReferenceException: first-player choice\n")
    (root / "game-error.json").write_text('{"code":"RECEIVE_SHAPE"}')
    (root / "viewer-bootstrap.json").write_text("PRIVATE_AUTHENTICATION")
    (root / "launch.json").write_text("PRIVATE_DECK")
    launch.close()
    assert not root.exists()
    assert launch.log_directory.parent == tmp_path / "core/logs/unity-sessions"
    assert (
        launch.log_directory / "player.log"
    ).read_text() == "NullReferenceException: first-player choice\n"
    report = json.loads((launch.log_directory / "diagnostic.json").read_text())
    assert report["error_code"] == "RECEIVE_SHAPE"
    assert report["client_errors"] == ["NullReferenceException"]
    assert {p.name for p in launch.log_directory.iterdir()} == {
        "player.log",
        "diagnostic.json",
    }
    archived = launch.log_directory
    launch.close()
    assert launch.log_directory == archived


def test_log_retention_limits_sessions_and_preserves_oversized_log_tail(
    tmp_path, monkeypatch
):
    from mtg_play import session_logs

    class FrozenDatetime(session_logs.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 4, tzinfo=tz)

    monkeypatch.setattr(session_logs, "datetime", FrozenDatetime)
    source = tmp_path / "source"
    source.mkdir()
    destination = tmp_path / "archive"
    monkeypatch.setattr(session_logs, "MAX_SESSIONS", 2)
    monkeypatch.setattr(session_logs, "MAX_PLAYER_LOG_BYTES", 16)
    (source / "player.log").write_bytes(b"old data " * 20 + b"FINAL_EXCEPTION\n")
    first = session_logs.retain_session_logs(source, destination=destination)
    second = session_logs.retain_session_logs(source, destination=destination)
    third = session_logs.retain_session_logs(source, destination=destination)
    assert not first.exists()
    assert second.is_dir() and third.is_dir()
    assert (third / "player.log").read_bytes().endswith(b"FINAL_EXCEPTION\n")
    assert (third / "player.log").stat().st_size <= 16
    assert (
        json.loads((third / "diagnostic.json").read_text())["player_log_truncated"]
        is True
    )


def test_log_storage_failure_does_not_prevent_private_workspace_cleanup(monkeypatch):
    launch = LiveGameLaunch()
    launch.allocate()
    root = launch.root
    (root / "player.log").write_text("a failure")

    def unavailable(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr("mtg_play.live_game.retain_session_logs", unavailable)
    launch.close()
    assert not root.exists()
    assert launch.root is None
    assert launch.log_directory is None


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


def test_rules_resolution_ignores_printing_and_preserves_artwork_identity():
    from mtg_play.live_game import resolve_rules_manifest

    source = {
        "seats": [
            {
                "document": {
                    "deck": {
                        "entries": [
                            dict(
                                name="Front // Back",
                                set_code="custom",
                                collector_number="999",
                                card_id="deck-artwork",
                                oracle_id="oracle",
                                entry_id="entry",
                                quantity=2,
                            )
                        ]
                    }
                }
            }
        ]
    }
    before = json.dumps(source)

    def request(command):
        assert command == dict(
            command="resolve_rules",
            cards=[dict(key="0", name="Front // Back", set="", number="")],
        )
        return [dict(key="0", name="Front", set="ENGINE", number="1")]

    result = resolve_rules_manifest(source, request)
    entry = result["seats"][0]["document"]["deck"]["entries"][0]
    assert (entry["name"], entry["set_code"], entry["collector_number"]) == (
        "Front",
        "ENGINE",
        "1",
    )
    assert (
        entry["card_id"],
        entry["oracle_id"],
        entry["entry_id"],
        entry["quantity"],
    ) == ("deck-artwork", "oracle", "entry", 2)
    assert json.dumps(source) == before


@pytest.mark.parametrize(
    "response",
    [
        [],
        {},
        [dict(key="0", error="CARD_NOT_SUPPORTED")],
        [dict(key="wrong", name="Forest", set="M21", number="1")],
    ],
)
def test_rules_resolution_rejects_missing_or_malformed_engine_results(response):
    from mtg_play.live_game import resolve_rules_manifest

    manifest = {"seats": [{"document": {"deck": {"entries": [dict(name="Forest")]}}}]}
    with pytest.raises(LiveGameError, match="CARD_"):
        resolve_rules_manifest(manifest, lambda command: response)


def test_audited_rules_alias_preserves_saved_name_and_artwork():
    from mtg_play.live_game import resolve_rules_manifest

    source = {
        "seats": [
            {
                "document": {
                    "deck": {
                        "entries": [
                            dict(
                                name="Mj\u00f6lnir, Hammer of Thor",
                                oracle_id="7f9a8845-d760-44a7-a4c9-8a20dba4e14a",
                                card_id="selected-art",
                            )
                        ]
                    }
                }
            }
        ]
    }

    def request(command):
        assert command["cards"][0]["name"] == "Mjolnir, Hammer of Thor"
        return [dict(key="0", name="Mjolnir, Hammer of Thor", set="MSH", number="146")]

    result = resolve_rules_manifest(source, request)
    assert (
        result["seats"][0]["document"]["deck"]["entries"][0]["card_id"]
        == "selected-art"
    )
    assert (
        source["seats"][0]["document"]["deck"]["entries"][0]["name"]
        == "Mj\u00f6lnir, Hammer of Thor"
    )


def test_rules_alias_never_guesses_other_names_or_oracle_identities():
    from mtg_play.rules_identity import engine_rule_name

    assert (
        engine_rule_name("Mj\u00f6lnir, Hammer of Thor", "wrong-oracle")
        == "Mj\u00f6lnir, Hammer of Thor"
    )
    assert engine_rule_name("Other \u00f6 card") == "Other \u00f6 card"


def test_canonical_rules_name_uses_stored_oracle_identity_without_rewriting_deck():
    from mtg_play.live_game import resolve_rules_manifest

    source = {
        "seats": [
            {
                "document": {
                    "deck": {
                        "entries": [
                            dict(
                                name="Jeskas Will",
                                oracle_id="oracle",
                                card_id="selected-art",
                            )
                        ]
                    }
                }
            }
        ]
    }
    before = json.dumps(source)

    def request(command):
        assert command["cards"][0]["name"] == "Jeska's Will"
        return [dict(key="0", name="Jeska's Will", set="CMR", number="187")]

    resolved = resolve_rules_manifest(
        source, request, {"oracle": dict(name="Jeska's Will", layout="normal")}
    )
    assert (
        resolved["seats"][0]["document"]["deck"]["entries"][0]["card_id"]
        == "selected-art"
    )
    assert json.dumps(source) == before


def test_freeform_commander_projection_preserves_saved_deck_and_includes_ordinary_cards():
    from mtg_play.decks import document_for_format, prepare_deck
    from mtg_play.readiness import local_readiness

    setup = GameSetup(
        (MatchSeat("human", "Human"), MatchSeat("ai", "AI", "engine_ai")), "freeform"
    )
    document = native_deck(True)
    document.deck.extras.pop("companion_entry_id", None)
    document.deck.entries = [
        entry for entry in document.deck.entries if entry.entry_id != "companion"
    ]
    for entry in document.deck.entries:
        if entry.section not in ("considering", "excluded"):
            entry.name = entry.entry_id.title()
            entry.oracle_id = None
            entry.set_code = "TST"
            entry.collector_number = entry.entry_id
    before = document.to_dict()
    projected = document_for_format(document, commander=False)
    assert projected.deck.commander_entry_ids == []
    assert all(entry.section != "commander" for entry in projected.deck.entries)
    assert local_readiness(document, "freeform").can_start
    value = json.loads(
        project_launch(setup, {"human": document, "ai": document}, "0.5.217-alpha.1")
    )
    assert value["seats"][0]["document"]["deck"]["commander_entry_ids"] == []
    assert any(
        entry["entry_id"] == "commander" and entry["section"] == "mainboard"
        for entry in value["seats"][0]["document"]["deck"]["entries"]
    )

    def resolve(queries):
        return [
            dict(
                query, set=query["set"] or "TST", number=query["number"] or query["key"]
            )
            for query in queries
        ]

    prepared = prepare_deck(document, resolve)
    assert not prepared.sideboard
    assert document.to_dict() == before


def test_disconnect_retains_original_unsupported_context_without_private_values():
    launch = LiveGameLaunch()
    launch.allocate()
    root = launch.root
    (root / "game-error.json").write_text(
        json.dumps(dict(code="LIVE_UNITY_DISCONNECTED"))
    )
    (root / "game-unsupported.json").write_text(
        json.dumps(
            dict(
                code="UNSUPPORTED_GAME_TARGET_OPTIONS",
                prompt_family="GAME_TARGET",
                phase="PRECOMBAT_MAIN",
                targets_count=0,
                cards_count=1,
                private="PRIVATE_CARD_NAME",
                message="PRIVATE_PROMPT",
                amounts_count=-1,
            )
        )
    )
    launch.close()
    assert launch.last_error == "LIVE_UNITY_DISCONNECTED"
    assert launch.unsupported_diagnostics == dict(
        code="UNSUPPORTED_GAME_TARGET_OPTIONS",
        prompt_family="GAME_TARGET",
        phase="PRECOMBAT_MAIN",
        targets_count=0,
        cards_count=1,
    )
    retained = json.loads((launch.log_directory / "diagnostic.json").read_text())
    assert retained["unsupported"] == launch.unsupported_diagnostics
    assert "PRIVATE" not in json.dumps(retained)


def test_owned_process_exit_evidence_is_retained_separately_from_error():
    launch = LiveGameLaunch()
    launch.allocate()
    (launch.root / "player.log").write_text("Orderly viewer shutdown")
    launch.owner = SimpleNamespace(
        close=lambda: SimpleNamespace(
            confirmed=True,
            children=[
                SimpleNamespace(role="client", exit_code=0, forced=False, reaped=True)
            ],
        )
    )
    launch.close()
    retained = json.loads((launch.log_directory / "diagnostic.json").read_text())
    assert retained["processes"] == [
        dict(role="client", exit_code=0, forced=False, reaped=True)
    ]
