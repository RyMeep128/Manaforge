"""Adapter boundary regressions. CI runs these; no engine or Qt is required."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import queue
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mtg_core"))
from mtg_core.decks import DeckDocument, Deck, DeckEntry
from mtg_play.adapter import AdapterError, LocalGameAdapter, XmageGameSession
from mtg_play.contracts import GameSetup, MatchSeat, CardIdentity
from mtg_play.decks import DeckTranslationError, PreparedDeck, prepare_deck
from mtg_play.fake import ScriptedGameSession


def resolve(queries):
    return [dict(query, name="Forest", set="M10", number="248") for query in queries]


def test_deck_translation_preserves_source_and_artwork_independence():
    document = DeckDocument(
        deck=Deck(
            entries=[
                DeckEntry(
                    "entry",
                    "Old label",
                    3,
                    oracle_id="oracle",
                    card_id="chosen-print",
                    image_asset_id=None,
                )
            ]
        )
    )
    before = deepcopy(document.to_dict())
    deck = prepare_deck(document, resolve, lambda oid: SimpleNamespace(name="Forest"))
    assert deck.cards[0]["quantity"] == 3
    assert deck.bindings[("M10", "248")] == CardIdentity(
        "oracle", "chosen-print", "entry"
    )
    assert document.to_dict() == before


def test_unresolved_oracle_and_unsupported_sections_report_each_entry():
    document = DeckDocument(
        deck=Deck(
            entries=[
                DeckEntry("a", "Forest", oracle_id="missing"),
                DeckEntry("b", "Forest", section="custom"),
            ]
        )
    )
    with pytest.raises(DeckTranslationError) as failure:
        prepare_deck(document, resolve)
    assert {issue.entry_id for issue in failure.value.issues} == {"a", "b"}


def test_ambiguous_printing_binding_fails_instead_of_assigning_art_arbitrarily():
    document = DeckDocument(
        deck=Deck(
            entries=[
                DeckEntry("a", "Forest", card_id="art-one"),
                DeckEntry("b", "Forest", card_id="art-two"),
            ]
        )
    )
    with pytest.raises(DeckTranslationError) as failure:
        prepare_deck(document, resolve)
    assert failure.value.issues[0].code == "AMBIGUOUS_INSTANCE_PRINTING"


@pytest.fixture
def session():
    setup = GameSetup((MatchSeat("one", "One"), MatchSeat("two", "Two")))
    owner = SimpleNamespace()
    decks = (PreparedDeck((), (), {}), PreparedDeck((), (), {}))
    session = XmageGameSession(owner, setup, decks)
    session._clients = {
        seat.seat_id: (None, SimpleNamespace(events=queue.Queue()))
        for seat in setup.seats
    }
    session._player_ids = {"engine-player-one": "one", "engine-player-two": "two"}
    session._names = {"internal-one": "one", "internal-two": "two"}
    session._game_ids = {"one": "engine-game", "two": "engine-game"}
    return session


def state(sequence, *, zone="hand", hidden=False):
    card = dict(
        id="engine-card",
        hidden=hidden,
        name="PRIVATE_CARD_NAME",
        set="SOM",
        number="174",
        type="Artifact Creature",
        power="1",
        toughness="1",
    )
    players = [
        dict(
            id="engine-player-one",
            name="internal-one",
            life=0,
            hand_count=1,
            library_count=0,
            battlefield=[],
        ),
        dict(
            id="engine-player-two",
            name="internal-two",
            life=20,
            hand_count=7,
            library_count=53,
            battlefield=[],
        ),
    ]
    result = dict(
        event="game_state",
        sequence=sequence,
        viewer="engine-player-one",
        game_id="engine-game",
        turn=1,
        phase=None,
        step=None,
        active_player="internal-one",
        priority_player="internal-one",
        players=players,
        hand=[card] if zone == "hand" else [],
        stack=[],
        playable=["engine-card"],
    )
    if zone == "battlefield":
        players[0]["battlefield"] = [card]
    return result


def inject(session, event, player="one"):
    session._clients[player][1].events.put(event)
    session._pump()


def test_public_snapshot_is_serializable_and_hides_engine_identifiers(session):
    inject(session, state(1))
    view = session.snapshot("one")
    payload = json.dumps(view.to_dict())
    assert (
        "engine-card" not in payload
        and "engine-player" not in payload
        and "internal-one" not in payload
    )
    assert view.players[0].life == 0 and view.players[0].library_count == 0
    assert view.phase is None
    assert all(obj.owner_id == "one" for obj in view.objects if obj.zone == "hand")
    with pytest.raises(AdapterError):
        session.snapshot("unassigned")


def test_hidden_state_scrubs_characteristics_and_selected_printing(session):
    inject(session, state(1, hidden=True))
    view = session.snapshot("one")
    assert (
        view.objects[0].characteristics is None
        and view.objects[0].card_identity is None
    )
    assert "PRIVATE_CARD_NAME" not in json.dumps(view.to_dict())


def test_identity_retires_even_when_consumer_skips_intermediate_zone_updates(session):
    inject(session, state(1))
    original = session.snapshot("one").objects[0].object_id
    inject(session, state(2, zone="battlefield"))
    inject(session, state(3))
    assert session.snapshot("one").objects[0].object_id != original
    same = session.snapshot("one").objects[0].object_id
    inject(
        session, state(2, hidden=True)
    )  # Obsolete snapshot must not conceal current state.
    assert session.snapshot("one").objects[0].object_id == same


def test_revealed_then_concealed_object_gets_new_reference(session):
    inject(session, state(1))
    original = session.snapshot("one").objects[0].object_id
    inject(session, state(2, hidden=True))
    concealed = session.snapshot("one").objects[0]
    assert concealed.hidden and concealed.object_id != original


def test_scripted_fake_obeys_stale_decision_contract(session):
    inject(session, state(1))
    inject(
        session,
        dict(event="decision", decision_id=2, kind="GAME_ASK", message="Mulligan?"),
    )
    snapshot = session.snapshot("one")
    fake = ScriptedGameSession((snapshot,))
    decision = snapshot.decision
    assert (
        fake.choose("one", decision.decision_id, decision.options[0].option_id).outcome
        == "submitted"
    )
    assert (
        fake.choose("one", decision.decision_id, decision.options[0].option_id).outcome
        == "rejected"
    )
    with pytest.raises(ValueError):
        fake.publish(replace(snapshot, revision=0))


def test_unknown_prompt_fails_explicitly_without_exposing_payload(session):
    inject(session, state(1))
    inject(
        session, dict(event="error", message="UNSUPPORTED_DECISION: PRIVATE_CARD_NAME")
    )
    events = session.poll("one")
    assert any(event.code == "UNSUPPORTED_DECISION" for event in events)
    assert "PRIVATE_CARD_NAME" not in json.dumps([event.to_dict() for event in events])


def test_obsolete_decision_cannot_reopen_consumed_prompt(session):
    inject(session, state(1))
    prompt = dict(event="decision", decision_id=2, kind="GAME_ASK", message="Mulligan?")
    inject(session, prompt)
    assert session.snapshot("one").decision is not None
    session._pending.pop("one")
    inject(session, prompt)
    assert session.snapshot("one").decision is None


def test_obsolete_request_acknowledgements_are_ignored(session):
    inject(session, dict(event="response_sent", request_id="obsolete", accepted=True))
    assert not session._replies


def test_disconnect_reports_failure_and_blocks_commands(session):
    inject(session, state(1))
    inject(
        session,
        dict(event="decision", decision_id=2, kind="GAME_ASK", message="Mulligan?"),
    )
    previous = session.snapshot("one").decision
    inject(session, None)
    assert session.snapshot("one").status == "failed"
    assert (
        session.choose(
            "one", previous.decision_id, previous.options[0].option_id
        ).outcome
        == "rejected"
    )
    assert any(event.code == "ENGINE_CONNECTION_LOST" for event in session.poll("one"))


def test_amount_constraints_and_unsupported_cancellation_are_public(session):
    inject(session, state(1))
    inject(
        session,
        dict(
            event="decision",
            decision_id=2,
            kind="GAME_GET_AMOUNT",
            message="Choose X",
            min=0,
            max=4,
        ),
    )
    view = session.snapshot("one")
    assert view.decision.minimum == 0 and view.decision.maximum == 4
    assert (
        session.choose_number("one", view.decision.decision_id, True).outcome
        == "rejected"
    )
    assert (
        session.choose_number("one", view.decision.decision_id, 5).outcome == "rejected"
    )
    assert session.cancel("one", view.decision.decision_id).outcome == "rejected"
    assert session.snapshot("one").decision.decision_id == view.decision.decision_id


def test_private_prompts_remain_independent_for_each_seat(session):
    inject(session, state(1))
    other = state(1)
    other["viewer"] = "engine-player-two"
    other["hand"][0]["id"] = "other-engine-card"
    other["hand"][0]["name"] = "OTHER_PRIVATE_CARD"
    inject(session, other, "two")
    inject(
        session,
        dict(
            event="decision",
            decision_id=2,
            kind="GAME_ASK",
            message="ONE_PRIVATE_PROMPT",
        ),
    )
    inject(
        session,
        dict(
            event="decision",
            decision_id=3,
            kind="GAME_ASK",
            message="TWO_PRIVATE_PROMPT",
        ),
        "two",
    )
    payload = json.dumps(session.snapshot("one").to_dict())
    assert "OTHER_PRIVATE_CARD" not in payload and "TWO_PRIVATE_PROMPT" not in payload
    assert session.snapshot("two").decision.prompt == "TWO_PRIVATE_PROMPT"


def test_closed_session_fails_explicitly(session):
    inject(session, state(1))
    session._closed = True
    with pytest.raises(AdapterError, match="SESSION_CLOSED"):
        session.snapshot("one")


def test_compatibility_is_available_without_starting_engine_or_importing_qt():
    adapter = LocalGameAdapter()
    payload = adapter.compatibility.to_dict()
    assert payload["engine_version"] == "1.4.62-V1"
    assert payload["protocol_version"] == 1
    assert len(payload["artifact_manifest_sha256"]) == 64


def test_public_modules_import_in_isolated_standard_library_interpreter():
    import subprocess

    products = str(Path(__file__).resolve().parents[2])
    code = (
        "import sys; sys.path.insert(0, " + repr(products) + "); "
        "import mtg_play.contracts, mtg_play.adapter, mtg_play.fake; "
        "assert not any(name.startswith(('PySide', 'PyQt', 'mtg_core')) for name in sys.modules)"
    )
    subprocess.run([sys.executable, "-S", "-c", code], check=True, timeout=10)


def test_battlefield_empty_owner_name_means_same_as_controller(session):
    identity = CardIdentity("oracle", "selected-print", "entry")
    session._decks = (
        PreparedDeck((), (), {("SOM", "174"): identity}),
        PreparedDeck((), (), {}),
    )
    update = state(1, zone="battlefield")
    update["players"][0]["battlefield"][0].update(
        owner_name="", controller_name="internal-one", token=False
    )
    inject(session, update)
    obj = session.snapshot("one").objects[0]
    assert obj.owner_id == obj.controller_id == "one"
    assert obj.card_identity == identity


def test_user_facing_prompt_replaces_internal_player_names_and_engine_ids(session):
    inject(session, state(1))
    inject(
        session,
        dict(
            event="decision",
            decision_id=2,
            kind="GAME_ASK",
            message="internal-one: target 12345678-1234-1234-1234-123456789abc?",
        ),
    )
    prompt = session.snapshot("one").decision.prompt
    assert "internal-one" not in prompt and "12345678-1234" not in prompt
    assert "One" in prompt


def test_unconfirmed_transport_response_fails_session_without_replaying(session):
    inject(session, state(1))
    inject(
        session,
        dict(event="decision", decision_id=2, kind="GAME_ASK", message="Mulligan?"),
    )
    decision = session.snapshot("one").decision
    session._request = lambda *args, **kwargs: {"accepted": False}
    result = session.choose("one", decision.decision_id, decision.options[0].option_id)
    assert result.outcome == "uncertain"
    assert session.snapshot("one").status == "failed"
    assert (
        session.choose(
            "one", decision.decision_id, decision.options[0].option_id
        ).outcome
        == "rejected"
    )


def test_engine_incarnation_retires_reference_without_intermediate_zone_snapshot(
    session,
):
    first = state(1, zone="battlefield")
    first["players"][0]["battlefield"][0]["incarnation"] = 3
    inject(session, first)
    before = session.snapshot("one").objects[0].object_id
    returned = state(2, zone="battlefield")
    returned["players"][0]["battlefield"][0]["incarnation"] = 5
    inject(session, returned)
    view = session.snapshot("one")
    assert view.objects[0].object_id != before
    assert "incarnation" not in json.dumps(view.to_dict())


def test_metadata_retry_does_not_publish_an_incoherent_view(session):
    update = state(1)
    update["cycle"] = 7
    session._owner._metadata = lambda view: {"status": "retry"}
    inject(session, update)
    with pytest.raises(AdapterError, match="SNAPSHOT_NOT_READY"):
        session.snapshot("one")
    session._owner._metadata = lambda view: dict(
        status="ok",
        cycle=7,
        objects={"engine-card": {"incarnation": 2}},
        commanders=[],
        players=[
            dict(id="engine-player-one", lost=False, left=False),
            dict(id="engine-player-two", lost=False, left=False),
        ],
    )
    view = session.snapshot("one")
    assert view.players[0].eliminated is False
    assert view.objects and view.commanders == ()


def test_commander_designation_is_distinct_from_current_object_identity(session):
    update = state(1)
    update["hand"][0]["incarnation"] = 1
    update["commanders"] = [
        dict(
            id="engine-card",
            owner="engine-player-one",
            name="Known commander",
            set="SOM",
            number="174",
            plays=1,
            tax="{2}",
            damage={"engine-player-two": 2},
        )
    ]
    inject(session, update)
    original = session.snapshot("one")
    update = deepcopy(update)
    update["sequence"] = 2
    update["hand"][0]["incarnation"] = 3
    inject(session, update)
    returned = session.snapshot("one")
    assert original.commanders[0].commander_id == returned.commanders[0].commander_id
    assert original.objects[0].object_id != returned.objects[0].object_id
    assert returned.commanders[0].damage_dealt == (("two", 2),)
    assert returned.commanders[0].additional_cast_cost == "{2}"
    assert "engine-card" not in json.dumps(returned.to_dict())


def test_private_observations_clear_without_exposing_persistent_object_links(session):
    revealed = state(1)
    revealed["observations"] = [
        dict(source="looked_at", hidden=False, name="SECRET", set="ABC", number="1")
    ]
    inject(session, revealed)
    view = session.snapshot("one")
    assert view.observations[0].name == "SECRET"
    assert not hasattr(view.observations[0], "object_id")
    assert not session.poll("two")
    inject(session, state(2))
    assert session.snapshot("one").observations == ()
    events = session.poll("one")
    assert any(event.kind == "cards_observed" for event in events)
    assert any(event.kind == "observations_cleared" for event in events)
    # Obsolete reveal cannot restore a concealed current observation.
    inject(session, revealed)
    assert session.snapshot("one").observations == ()


def test_hidden_observation_scrubs_even_malformed_engine_printing_fields(session):
    update = state(1)
    update["observations"] = [
        dict(
            source="revealed", hidden=True, name="SECRET", set="SECRET_SET", number="42"
        )
    ]
    inject(session, update)
    payload = json.dumps(session.snapshot("one").to_dict())
    assert "SECRET" not in payload
    assert session.snapshot("one").observations[0].name is None


def test_selected_targets_can_finish_without_claiming_cancellation(session):
    inject(session, state(1))
    inject(
        session,
        dict(
            event="decision",
            decision_id=2,
            kind="GAME_TARGET",
            message="Choose targets",
            targets=[],
            selected_targets=["engine-card"],
            can_finish=True,
            cancellable=False,
        ),
    )
    request = session.snapshot("one").decision
    assert len(request.options) == 1 and request.options[0].selected
    assert request.can_finish and not request.cancellable
    assert session.cancel("one", request.decision_id).outcome == "rejected"
    responses = []
    session._request = lambda *args, **kwargs: (
        responses.append(kwargs) or dict(accepted=True)
    )
    assert session.finish_selection("one", request.decision_id).outcome == "submitted"
    assert responses[0]["value"] is False


def test_copy_uses_physical_printing_instead_of_copied_display_printing(session):
    identity = CardIdentity("clone-oracle", "clone-print", "clone-entry")
    session._decks = (
        PreparedDeck((), (), {("M10", "45"): identity}),
        PreparedDeck((), (), {}),
    )
    update = state(1, zone="battlefield")
    update["players"][0]["battlefield"][0].update(
        owner="engine-player-one",
        physical_set="M10",
        physical_number="45",
        is_copy=True,
        name="Memnite",
    )
    inject(session, update)
    obj = session.snapshot("one").objects[0]
    assert obj.card_identity == identity
    assert obj.characteristics.name == "Memnite"
