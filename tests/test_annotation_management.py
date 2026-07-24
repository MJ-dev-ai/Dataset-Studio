from PyQt6.QtGui import QColor, QImage, QPainterPath, QPixmap
from PyQt6.QtWidgets import QApplication

from ui.imagecanvas import ImageCanvas


def test_existing_annotation_can_be_selected_and_removed():
    app = QApplication.instance() or QApplication([])
    image = QImage(100, 80, QImage.Format.Format_RGB32)
    image.fill(QColor("black"))
    canvas = ImageCanvas()
    canvas.set_image(QPixmap.fromImage(image))
    path = QPainterPath()
    path.addRect(10, 10, 20, 15)
    canvas.set_selection(path)
    assert canvas.add_annotation_from_selection(3, "Crack")
    assert canvas.select_annotation(0)
    assert canvas.selection_bounds().toAlignedRect().width() == 20
    assert canvas.remove_annotation(0)
    assert canvas.annotations == []
    assert app is not None
