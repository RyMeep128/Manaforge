import copy

import pytest

import image


def test_is_pre_cropped_image_name_detects_scryfall_prefix():
    assert image.is_pre_cropped_image_name("scryfall_moc_166_card-name.png") is True
    assert image.is_pre_cropped_image_name("card-a.png") is False


def test_effective_dpi_from_dimensions_uses_card_frame_type():
    regular_dpi = image.effective_dpi_from_dimensions(816, 1110, "card-a.png")
    scryfall_dpi = image.effective_dpi_from_dimensions(
        744, 1038, "scryfall_moc_166_card-name.png"
    )

    assert round(regular_dpi) == 300
    assert round(scryfall_dpi) == 300


def test_cropper_skips_crop_for_scryfall_images(monkeypatch, tmp_path):
    image_dir = tmp_path / "images"
    crop_dir = image_dir / "crop"
    image_dir.mkdir()
    crop_dir.mkdir()
    (image_dir / "scryfall_moc_166_card-name.png").write_bytes(b"stub")

    writes = []
    crop_calls = []

    monkeypatch.setattr(image, "list_image_files", lambda folder: ["scryfall_moc_166_card-name.png"])
    monkeypatch.setattr(image, "read_image", lambda path: "raw-image")
    monkeypatch.setattr(
        image,
        "write_image",
        lambda path, data: writes.append((path, data)),
    )
    monkeypatch.setattr(
        image,
        "crop_image",
        lambda *args, **kwargs: crop_calls.append(args) or "cropped-image",
    )
    monkeypatch.setattr(image, "need_cache_previews", lambda crop_dir_arg, img_dict: False)

    messages = []
    image.cropper(
        str(image_dir),
        str(crop_dir),
        str(tmp_path / "img.cache"),
        {},
        bleed_edge=None,
        max_dpi=None,
        do_vibrance_bump=False,
        uncrop=False,
        print_fn=messages.append,
    )

    assert crop_calls == []
    assert writes == [(str(crop_dir / "scryfall_moc_166_card-name.png"), "raw-image")]
    assert any("Skipping crop for pre-cropped image" in message for message in messages)


def test_cropper_still_crops_non_scryfall_images(monkeypatch, tmp_path):
    image_dir = tmp_path / "images"
    crop_dir = image_dir / "crop"
    image_dir.mkdir()
    crop_dir.mkdir()
    (image_dir / "card-a.png").write_bytes(b"stub")

    writes = []
    crop_calls = []

    monkeypatch.setattr(image, "list_image_files", lambda folder: ["card-a.png"])
    monkeypatch.setattr(image, "read_image", lambda path: "raw-image")
    monkeypatch.setattr(
        image,
        "write_image",
        lambda path, data: writes.append((path, data)),
    )
    monkeypatch.setattr(
        image,
        "crop_image",
        lambda *args, **kwargs: crop_calls.append(args) or "cropped-image",
    )
    monkeypatch.setattr(image, "need_cache_previews", lambda crop_dir_arg, img_dict: False)

    image.cropper(
        str(image_dir),
        str(crop_dir),
        str(tmp_path / "img.cache"),
        {},
        bleed_edge=None,
        max_dpi=None,
        do_vibrance_bump=False,
        uncrop=False,
        print_fn=lambda _message: None,
    )

    assert len(crop_calls) == 1
    assert writes == [(str(crop_dir / "card-a.png"), "cropped-image")]


def test_need_cache_previews_accepts_cached_source_metadata(monkeypatch):
    monkeypatch.setattr(
        image,
        "list_image_files",
        lambda folder: ["card-a.png"] if folder.endswith("crop") else ["card-a.png"],
    )

    img_dict = {
        "card-a.png": {
            "size": [248, 346],
            "thumb": {"size": [112, 156], "data": "thumb"},
            "uncropped": {"size": [186, 260], "data": "uncropped"},
            "effective_dpi": 300,
        }
    }

    assert image.need_cache_previews("images/crop", img_dict, "images") is False


def test_cached_image_bytes_codec_round_trips_base64():
    original = b"\x89PNG\r\n\x1a\npayload"

    encoded = image.encode_cached_image_bytes(original)
    decoded = image.decode_cached_image_bytes(encoded)

    assert isinstance(encoded, str)
    assert decoded == original


def test_decode_cached_image_bytes_supports_legacy_bytes_literal():
    legacy_value = r"""b'\x89PNG\r\n\x1a\npayload'"""

    assert image.decode_cached_image_bytes(legacy_value) == b"\x89PNG\r\n\x1a\npayload"


def test_decode_cached_image_bytes_rejects_invalid_payload():
    with pytest.raises(ValueError):
        image.decode_cached_image_bytes("not-valid-base64%%%")


def test_cache_previews_rewrites_legacy_cached_payloads(monkeypatch):
    monkeypatch.setattr(image, "list_files", lambda _folder, _extensions: ["card-a.png"])
    monkeypatch.setattr(image.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(image, "read_image", lambda _path: "raw-image")
    to_bytes_results = iter(
        [
            (b"preview-bytes", (248, 346)),
            (b"thumb-bytes", (112, 156)),
            (b"uncropped-bytes", (186, 260)),
        ]
    )
    monkeypatch.setattr(image, "to_bytes", lambda *_args, **_kwargs: next(to_bytes_results))
    monkeypatch.setattr(image, "effective_dpi_from_dimensions", lambda *_args: 300)
    writes = []
    monkeypatch.setattr(
        image,
        "write_json_atomic",
        lambda path, data, ensure_ascii=False: writes.append((path, copy.deepcopy(data), ensure_ascii)),
    )

    data = {
        "card-a.png": {
            "data": "b'preview-bytes'",
            "size": [248, 346],
            "thumb": {"data": "b'thumb-bytes'", "size": [112, 156]},
            "uncropped": {"data": "b'uncropped-bytes'", "size": [186, 260]},
            "effective_dpi": 300,
        }
    }

    image.cache_previews("img.cache", "images", "images/crop", lambda _message: None, data)

    assert data["card-a.png"]["data"] == image.encode_cached_image_bytes(b"preview-bytes")
    assert data["card-a.png"]["thumb"]["data"] == image.encode_cached_image_bytes(b"thumb-bytes")
    assert data["card-a.png"]["uncropped"]["data"] == image.encode_cached_image_bytes(b"uncropped-bytes")
    assert writes == [("img.cache", copy.deepcopy(data), False)]
