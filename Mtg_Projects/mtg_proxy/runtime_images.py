from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy
from PIL import Image as PILImage

import image
import util
from config import CFG
from models import ProjectCardEntry, ProjectState, as_project_state
from mtg_core import get_default_card_service


def _runtime_cache_root(state: ProjectState) -> str:
    root = os.path.join(state.image_dir, ".runtime_cache")
    os.makedirs(root, exist_ok=True)
    return root


def _source_cache_root(state: ProjectState) -> str:
    root = os.path.join(_runtime_cache_root(state), "source_cache")
    os.makedirs(root, exist_ok=True)
    return root


def _processed_cache_root(state: ProjectState) -> str:
    root = os.path.join(_runtime_cache_root(state), "processed_cache")
    os.makedirs(root, exist_ok=True)
    return root


def _preview_cache_path(state: ProjectState) -> str:
    path = state.img_cache
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return path


def _load_preview_cache(
    state: ProjectState,
    *,
    raise_on_load_error: bool = False,
) -> dict[str, dict]:
    path = _preview_cache_path(state)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fp:
            payload = json.load(fp)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        if raise_on_load_error:
            raise
        return {}
    if not isinstance(payload, dict):
        if raise_on_load_error:
            raise TypeError("preview cache payload must be a dictionary")
        return {}

    cache_data = {}
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        try:
            image.normalize_cached_preview_entry(value)
        except (TypeError, ValueError):
            continue
        cache_data[key] = value
    return cache_data


def _save_preview_cache(state: ProjectState, cache_data: dict[str, dict]) -> None:
    util.write_json_atomic(_preview_cache_path(state), cache_data, ensure_ascii=False)


def _is_usable_preview_entry(entry: dict | None) -> bool:
    if not isinstance(entry, dict):
        return False
    thumb = entry.get("thumb")
    uncropped = entry.get("uncropped")
    if (
        "data" not in entry
        or "size" not in entry
        or not isinstance(thumb, dict)
        or "data" not in thumb
        or "size" not in thumb
        or not isinstance(uncropped, dict)
        or "data" not in uncropped
        or "size" not in uncropped
        or "effective_dpi" not in entry
    ):
        return False
    try:
        image.decode_cached_image_bytes(entry["data"])
        image.decode_cached_image_bytes(thumb["data"])
        image.decode_cached_image_bytes(uncropped["data"])
    except (TypeError, ValueError):
        return False
    return True


def _entry_by_front_or_back(state: ProjectState, card_name: str) -> tuple[ProjectCardEntry | None, str]:
    if card_name == state.backside_default:
        return None, "default_back"
    entry = state.get_card_entry(card_name)
    if entry is not None:
        return entry, "front"
    for candidate in state.card_entries_store.values():
        if candidate.backside_name == card_name:
            return candidate, "back"
    return None, "missing"


def _asset_details(state: ProjectState, card_name: str) -> tuple[str | None, str | None, str]:
    entry, side = _entry_by_front_or_back(state, card_name)
    if side == "default_back":
        return state.backside_default_asset_id, state.backside_default, "default_back"
    if entry is None:
        return None, card_name, side
    if side == "back":
        return entry.backside_asset_id, entry.backside_name or card_name, "back"
    return entry.image_asset_id, entry.front_name, "front"


def _local_source_path(state: ProjectState, label_name: str) -> str | None:
    candidate = os.path.join(state.image_dir, label_name)
    if os.path.exists(candidate):
        return candidate
    return None


def _asset_key(state: ProjectState, card_name: str) -> str:
    asset_id, label_name, side = _asset_details(state, card_name)
    if asset_id:
        return f"asset:{asset_id}:{side}"
    source_path = _local_source_path(state, label_name or card_name)
    if source_path and os.path.exists(source_path):
        stat = os.stat(source_path)
        return f"path:{source_path}:{int(stat.st_mtime)}:{stat.st_size}:{side}"
    return f"missing:{card_name}:{side}"


def _processing_fingerprint(state: ProjectState, card_name: str) -> str:
    payload = {
        "card_name": card_name,
        "bleed_edge": str(state.bleed_edge),
        "vibrance": bool(CFG.VibranceBump),
        "max_dpi": int(CFG.MaxDPI) if CFG.MaxDPI is not None else None,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _preview_cache_key(state: ProjectState, card_name: str) -> tuple[str, str, str]:
    asset_key = _asset_key(state, card_name)
    fingerprint = _processing_fingerprint(state, card_name)
    return asset_key, fingerprint, f"{asset_key}|{fingerprint}"


def get_source_path(project_like, card_name: str) -> str | None:
    state = as_project_state(project_like)
    if not card_name:
        return None
    asset_id, label_name, _side = _asset_details(state, card_name)
    if asset_id:
        return get_default_card_service().materialize_image_asset(
            asset_id,
            preferred_name=label_name or card_name,
            output_root=_source_cache_root(state),
        )
    return _local_source_path(state, label_name or card_name)


def _write_processed_image(path: str, source_path: str, card_name: str, bleed_edge: float) -> str | None:
    if os.path.exists(path):
        return path

    source_image = image.read_image(source_path)
    if not image.is_decoded_image_valid(source_image):
        return None

    if image.is_pre_cropped_image_name(card_name):
        processed = source_image
    else:
        processed = image.crop_image(
            source_image,
            card_name,
            bleed_edge if bleed_edge > 0 else None,
            CFG.MaxDPI,
        )

    if CFG.VibranceBump and image.vibrance_cube is not None:
        processed = numpy.array(PILImage.fromarray(processed).filter(image.vibrance_cube))

    image.write_image(path, processed)
    return path


def get_processed_path(project_like, card_name: str) -> str | None:
    state = as_project_state(project_like)
    if not card_name:
        return None
    source_path = get_source_path(state, card_name)
    if not source_path:
        return None
    label_name = (_asset_details(state, card_name)[1] or card_name)
    extension = os.path.splitext(label_name)[1].lower() or ".png"
    file_name = f"{hashlib.sha256((_asset_key(state, card_name) + _processing_fingerprint(state, card_name)).encode('utf-8')).hexdigest()}{extension}"
    processed_path = os.path.join(_processed_cache_root(state), file_name)
    return _write_processed_image(processed_path, source_path, card_name, float(state.bleed_edge))


def _processed_path_for_asset_key(state: ProjectState, card_name: str, asset_key: str) -> str:
    label_name = (_asset_details(state, card_name)[1] or card_name)
    extension = os.path.splitext(label_name)[1].lower() or ".png"
    file_name = f"{hashlib.sha256((asset_key + _processing_fingerprint(state, card_name)).encode('utf-8')).hexdigest()}{extension}"
    return os.path.join(_processed_cache_root(state), file_name)


def _build_preview_entry(state: ProjectState, card_name: str) -> dict | None:
    processed_path = get_processed_path(state, card_name)
    source_path = get_source_path(state, card_name)
    if not processed_path or not source_path:
        return None

    processed_img = image.read_image(processed_path)
    source_img = image.read_image(source_path)
    if not image.is_decoded_image_valid(processed_img) or not image.is_decoded_image_valid(source_img):
        return None

    _h, w, _c = processed_img.shape
    scale = 248 / w
    preview_size = (round(w * scale), round(processed_img.shape[0] * scale))
    preview_data, preview_dims = image.to_bytes(processed_img, preview_size)
    thumb_data, thumb_dims = image.to_bytes(
        processed_img,
        (preview_size[0] * 0.45, preview_size[1] * 0.45),
    )

    _sh, sw, _sc = source_img.shape
    uncropped_scale = 186 / sw
    uncropped_size = (round(sw * uncropped_scale), round(source_img.shape[0] * uncropped_scale))
    uncropped_data, uncropped_dims = image.to_bytes(source_img, uncropped_size)

    return {
        "data": image.encode_cached_image_bytes(preview_data),
        "size": preview_dims,
        "thumb": {
            "data": image.encode_cached_image_bytes(thumb_data),
            "size": thumb_dims,
        },
        "uncropped": {
            "data": image.encode_cached_image_bytes(uncropped_data),
            "size": uncropped_dims,
        },
        "effective_dpi": image.effective_dpi_from_dimensions(sw, source_img.shape[0], card_name),
        "_asset_key": _asset_key(state, card_name),
        "_fingerprint": _processing_fingerprint(state, card_name),
    }


def ensure_preview_entry(project_like, img_dict: dict, card_name: str) -> dict | None:
    state = as_project_state(project_like)
    if not card_name:
        return None
    asset_key, fingerprint, cache_key = _preview_cache_key(state, card_name)

    cached_entry = img_dict.get(card_name)
    if (
        isinstance(cached_entry, dict)
        and cached_entry.get("_asset_key") == asset_key
        and cached_entry.get("_fingerprint") == fingerprint
        and _is_usable_preview_entry(cached_entry)
    ):
        return cached_entry

    preview_cache = _load_preview_cache(state)
    cached_entry = _cached_preview_for_card(
        preview_cache,
        card_name,
        asset_key,
        fingerprint,
        cache_key,
    )
    if cached_entry is not None:
        img_dict[card_name] = cached_entry
        return cached_entry

    built = _build_preview_entry(state, card_name)
    if built is None:
        img_dict.pop(card_name, None)
        return None

    preview_cache[cache_key] = built
    _save_preview_cache(state, preview_cache)
    img_dict[card_name] = built
    return built


def _cached_preview_for_card(
    preview_cache: dict[str, dict],
    card_name: str,
    asset_key: str,
    fingerprint: str,
    cache_key: str,
) -> dict | None:
    cached_entry = preview_cache.get(cache_key)
    if _is_usable_preview_entry(cached_entry):
        cached_entry["_asset_key"] = asset_key
        cached_entry["_fingerprint"] = fingerprint
        return cached_entry

    legacy_entry = preview_cache.get(card_name)
    if _is_usable_preview_entry(legacy_entry):
        legacy_entry["_asset_key"] = asset_key
        legacy_entry["_fingerprint"] = fingerprint
        return legacy_entry

    return None


def hydrate_preview_entries(
    project_like,
    img_dict: dict,
    card_names: list[str] | None = None,
    *,
    raise_on_load_error: bool = False,
) -> int:
    state = as_project_state(project_like)
    preview_cache = _load_preview_cache(state, raise_on_load_error=raise_on_load_error)
    if card_names is None:
        card_names = list(state.cards.keys())

    hydrated_count = 0
    for card_name in card_names:
        asset_key, fingerprint, cache_key = _preview_cache_key(state, card_name)
        cached_entry = _cached_preview_for_card(
            preview_cache,
            card_name,
            asset_key,
            fingerprint,
            cache_key,
        )
        if cached_entry is None:
            continue
        img_dict[card_name] = cached_entry
        hydrated_count += 1
    return hydrated_count


def invalidate_entry(project_like, img_dict: dict, card_name: str) -> None:
    state = as_project_state(project_like)
    if not card_name:
        return
    current_asset_key = _asset_key(state, card_name)
    asset_keys = {current_asset_key}
    existing = img_dict.pop(card_name, None)
    if isinstance(existing, dict) and existing.get("_asset_key"):
        asset_keys.add(existing.get("_asset_key"))

    for asset_key in asset_keys:
        processed_path = _processed_path_for_asset_key(state, card_name, asset_key)
        if os.path.exists(processed_path):
            try:
                os.remove(processed_path)
            except OSError:
                pass

    preview_cache = _load_preview_cache(state)
    stale_keys = []
    for key, value in preview_cache.items():
        if not isinstance(value, dict):
            stale_keys.append(key)
            continue
        if value.get("_asset_key") in asset_keys:
            stale_keys.append(key)
    if stale_keys:
        for key in stale_keys:
            preview_cache.pop(key, None)
        _save_preview_cache(state, preview_cache)


def invalidate_all(project_like, img_dict: dict) -> None:
    state = as_project_state(project_like)
    img_dict.clear()
    cache_path = _preview_cache_path(state)
    if os.path.exists(cache_path):
        try:
            os.remove(cache_path)
        except OSError:
            pass


def prune_unused_entries(project_like, img_dict: dict) -> None:
    state = as_project_state(project_like)
    valid_names = set(state.cards.keys())
    for key in list(img_dict.keys()):
        if key not in valid_names:
            img_dict.pop(key, None)


def warm_preview_entries(project_like, img_dict: dict, card_names: list[str]) -> None:
    state = as_project_state(project_like)
    for card_name in card_names:
        if card_name.startswith("__"):
            continue
        ensure_preview_entry(state, img_dict, card_name)
