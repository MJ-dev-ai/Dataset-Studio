"""Healing quality, preview parity and real Qt gesture lifecycle regression tests."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading
import time

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QSettings, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.qt_image import bgr_to_qpixmap, qimage_to_bgr
from core.mapset import MapSet
from service import editing_service
import tools.healing_preview as preview_module
from tools.healing_preview import HealingPreviewController, HealingPreviewSession, render_healing_preview
from tools.paint_tools import HealingBrushTool
from tools.toolmanager import ToolMode
from ui.imagecanvas import ImageCanvas
from ui.mainwindow import MainWindow
from worker.editing_worker import EditingWorker


def sample():
    """A dark scratch over a clean textured surface with a translated sample."""
    y, x = np.mgrid[:140, :180]
    image = np.repeat((120 + 12 * np.sin(x / 5) + 4 * np.cos(y / 5)).astype(np.uint8)[:, :, None], 3, axis=2)
    image[78:83, 90:131] = 20
    return image


def gesture():
    return [((30, 30), (70, 30), (90, 80), (130, 80))]


def wait_until(predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(5)
    assert predicate(), "healing preview did not settle"


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def test_one_solve_and_event_density_independent_opacity(monkeypatch):
    """Splitting a straight gesture or duplicating points cannot build up opacity."""
    original = editing_service.seamless_clone
    calls = []
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(editing_service, "seamless_clone", counted)
    image = sample()
    sparse = editing_service.apply_healing_strokes(image, gesture(), 20, .35)
    assert len(calls) == 1
    dense = []
    for step in range(40):
        dense.append(((30 + step, 30), (31 + step, 30), (90 + step, 80), (91 + step, 80)))
        dense.append(((31 + step, 30), (31 + step, 30), (91 + step, 80), (91 + step, 80)))
    result = editing_service.apply_healing_strokes(image, dense, 20, .35)
    assert len(calls) == 2
    np.testing.assert_array_equal(result, sparse)
    full = editing_service.apply_healing_strokes(image, gesture(), 20, 1)
    np.testing.assert_array_equal(result, cv2.addWeighted(full, .35, image, .65, 0))
    assert result[80, 100, 0] > image[80, 100, 0]
    np.testing.assert_array_equal(image, sample())


@pytest.mark.parametrize("opacity", [0, .25, 1])
@pytest.mark.parametrize("strokes", [gesture(), [((0, 0), (20, 0), (90, 80), (110, 80))], [((30, 30), (30, 30), (90, 80), (90, 80))]])
def test_preview_exactly_matches_final_worker(app, opacity, strokes):
    """Click, continuous stroke and source-edge cases share final pixel output."""
    image = sample()
    session = HealingPreviewSession(bgr_to_qpixmap(image).toImage(), 20, opacity)
    preview = render_healing_preview(session, strokes)
    worker = EditingWorker("heal", "healing", {"images": {"map": image}, "strokes": strokes, "size": 20, "opacity": opacity})
    output, errors = [], []
    worker.succeeded.connect(lambda _id, result: output.append(result["map"]))
    worker.failed.connect(lambda *args: errors.append(args))
    worker._execute_healing()
    assert not errors
    np.testing.assert_array_equal(preview, output[0])


def test_source_clipping_and_inplace_use_unchanged_source():
    image = sample()
    stroke = [((-10, 0), (30, 0), (80, 80), (120, 80))]
    result = editing_service.apply_healing_strokes(image, stroke, 20)
    np.testing.assert_array_equal(result[:, :90], image[:, :90])
    np.testing.assert_array_equal(result[:80], image[:80])
    overlapping = [((95, 80), (125, 80), (100, 80), (130, 80))]
    expected = editing_service.apply_healing_strokes(image, overlapping, 20, .7)
    mutable = image.copy()
    actual = editing_service.apply_healing_strokes(mutable, overlapping, 20, .7, inplace=True)
    assert actual is mutable
    np.testing.assert_array_equal(actual, expected)


def test_empty_source_overlap_and_cancellation_preserve_image():
    image = sample()
    no_overlap = [((-200, -200), (-200, -200), (100, 80), (100, 80))]
    np.testing.assert_array_equal(editing_service.apply_healing_strokes(image, no_overlap, 20), image)
    def cancel():
        raise RuntimeError("cancelled")
    with pytest.raises(RuntimeError, match="cancelled"):
        editing_service.apply_healing_strokes(image, gesture(), 20, inplace=True, check_cancelled=cancel)
    np.testing.assert_array_equal(image, sample())


def test_gesture_freezes_options_and_moves_source_indicator():
    tool = HealingBrushTool()
    tool.set_source_anchor(QPointF(30, 30))
    tool.options.size, tool.options.opacity = 20, .4
    tool.begin_healing_stroke(QPointF(90, 80))
    tool.options.size, tool.options.opacity = 60, 1
    tool.continue_healing_stroke(QPointF(130, 80))
    assert tool.sampling_position == QPointF(70, 30)
    assert tool.cursor_radius == 10
    finish = tool.finish_healing_stroke(QPointF(130, 80))
    assert len(finish.strokes) == 2
    assert (finish.size, finish.opacity) == (20, .4)
    assert tool.cursor_radius == 30


@pytest.fixture
def window(app, tmp_path):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    w = MainWindow()
    w.resize(1440, 900)
    w.show()
    app.processEvents()
    w.canvas.set_image(bgr_to_qpixmap(sample()))
    w.canvas.zoom, w.canvas.pan_offset = 1, QPointF()
    w.ui_setup.activate_tool(ToolMode.HEALING_BRUSH)
    yield w
    w.tool_manager.healing_preview.close()
    w.tool_manager.patch_preview.close()
    app.removeEventFilter(w)
    w.hide()
    w.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def draw_start(window):
    c = window.canvas
    QTest.mouseClick(c, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.AltModifier, QPoint(30, 30))
    QTest.mousePress(c, Qt.MouseButton.LeftButton, pos=QPoint(90, 80))
    event = QMouseEvent(QEvent.Type.MouseMove, QPointF(130, 80), QPointF(130, 80), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(c, event)


def deliver_worker(window, request):
    """Run the real service worker and deliver its result through UI handlers."""
    task_id, operation, payload = request
    worker = EditingWorker(task_id, operation, payload)
    errors = []
    worker.succeeded.connect(window._on_task_succeeded)
    worker.failed.connect(lambda *args: errors.append(args))
    worker.finished.connect(window._on_task_finished)
    worker._execute_healing()
    assert not errors


def test_drag_preview_commit_and_single_undo(window):
    c, manager = window.canvas, window.tool_manager
    requests = []
    window.task_requested.connect(lambda *args: requests.append(args))
    before = c.pixmap.cacheKey()
    draw_start(window)
    wait_until(lambda: not manager.healing_preview._timer.isActive())
    preview = qimage_to_bgr(c.healing_preview_pixmap)
    assert "최종 합성" in c.healing_preview_status
    assert c.pixmap.cacheKey() == before and not c._undo and not c.is_modified
    assert manager.healing_source_anchor == QPointF(70, 30)
    QTest.mouseRelease(c, Qt.MouseButton.LeftButton, pos=QPoint(130, 80))
    assert len(requests) == 1
    # A second drag is refused until Apply completes, without recording history.
    QTest.mousePress(c, Qt.MouseButton.LeftButton, pos=QPoint(90, 80))
    assert not manager.tool(ToolMode.HEALING_BRUSH).is_editing
    QTest.mouseRelease(c, Qt.MouseButton.LeftButton, pos=QPoint(90, 80))
    assert len(requests) == 1
    deliver_worker(window, requests[0])
    np.testing.assert_array_equal(qimage_to_bgr(c.pixmap), preview)
    assert c.healing_preview_pixmap.isNull() and len(c._undo) == 1
    assert c.undo()
    np.testing.assert_array_equal(qimage_to_bgr(c.pixmap), sample())
    assert c.redo()
    np.testing.assert_array_equal(qimage_to_bgr(c.pixmap), preview)


@pytest.mark.parametrize("cancel", ["escape", "tool", "image", "focus"])
def test_unfinished_gesture_cancels_without_history(window, cancel):
    c, manager = window.canvas, window.tool_manager
    draw_start(window)
    if cancel == "escape":
        QTest.keyClick(c, Qt.Key.Key_Escape)
    elif cancel == "tool":
        window.ui_setup.activate_tool(ToolMode.BRUSH)
    elif cancel == "image":
        c.set_image(bgr_to_qpixmap(sample()))
    else:
        QApplication.sendEvent(c, QEvent(QEvent.Type.FocusOut))
    wait_until(lambda: not manager.healing_preview._timer.isActive())
    assert not manager.tool(ToolMode.HEALING_BRUSH).is_editing
    assert c.healing_preview_pixmap.isNull() and not c._undo and not c.is_modified


def test_changed_image_rejects_delayed_commit(window):
    requests = []
    window.task_requested.connect(lambda *args: requests.append(args))
    assert window.apply_mapset_healing_strokes(gesture(), 20, 1)
    changed = np.full_like(sample(), 40)
    window.canvas.set_image(bgr_to_qpixmap(changed))
    deliver_worker(window, requests[0])
    np.testing.assert_array_equal(qimage_to_bgr(window.canvas.pixmap), changed)
    assert not window.canvas._undo


def test_mapset_uses_visible_edits_and_one_history_entry(window, tmp_path, monkeypatch):
    """Every map is healed, and the visible map never samples an older disk edit."""
    paths = {key: tmp_path / f"{key}.png" for key in ("albedo", "normal")}
    window.current_mapset = MapSet(tmp_path, tuple(paths.items()), None)
    window.current_image_path = paths["albedo"]
    old, visible = sample(), sample()
    visible[:60] = np.clip(visible[:60].astype(int) + 20, 0, 255).astype(np.uint8)
    normal = np.roll(sample(), 2, axis=2)
    window._map_edit_states = {str(paths["albedo"].resolve()): bgr_to_qpixmap(old).toImage(), str(paths["normal"].resolve()): bgr_to_qpixmap(normal).toImage()}
    window.canvas.set_map_image(bgr_to_qpixmap(visible), modified=True)
    monkeypatch.setattr(window, "_update_image_property_panel", lambda *args: None)
    requests = []
    window.task_requested.connect(lambda *args: requests.append(args))
    assert window.apply_mapset_healing_strokes(gesture(), 20, .6)
    deliver_worker(window, requests[0])
    for key, original in [("albedo", visible), ("normal", normal)]:
        expected = editing_service.apply_healing_strokes(original, gesture(), 20, .6)
        np.testing.assert_array_equal(qimage_to_bgr(window._map_edit_states[str(paths[key].resolve())]), expected)
    assert len(window._mapset_undo) == 1
    assert window.undo_mapset_edit()
    np.testing.assert_array_equal(qimage_to_bgr(window.canvas.pixmap), visible)
    np.testing.assert_array_equal(qimage_to_bgr(window._map_edit_states[str(paths["normal"].resolve())]), normal)


def test_noop_commit_never_marks_image_modified(window):
    requests = []
    window.task_requested.connect(lambda *args: requests.append(args))
    assert not window.apply_mapset_healing_strokes(gesture(), 20, 0)
    assert not requests
    outside = [((-200, -200), (-200, -200), (100, 80), (100, 80))]
    assert window.apply_mapset_healing_strokes(outside, 20, 1)
    deliver_worker(window, requests[0])
    assert not window.canvas.is_modified and not window.canvas._undo


def test_preview_failure_can_be_cancelled_without_changing_pixels(window, monkeypatch):
    def fail(*args):
        raise RuntimeError("test healing failure")
    monkeypatch.setattr(preview_module, "render_healing_preview", fail)
    draw_start(window)
    wait_until(lambda: not window.tool_manager.healing_preview._timer.isActive())
    assert "미리보기 실패" in window.canvas.healing_preview_status
    QTest.keyClick(window.canvas, Qt.Key.Key_Escape)
    assert not window.canvas.healing_preview_status
    np.testing.assert_array_equal(qimage_to_bgr(window.canvas.pixmap), sample())
    assert not window.canvas._undo


def test_changing_source_offset_mid_gesture_is_rejected():
    strokes = gesture() + [((0, 0), (0, 0), (100, 80), (100, 80))]
    with pytest.raises(ValueError, match="offset"):
        editing_service.apply_healing_strokes(sample(), strokes, 20)


def test_latest_only_preview_and_destroy_while_running(app, monkeypatch):
    started, release = threading.Event(), threading.Event()
    original = preview_module.render_healing_preview
    calls, worker_threads = [], []
    def delayed(session, strokes):
        calls.append(len(strokes))
        worker_threads.append(threading.get_ident())
        if len(calls) == 1:
            started.set()
            assert release.wait(3)
        return original(session, strokes)
    monkeypatch.setattr(preview_module, "render_healing_preview", delayed)
    canvas = ImageCanvas()
    canvas.set_image(bgr_to_qpixmap(sample()))
    controller = HealingPreviewController(canvas)
    try:
        controller.begin(20, 1)
        controller.request(gesture())
        wait_until(started.is_set)
        controller.request(gesture() * 2)
        controller.request(gesture() * 3)
        assert len(controller._pending[1]) == 3
    finally:
        release.set()
    wait_until(lambda: not controller._timer.isActive())
    assert calls == [1, 3]
    assert all(t != threading.get_ident() for t in worker_threads)
    np.testing.assert_array_equal(qimage_to_bgr(canvas.healing_preview_pixmap), editing_service.apply_healing_strokes(sample(), gesture(), 20))
    controller.begin(20, 1)
    controller.request(gesture())
    future = controller._future
    canvas.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    wait_until(future.done)
    assert future.cancelled() or future.exception() is None
