"""Shared one-time Core cache image conversion; never the Unity render thread."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage


def cached_rgba(path, max_edge):
    image = QImage(str(path))
    if image.isNull():
        return None
    if max(image.width(), image.height()) > max_edge:
        image = image.scaled(
            max_edge,
            max_edge,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    image = image.convertToFormat(QImage.Format.Format_RGBA8888).mirrored(False, True)
    width, height = image.width(), image.height()
    return width, height, image.constBits().asstring(width * height * 4)
