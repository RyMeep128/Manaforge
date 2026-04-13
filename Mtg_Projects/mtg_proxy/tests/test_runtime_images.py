import uuid
import hashlib
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
