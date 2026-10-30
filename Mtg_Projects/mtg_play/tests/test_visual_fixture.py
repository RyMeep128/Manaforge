"""Offline fixture publication, authentic-source preservation and raw pixel contract."""

import hashlib
import json

from PyQt6.QtGui import QColor, QImage
import pytest

from mtg_play.visual_fixture import export_visual_fixture, VisualFixtureError
from mtg_play.tests.test_visual_catalog import Service, card


def source(tmp_path):
    path = tmp_path / "authentic-source.png"
    image = QImage(2, 3, QImage.Format.Format_RGBA8888)
    image.fill(QColor("red"))
    image.setPixelColor(0, 2, QColor(10, 20, 30, 255))
    assert image.save(str(path), "PNG")
    return path


def test_raw_rgba_is_bottom_left_and_original_source_is_unchanged(tmp_path):
    path = source(tmp_path)
    before = path.read_bytes()
    service = Service(card("selected"), paths={("selected", "default"): path})
    output = tmp_path / "bundle"
    manifest = export_visual_fixture(service, [("selected", 0)], output)
    asset = manifest["assets"][0]
    raw = (output / asset["file"]).read_bytes()
    assert raw[:4] == bytes([10, 20, 30, 255])
    assert asset["row_origin"] == "bottom_left" and asset["pixel_format"] == "RGBA8"
    assert (asset["width"], asset["height"], len(raw)) == (2, 3, 24)
    assert hashlib.sha256(raw).hexdigest() == asset["sha256"]
    assert path.read_bytes() == before
    assert manifest["fixture_only"] is True
    assert manifest["cards"][0]["values_source"] == "printed_reference_mock"
    assert (
        json.loads((output / "manifest.json").read_text(encoding="utf-8")) == manifest
    )
    assert str(path) not in json.dumps(manifest)
    assert "local_path" not in json.dumps(manifest)


def test_selected_original_and_standard_candidate_share_resources_without_substitution(
    tmp_path,
):
    path = source(tmp_path)
    selected = card("special")
    selected["full_art"] = True
    service = Service(
        selected,
        [card("standard")],
        {("special", "default"): path, ("standard", "default"): path},
    )
    manifest = export_visual_fixture(service, [("special", 0)], tmp_path / "bundle")
    assert len(manifest["assets"]) == 1
    visual = manifest["cards"][0]
    assert visual["selected_printing_id"] == "special"
    assert [item["cached"] for item in visual["candidates"]] == [True, True]
    assert visual["candidates"][0]["standard_compatible"] is False
    assert visual["candidates"][1]["standard_compatible"] is True
    assert "rendered_printing_id" not in visual  # Unity's existing policy chooses it.


def test_correct_face_reference_and_asset_are_preserved(tmp_path):
    path = source(tmp_path)
    selected = card("selected")
    selected.update(
        layout="transform",
        card_faces=[
            {"name": "Front"},
            {"name": "Back", "oracle_text": "Printed back text"},
        ],
    )
    service = Service(selected, paths={("selected", "face-1"): path})
    visual = export_visual_fixture(service, [("selected", 1)], tmp_path / "bundle")[
        "cards"
    ][0]
    assert visual["selected_face"] == "Back"
    assert visual["mock_values"]["name"] == "Back"
    assert visual["candidates"][0]["face_index"] == 1
    assert ("selected", "default") not in service.calls


def test_no_artwork_publishes_no_manifest_or_fake_image(tmp_path):
    output = tmp_path / "bundle"
    with pytest.raises(VisualFixtureError, match="VISUAL_FIXTURE_NO_ARTWORK"):
        export_visual_fixture(Service(card("selected")), [("selected", 0)], output)
    assert not (output / "manifest.json").exists()
    assert not list(output.glob("*.rgba"))


def test_budget_failure_leaves_no_loadable_manifest(tmp_path):
    path = source(tmp_path)
    service = Service(card("selected"), paths={("selected", "default"): path})
    output = tmp_path / "bundle"
    with pytest.raises(VisualFixtureError, match="VISUAL_FIXTURE_BUDGET"):
        export_visual_fixture(service, [("selected", 0)], output, max_asset_bytes=1)
    assert not (output / "manifest.json").exists()


def test_existing_destination_is_never_overwritten(tmp_path):
    output = tmp_path / "bundle"
    output.mkdir()
    original = output / "keep.txt"
    original.write_text("original", encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_visual_fixture(Service(card("selected")), [("selected", 0)], output)
    assert original.read_text(encoding="utf-8") == "original"


def test_scaling_is_bounded_and_never_upscales(tmp_path):
    path = source(tmp_path)
    service = Service(card("selected"), paths={("selected", "default"): path})
    asset = export_visual_fixture(
        service, [("selected", 0)], tmp_path / "small", max_edge=2
    )["assets"][0]
    assert max(asset["width"], asset["height"]) <= 2
    asset = export_visual_fixture(
        service, [("selected", 0)], tmp_path / "normal", max_edge=100
    )["assets"][0]
    assert (asset["width"], asset["height"]) == (2, 3)


def test_expanded_gallery_capacity_still_shares_artwork(tmp_path):
    path = source(tmp_path)
    service = Service(card("selected"), paths={("selected", "default"): path})
    manifest = export_visual_fixture(
        service, [("selected", 0)] * 32, tmp_path / "gallery"
    )
    assert len(manifest["cards"]) == 32
    assert len(manifest["assets"]) == 1


def test_expanded_gallery_keeps_the_unity_48_asset_limit(tmp_path, monkeypatch):
    from mtg_play.visual_catalog import VisualAssetCandidate

    def candidates(service, printing, face_index, **kwargs):
        result = []
        for i in range(3):
            index = int(printing.split("-")[1]) * 3 + i
            path = tmp_path / f"source-{index}.png"
            image = QImage(1, 1, QImage.Format.Format_RGBA8888)
            image.fill(QColor(index, 0, 0, 255))
            assert image.save(str(path), "PNG")
            result.append(
                VisualAssetCandidate(
                    "oracle", f"{printing}-{i}", "Card", 0, True, True, str(path)
                )
            )
        return result

    monkeypatch.setattr("mtg_play.visual_fixture.collect_visual_candidates", candidates)
    output = tmp_path / "bounded"
    with pytest.raises(VisualFixtureError, match="VISUAL_FIXTURE_ASSET_LIMIT"):
        export_visual_fixture(
            Service(card("selected")), [(f"p-{i}", 0) for i in range(17)], output
        )
    assert not (output / "manifest.json").exists()
