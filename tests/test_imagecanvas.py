from PyQt6.QtGui import QColor, QImage, QPainterPath, QPixmap
from PyQt6.QtWidgets import QApplication

from ui.imagecanvas import ImageCanvas, calculate_history_limit


def test_history_limit_shrinks_for_large_images():
    assert calculate_history_limit(256, 256) == 50
    assert 1 <= calculate_history_limit(5056, 5064) < 10


def test_selection_creates_yolo_annotation():
    app = QApplication.instance() or QApplication([])
    image = QImage(100, 80, QImage.Format.Format_RGB32)
    image.fill(QColor("black"))
    canvas = ImageCanvas()
    canvas.set_image(QPixmap.fromImage(image))
    path = QPainterPath()
    path.addRect(10, 20, 20, 20)
    canvas.set_selection(path)
    assert canvas.add_annotation_from_selection(3, "Crack")
    assert canvas.yolo_lines() == ["3 0.200000 0.375000 0.200000 0.250000"]
    assert app is not None
