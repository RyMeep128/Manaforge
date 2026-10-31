import hashlib
import json

import pytest
from PyQt6.QtGui import QColor, QImage

from mtg_play.artwork_bundle import ArtworkBundleError, export_artwork_bundle
from mtg_play.tests.test_visual_catalog import Service, card


def test_exact_cached_pixels_pin_context_and_source_are_preserved(tmp_path):
    source = tmp_path / "original.png"
    image = QImage(2, 3, QImage.Format.Format_RGBA8888)
    image.fill(QColor("red"))
    image.setPixelColor(0, 2, QColor(10, 20, 30, 255))
    assert image.save(str(source))
    before = source.read_bytes()
    service = Service(
        card("selected", type_line="Creature"), paths={("selected", "default"): source}
    )
    output = tmp_path / "assets"
    manifest, pin = export_artwork_bundle(
        service, ["selected"], output, session_id="session", viewer_id="one"
    )
    entry = manifest["entries"][0]
    raw = (output / entry["file"]).read_bytes()
    assert raw[:4] == bytes([10, 20, 30, 255])
    assert entry["printing_id"] == "selected" and entry["oracle_id"] == "oracle"
    assert entry["sha256"] == hashlib.sha256(raw).hexdigest()
    assert pin == hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest()
    assert manifest["viewer_id"] == "one" and manifest["session_id"] == "session"
    assert source.read_bytes() == before and str(source) not in json.dumps(manifest)


def test_available_alternative_never_substitutes_for_missing_selected_art(tmp_path):
    source = tmp_path / "alternate.png"
    image = QImage(2, 2, QImage.Format.Format_RGBA8888)
    image.fill(0)
    assert image.save(str(source))
    service = Service(
        card("selected", type_line="Creature"),
        [card("alternate", type_line="Creature")],
        {("alternate", "default"): source},
    )
    manifest, _ = export_artwork_bundle(
        service, ["selected"], tmp_path / "assets", session_id="s", viewer_id="v"
    )
    assert manifest["entries"] == []
    assert manifest["unavailable"] == [
        {"printing_id": "selected", "code": "ARTWORK_MISSING"}
    ]


def test_unsupported_printing_is_explicit_and_no_deck_or_source_path_is_exported(
    tmp_path,
):
    payload = card("selected", type_line="Creature")
    payload["full_art"] = True
    service = Service(payload)
    manifest, _ = export_artwork_bundle(
        service, ["selected"], tmp_path / "assets", session_id="s", viewer_id="v"
    )
    assert (
        manifest["entries"] == []
        and manifest["unavailable"][0]["code"] == "ARTWORK_FACE_UNSUPPORTED"
    )
    assert "deck" not in json.dumps(manifest) and "local_path" not in json.dumps(
        manifest
    )


@pytest.mark.parametrize("ids", [[], ["a", "a"], [None], [["a"]]])
def test_bad_input_never_creates_an_output_directory(tmp_path, ids):
    output = tmp_path / "assets"
    with pytest.raises(ArtworkBundleError):
        export_artwork_bundle(None, ids, output, session_id="s", viewer_id="v")
    assert not output.exists()


def test_budget_failure_never_publishes_a_partial_manifest(tmp_path):
    source = tmp_path / "source.png"
    image = QImage(2, 2, QImage.Format.Format_RGBA8888)
    image.fill(0)
    assert image.save(str(source))
    service = Service(
        card("selected", type_line="Creature"), paths={("selected", "default"): source}
    )
    output = tmp_path / "assets"
    with pytest.raises(ArtworkBundleError, match="CORE_ARTWORK_BUDGET"):
        export_artwork_bundle(
            service,
            ["selected"],
            output,
            session_id="s",
            viewer_id="v",
            max_asset_bytes=1,
        )
    assert not (output / "manifest.json").exists()
