from PyQt6.QtGui import QColor, QImage, QPainterPath, QPixmap
from PyQt6.QtWidgets import QApplication

from ui.imagecanvas import ImageCanvas


def test_map_switch_preserves_selection_and_view_state():
    app = QApplication.instance() or QApplication([])
    canvas = ImageCanvas()
    first = QImage(100, 80, QImage.Format.Format_RGB32)
    first.fill(QColor("red"))
    second = QImage(100, 80, QImage.Format.Format_RGB32)
    second.fill(QColor("blue"))
    canvas.set_image(QPixmap.fromImage(first))
    selection = QPainterPath()
    selection.addRect(10, 10, 20, 20)
    canvas.set_selection(selection)
    canvas.zoom = 1.75
    canvas.pan_offset.setX(-25)
    state = canvas.view_state()
    canvas.set_map_image(QPixmap.fromImage(second))
    canvas.apply_view_state(*state)
    assert canvas.has_selection()
    assert canvas.zoom == 1.75
    actual = canvas.view_state()
    assert all(abs(left - right) < 1e-9 for left, right in zip(actual, state))
    assert app is not None
