"""Offline real-printing crop review. This is artwork evidence, not gameplay proof."""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import uuid

from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from .artwork_cache import read_local_image, RENDER_VERSION
from .assets import MatchAssets
from .ui_acceptance import configure_visual_review


def build_review(printing_id, front, *, output, back=None, layout="normal"):
    printing_id = str(uuid.UUID(printing_id))
    if layout not in {"normal", "transform", "modal_dfc", "flip"}:
        raise ValueError("Unsupported review layout")
    if back is not None and layout in {"normal", "flip"}:
        raise ValueError("Use a double-faced layout for a separate back image")
    if layout in {"transform", "modal_dfc"} and back is None:
        raise ValueError("A double-faced review requires the cached back image")
    app = W.QApplication.instance()
    if app is None:
        raise RuntimeError("Create QApplication before reviewing artwork")
    configure_visual_review(app)
    paths = [("default", Path(front).resolve())]
    if back is not None:
        paths.append(("face-1", Path(back).resolve()))
    sources = []
    for variant, path in paths:
        payload = path.read_bytes()
        if G.QImage.fromData(payload).isNull():
            raise ValueError("Review source is not a readable local image")
        sources.append(
            (printing_id, variant, str(path), hashlib.sha256(payload).hexdigest())
        )
    manifest = MatchAssets(tuple(sources), ((printing_id, layout),), ())
    service = manifest.image_service()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    faces = (0, 1) if layout == "flip" or back is not None else (0,)
    sheet = G.QImage(640 * len(faces), 660, G.QImage.Format.Format_RGB32)
    sheet.fill(G.QColor("#10151b"))
    painter = G.QPainter(sheet)
    try:
        painter.setFont(app.font())
        painter.setPen(G.QColor("#edf2f7"))
        painter.drawText(
            C.QRect(20, 12, sheet.width() - 40, 40),
            C.Qt.AlignmentFlag.AlignLeft | C.Qt.AlignmentFlag.AlignVCenter,
            "Local printing artwork review - no game or rules simulation",
        )
        evidence = []
        for face in faces:
            full = read_local_image(
                service, (printing_id, None, 600, face), cache_root=output / "derived"
            )
            crop = read_local_image(
                service,
                (printing_id, None, 300, face, RENDER_VERSION),
                cache_root=output / "derived",
            )
            if full.isNull() or crop.isNull():
                raise ValueError(
                    "A review face could not be loaded from its frozen local source"
                )
            offset = face * 640
            for image, x, label in (
                (full, offset + 20, "Full printing"),
                (crop, offset + 330, "Battlefield crop"),
            ):
                painter.drawText(
                    C.QRect(x, 60, 290, 32),
                    C.Qt.AlignmentFlag.AlignLeft | C.Qt.AlignmentFlag.AlignVCenter,
                    f"{label} - face {face + 1}",
                )
                scaled = image.scaled(
                    290,
                    430,
                    C.Qt.AspectRatioMode.KeepAspectRatio,
                    C.Qt.TransformationMode.SmoothTransformation,
                )
                painter.drawImage(x, 100, scaled)
            evidence.append(
                dict(
                    face=face,
                    full_size=[full.width(), full.height()],
                    crop_size=[crop.width(), crop.height()],
                )
            )
        painter.drawText(
            C.QRect(20, 554, sheet.width() - 40, 42),
            C.Qt.TextFlag.TextWordWrap,
            "Check name bar, artwork, border and removed lower rules area. Unusual frames may crop imperfectly. Originals remain unchanged.",
        )
        painter.drawText(
            C.QRect(20, 606, sheet.width() - 40, 32),
            C.Qt.AlignmentFlag.AlignLeft | C.Qt.AlignmentFlag.AlignVCenter,
            "Printing: " + printing_id + " | " + RENDER_VERSION,
        )
    finally:
        painter.end()
    if not sheet.save(str(output / "artwork-review.png"), "PNG"):
        raise OSError("Could not save the review sheet")
    unchanged = all(
        hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
        for _, _, path, digest in sources
    )
    if not unchanged:
        raise ValueError("A source image changed during review")
    report = dict(
        schema=1,
        purpose="local_artwork_review",
        gameplay_evidence=False,
        printing_id=printing_id,
        layout=layout,
        render_version=RENDER_VERSION,
        source_sha256=[row[3] for row in sources],
        sources_unchanged=True,
        faces=evidence,
    )
    (output / "review.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--printing-id", required=True)
    parser.add_argument(
        "--front", type=Path, required=True, help="Existing cached full printing image"
    )
    parser.add_argument(
        "--back", type=Path, help="Existing cached alternate-face image"
    )
    parser.add_argument(
        "--layout",
        choices=("normal", "transform", "modal_dfc", "flip"),
        default="normal",
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="New local review directory"
    )
    args = parser.parse_args()
    app = W.QApplication.instance() or W.QApplication([])
    build_review(
        args.printing_id,
        args.front,
        output=args.output,
        back=args.back,
        layout=args.layout,
    )
    return app  # Keep Qt alive until all image rendering has finished.


if __name__ == "__main__":
    main()
