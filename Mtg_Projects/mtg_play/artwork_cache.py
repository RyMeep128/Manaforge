"""Local printing artwork derivatives. No download or remote fallback APIs."""

import hashlib
import json
from pathlib import Path

from PyQt6 import QtCore as C, QtGui as G
from mtg_core.paths import core_data_root
from mtg_ui.loading import LoadingThread

RENDER_VERSION = "battlefield-1"
CROP_HEIGHT = 0.58


def local_source(service, printing_id, face):
    """Resolve exactly this printing/face, never substitute another printing."""
    if not face:
        path = service.get_image_path(printing_id)
        return Path(path) if path else None, False
    payload = service.get_card(card_id=printing_id) or {}
    if payload.get("layout") == "flip":
        path = service.get_image_path(printing_id)
        return Path(path) if path else None, True
    path = service.get_image_path(printing_id, variant=f"face-{face}")
    return Path(path) if path else None, False


def read_local_image(service, key, *, cache_root=None):
    """Decode on a worker, optionally reusing an atomic disk-cached crop.

    Keys keep printing, asset slot, resolution and face in their established
    positions; a fifth item requests the battlefield rendering version.
    """
    printing, _, resolution, face = key[:4]
    path, flip = local_source(service, printing, face)
    if path is None or not path.is_file():
        return G.QImage()
    source = path.read_bytes()
    cropped = len(key) > 4 and key[4] == RENDER_VERSION
    target = None
    if cropped:
        identity = json.dumps(
            [
                printing,
                face,
                flip,
                RENDER_VERSION,
                resolution,
                hashlib.sha256(source).hexdigest(),
            ],
            separators=(",", ":"),
        )
        digest = hashlib.sha256(identity.encode()).hexdigest()
        root = (
            Path(cache_root)
            if cache_root is not None
            else core_data_root() / "play-artwork"
        )
        target = root / RENDER_VERSION / (digest + ".png")
        cached = G.QImage(str(target))
        if not cached.isNull():
            return cached
    image = G.QImage.fromData(source)
    if image.isNull():
        return image
    if flip:
        image = image.transformed(G.QTransform().rotate(180))
    if cropped:
        image = image.copy(
            0, 0, image.width(), max(1, round(image.height() * CROP_HEIGHT))
        )
    image = image.scaledToWidth(
        min(image.width(), resolution), C.Qt.TransformationMode.SmoothTransformation
    )
    if target is not None:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            output = C.QSaveFile(str(target))
            if output.open(C.QIODevice.OpenModeFlag.WriteOnly):
                if image.save(output, "PNG"):
                    output.commit()
                else:
                    output.cancelWriting()
        except OSError:
            pass  # A read-only cache must not hide available local artwork.
    return image


class PlayImageReader(LoadingThread):
    loaded = C.pyqtSignal(object, G.QImage)
    failed = C.pyqtSignal(object, str, float)

    def __init__(self, service, key, parent):
        super().__init__(parent)
        self.service, self.key = service, key

    def run(self):
        try:
            image = read_local_image(self.service, self.key)
        except Exception:
            image = G.QImage()
            self.failed.emit(self.key, "LOCAL_ARTWORK_UNAVAILABLE", 0)
        self.loaded.emit(self.key, image)
