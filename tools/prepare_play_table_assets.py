"""Curate supplied decorative UI textures into the ignored local Unity resource pack."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "Mtg_Projects/mtg_play_unity"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument(
        "--unitypy-directory",
        type=Path,
        default=PROJECT / "Artifacts/AssetInspection/python",
    )
    args = parser.parse_args()
    sys.path.insert(0, str(args.unitypy_directory))
    import UnityPy

    UnityPy.config.FALLBACK_UNITY_VERSION = "6000.3.14f1"
    bundles = args.asset_root / "Downloads/AssetBundle"
    output = PROJECT / "Assets/Manaforge/Runtime/Resources/LocalCardVisuals/PlayHUD"
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for pattern, identities in [
        (
            "Textures_Bucket_UI.DuelScene.DuelSceneUIPrefabs_0_*",
            {1888041602498328757: "PlayerNameBacker"},
        ),
        (
            "Textures_Bucket_Card.Parts.AnimatedCardbackPart_0_*",
            {4086297360495280151: "CardBackLogo"},
        ),
    ]:
        matches = list(bundles.glob(pattern))
        if len(matches) != 1:
            parser.error("Expected exactly one supplied texture bundle: " + pattern)
        source = matches[0]
        for obj in UnityPy.load(str(source)).objects:
            if obj.type.name != "Texture2D" or obj.path_id not in identities:
                continue
            texture = obj.read()
            name = identities[obj.path_id] + ".png"
            texture.image.save(output / name)
            records.append(
                dict(
                    bundle=source.name,
                    path_id=str(obj.path_id),
                    name=texture.m_Name,
                    file=name,
                    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                )
            )
    if len(records) != 2:
        parser.error("A required supplied texture was missing")
    (output / "provenance.json").write_text(
        json.dumps(records, indent=2), encoding="utf-8"
    )
    print(output)


if __name__ == "__main__":
    main()
