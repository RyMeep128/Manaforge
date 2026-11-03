"""Local crop/cache/offline regressions; run in GitHub Actions."""

from dataclasses import replace
from threading import get_ident

import pytest
from PyQt6 import QtGui as G, QtWidgets as W
from mtg_play.artwork_cache import read_local_image, RENDER_VERSION
from mtg_play.artwork import PlayArtwork
from mtg_play.contracts import CardIdentity
from mtg_play.tests.test_table import card
from mtg_play.tests.test_presentation import drain


@pytest.fixture
def app():
    return W.QApplication.instance() or W.QApplication([])


def source(path, top="green", bottom="red"):
    image = G.QImage(100, 140, G.QImage.Format.Format_RGB32)
    image.fill(G.QColor(top))
    painter = G.QPainter(image)
    painter.fillRect(0, 82, 100, 58, G.QColor(bottom))
    painter.end()
    assert image.save(str(path), "PNG")
    return path


def test_readable_resolution_keeps_native_detail_without_upscaling(tmp_path, app):
    path = tmp_path / "native.png"
    image = G.QImage(1400, 1960, G.QImage.Format.Format_RGB32)
    image.fill(G.QColor("green"))
    assert image.save(str(path), "PNG")
    obj = replace(
        card("visible", zone="hand"), card_identity=CardIdentity(None, "printing", None)
    )
    service = LocalOnlyService({("printing", "default"): path})
    normal = PlayArtwork.key(obj)
    detailed = PlayArtwork.key(obj, detailed=True)
    assert normal[2] == 600
    assert detailed[2] == 1200
    assert read_local_image(service, normal).width() == 600
    assert read_local_image(service, detailed).width() == 1200
    source(path)
    assert read_local_image(service, detailed).width() == 100


def test_inspection_samples_physical_pixels_for_high_dpi(app):
    from mtg_play.table import inspection_pixmap

    class Display:
        def devicePixelRatioF(self):
            return 2.0

    image = G.QPixmap(1200, 1680)
    image.fill(G.QColor("green"))
    result = inspection_pixmap(image, Display(), 400, 560)
    assert result.width() == 800
    assert result.height() == 1120
    assert result.devicePixelRatioF() == 2.0


class LocalOnlyService:
    def __init__(self, paths, layout="transform"):
        self.paths, self.layout, self.calls = paths, layout, []

    def get_image_path(self, printing, variant="default"):
        self.calls.append((printing, variant, get_ident()))
        return self.paths.get((printing, variant))

    def get_card(self, **kwargs):
        return {"layout": self.layout}

    def ensure_image(self, *a, **k):
        raise AssertionError("Remote fallback forbidden")

    ensure_face_image = ensure_image
    fetch_bytes_fn = ensure_image
    fetch_missing_card = ensure_image


def test_crop_preserves_upper_card_and_original_and_reuses_shared_cache(tmp_path):
    path = source(tmp_path / "front.png")
    original = path.read_bytes()
    service = LocalOnlyService({("printing", "default"): path})
    key = ("printing", None, 300, 0, RENDER_VERSION)
    cropped = read_local_image(service, key, cache_root=tmp_path / "cache")
    assert (cropped.width(), cropped.height()) == (100, 76)
    assert cropped.pixelColor(50, 75) == G.QColor("green")
    files = list((tmp_path / "cache").rglob("*.png"))
    assert len(files) == 1
    modified = files[0].stat().st_mtime_ns
    assert read_local_image(service, key, cache_root=tmp_path / "cache") == cropped
    assert files[0].stat().st_mtime_ns == modified
    detailed = read_local_image(service, ("printing", None, 600, 0))
    assert detailed.height() == 140 and detailed.pixelColor(50, 139) == G.QColor("red")
    assert path.read_bytes() == original
    source(path, top="blue")
    updated = read_local_image(service, key, cache_root=tmp_path / "cache")
    assert updated.pixelColor(50, 0) == G.QColor("blue")
    assert len(list((tmp_path / "cache").rglob("*.png"))) == 2


def test_face_sources_and_flip_orientation_remain_printing_specific(tmp_path):
    front = source(tmp_path / "front.png")
    back = source(tmp_path / "back.png", top="blue")
    service = LocalOnlyService(
        {("printing", "default"): front, ("printing", "face-1"): back}
    )
    key = ("printing", None, 300, 1, RENDER_VERSION)
    assert read_local_image(service, key, cache_root=tmp_path).pixelColor(
        50, 0
    ) == G.QColor("blue")
    assert read_local_image(service, ("other", None, 300, 1)).isNull()
    flip = LocalOnlyService({("printing", "default"): front}, layout="flip")
    assert read_local_image(flip, key, cache_root=tmp_path).pixelColor(
        50, 0
    ) == G.QColor("red")


def test_missing_or_corrupt_local_face_is_placeholder_without_remote_fallback(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    service = LocalOnlyService({("printing", "default"): bad})
    assert read_local_image(
        service, ("printing", None, 300, 0, RENDER_VERSION), cache_root=tmp_path
    ).isNull()
    assert read_local_image(service, ("printing", None, 600, 1)).isNull()
    assert read_local_image(service, ("unknown", None, 600, 0)).isNull()


def test_play_reader_generates_crop_off_gui_and_inspection_keeps_full_key(
    app, tmp_path, monkeypatch
):
    monkeypatch.setenv("PRINT_PROXY_PREP_DATA_DIR", str(tmp_path / "data"))
    path = source(tmp_path / "front.png")
    service = LocalOnlyService({("printing", "default"): path})
    artwork = PlayArtwork(service)
    obj = card("one", card_identity=CardIdentity("oracle", "printing", "entry"))
    artwork.show_objects((obj,))
    assert artwork.key(obj)[4] == RENDER_VERSION
    assert len(artwork.key(obj, detailed=True)) == 4
    assert len(artwork.key(replace(obj, zone="hand"))) == 4
    artwork.get(obj)
    drain(app, lambda: artwork.key(obj) in artwork.cache and artwork.worker is None)
    assert artwork.get(obj).height() == 76
    assert service.calls and all(
        thread != get_ident() for _, _, thread in service.calls
    )
    artwork.get(obj, detailed=True)
    drain(
        app,
        lambda: (
            artwork.key(obj, detailed=True) in artwork.cache and artwork.worker is None
        ),
    )
    assert artwork.get(obj, detailed=True).height() == 140
    assert artwork.shutdown()


def test_generic_crop_excludes_top_of_lower_rules_area(tmp_path):
    path = source(tmp_path / "rules.png")
    image = G.QImage(str(path))
    painter = G.QPainter(image)
    painter.fillRect(0, 78, 100, 62, G.QColor("red"))
    painter.end()
    assert image.save(str(path), "PNG")
    service = LocalOnlyService({("printing", "default"): path}, layout="normal")
    crop = read_local_image(
        service,
        ("printing", None, 300, 0, RENDER_VERSION),
        cache_root=tmp_path / "cache",
    )
    assert crop.height() == 76
    assert crop.pixelColor(50, crop.height() - 1) == G.QColor("green")
