import uuid
import hashlib
import json
from pathlib import Path

import runtime_images
from models import ProjectState
from mtg_core import get_default_card_service


def _workspace_runtime_dir(name: str) -> Path:
    base = Path(__file__).resolve().parents[1] / "projects" / ".codex_test_runtime"
    base.mkdir(parents=True, exist_ok=True)
    target = base / f"{name}_{uuid.uuid4().hex}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _cached_preview_entry(asset_key: str, fingerprint: str, data: bytes = b"preview") -> dict:
    return {
        "data": runtime_images.image.encode_cached_image_bytes(data),
        "size": [2, 3],
        "thumb": {
            "data": runtime_images.image.encode_cached_image_bytes(b"thumb"),
            "size": [1, 2],
        },
        "uncropped": {
            "data": runtime_images.image.encode_cached_image_bytes(b"uncropped"),
            "size": [4, 5],
        },
        "effective_dpi": 300,
        "_asset_key": asset_key,
        "_fingerprint": fingerprint,
    }


def test_source_path_uses_new_asset_bytes_after_card_art_replacement():
    runtime_dir = _workspace_runtime_dir("runtime_new_art_source")
    image_dir = runtime_dir / "images"
    image_dir.mkdir()
    service = get_default_card_service()
    old_asset_id = service.store_image_bytes(b"old-runtime-art", extension="png", source="test")
    new_asset_id = service.store_image_bytes(b"new-runtime-art", extension="png", source="test")
    card_name = "scryfall_sos_274_island.png"
    state = ProjectState(image_dir=str(image_dir), img_cache=str(runtime_dir / "img.cache"))
    state.apply_imported_card(card_name, 1, image_asset_id=old_asset_id)

    old_path = runtime_images.get_source_path(state, card_name)
    state.set_card_image_refs(card_name, image_asset_id=new_asset_id)
    new_path = runtime_images.get_source_path(state, card_name)

    assert old_path is not None
    assert new_path is not None
    assert old_path != new_path
    assert Path(old_path).read_bytes() == b"old-runtime-art"
    assert Path(new_path).read_bytes() == b"new-runtime-art"


def test_invalidate_entry_removes_processed_cache_for_same_asset_key():
    runtime_dir = _workspace_runtime_dir("runtime_same_asset_invalidate")
    image_dir = runtime_dir / "images"
    image_dir.mkdir()
    service = get_default_card_service()
    asset_id = service.store_image_bytes(b"same-runtime-art", extension="png", source="test")
    card_name = "scryfall_sos_274_island.png"
    state = ProjectState(image_dir=str(image_dir), img_cache=str(runtime_dir / "img.cache"))
    state.apply_imported_card(card_name, 1, image_asset_id=asset_id)

    asset_key = f"asset:{asset_id}:front"
    fingerprint = runtime_images._processing_fingerprint(state, card_name)
    processed_name = hashlib.sha256((asset_key + fingerprint).encode("utf-8")).hexdigest() + ".png"
    processed_path = image_dir / ".runtime_cache" / "processed_cache" / processed_name
    processed_path.parent.mkdir(parents=True)
    processed_path.write_bytes(b"stale-processed-art")
    img_dict = {card_name: {"_asset_key": asset_key, "_fingerprint": fingerprint}}

    runtime_images.invalidate_entry(state, img_dict, card_name)

    assert card_name not in img_dict
    assert not processed_path.exists()


def test_hydrate_preview_entries_maps_asset_cache_key_to_card_name():
    runtime_dir = _workspace_runtime_dir("runtime_hydrate_preview")
    state = ProjectState(image_dir=str(runtime_dir / "images"), img_cache=str(runtime_dir / "img.cache"))
    card_name = "scryfall_sos_272_plains.png"
    state.apply_imported_card(card_name, 1, image_asset_id="asset-hydrate")
    asset_key, fingerprint, cache_key = runtime_images._preview_cache_key(state, card_name)
    entry = _cached_preview_entry(asset_key, fingerprint)
    Path(state.img_cache).write_text(json.dumps({cache_key: entry}), encoding="utf-8")
    img_dict = {}

    hydrated_count = runtime_images.hydrate_preview_entries(state, img_dict)

    assert hydrated_count == 1
    assert list(img_dict.keys()) == [card_name]
    assert img_dict[card_name]["_asset_key"] == asset_key
    assert img_dict[card_name]["_fingerprint"] == fingerprint


def test_hydrate_preview_entries_ignores_stale_fingerprint():
    runtime_dir = _workspace_runtime_dir("runtime_hydrate_stale")
    state = ProjectState(image_dir=str(runtime_dir / "images"), img_cache=str(runtime_dir / "img.cache"))
    card_name = "scryfall_sos_274_island.png"
    state.apply_imported_card(card_name, 1, image_asset_id="asset-stale")
    asset_key, _fingerprint, _cache_key = runtime_images._preview_cache_key(state, card_name)
    stale_fingerprint = "stale-fingerprint"
    stale_entry = _cached_preview_entry(asset_key, stale_fingerprint)
    Path(state.img_cache).write_text(
        json.dumps({f"{asset_key}|{stale_fingerprint}": stale_entry}),
        encoding="utf-8",
    )
    img_dict = {}

    hydrated_count = runtime_images.hydrate_preview_entries(state, img_dict)

    assert hydrated_count == 0
    assert img_dict == {}


def test_malformed_preview_cache_entry_falls_back_to_rebuild(monkeypatch):
    runtime_dir = _workspace_runtime_dir("runtime_hydrate_malformed")
    state = ProjectState(image_dir=str(runtime_dir / "images"), img_cache=str(runtime_dir / "img.cache"))
    card_name = "scryfall_tla_167_badgermole-cub.png"
    state.apply_imported_card(card_name, 1, image_asset_id="asset-malformed")
    asset_key, fingerprint, cache_key = runtime_images._preview_cache_key(state, card_name)
    Path(state.img_cache).write_text(
        json.dumps(
            {
                cache_key: {
                    "data": "not valid base64",
                    "size": [2, 3],
                    "thumb": {"data": "not valid base64", "size": [1, 2]},
                    "uncropped": {"data": "not valid base64", "size": [4, 5]},
                    "effective_dpi": 300,
                    "_asset_key": asset_key,
                    "_fingerprint": fingerprint,
                }
            }
        ),
        encoding="utf-8",
    )
    rebuilt_entry = _cached_preview_entry(asset_key, fingerprint, b"rebuilt")
    monkeypatch.setattr(runtime_images, "_build_preview_entry", lambda _state, _card_name: rebuilt_entry)
    img_dict = {}

    result = runtime_images.ensure_preview_entry(state, img_dict, card_name)

    assert result == rebuilt_entry
    assert img_dict[card_name] == rebuilt_entry
