import json
import logging
import os
import re
import time
from pathlib import Path

import util
import image
from config import CFG
from constants import page_sizes
from models import ProjectState, as_project_state
import runtime_images


logger = logging.getLogger(__name__)


def _project_runtime_root(project_path: str | None = None) -> str:
    if project_path:
        project_file = Path(project_path)
        runtime_root = project_file.parent / ".runtime" / project_file.stem
    else:
        runtime_root = Path("Mtg_Projects") / "mtg_proxy" / "projects" / ".runtime" / "draft"
    runtime_root.mkdir(parents=True, exist_ok=True)
    return str(runtime_root.resolve())


def _assign_runtime_paths(state: ProjectState, project_path: str | None = None) -> None:
    runtime_root = _project_runtime_root(project_path)
    state.image_dir = runtime_root
    state.img_cache = os.path.join(runtime_root, "img.cache")


def _sync_legacy_project_dict(target, state: ProjectState) -> ProjectState:
    if isinstance(target, ProjectState):
        target.copy_from(state)
        return target
    target.clear()
    target.update(state.to_dict())
    return state


def _parse_scryfall_card_metadata(card_name):
    stem = os.path.splitext(os.path.basename(card_name))[0]
    match = re.match(r"^(?:__)?scryfall_([^_]+)_([^_]+)_(.+)$", stem)
    if match is None:
        return None

    return {
        "name": re.sub(r"\s+", " ", match.group(3).replace("-", " ").strip("_ ")).strip().title(),
        "set_code": match.group(1).lower(),
        "collector_number": match.group(2),
    }


def _detect_default_back_image(source_list, crop_list):
    back_candidates = sorted(
        {
            img_name
            for img_name in list(source_list) + list(crop_list)
            if img_name.startswith("__back")
        }
    )
    if not back_candidates:
        return None
    return back_candidates[0]


def init_dict(print_dict, img_dict, warn_fn=None):
    state = as_project_state(print_dict)
    if not state.pagesize:
        default_page_size = CFG.DefaultPageSize
        state.pagesize = default_page_size if default_page_size in page_sizes else "Letter"

    if not os.path.isabs(state.image_dir) or state.image_dir == "images":
        _assign_runtime_paths(state)
    image_dir = state.image_dir
    crop_dir = os.path.join(image_dir, "crop")
    image.init_image_folder(image_dir, crop_dir)

    crop_list = image.list_image_files(crop_dir)
    source_list = image.list_image_files(image_dir)
    if crop_list or source_list:
        detected_default_back = _detect_default_back_image(source_list, crop_list)
        if detected_default_back is not None:
            state.backside_default = detected_default_back
        file_backed_names = set(crop_list) | set(source_list)
        asset_backed_names = {
            entry.front_name
            for entry in state.card_entries_store.values()
            if entry.image_asset_id
        }
        asset_backed_names.update(
            entry.backside_name
            for entry in state.card_entries_store.values()
            if entry.backside_name and entry.backside_asset_id
        )
        state.remove_missing_cards(file_backed_names | asset_backed_names)
        for img in crop_list:
            if img not in state.cards:
                state.cards[img] = 0 if img.startswith("__") else 1

    bleed_edge = str(state.bleed_edge)
    bleed_edge = util.cap_bleed_edge_str(bleed_edge)
    if not util.is_number_string(bleed_edge):
        bleed_edge = "0"
    state.bleed_edge = bleed_edge

    state._rebuild_entries_from_legacy_maps()
    state._rebuild_legacy_maps_from_entries()
    state.ensure_card_defaults(list(state.cards.keys()))

    for img in list(state.cards.keys()):
        parsed_metadata = _parse_scryfall_card_metadata(img)
        if parsed_metadata is not None:
            state.set_card_metadata(img, parsed_metadata)

    img_cache = state.img_cache
    if os.path.exists(img_cache):
        try:
            with open(img_cache, "r", encoding="utf-8") as fp:
                loaded_img_dict = json.load(fp)
                for value in loaded_img_dict.values():
                    if isinstance(value, dict):
                        image.normalize_cached_preview_entry(value)
                img_dict.clear()
                for key, value in loaded_img_dict.items():
                    img_dict[key] = value
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("project image cache reset path=%s error=%s", img_cache, exc)
            img_dict.clear()
            if warn_fn is not None:
                warn_fn(
                    "Cache Reset",
                    "The image cache could not be loaded and was reset. Thumbnails will be rebuilt.",
                )

    return _sync_legacy_project_dict(print_dict, state)


def init_images(print_dict, img_dict, print_fn):
    state = as_project_state(print_dict)
    return _sync_legacy_project_dict(print_dict, state)


def refresh_after_image_changes(print_dict, img_dict, print_fn, warn_fn=None):
    init_dict(print_dict, img_dict, warn_fn)
    init_images(print_dict, img_dict, print_fn)
    return init_dict(print_dict, img_dict, warn_fn)


def delete_card_files(print_dict, img_dict, card_name):
    state = as_project_state(print_dict)
    image_dir = state.image_dir

    deleted_count = 0

    source_path = os.path.join(image_dir, card_name)
    if os.path.exists(source_path):
        os.remove(source_path)
        deleted_count += 1

    crop_dir = os.path.join(image_dir, "crop")
    if os.path.exists(crop_dir):
        for root, _dirs, files in os.walk(crop_dir, topdown=False):
            for file_name in files:
                if file_name != card_name:
                    continue
                os.remove(os.path.join(root, file_name))
                deleted_count += 1
            if root != crop_dir and len(os.listdir(root)) == 0:
                os.rmdir(root)

    runtime_images.invalidate_entry(state, img_dict, card_name)
    img_cache = state.img_cache
    if img_cache and os.path.exists(img_cache):
        try:
            with open(img_cache, "r", encoding="utf-8") as fp:
                cache_data = json.load(fp)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            cache_data = None
        if isinstance(cache_data, dict) and card_name in cache_data:
            del cache_data[card_name]
            util.write_json_atomic(img_cache, cache_data)
    state.remove_card(card_name)
    _sync_legacy_project_dict(print_dict, state)
    return deleted_count


def clear_old_cards(print_dict, img_dict):
    state = as_project_state(print_dict)
    image_dir = state.image_dir

    deleted_count = 0

    for img_name in image.list_image_files(image_dir):
        if img_name.startswith("__back"):
            continue
        os.remove(os.path.join(image_dir, img_name))
        deleted_count += 1

    crop_dir = os.path.join(image_dir, "crop")
    if os.path.exists(crop_dir):
        for root, _dirs, files in os.walk(crop_dir, topdown=False):
            for file_name in files:
                if os.path.splitext(file_name)[1].lower() not in image.valid_image_extensions:
                    continue
                if file_name.startswith("__back"):
                    continue
                os.remove(os.path.join(root, file_name))
                deleted_count += 1
            if root != crop_dir and len(os.listdir(root)) == 0:
                os.rmdir(root)

    runtime_images.invalidate_all(state, img_dict)
    for card_name in [name for name in list(state.cards.keys()) if not name.startswith("__")]:
        state.remove_card(card_name)

    init_dict(state, img_dict)
    _sync_legacy_project_dict(print_dict, state)
    return deleted_count


def load(print_dict, img_dict, json_path, print_fn, warn_fn=None):
    state = as_project_state(print_dict)
    load_target = print_dict if not isinstance(print_dict, ProjectState) else state
    loaded_successfully = False
    try:
        with open(json_path, "r", encoding="utf-8") as fp:
            loaded_print_dict = json.load(fp)
            state.copy_from(ProjectState.from_dict(loaded_print_dict))
            _assign_runtime_paths(state, json_path)
            loaded_successfully = True
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("project load failed path=%s error=%s", json_path, exc)
        print_fn(f"Error: Failed loading project ({exc})... Resetting...")
        if warn_fn is not None:
            warn_fn(
                "Project Load Failed",
                f"The project file could not be loaded and the project was reset.\n\n{exc}",
            )
        time.sleep(1)
        state.copy_from(ProjectState())
        _assign_runtime_paths(state, json_path)

    if isinstance(print_dict, ProjectState):
        load_target = state
    elif loaded_successfully:
        print_dict.clear()
        print_dict.update(state.to_dict())
        load_target = print_dict
    else:
        print_dict.clear()
        load_target = print_dict

    init_dict(load_target, img_dict, warn_fn)
    init_images(load_target, img_dict, print_fn)
    return loaded_successfully
