import pytest

import card_layouts
import pdf
from models import ProjectState
from services import layout_service


@pytest.mark.parametrize("layout", [
    "meld", "split", "aftermath", "adventure", "flip", "planar",
    "scheme", "token", "custom",
])
def test_single_image_layouts_use_one_slot_by_default(layout):
    policy = card_layouts.policy_for_layout(layout)
    state = ProjectState.from_dict({"cards": {f"{layout}.png": 1}})
    copy = next(iter(layout_service.copies(state).values()))

    assert policy.image_mode == "single-image"
    assert policy.paired_back is False
    assert policy.footprint == "single-slot"
    assert copy["span"] == 1


@pytest.mark.parametrize("layout", [
    "transform", "modal_dfc", "double_faced_token", "reversible_card",
    "art_series",
])
def test_independently_imaged_dfc_layouts_require_paired_backs(layout):
    payload = {
        "layout": layout,
        "card_faces": [
            {"image_uris": {"png": "front"}},
            {"image_uris": {"png": "back"}},
        ],
    }

    assert card_layouts.policy_for_layout(layout).paired_back is True
    assert card_layouts.has_printed_back(payload) is True


def test_battle_uses_scryfall_transform_pairing_rule():
    payload = {
        "layout": "transform", "type_line": "Battle — Siege",
        "card_faces": [
            {"image_uris": {"png": "battle-front"}},
            {"image_uris": {"png": "creature-back"}},
        ],
    }

    assert card_layouts.has_printed_back(payload) is True


@pytest.mark.parametrize("layout", ["split", "aftermath", "adventure", "flip", "custom"])
def test_non_dfc_layout_never_invents_back_from_face_metadata(layout):
    payload = {
        "layout": layout,
        "card_faces": [{"name": "First"}, {"name": "Second"}],
    }

    assert card_layouts.has_printed_back(payload) is False


def test_oversized_remains_explicit_for_landscape_and_custom_layouts():
    for name in ("plane.png", "scheme.png", "custom.png"):
        state = ProjectState.from_dict({
            "cards": {name: 1}, "oversized_enabled": True,
            "oversized": {name: True},
        })
        copy = next(iter(layout_service.copies(state).values()))
        assert copy["span"] == 2


@pytest.mark.parametrize("card_layout", [
    "normal", "transform", "modal_dfc", "double_faced_token",
    "reversible_card", "art_series", "meld", "split", "aftermath", "adventure",
    "flip", "planar", "scheme", "token", "custom",
])
def test_every_supported_layout_can_roundtrip_an_oversized_mirrored_back(card_layout):
    name = f"{card_layout}-front.png"
    back = f"{card_layout}-back.png"
    policy = card_layouts.policy_for_layout(card_layout)
    state = ProjectState.from_dict({
        "cards": {name: 1},
        "oversized_enabled": True,
        "oversized": {name: True},
        "backside_enabled": True,
        "backsides": {name: back},
    })
    state = ProjectState.from_dict(state.to_persisted_dict())
    items, _ = layout_service.resolve(state, 3, 1)

    assert policy.oversized_compatible is True
    assert layout_service.cells(items[0]) == {(0, 0, 0), (0, 0, 1)}
    front_pages = layout_service.pages_from_items(state, items, 3, 1)
    back_page = next(
        page for page in pdf.make_render_page_sequence(state, front_pages)
        if page["backside"])
    back_grid = pdf.distribute_cards_to_grid(back_page["cards"], False, 3, 1)
    assert back_grid[0][1] == (back, False, True)
    assert back_grid[0][2] == (None, None, None)


@pytest.mark.parametrize("card_layout", [
    "transform", "modal_dfc", "double_faced_token", "reversible_card",
    "art_series",
])
def test_oversized_dfc_requires_two_horizontal_slots(card_layout):
    name = f"{card_layout}.png"
    state = ProjectState.from_dict({
        "cards": {name: 1}, "oversized_enabled": True,
        "oversized": {name: True},
    })

    with pytest.raises(ValueError, match="cannot fit"):
        layout_service.resolve(state, 1, 9)


def test_unknown_layout_uses_safe_single_image_fallback():
    policy = card_layouts.policy_for_layout("future_tri_fold")

    assert policy.recognized is False
    assert policy.image_mode == "single-image"
    assert policy.paired_back is False
    assert policy.footprint == "single-slot"
    assert policy.oversized_compatible is True
