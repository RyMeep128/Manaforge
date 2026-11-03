"""Prepare optional local Arena draw-motion data; never copies supplied runtime code."""

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
    sources = list(
        (args.asset_root / "Downloads/AssetBundle").glob(
            "Bucket_Card.MovementPayload_Spline_0_*.mtga"
        )
    )
    if len(sources) != 1:
        parser.error("Expected one supplied movement spline bundle")
    source = sources[0]
    for obj in UnityPy.load(str(source)).objects:
        if obj.type.name != "MonoBehaviour":
            continue
        data = obj.read_typetree()
        if data.get("m_Name") != "LibraryToHandSplineDefault-FaceDown":
            continue
        keys = data["Easing"]["m_Curve"]
        nodes = data["Spline"]["Nodes"]
        first, last = nodes[0]["Position"]["z"], nodes[-1]["Position"]["z"]
        lift = [
            first + (last - first) * i / (len(nodes) - 1) - node["Position"]["z"]
            for i, node in enumerate(nodes)
        ]
        maximum = max(abs(value) for value in lift)
        payload = dict(
            times=[key["time"] for key in keys],
            values=[key["value"] for key in keys],
            lift=[value / maximum for value in lift],
            source_bundle=source.name,
            source_path_id=str(obj.path_id),
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        )
        output = PROJECT / "Assets/Manaforge/Runtime/Resources/LocalCardVisuals/Motion"
        output.mkdir(parents=True, exist_ok=True)
        (output / "LibraryToHand.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        print(output / "LibraryToHand.json")
        return
    parser.error("Supplied face-down draw spline was not found")


if __name__ == "__main__":
    main()
