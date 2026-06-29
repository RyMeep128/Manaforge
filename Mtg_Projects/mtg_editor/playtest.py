from __future__ import annotations

from dataclasses import dataclass, field
import random

from mtg_editor.models import DeckCard, DeckProject


DEFAULT_PLAYTEST_SECTIONS = {"main"}


@dataclass(frozen=True)
class PlaytestCard:
    card_id: str
    name: str
    copy_number: int
    section: str
    image_path: str | None = None
    image_uri: str | None = None
    image_asset_id: str | None = None
    local_image_path: str | None = None
    preview_uri: str | None = None
    thumbnail_uri: str | None = None
    catalog_status: str | None = None
    missing_image: bool = False


@dataclass
class PlaytestSession:
    original_library: list[PlaytestCard]
    library: list[PlaytestCard]
    hand: list[PlaytestCard]
    draw_history: list[PlaytestCard] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sections: set[str] = field(default_factory=lambda: set(DEFAULT_PLAYTEST_SECTIONS))
    seed: int | str | None = None


def build_playtest_library(
    project: DeckProject,
    sections: set[str] | list[str] | tuple[str, ...] | None = None,
) -> list[PlaytestCard]:
    allowed_sections = _normalize_sections(sections)
    library: list[PlaytestCard] = []
    for card in project.cards:
        if card.quantity <= 0 or card.section not in allowed_sections:
            continue
        for copy_number in range(1, card.quantity + 1):
            library.append(_playtest_card_from_deck_card(card, copy_number))
    return library


def start_playtest(
    project: DeckProject,
    hand_size: int = 7,
    seed: int | str | None = None,
    sections: set[str] | list[str] | tuple[str, ...] | None = None,
) -> PlaytestSession:
    full_library = build_playtest_library(project, sections=sections)
    shuffled_library = _shuffled(full_library, seed)
    hand, remaining_library = _draw_from_library(shuffled_library, hand_size)
    warnings = _build_warnings(full_library, hand_size)
    return PlaytestSession(
        original_library=list(shuffled_library),
        library=remaining_library,
        hand=hand,
        draw_history=[],
        warnings=warnings,
        sections=_normalize_sections(sections),
        seed=seed,
    )


def mulligan(session: PlaytestSession, hand_size: int) -> PlaytestSession:
    shuffled_library = _shuffled(session.original_library, _next_seed(session.seed, "mulligan", hand_size))
    hand, remaining_library = _draw_from_library(shuffled_library, hand_size)
    return PlaytestSession(
        original_library=list(shuffled_library),
        library=remaining_library,
        hand=hand,
        draw_history=[],
        warnings=_build_warnings(session.original_library, hand_size),
        sections=set(session.sections),
        seed=session.seed,
    )


def draw_cards(session: PlaytestSession, count: int = 1) -> list[PlaytestCard]:
    draw_count = max(0, int(count))
    drawn = session.library[:draw_count]
    session.library = session.library[draw_count:]
    session.hand.extend(drawn)
    session.draw_history.extend(drawn)
    if draw_count > len(drawn):
        _add_warning(session.warnings, "The playtest library is empty.")
    return drawn


def reset_playtest(
    session: PlaytestSession,
    hand_size: int = 7,
    seed: int | str | None = None,
) -> PlaytestSession:
    next_seed = session.seed if seed is None else seed
    shuffled_library = _shuffled(session.original_library, next_seed)
    hand, remaining_library = _draw_from_library(shuffled_library, hand_size)
    return PlaytestSession(
        original_library=list(shuffled_library),
        library=remaining_library,
        hand=hand,
        draw_history=[],
        warnings=_build_warnings(shuffled_library, hand_size),
        sections=set(session.sections),
        seed=next_seed,
    )


def append_playtest_note(project: DeckProject, note: str) -> None:
    clean_note = str(note or "").strip()
    if not clean_note:
        return
    entry = f"Playtest: {clean_note}"
    project.notes = f"{project.notes.rstrip()}\n{entry}".strip()


def _playtest_card_from_deck_card(card: DeckCard, copy_number: int) -> PlaytestCard:
    missing_image = not _has_image(card)
    return PlaytestCard(
        card_id=card.card_id,
        name=card.name,
        copy_number=copy_number,
        section=card.section,
        image_path=card.image_path,
        image_uri=card.image_uri,
        image_asset_id=card.image_asset_id,
        local_image_path=card.local_image_path,
        preview_uri=card.preview_uri,
        thumbnail_uri=card.thumbnail_uri,
        catalog_status=card.catalog_status,
        missing_image=missing_image,
    )


def _normalize_sections(
    sections: set[str] | list[str] | tuple[str, ...] | None,
) -> set[str]:
    if sections is None:
        return set(DEFAULT_PLAYTEST_SECTIONS)
    normalized = {"_".join(str(section or "").strip().lower().split()) for section in sections}
    return {section for section in normalized if section} or set(DEFAULT_PLAYTEST_SECTIONS)


def _shuffled(library: list[PlaytestCard], seed: int | str | None) -> list[PlaytestCard]:
    shuffled_library = list(library)
    random.Random(seed).shuffle(shuffled_library)
    return shuffled_library


def _draw_from_library(
    library: list[PlaytestCard],
    count: int,
) -> tuple[list[PlaytestCard], list[PlaytestCard]]:
    draw_count = max(0, int(count))
    return library[:draw_count], library[draw_count:]


def _build_warnings(library: list[PlaytestCard], requested_hand_size: int) -> list[str]:
    warnings: list[str] = []
    if not library:
        warnings.append("The playtest library is empty.")
    elif requested_hand_size > len(library):
        warnings.append("The requested hand is larger than the playtest library.")
    if any(card.missing_image for card in library):
        warnings.append("Some playtest cards are missing printable images.")
    return warnings


def _add_warning(warnings: list[str], warning: str) -> None:
    if warning not in warnings:
        warnings.append(warning)


def _next_seed(seed: int | str | None, action: str, value: int) -> str | None:
    if seed is None:
        return None
    return f"{seed}:{action}:{value}"


def _has_image(card: DeckCard) -> bool:
    return any(
        [
            card.image_path,
            card.image_uri,
            card.image_asset_id,
            card.local_image_path,
            card.preview_uri,
            card.thumbnail_uri,
        ]
    )
