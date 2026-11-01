"""Curate one owner-provided Arena textures for optional local opening buttons."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = "Downloads/AssetBundle/Textures_Bucket_EventComponents.MainButtonComponentPayload_0_054bf470-5417e6ab9a508e652dbd8e6e7864781c.mtga"
PIN = "30e808233a4b573403dc44d2ec36b710d56064a4c62e14c3ccbdb39f2052b725"
TEXTURES = {
    "MainButton_Orange_Up": -8745388354193192827,
    "MainButton_Blue_Up": -5175006699134861056,
}


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
    assets = ROOT / "Mtg_Projects/mtg_play_unity/Assets"
    destination = assets / "Manaforge/Runtime/Resources/LocalCardVisuals/Buttons"
    if not destination.resolve().is_relative_to(assets.resolve()):
        parser.error("Button destination escaped Unity assets")
    destination.mkdir(parents=True, exist_ok=True)
    for name, path_id in TEXTURES.items():
        matches = [
            obj
            for obj in environment.objects
            if obj.type.name == "Texture2D" and obj.path_id == path_id
        ]
        if len(matches) != 1:
            parser.error("Pinned button texture is unavailable")
        texture = matches[0].read()
        if texture.m_Name != name or (texture.m_Width, texture.m_Height) != (440, 100):
            parser.error("Pinned button metadata changed")
        image = texture.image.convert("RGBA")
        pixels_pin = hashlib.sha256(image.tobytes()).hexdigest()
        target = destination / (name + ".png")
        if target.exists():
            from PIL import Image

            with Image.open(target) as existing:
                if (
                    existing.size != image.size
                    or hashlib.sha256(existing.convert("RGBA").tobytes()).hexdigest()
                    != pixels_pin
                ):
                    parser.error(
                        "Existing local button differs; preserve it before preparing"
                    )
        else:
            image.save(target)
        provenance = dict(
            source_bundle=BUNDLE,
            source_sha256=PIN,
            texture_name=name,
            path_id=path_id,
            width=440,
            height=100,
            rgba_sha256=pixels_pin,
            decoder="UnityPy 1.25.4",
            suppressed_version_fallback="6000.3.14f1",
        )
        (destination / (name + ".provenance.json")).write_text(
            json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
        )
    print("Prepared pinned Arena button textures; Downloads unchanged.")


if __name__ == "__main__":
    main()
