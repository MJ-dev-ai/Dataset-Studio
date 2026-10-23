"""Actual Qt event tests for tool state, shortcut focus and context panels."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSettings, Qt
from PySide6.QtGui import QColor, QPainterPath
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit
from core.qt_image import bgr_to_qpixmap
from tools.patch_tools import transform_patch
from tools.selection_tools import RectSelectionTool
from tools.toolmanager import ToolMode
from ui.mainwindow import MainWindow


@pytest.fixture(scope="module")
def window(tmp_path_factory):
    """Use temporary settings and synthetic image pixels only."""
    app = QApplication.instance() or QApplication([])
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path_factory.mktemp("settings")))
    w = MainWindow()
    w.resize(1440, 900)
    w.show()
    w.canvas.set_image(bgr_to_qpixmap(np.full((300, 400, 3), 120, np.uint8)))
    app.processEvents()
    yield w
    w.hide()
    app.removeEventFilter(w)
    w.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_tool_keys_and_context_panels(window):
    c = window.canvas
    c.setFocus()
    for key, mode, page in [(Qt.Key.Key_B, ToolMode.BRUSH, "pageOptionsBrush"), (Qt.Key.Key_M, ToolMode.RECT, "pageOptionsSelect"), (Qt.Key.Key_K, ToolMode.PATCH, "pageOptionsPaste"), (Qt.Key.Key_W, ToolMode.BBOX, "pageOptionsSelect")]:
        QTest.keyClick(c, key)
        assert window.tool_manager.current_mode == mode
        assert window.toolOptionsStack.currentWidget().objectName() == page
        assert window.group_paste_transform.isVisible() == (mode == ToolMode.PATCH)
        assert window.group_labeling.isVisible() == (mode in {ToolMode.RECT, ToolMode.BBOX})
    QTest.mouseClick(window.toolboxPatch, Qt.MouseButton.LeftButton)
    assert window.toolboxPatch.isChecked()
    assert not window.toolboxBBox.isChecked()
    QTest.mouseClick(window.toolboxBBox, Qt.MouseButton.LeftButton)
    assert window.action_labeling_tool.isChecked()
    assert window.action_labeling_tool.shortcut().toString() == "W"


def test_space_pan_restores_tool_and_brackets_sync(window):
    c = window.canvas
    window.ui_setup.activate_tool(ToolMode.BRUSH)
    old_size = window.tool_manager.tool(ToolMode.BRUSH).options.size
    QTest.keyClick(c, Qt.Key.Key_BracketRight)
    assert window.spinOptionsBrushSize.value() > old_size
    QTest.keyPress(c, Qt.Key.Key_Space)
    QTest.mousePress(c, Qt.MouseButton.LeftButton, pos=QPoint(50, 50))
    assert c.is_panning
    assert window.tool_manager.current_mode == ToolMode.BRUSH
    QTest.mouseRelease(c, Qt.MouseButton.LeftButton, pos=QPoint(80, 60))
    QTest.keyRelease(c, Qt.Key.Key_Space)
    assert not c.is_panning
    assert not window.tool_manager._space_pressed
    assert window.tool_manager.current_mode == ToolMode.BRUSH


def test_text_input_keeps_undo_and_tool_letters(window, monkeypatch):
    text = QLineEdit(window)
    text.show()
    text.setFocus()
    calls = []
    monkeypatch.setattr(window, "undo_edit", lambda: calls.append("image undo"))
    current = window.tool_manager.current_mode
    QTest.keyClicks(text, "bjkm")
    assert text.text() == "bjkm"
    QTest.keyClick(text, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert not calls
    assert window.tool_manager.current_mode == current
    text.deleteLater()


def test_polygon_backspace_enter_and_selection_intersection(window):
    m, c = window.tool_manager, window.canvas
    window.ui_setup.activate_tool(ToolMode.POLYGON)
    tool = m.tool(ToolMode.POLYGON)
    for point in [QPointF(10, 10), QPointF(80, 10), QPointF(80, 80), QPointF(10, 80)]:
        tool.add_point(point, "replace", QPainterPath())
    QTest.keyClick(c, Qt.Key.Key_Backspace)
    assert len(tool.points) == 3
    QTest.keyClick(c, Qt.Key.Key_Return)
    assert c.has_selection()
    assert not tool.points
    selection = RectSelectionTool()
    mods = Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier
    assert selection.combine_mode_from_modifiers(mods) == "intersect"
    a, b = QPainterPath(), QPainterPath()
    a.addRect(QRectF(0, 0, 20, 20))
    b.addRect(QRectF(10, 10, 20, 20))
    selection.begin_selection("intersect", a)
    assert selection.combined_selection(b).boundingRect() == QRectF(10, 10, 10, 10)


def test_healing_alt_sample_and_patch_keyboard(window, monkeypatch):
    c, m = window.canvas, window.tool_manager
    window.ui_setup.activate_tool(ToolMode.HEALING_BRUSH)
    QTest.mouseClick(c, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.AltModifier, QPoint(80, 80))
    assert m.tool(ToolMode.HEALING_BRUSH).has_source_anchor
    tool = m.tool(ToolMode.PATCH)
    tool.load_selection_patch(np.full((20, 20, 3), 100, np.uint8), np.full((20, 20), 255, np.uint8), 50, 50)
    tool.set_target_size(400, 300)
    tool.state.placement_active = True
    window.ui_setup.activate_tool(ToolMode.PATCH)
    QTest.keyClick(c, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    assert tool.state.x_pos == 60
    assert window.spin_paste_x.value() == 60
    calls = []
    monkeypatch.setattr(window.ui_setup, "_apply_poisson", lambda: calls.append("apply"))
    QTest.keyClick(c, Qt.Key.Key_Return)
    assert calls == ["apply"]
    QTest.keyClick(c, Qt.Key.Key_Escape)
    assert not m.has_patch_preview()


@pytest.mark.parametrize("channels", [1, 3])
def test_rotated_mask_does_not_pick_up_black_background(channels):
    mask = np.zeros((32, 32), np.uint8)
    mask[8:24, 8:24] = 255
    image = np.where(mask > 0, 200, 0).astype(np.uint8)
    if channels == 3:
        image = np.repeat(image[:, :, None], 3, axis=2)
    output, selected = transform_patch(image, 1.3, 27, mask)
    assert np.all(output[selected > 0] == 200)


def test_fill_fallback_respects_selection_and_opacity(window, monkeypatch):
    """A declined MapSet edit must not silently widen a fill to the whole image."""
    c, m = window.canvas, window.tool_manager
    c.set_image(bgr_to_qpixmap(np.full((300, 400, 3), 100, np.uint8)))
    path = QPainterPath()
    path.addRect(QRectF(10, 10, 30, 30))
    c.set_selection(path)
    monkeypatch.setattr(window, "apply_mapset_selection_fill", lambda *args: False)
    window.ui_setup.activate_tool(ToolMode.FILL)
    options = m.tool(ToolMode.FILL).options
    options.color, options.opacity = QColor(200, 200, 200), .5
    assert m._apply_fill(options)
    image = c.pixmap.toImage()
    assert image.pixelColor(0, 0).red() == 100
    assert abs(image.pixelColor(20, 20).red() - 150) <= 1
    assert c.selection_bounds() == QRectF(10, 10, 30, 30)
