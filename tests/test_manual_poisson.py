import numpy as np
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QPainterPath, QPixmap
from PyQt6.QtWidgets import QApplication

from tools.patch_tools import PatchTool
from ui.imagecanvas import ImageCanvas
from core.patch_clipboard import PatchClipboard


def _canvas_with_selection() -> ImageCanvas:
    """Create a canvas with one rectangular source selection."""
    image = QImage(40, 30, QImage.Format.Format_RGB888)
    image.fill(QColor(80, 90, 100))
    canvas = ImageCanvas()
    canvas.set_image(QPixmap.fromImage(image))
    path = QPainterPath()
    path.addRect(5, 6, 10, 8)
    canvas.set_selection(path)
    return canvas


def test_manual_patch_preview_does_not_commit_pixels():
    """Moving a copied patch should update only the overlay preview."""
    app = QApplication.instance() or QApplication([])
    canvas = _canvas_with_selection()
    tool = PatchTool(canvas)

    assert tool.copy_from_selection("source.png")
    assert not canvas.has_patch_preview()
    assert tool.begin_placement(20, 10)
    revision = canvas.revision
    tool.set_position(20, 10)

    assert canvas.has_patch_preview()
    assert canvas.revision == revision
    assert tool.state.source_name == "source.png"
    assert app is not None


def test_manual_poisson_request_contains_clamped_transformed_inputs():
    """The worker request must contain owned arrays and valid placement."""
    app = QApplication.instance() or QApplication([])
    canvas = _canvas_with_selection()
    tool = PatchTool(canvas)
    assert tool.copy_from_selection("source.png")
    assert tool.begin_placement(5, 6)
    tool.set_scale(1.5)
    tool.set_rotation(15)
    tool.set_position(10_000, 10_000)

    target, patch, mask, x_pos, y_pos = tool.composition_inputs()

    assert isinstance(target, np.ndarray)
    assert patch.shape[:2] == mask.shape[:2]
    assert x_pos + patch.shape[1] <= target.shape[1]
    assert y_pos + patch.shape[0] <= target.shape[0]
    assert app is not None


def test_commit_consumes_active_placement_but_not_canvas_history():
    """After Apply, another click must not create a duplicate patch preview."""
    app = QApplication.instance() or QApplication([])
    canvas = _canvas_with_selection()
    tool = PatchTool(canvas)
    assert tool.copy_from_selection("source.png")
    assert tool.begin_placement(10, 10)
    result = np.full((30, 40, 3), 120, dtype=np.uint8)

    tool.commit_result(result)

    assert not tool.paste_preview()
    assert not canvas.has_patch_preview()
    assert canvas.revision == 1
    tool.mouse_move_event(
        _MouseEvent(QPointF(12, 12), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton)
    )
    assert app is not None


class _MouseEvent:
    def __init__(self, position: QPointF, button, buttons):
        self._position = position
        self._button = button
        self._buttons = buttons

    def position(self):
        return self._position

    def button(self):
        return self._button

    def buttons(self):
        return self._buttons

    def accept(self):
        pass


def test_right_drag_rotates_patch_around_its_center():
    """Right-button angular dragging should update rotation without moving the patch."""
    app = QApplication.instance() or QApplication([])
    canvas = _canvas_with_selection()
    tool = PatchTool(canvas)
    assert tool.copy_from_selection("source.png")
    assert tool.begin_placement(5, 6)
    center = QPointF(10, 10)
    tool.mouse_press_event(
        _MouseEvent(center + QPointF(10, 0), Qt.MouseButton.RightButton, Qt.MouseButton.RightButton)
    )
    tool.mouse_move_event(
        _MouseEvent(center + QPointF(0, 10), Qt.MouseButton.NoButton, Qt.MouseButton.RightButton)
    )

    assert 85 <= tool.state.angle <= 95
    rotated, _ = tool.transformed_patch()
    rotated_center = (
        tool.state.x_pos + rotated.shape[1] / 2,
        tool.state.y_pos + rotated.shape[0] / 2,
    )
    assert abs(rotated_center[0] - center.x()) <= 1
    assert abs(rotated_center[1] - center.y()) <= 1
    assert app is not None


def test_mapset_composition_uses_corresponding_source_patch_for_each_target():
    """Manual Poisson input must be built for the whole target MapSet."""
    app = QApplication.instance() or QApplication([])
    canvas = _canvas_with_selection()
    tool = PatchTool(canvas)
    clipboard = PatchClipboard()
    mask = np.full((4, 5), 255, dtype=np.uint8)
    clip = clipboard.add_mapset(
        {
            "albedo_map": np.full((4, 5, 3), 10, dtype=np.uint8),
            "normal_map": np.full((4, 5, 3), 20, dtype=np.uint8),
        },
        mask,
        "MapSet Patch",
        preview_key="albedo_map",
    )
    assert tool.load_clip(clip, 10, 10, "albedo_map")
    targets = {
        "albedo_map": np.zeros((30, 40, 3), dtype=np.uint8),
        "normal_map": np.zeros((30, 40, 3), dtype=np.uint8),
    }

    inputs = tool.mapset_composition_inputs(targets)

    assert set(inputs) == {"albedo_map", "normal_map"}
    assert np.all(inputs["albedo_map"][1] == 10)
    assert np.all(inputs["normal_map"][1] == 20)
    assert app is not None
