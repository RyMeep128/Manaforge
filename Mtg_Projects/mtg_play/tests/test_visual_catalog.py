"""Focused offline catalog boundary checks, with synthetic artwork only."""

import pytest
from PyQt6.QtGui import QImage

from mtg_play.visual_catalog import collect_visual_candidates


def card(identity, **overrides):
    return dict(
        id=identity,
        oracle_id="oracle",
        name="Card",
        layout="normal",
        frame="2015",
        border_color="black",
        full_art=False,
        textless=False,
        promo=False,
        **overrides,
    )


class Service:
    def __init__(self, selected, prints=(), paths=None):
        self.selected, self.prints, self.paths = selected, list(prints), paths or {}
        self.calls = []

    def get_card(self, *, card_id):
        self.calls.append(("card", card_id))
        return self.selected

    def get_prints(self, oracle_id, *, allow_remote):
        assert allow_remote is False
        self.calls.append(("prints", oracle_id))
        return self.prints

    def get_image_path(self, identity, *, variant):
        self.calls.append((identity, variant))
        return self.paths.get((identity, variant))


def image(tmp_path):
    path = tmp_path / "image.png"
    value = QImage(4, 4, QImage.Format.Format_RGB32)
    value.fill(0)
    assert value.save(str(path), "PNG")
    return path


def test_preserves_selection_and_catalog_order_is_deterministic(tmp_path):
    selected = card("special")
    selected["full_art"] = True
    service = Service(
        selected, [card("z"), card("a"), selected], {("a", "default"): image(tmp_path)}
    )
    result = collect_visual_candidates(service, "special")
    assert tuple(item.printing_id for item in result) == ("special", "a", "z")
    assert not result[0].standard_compatible
    assert result[1].standard_compatible and result[1].cached
    assert selected["full_art"] is True
    with pytest.raises(AttributeError):
        result[0].printing_id = "changed"


def test_concealed_input_never_accesses_service():
    assert collect_visual_candidates(None, None, concealed=True) == ()


def test_wrong_oracle_and_wrong_face_are_excluded():
    selected = card("selected")
    selected.update(
        layout="transform", card_faces=[{"name": "Front"}, {"name": "Back"}]
    )
    wrong = card("wrong")
    wrong["oracle_id"] = "unrelated"
    front = card("front")
    front["name"] = "Front"
    service = Service(selected, [wrong, front])
    result = collect_visual_candidates(service, "selected", 1)
    assert len(result) == 1
    assert result[0].face_key == "Back"
    assert ("selected", "face-1") in service.calls
    assert ("selected", "default") not in service.calls


def test_face_matching_uses_name_not_index():
    selected = card("selected")
    selected.update(
        layout="transform", card_faces=[{"name": "Front"}, {"name": "Back"}]
    )
    alternate = card("alternate")
    alternate.update(
        layout="transform", card_faces=[{"name": "Back"}, {"name": "Front"}]
    )
    result = collect_visual_candidates(Service(selected, [alternate]), "selected", 1)
    assert result[1].face_index == 0
    assert result[1].face_key == "Back"


def test_corrupt_or_missing_files_are_not_cached(tmp_path):
    corrupt = tmp_path / "corrupt.png"
    corrupt.write_bytes(b"not an image")
    service = Service(
        card("selected"), [card("missing")], {("selected", "default"): corrupt}
    )
    result = collect_visual_candidates(service, "selected")
    assert all(not item.cached and item.local_path is None for item in result)


def test_flip_back_is_not_marked_as_front_artwork(tmp_path):
    selected = card("selected")
    selected.update(layout="flip", card_faces=[{"name": "Front"}, {"name": "Back"}])
    service = Service(selected, paths={("selected", "default"): image(tmp_path)})
    result = collect_visual_candidates(service, "selected", 1)
    assert not result[0].cached
    assert not any(call[0] == "selected" for call in service.calls)


@pytest.mark.parametrize(
    "field,value",
    [
        ("layout", "saga"),
        ("frame", "1997"),
        ("border_color", "borderless"),
        ("full_art", True),
        ("promo", True),
        ("textless", True),
        ("frame_effects", ["showcase"]),
        ("full_art", None),
    ],
)
def test_special_or_unknown_treatments_stay_authentic(field, value):
    selected = card("selected")
    selected[field] = value
    assert not collect_visual_candidates(Service(selected), "selected")[
        0
    ].standard_compatible


@pytest.mark.parametrize("face", [-1, True, 5])
def test_invalid_or_unavailable_face_is_explicit(face):
    with pytest.raises(ValueError, match="VISUAL_"):
        collect_visual_candidates(Service(card("selected")), "selected", face)


def test_ambiguous_selected_face_is_rejected_before_asset_access():
    selected = card("selected")
    selected["card_faces"] = [{"name": "Same"}, {"name": "Same"}]
    service = Service(selected)
    with pytest.raises(ValueError, match="VISUAL_FACE_AMBIGUOUS"):
        collect_visual_candidates(service, "selected", 1)
    assert service.calls == [("card", "selected")]


def test_opt_in_budget_preserves_selected_then_prefers_standard_without_decoding_every_print(
    tmp_path,
):
    selected = card("selected")
    selected["full_art"] = True
    other_special = card("0-special")
    other_special["full_art"] = True
    path = image(tmp_path)
    service = Service(
        selected,
        [other_special, card("a-standard")],
        {
            ("selected", "default"): path,
            ("0-special", "default"): path,
            ("a-standard", "default"): path,
        },
    )
    result = collect_visual_candidates(service, "selected", max_cached_candidates=2)
    assert [(item.printing_id, item.cached) for item in result] == [
        ("selected", True),
        ("a-standard", True),
        ("0-special", False),
    ]
    assert ("0-special", "default") not in service.calls


def test_invalid_preparation_budget_fails_before_catalog_access():
    with pytest.raises(ValueError, match="VISUAL_CANDIDATE_BUDGET"):
        collect_visual_candidates(None, "selected", max_cached_candidates=0)
