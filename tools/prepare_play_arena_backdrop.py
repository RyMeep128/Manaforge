"""Curate one owner-provided Arena texture for an optional local opening backdrop."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = "Downloads/AssetBundle/Textures_Scene_Battlefield_STX_1b295122-29db96c9c8fac1e5be51b458911676a5.mtga"
PIN = "6b0bb5f72c0e34639946c1d3f294c6431f16c4be50e381da64014efbc44e82f4"
PATH_ID = -8961145794100977760


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
        parser.error("Pinned floor texture is unavailable")
    texture = matches[0].read()
    if texture.m_Name != "tex_floor_d" or (texture.m_Width, texture.m_Height) != (
        2048,
        1024,
    ):
        parser.error("Pinned floor texture metadata changed")
    image = texture.image.convert("RGBA")
    pixels_pin = hashlib.sha256(image.tobytes()).hexdigest()
    assets = ROOT / "Mtg_Projects/mtg_play_unity/Assets"
    destination = assets / "Manaforge/Runtime/Resources/LocalCardVisuals/Playmats"
    if not destination.resolve().is_relative_to(assets.resolve()):
        parser.error("Backdrop destination escaped the Unity assets directory")
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "StrixhavenFloor.png"
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
    (destination / "StrixhavenFloor.provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "Prepared the pinned Arena floor texture in ignored local resources; source Downloads unchanged."
    )


if __name__ == "__main__":
    main()
