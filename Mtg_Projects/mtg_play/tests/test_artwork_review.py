"""Offline review artifacts use real image bytes, never an engine or downloads."""

import json
import socket
import urllib.request
from uuid import uuid4

import pytest
from PyQt6 import QtGui as G, QtWidgets as W
from mtg_play.artwork_review import build_review
from mtg_play.tests.test_artwork_cache import source


@pytest.fixture
def app():
    return W.QApplication.instance() or W.QApplication([])


@pytest.mark.parametrize("layout", ["normal", "transform", "flip"])
def test_review_preserves_sources_and_builds_full_crop_face_evidence_offline(
    app, tmp_path, monkeypatch, layout
):
    front = source(tmp_path / "front.png")
    back = source(tmp_path / "back.png", top="blue") if layout == "transform" else None
    originals = {path: path.read_bytes() for path in (front, back) if path is not None}

    def forbidden(*args, **kwargs):
        raise AssertionError("Review must not use the network")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    output = tmp_path / "review"
    report = build_review(str(uuid4()), front, back=back, layout=layout, output=output)
    assert report["gameplay_evidence"] is False and report["sources_unchanged"]
    assert len(report["faces"]) == (1 if layout == "normal" else 2)
    assert all(row["full_size"][1] > row["crop_size"][1] for row in report["faces"])
    assert not G.QImage(str(output / "artwork-review.png")).isNull()
    assert (
        json.loads((output / "review.json").read_text())["printing_id"]
        == report["printing_id"]
    )
    assert all(path.read_bytes() == contents for path, contents in originals.items())
    assert str(tmp_path) not in json.dumps(report)
    with pytest.raises(FileExistsError):
        build_review(str(uuid4()), front, back=back, layout=layout, output=output)


def test_review_rejects_missing_corrupt_or_ambiguous_faces(app, tmp_path):
    front = source(tmp_path / "front.png")
    with pytest.raises(ValueError, match="requires the cached back"):
        build_review(
            str(uuid4()), front, layout="transform", output=tmp_path / "missing"
        )
    front.write_bytes(b"not an image")
    with pytest.raises(ValueError, match="readable local image"):
        build_review(str(uuid4()), front, output=tmp_path / "corrupt")
    assert not (tmp_path / "corrupt").exists()
