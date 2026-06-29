from __future__ import annotations

from mtg_editor.models import DeckProject
from mtg_editor.playtest import (
    append_playtest_note,
    build_playtest_library,
    draw_cards,
    mulligan,
    reset_playtest,
    start_playtest,
)


def test_build_playtest_library_expands_main_deck_quantities_only():
    project = _project()

    library = build_playtest_library(project)

    assert len(library) == 9
    assert [(card.card_id, card.copy_number) for card in library].count(("bolt", 1)) == 1
    assert [card.copy_number for card in library if card.card_id == "bolt"] == [1, 2, 3, 4]
    assert [card.card_id for card in library] == [
        "bolt",
        "bolt",
        "bolt",
        "bolt",
        "island",
        "island",
        "island",
        "missing",
        "missing",
    ]
    assert all(card.section == "main" for card in library)


def test_build_playtest_library_can_include_extra_sections():
    project = _project()

    library = build_playtest_library(project, sections={"main", "sideboard", "commander"})

    assert len(library) == 12
    assert [card.card_id for card in library].count("sideboard") == 2
    assert [card.card_id for card in library].count("commander") == 1
    assert "excluded" not in {card.card_id for card in library}


def test_start_playtest_draws_deterministic_opening_hand():
    project = _project()

    first = start_playtest(project, hand_size=7, seed=123)
    second = start_playtest(project, hand_size=7, seed=123)

    assert _signature(first.hand) == _signature(second.hand)
    assert len(first.original_library) == 9
    assert len(first.hand) == 7
    assert len(first.library) == 2
    assert first.draw_history == []
    assert "Some playtest cards are missing printable images." in first.warnings


def test_mulligan_reshuffles_full_library_to_requested_hand_sizes():
    session = start_playtest(_project(), hand_size=7, seed="deck")

    six = mulligan(session, 6)
    five = mulligan(six, 5)
    one = mulligan(five, 1)

    assert len(six.original_library) == 9
    assert len(six.hand) == 6
    assert len(six.library) == 3
    assert six.draw_history == []
    assert len(five.hand) == 5
    assert len(five.library) == 4
    assert len(one.hand) == 1
    assert len(one.library) == 8


def test_draw_cards_updates_library_hand_and_history():
    session = start_playtest(_project(), hand_size=3, seed=9)
    opening_hand = list(session.hand)

    first_draw = draw_cards(session)
    rest = draw_cards(session, 99)

    assert len(first_draw) == 1
    assert len(rest) == 5
    assert len(session.library) == 0
    assert session.hand == opening_hand + first_draw + rest
    assert session.draw_history == first_draw + rest
    assert "The playtest library is empty." in session.warnings


def test_reset_playtest_restores_full_library_and_clears_history():
    session = start_playtest(_project(), hand_size=3, seed=9)
    draw_cards(session, 2)

    reset = reset_playtest(session, hand_size=4, seed=10)

    assert len(reset.original_library) == 9
    assert len(reset.hand) == 4
    assert len(reset.library) == 5
    assert reset.draw_history == []
    assert len(session.hand) == 5


def test_missing_image_cards_warn_but_remain_playable():
    session = start_playtest(_project(), hand_size=9, seed=1)

    missing_cards = [card for card in session.hand if card.missing_image]

    assert [card.card_id for card in missing_cards] == ["missing", "missing"]
    assert "Some playtest cards are missing printable images." in session.warnings


def test_start_playtest_handles_empty_library_without_crashing():
    project = DeckProject.new()

    session = start_playtest(project, hand_size=7, seed=1)

    assert session.original_library == []
    assert session.library == []
    assert session.hand == []
    assert session.warnings == ["The playtest library is empty."]


def test_append_playtest_note_persists_in_project_notes():
    project = DeckProject.new()
    project.notes = "Initial note."

    append_playtest_note(project, "Need more lands.")
    append_playtest_note(project, "  ")
    append_playtest_note(project, "Opening hands are smooth.")

    assert project.notes == "\n".join(
        [
            "Initial note.",
            "Playtest: Need more lands.",
            "Playtest: Opening hands are smooth.",
        ]
    )


def test_playtest_does_not_change_project_quantities_or_sections():
    project = _project()
    before = [(card.card_id, card.quantity, card.section) for card in project.cards]

    session = start_playtest(project, hand_size=7, seed=4)
    draw_cards(session, 2)
    mulligan(session, 5)
    reset_playtest(session, hand_size=7)

    assert [(card.card_id, card.quantity, card.section) for card in project.cards] == before


def _project():
    project = DeckProject.new("Playtest")
    project.add_card(
        "Lightning Bolt",
        quantity=4,
        card_id="bolt",
        image_uri="https://img.test/bolt.png",
        catalog_status="resolved",
    )
    project.add_card(
        "Island",
        quantity=3,
        card_id="island",
        image_uri="https://img.test/island.png",
        catalog_status="resolved",
    )
    project.add_card(
        "Mystery Card",
        quantity=2,
        card_id="missing",
        catalog_status="unresolved",
    )
    project.add_card(
        "Sideboard Card",
        quantity=2,
        card_id="sideboard",
        section="sideboard",
        image_uri="https://img.test/sideboard.png",
    )
    project.add_card(
        "Commander Card",
        quantity=1,
        card_id="commander",
        section="commander",
        image_uri="https://img.test/commander.png",
    )
    project.add_card("Zero Card", quantity=0, card_id="zero")
    project.add_card("Excluded Card", quantity=1, card_id="excluded", section="excluded")
    return project


def _signature(cards):
    return [(card.card_id, card.copy_number) for card in cards]
