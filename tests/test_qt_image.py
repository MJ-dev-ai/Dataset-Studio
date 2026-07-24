import numpy as np
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from core.qt_image import bgr_mask_to_qpixmap, bgr_to_qpixmap, qimage_to_bgr


def test_qt_opencv_round_trip_preserves_bgr_pixels():
    app = QApplication.instance() or QApplication([])
    source = np.zeros((3, 4, 3), dtype=np.uint8)
    source[1, 2] = (10, 20, 240)
    assert np.array_equal(qimage_to_bgr(bgr_to_qpixmap(source)), source)
    assert app is not None


def test_masked_pixmap_preserves_patch_alpha():
    """Manual patch previews must use the selection mask as alpha."""
    app = QApplication.instance() or QApplication([])
    patch = np.full((2, 3, 3), (10, 20, 30), dtype=np.uint8)
    mask = np.array([[0, 255, 0], [255, 255, 0]], dtype=np.uint8)

    image_format = QImage.Format.Format_RGBA8888
    image = bgr_mask_to_qpixmap(patch, mask).toImage().convertToFormat(image_format)

    assert image.pixelColor(0, 0).alpha() == 0
    assert image.pixelColor(1, 0).alpha() == 210
    assert image.format() == image_format
    assert app is not None
