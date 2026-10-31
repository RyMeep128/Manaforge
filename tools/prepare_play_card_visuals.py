"""Install owner-supplied fonts and rasterize cached symbol SVGs into a local Unity pack."""

import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "Mtg_Projects/mtg_play_unity/Assets/Manaforge/Runtime/Resources/LocalCardVisuals"
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plantin-directory", type=Path, required=True)
    parser.add_argument("--beleren-directory", type=Path, required=True)
    parser.add_argument("--svg-directory", type=Path, required=True)
    args = parser.parse_args()
    if OUTPUT.is_symlink() or (hasattr(OUTPUT, "is_junction") and OUTPUT.is_junction()):
        parser.error("Local visual output cannot be a link")
    fonts = {
        "BelerenBold.ttf": args.beleren_directory / "Beleren2016-Bold.ttf",
        "BelerenSmallCaps.ttf": args.beleren_directory
        / "Beleren2016SmallCaps-Bold.ttf",
        "PlantinRegular.ttf": args.plantin_directory / "PlantinMTProRg.TTF",
        "PlantinBold.ttf": args.plantin_directory / "PlantinMTProBold.TTF",
        "PlantinItalic.ttf": args.plantin_directory / "PlantinMTProRgIt.TTF",
        "PlantinBoldItalic.ttf": args.plantin_directory / "PlantinMTProBoldIt.TTF",
    }
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import QByteArray, Qt
    from PyQt6.QtGui import QGuiApplication, QImage, QPainter
    from PyQt6.QtSvg import QSvgRenderer

    app = QGuiApplication.instance() or QGuiApplication([])
    records = []
    for name, source in fonts.items():
        data = source.read_bytes()
        if len(data) > 2 * 1024 * 1024 or data[:4] not in (
            b"\x00\x01\x00\x00",
            b"OTTO",
        ):
            parser.error("Invalid font source")
        target = OUTPUT / "Fonts" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != data:
            parser.error(
                "Existing font differs; do not overwrite an unreviewed local font"
            )
        target.write_bytes(data)
        records.append(
            {"file": "Fonts/" + name, "sha256": hashlib.sha256(data).hexdigest()}
        )
    sources = sorted(args.svg_directory.glob("*.svg"))
    if not 1 <= len(sources) <= 128:
        parser.error("Symbol source count exceeds the pack limit")
    symbols = OUTPUT / "Symbols"
    symbols.mkdir(exist_ok=True)
    for source in sources:
        if not all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in source.stem):
            parser.error("Invalid symbol filename")
        data = source.read_bytes()
        if len(data) > 262144:
            parser.error("Symbol source exceeds the limit")
        renderer = QSvgRenderer(QByteArray(data))
        if not renderer.isValid():
            parser.error("Invalid symbol SVG")
        image = QImage(128, 128, QImage.Format.Format_RGBA8888)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        target = symbols / (source.stem + ".png")
        if not image.save(str(target), "PNG"):
            parser.error("Symbol rasterization failed")
        records.append(
            {
                "file": "Symbols/" + target.name,
                "source_sha256": hashlib.sha256(data).hexdigest(),
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
        )
    (OUTPUT / "provenance.json").write_text(
        json.dumps({"pack_version": 1, "files": records}, indent=2), encoding="utf-8"
    )
    print(
        f"Local visual pack: {len(fonts)} fonts and {len(sources)} 128px symbol sprites; no network or source modifications"
    )
    del app


if __name__ == "__main__":
    main()
