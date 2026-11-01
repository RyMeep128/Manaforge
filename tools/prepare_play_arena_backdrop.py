"""Curate one owner-provided Arena texture for an optional local opening backdrop."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = "Downloads/AssetBundle/Textures_Scene_Battlefield_SOS_227120da-8629b126fc8376c7ceac3a327c604380.mtga"
PIN = "ae4fd8edfddd3ce813e7d65be80d56cf2389e8c42259a9d74b6b4d269f6b0c97"
PATH_ID = 2994448792846277816


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path.home() / "Downloads/Assets from Wizards, given with permission",
    )
    parser.add_argument(
        "--python-libs",
        type=Path,
        default=ROOT / "Mtg_Projects/mtg_play_unity/Artifacts/AssetInspection/python",
    )
    args = parser.parse_args()
    source = args.source_root / BUNDLE
    if hashlib.sha256(source.read_bytes()).hexdigest() != PIN:
        parser.error(
            "Provided Arena texture bundle does not match the inspected source pin"
        )
    sys.path.insert(0, str(args.python_libs))
    import UnityPy

    if UnityPy.__version__ != "1.25.4":
        parser.error("Use the isolated UnityPy 1.25.4 inspection environment")
    UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.14f1"
    environment = UnityPy.load(str(source))
    matches = [
        obj
        for obj in environment.objects
        if obj.type.name == "Texture2D" and obj.path_id == PATH_ID
    ]
    if len(matches) != 1:
        parser.error("Pinned battlefield texture is unavailable")
    texture = matches[0].read()
    if texture.m_Name != "SOS_BF_NoInteractables" or (
        texture.m_Width,
        texture.m_Height,
    ) != (
        2048,
        1024,
    ):
        parser.error("Pinned battlefield texture metadata changed")
    image = texture.image.convert("RGBA")
    pixels_pin = hashlib.sha256(image.tobytes()).hexdigest()
    assets = ROOT / "Mtg_Projects/mtg_play_unity/Assets"
    destination = assets / "Manaforge/Runtime/Resources/LocalCardVisuals/Playmats"
    if not destination.resolve().is_relative_to(assets.resolve()):
        parser.error("Backdrop destination escaped the Unity assets directory")
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "ArenaTutorialBattlefield.png"
    if target.exists():
        from PIL import Image

        with Image.open(target) as existing:
            if (
                hashlib.sha256(existing.convert("RGBA").tobytes()).hexdigest()
                != pixels_pin
            ):
                parser.error(
                    "Existing local backdrop differs; preserve it before preparing this source"
                )
    else:
        image.save(target)
    provenance = dict(
        source_bundle=BUNDLE,
        source_sha256=PIN,
        texture_name=texture.m_Name,
        path_id=PATH_ID,
        width=2048,
        height=1024,
        rgba_sha256=pixels_pin,
        decoder="UnityPy 1.25.4",
        suppressed_version_fallback="6000.3.14f1",
    )
    (destination / "ArenaTutorialBattlefield.provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "Prepared the pinned Arena battlefield texture in ignored local resources; source Downloads unchanged."
    )


if __name__ == "__main__":
    main()
