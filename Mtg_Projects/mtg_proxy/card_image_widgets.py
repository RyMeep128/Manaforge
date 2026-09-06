"""Reusable card-image widgets and bounded decoded-pixmap caching."""
import hashlib
from PyQt6 import QtCore
from PyQt6.QtGui import QPixmap, QPixmapCache, QPainter, QPainterPath, QTransform
from PyQt6.QtWidgets import QLabel, QSizePolicy
import image
import fallback_image as fallback
from config import CFG
from constants import card_ratio, card_size_without_bleed_inch


def cached_preview_bytes(entry, field="data"):
    if not isinstance(entry, dict):
        raise TypeError("cached preview entry must be a dictionary")
    return image.decode_cached_image_bytes(entry[field])


class CardImage(QLabel):
    clicked = QtCore.pyqtSignal()
    double_clicked = QtCore.pyqtSignal()

    def __init__(self, img_data, img_size, round_corners=True, rotation=False):
        super().__init__()

        QPixmapCache.setCacheLimit(max(0, int(CFG.PreviewImageCacheMemoryMB)) * 1024)
        card_size_minimum_width_pixels = 130
        if rotation is not None:
            match rotation:
                case image.Rotation.RotateClockwise_90:
                    rotation = 90
                case image.Rotation.RotateCounterClockwise_90:
                    rotation = -90
                case image.Rotation.Rotate_180:
                    rotation = 180
        key = 'manaforge-card:' + hashlib.blake2b(img_data, digest_size=16).hexdigest() + repr((img_size, round_corners, rotation))
        pixmap = QPixmapCache.find(key)
        if pixmap is None:
            raw_pixmap = QPixmap()
            raw_pixmap.loadFromData(img_data, "PNG")
            pixmap = raw_pixmap


            if round_corners:
                card_corner_radius_inch = 1 / 8
                card_corner_radius_pixels = (
                    card_corner_radius_inch * img_size[0] / card_size_without_bleed_inch[0]
                )

                clipped_pixmap = QPixmap(int(img_size[0]), int(img_size[1]))
                clipped_pixmap.fill(QtCore.Qt.GlobalColor.transparent)

                path = QPainterPath()
                path.addRoundedRect(
                    QtCore.QRectF(pixmap.rect()),
                    card_corner_radius_pixels,
                    card_corner_radius_pixels,
                )

                painter = QPainter(clipped_pixmap)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

                painter.setClipPath(path)
                painter.drawPixmap(0, 0, pixmap)
                del painter

                pixmap = clipped_pixmap

            if rotation is not None:
                transform = QTransform()
                transform.rotate(rotation)
                pixmap = pixmap.transformed(transform)

            QPixmapCache.insert(key, pixmap)

        self.setPixmap(pixmap)

        self.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding
        )
        self.setScaledContents(True)
        self.setMinimumWidth(card_size_minimum_width_pixels)

        self._rotated = rotation in [-90, 90]

    def heightForWidth(self, width):
        if self._rotated:
            return int(width * card_ratio)
        else:
            return int(width / card_ratio)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.double_clicked.emit()


class BacksideImage(CardImage):
    def __init__(self, backside_name, img_dict):
        if backside_name in img_dict:
            backside_data = cached_preview_bytes(img_dict[backside_name])
            backside_size = img_dict[backside_name]["size"]
        else:
            backside_data = fallback.data
            backside_size = fallback.size

        super().__init__(backside_data, backside_size)


