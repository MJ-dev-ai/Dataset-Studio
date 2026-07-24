from __future__ import annotations

import cv2
import numpy as np
from PyQt6.QtGui import QImage, QPixmap


def qimage_to_bgr(image: QImage | QPixmap) -> np.ndarray:
    """Convert a Qt image to an owned OpenCV BGR array."""
    source = image.toImage() if isinstance(image, QPixmap) else image
    rgb = source.convertToFormat(QImage.Format.Format_RGB888)
    bits = rgb.bits()
    bits.setsize(rgb.sizeInBytes())
    view = np.frombuffer(bits, dtype=np.uint8).reshape(rgb.height(), rgb.bytesPerLine())
    pixels = view[:, : rgb.width() * 3].reshape(rgb.height(), rgb.width(), 3)
    return cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR).copy()


def bgr_to_qpixmap(array: np.ndarray) -> QPixmap:
    """Convert an OpenCV BGR array to a detached QPixmap."""
    rgb = cv2.cvtColor(array, cv2.COLOR_BGR2RGB)
    height, width = rgb.shape[:2]
    image = QImage(rgb.data, width, height, rgb.strides[0], QImage.Format.Format_RGB888)
    return QPixmap.fromImage(image.copy())


def bgr_mask_to_qpixmap(array: np.ndarray, mask: np.ndarray) -> QPixmap:
    """Convert a BGR patch and single-channel mask to an RGBA preview pixmap."""
    if array is None or array.size == 0:
        raise ValueError("patch image is empty")
    if mask is None or mask.size == 0 or mask.shape[:2] != array.shape[:2]:
        raise ValueError("patch mask must match patch size")
    bgr = array
    if bgr.ndim == 2:
        bgr = cv2.cvtColor(bgr, cv2.COLOR_GRAY2BGR)
    elif bgr.ndim == 3 and bgr.shape[2] == 4:
        bgr = cv2.cvtColor(bgr, cv2.COLOR_BGRA2BGR)
    if bgr.ndim != 3 or bgr.shape[2] != 3:
        raise ValueError("patch image must be grayscale, BGR, or BGRA")
    rgba = cv2.cvtColor(np.ascontiguousarray(bgr), cv2.COLOR_BGR2RGBA)
    alpha = mask
    if alpha.ndim == 3:
        alpha = np.max(alpha[:, :, :3], axis=2)
    rgba[:, :, 3] = np.where(alpha > 0, 210, 0).astype(np.uint8)
    height, width = rgba.shape[:2]
    image = QImage(rgba.data, width, height, rgba.strides[0], QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(image.copy())
