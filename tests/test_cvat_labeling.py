"""Real editor interactions for CVAT-inspired labeling, without user datasets."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSettings, Qt
from PySide6.QtGui import QMouseEvent, QPainterPath
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from core.mapset import MapSet
from core.qt_image import bgr_to_qpixmap
from tools.toolmanager import ToolMode
from ui.mainwindow import MainWindow


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    w = MainWindow()
    w.resize(1440, 900)
    w.show()
    app.processEvents()
    w.canvas.set_image(bgr_to_qpixmap(np.full((300, 400, 3), 110, np.uint8)))
    w.canvas.zoom, w.canvas.pan_offset = 1, QPointF()
    w._label_catalog = [(2, "균열"), (7, "찍힘")]
    w.annotation_panel.refresh()
    w._labels_modified = False
    def unexpected_dialog():
        pytest.fail("drawing must not open the class manager")
    monkeypatch.setattr(w, "show_label_manager", unexpected_dialog)
    yield w
    w.tool_manager.healing_preview.close()
    w.tool_manager.patch_preview.close()
    app.removeEventFilter(w)
    w.hide()
    w.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def move(canvas, x, y):
    event = QMouseEvent(QEvent.Type.MouseMove, QPointF(x, y), QPointF(x, y), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(canvas, event)


def draw(window, start=(20, 20), end=(100, 80)):
    c = window.canvas
    window.ui_setup.activate_tool(ToolMode.BBOX)
    QTest.mousePress(c, Qt.MouseButton.LeftButton, pos=QPoint(*start))
    move(c, *end)
    QTest.mouseRelease(c, Qt.MouseButton.LeftButton, pos=QPoint(*end))


def test_continuous_boxes_reuse_class_without_modal(window):
    c = window.canvas
    original = c.pixmap.cacheKey()
    draw(window)
    draw(window, (120, 100), (180, 150))
    assert [a.class_id for a in c.annotations] == [2, 2]
    assert window.tool_manager.current_mode == ToolMode.BBOX
    assert window.annotation_panel.objects.count() == 2
    assert window.annotation_panel.objects.currentRow() == 1
    assert window.annotation_panel.isVisible()
    assert c.pixmap.cacheKey() == original and not c._undo
    assert window._labels_modified
    assert len(c._annotation_undo) == 2
    QTest.keyClick(c, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert len(c.annotations) == 1
    QTest.keyClick(c, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert len(c.annotations) == 2


def test_missing_class_and_zero_area_click_are_noops(window):
    c = window.canvas
    window._label_catalog = []
    window.annotation_panel.refresh()
    draw(window)
    assert not c.annotations and not window._labels_modified
    window._label_catalog = [(2, "균열")]
    window.annotation_panel.refresh()
    draw(window, (30, 30), (30, 30))
    assert not c.annotations and not c._annotation_undo


def test_draw_clips_to_image_and_keeps_normalized_yolo(window):
    draw(window, (350, 250), (430, 330))
    box = window.canvas.annotations[0].bounds
    assert box == QRectF(350, 250, 50, 50)
    values = window.canvas.yolo_lines()[0].split()
    assert values[0] == "2"
    assert float(values[1]) == pytest.approx(375 / 400, abs=1e-6)
    assert float(values[4]) == pytest.approx(50 / 300, abs=1e-6)


def test_overlap_cycle_tab_and_scoped_delete(window):
    draw(window)
    draw(window, (30, 30), (90, 70))
    c = window.canvas
    window.ui_setup.activate_tool(ToolMode.RECT)
    QTest.mouseClick(c, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, QPoint(50, 50))
    assert c.selected_annotation_index == 0
    assert window.annotation_panel.objects.currentRow() == 0
    QTest.mouseClick(c, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, QPoint(50, 50))
    assert c.selected_annotation_index == 1
    QTest.keyClick(c, Qt.Key.Key_Tab)
    assert c.selected_annotation_index == 0 and c.hasFocus()
    QTest.keyClick(c, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
    assert c.selected_annotation_index == 1
    QTest.keyClick(c, Qt.Key.Key_Delete)
    assert len(c.annotations) == 1
    QTest.keyClick(c, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert len(c.annotations) == 2 and c.selected_annotation_index == 1
    c.clear_annotation_selection()
    assert not window.remove_active_annotation()
    assert len(c.annotations) == 2


def test_list_selection_numeric_edit_and_class_preserve_draw_choice(window):
    draw(window)
    draw(window, (120, 100), (180, 150))
    panel, c = window.annotation_panel, window.canvas
    panel.objects.setCurrentRow(0)
    assert c.selected_annotation_index == 0
    assert window.tool_manager.current_mode == ToolMode.RECT
    assert c.selection_bounds() == c.annotations[0].bounds
    for field, value in zip(panel.fields, (25, 35, 90, 55)):
        field.setValue(value)
    panel.class_combo.setCurrentIndex(panel.class_combo.findData(7))
    QTest.mouseClick(panel.apply_button, Qt.MouseButton.LeftButton)
    assert c.annotations[0].bounds == QRectF(25, 35, 90, 55)
    assert c.annotations[0].class_id == 7
    assert window.annotationClassCombo.currentData() == 2
    assert c.undo_annotation()
    assert c.annotations[0].bounds == QRectF(20, 20, 80, 60)
    assert c.annotations[0].class_id == 2


def test_nudge_clamps_without_shrinking_and_repeat_key(window):
    draw(window, (1, 1), (81, 61))
    c = window.canvas
    c.move_annotation(-1, -1)
    window.ui_setup.activate_tool(ToolMode.RECT)
    QTest.keyClick(c, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
    assert c.annotations[0].bounds == QRectF(0, 0, 80, 60)
    QTest.keyClick(c, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    assert c.annotations[0].bounds == QRectF(10, 0, 80, 60)
    QTest.keyClick(c, Qt.Key.Key_Down)
    assert c.annotations[0].bounds.y() == 1
    QTest.keyClick(c, Qt.Key.Key_N)
    assert window.tool_manager.current_mode == ToolMode.BBOX


def test_drag_is_one_transaction_and_updates_properties(window):
    draw(window)
    c = window.canvas
    c.reset_annotation_history()
    window._labels_modified = False
    window.ui_setup.activate_tool(ToolMode.RECT)
    QTest.mousePress(c, Qt.MouseButton.LeftButton, pos=QPoint(50, 50))
    move(c, 60, 55)
    move(c, 75, 65)
    assert not window._labels_modified and not c._annotation_undo
    assert window.annotation_panel.fields[0].value() == 45
    QTest.mouseRelease(c, Qt.MouseButton.LeftButton, pos=QPoint(75, 65))
    assert len(c._annotation_undo) == 1 and window._labels_modified
    assert c.annotations[0].bounds == QRectF(45, 35, 80, 60)
    QTest.keyClick(c, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert c.annotations[0].bounds == QRectF(20, 20, 80, 60)


@pytest.mark.parametrize("cancel", ["escape", "tool", "focus", "undo"])
def test_cancel_drag_restores_geometry_without_dirty_flag(window, cancel):
    draw(window)
    c = window.canvas
    c.reset_annotation_history()
    window._labels_modified = False
    window.ui_setup.activate_tool(ToolMode.RECT)
    QTest.mousePress(c, Qt.MouseButton.LeftButton, pos=QPoint(50, 50))
    move(c, 70, 60)
    if cancel == "escape":
        QTest.keyClick(c, Qt.Key.Key_Escape)
    elif cancel == "tool":
        window.ui_setup.activate_tool(ToolMode.BRUSH)
    elif cancel == "undo":
        QTest.keyClick(c, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    else:
        QApplication.sendEvent(c, QEvent(QEvent.Type.FocusOut))
    assert c.annotations[0].bounds == QRectF(20, 20, 80, 60)
    assert not window._labels_modified and not c._annotation_undo


def test_resize_and_cancel_new_box(window):
    draw(window)
    c = window.canvas
    window.ui_setup.activate_tool(ToolMode.RECT)
    QTest.mousePress(c, Qt.MouseButton.LeftButton, pos=QPoint(100, 80))
    move(c, 140, 110)
    QTest.mouseRelease(c, Qt.MouseButton.LeftButton, pos=QPoint(140, 110))
    assert c.annotations[0].bounds == QRectF(20, 20, 120, 90)
    window.ui_setup.activate_tool(ToolMode.BBOX)
    QTest.mousePress(c, Qt.MouseButton.LeftButton, pos=QPoint(180, 180))
    move(c, 210, 220)
    QTest.keyClick(c, Qt.Key.Key_Escape)
    QTest.mouseRelease(c, Qt.MouseButton.LeftButton, pos=QPoint(210, 220))
    assert len(c.annotations) == 1


def test_hidden_labels_are_not_hit_targets(window):
    draw(window)
    window.set_labels_visible(False)
    c = window.canvas
    assert c.annotation_at(QPointF(40, 40)) == -1
    assert not c.cycle_annotation()
    assert c.selected_annotation_index == -1
    assert not window.annotation_panel.visible_check.isChecked()
    window.annotation_panel.objects.setCurrentRow(0)
    assert c.labels_visible and c.selected_annotation_index == 0
    assert window.action_show_labels.isChecked()


def test_text_input_does_not_delete_or_change_tools(window):
    draw(window)
    field = QLineEdit(window)
    field.show()
    field.setFocus()
    QTest.keyClicks(field, "nnn")
    field.setCursorPosition(0)
    QTest.keyClick(field, Qt.Key.Key_Delete)
    assert field.text() == "nn" and len(window.canvas.annotations) == 1
    assert window.tool_manager.current_mode == ToolMode.BBOX
    field.deleteLater()


def test_empty_label_reload_clears_list_and_history(window, tmp_path):
    draw(window)
    path = tmp_path / "labels.txt"
    path.write_text("", encoding="utf-8")
    window.current_mapset = MapSet(tmp_path, (("image", tmp_path / "image.png"),), path)
    assert window.reload_current_yolo_labels()
    assert not window.canvas.annotations
    assert not window.canvas._annotation_undo
    assert window.annotation_panel.objects.count() == 0
    assert not window._labels_modified


def test_utf8_catalog_and_yolo_round_trip(window, tmp_path):
    window.project_root_folder = tmp_path
    window.current_mapset = MapSet(tmp_path, (("image", tmp_path / "image.png"),), tmp_path / "labels.txt")
    draw(window)
    window.annotationClassCombo.setCurrentIndex(1)
    draw(window, (110, 90), (190, 160))
    expected = window.canvas.yolo_lines()
    assert window.save_current_yolo_labels()
    assert "균열" in (tmp_path / "labels.json").read_text(encoding="utf-8")
    assert window.reload_current_yolo_labels()
    assert window.canvas.yolo_lines() == expected
    assert [a.class_name for a in window.canvas.annotations] == ["균열", "찍힘"]


def test_cached_unsaved_labels_restore_panel_state(window, tmp_path):
    window.current_mapset = MapSet(tmp_path, (("image", tmp_path / "image.png"),), tmp_path / "labels.txt")
    draw(window)
    window._cache_current_label_state()
    window._labels_modified = False
    window.canvas.annotations.clear()
    window._load_current_yolo_labels()
    assert len(window.canvas.annotations) == 1
    assert window._labels_modified and "미저장" in window.annotation_panel.count.text()
    assert not window.canvas._annotation_undo
