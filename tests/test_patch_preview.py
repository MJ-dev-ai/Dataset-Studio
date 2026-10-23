"""Pixel parity and asynchronous lifecycle checks for live patch composition."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading
import time

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.patch_clipboard import PatchClipboard
from core.qt_image import bgr_to_qpixmap, qimage_to_bgr
from service.editing_service import patch_mode_from_text
import tools.patch_preview as preview_module
from tools.patch_preview import PatchPreviewController, PreviewTarget, render_patch_preview
from tools.patch_tools import PatchPreview, PatchTool
from tools.toolmanager import ToolMode
from ui.imagecanvas import ImageCanvas
from ui.mainwindow import MainWindow
from worker.editing_worker import EditingWorker


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def wait_until(predicate, seconds=5):
    """Pump real Qt events while allowing the worker to run."""
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(5)
    assert predicate(), "preview did not settle"


def images():
    rng = np.random.default_rng(631)
    target = rng.integers(30, 210, (140, 180, 3), dtype=np.uint8)
    patch = rng.integers(50, 240, (30, 40, 3), dtype=np.uint8)
    mask = np.zeros((30, 40), np.uint8)
    mask[3:25, 9:37] = 255
    mask[8:13, 15:20] = 0
    return target, patch, mask


@pytest.mark.parametrize("label", ["Normal", "Mixed", "Detail Preserve", "Boundary Mixed", "Hard Paste"])
@pytest.mark.parametrize("map_key", ["albedo_map", "normal_map"])
@pytest.mark.parametrize("angle,scale,x,y", [(0, 1, 0, 0), (33, 1.2, 70, 65)])
def test_native_preview_matches_commit_after_independent_transform(app, label, map_key, angle, scale, x, y):
    """The displayed whole image equals EditingWorker, including untouched pixels."""
    target, source, mask = images()
    clip = PatchClipboard().add_mapset({map_key: source}, mask, "preview", preview_key=map_key)
    tool = PatchTool()
    assert tool.load_clip(clip, 50, 50, map_key, (180, 140))
    tool.state.angle, tool.state.scale = angle, scale
    tool.state.x_pos, tool.state.y_pos = x, y
    preview = tool.preview_payload()
    mode = patch_mode_from_text(label)
    pixels = render_patch_preview(PreviewTarget(bgr_to_qpixmap(target).toImage()), preview, mode, map_key)
    committed, errors = [], []
    worker = EditingWorker("parity", "manual_poisson", {
        "composition_inputs": tool.mapset_composition_inputs({map_key: target}), "mode": mode,
    })
    worker.succeeded.connect(lambda _id, result: committed.append(result[map_key]))
    worker.failed.connect(lambda *args: errors.append(args))
    worker._execute_manual_poisson()
    assert not errors
    displayed = target.copy()
    h, w = pixels.shape[:2]
    displayed[preview.y_pos:preview.y_pos + h, preview.x_pos:preview.x_pos + w] = pixels
    np.testing.assert_array_equal(displayed, committed[0])
    np.testing.assert_array_equal(target, images()[0])


@pytest.fixture
def controller(app):
    canvas = ImageCanvas()
    canvas.set_image(bgr_to_qpixmap(images()[0]))
    controller = PatchPreviewController(canvas)
    yield controller
    controller.close()
    canvas.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_latest_request_only_runs_and_gui_remains_responsive(controller, monkeypatch):
    """A blocked solve keeps one pending request and never paints stale pixels."""
    started, release = threading.Event(), threading.Event()
    calls, threads = [], []
    original = preview_module.render_patch_preview

    def delayed(target, patch, mode, key):
        calls.append(patch.x_pos)
        threads.append(threading.get_ident())
        if len(calls) == 1:
            started.set()
            assert release.wait(3)
        return original(target, patch, mode, key)

    monkeypatch.setattr(preview_module, "render_patch_preview", delayed)
    _, source, mask = images()
    before = controller.canvas.pixmap.cacheKey()
    try:
        controller.request((1,), PatchPreview(source, mask, 5, 5), "hard_paste", "albedo", "Hard Paste")
        wait_until(started.is_set)
        controller.request((2,), PatchPreview(source, mask, 15, 5), "hard_paste", "albedo", "Hard Paste")
        controller.request((3,), PatchPreview(source, mask, 25, 5), "hard_paste", "albedo", "Hard Paste")
        # QTimer callbacks and canvas edits can run while the solve is blocked.
        controller.canvas.set_zoom(2)
        assert controller.canvas.zoom == 2
        assert controller._pending[0] == (3,)
    finally:
        release.set()
    wait_until(lambda: not controller._timer.isActive())
    assert calls == [5, 25]
    assert all(t != threading.get_ident() for t in threads)
    assert controller.canvas.patch_preview_position.x() == 25
    assert "최종 합성" in controller.canvas.patch_preview_status
    assert controller.canvas.pixmap.cacheKey() == before
    assert not controller.canvas.is_modified
    assert not controller.canvas._undo


@pytest.mark.parametrize("action", ["clear", "close"])
def test_cancel_or_close_discards_inflight_result(controller, monkeypatch, action):
    """A completed worker cannot resurrect an overlay after cancellation/close."""
    started, release = threading.Event(), threading.Event()

    def delayed(*args):
        started.set()
        assert release.wait(3)
        return np.zeros((30, 40, 3), np.uint8)

    monkeypatch.setattr(preview_module, "render_patch_preview", delayed)
    _, source, mask = images()
    try:
        controller.request((1,), PatchPreview(source, mask, 5, 5), None, "albedo", "Detail Preserve")
        wait_until(started.is_set)
        future = controller._future
        getattr(controller, action)()
    finally:
        release.set()
    wait_until(future.done)
    controller._poll()
    assert not controller.canvas.has_patch_preview()
    assert not controller.canvas.patch_preview_status


def test_preview_failure_is_visible_and_new_request_recovers(controller, monkeypatch):
    """A failed solve must not silently present Hard Paste as the selected blend."""
    original = preview_module.render_patch_preview
    def fail(*args):
        raise RuntimeError("test solve failure")
    monkeypatch.setattr(preview_module, "render_patch_preview", fail)
    _, source, mask = images()
    patch = PatchPreview(source, mask, 5, 5)
    controller.request((1,), patch, None, "albedo", "Detail Preserve")
    wait_until(lambda: not controller._timer.isActive())
    assert "미리보기 실패" in controller.canvas.patch_preview_status
    assert not controller.canvas.has_patch_preview()
    monkeypatch.setattr(preview_module, "render_patch_preview", original)
    controller.request((2,), patch, None, "albedo", "Detail Preserve")
    wait_until(lambda: not controller._timer.isActive())
    assert "최종 합성" in controller.canvas.patch_preview_status


def test_image_switch_during_solve_uses_new_snapshot(controller, monkeypatch):
    """An old document solve cannot paint over a newly selected map."""
    original = preview_module.render_patch_preview
    started, release = threading.Event(), threading.Event()
    calls = []

    def delayed(target, patch, mode, key):
        calls.append(key)
        if len(calls) == 1:
            started.set()
            assert release.wait(3)
        return original(target, patch, mode, key)

    monkeypatch.setattr(preview_module, "render_patch_preview", delayed)
    target, source, mask = images()
    patch = PatchPreview(source, mask, 20, 20)
    try:
        controller.request((1,), patch, None, "albedo", "Detail Preserve")
        wait_until(started.is_set)
        controller.canvas.set_map_image(bgr_to_qpixmap(np.full_like(target, 60)))
        controller.request((2,), patch, None, "normal_map", "Detail Preserve")
    finally:
        release.set()
    wait_until(lambda: not controller._timer.isActive())
    expected = original(PreviewTarget(controller.canvas.pixmap.toImage()), patch, None, "normal_map")
    np.testing.assert_array_equal(qimage_to_bgr(controller.canvas.patch_preview_pixmap), expected)
    assert calls == ["albedo", "normal_map"]


def test_canvas_destruction_during_solve_has_no_worker_gui_access(app, monkeypatch):
    """Deleting the canvas must not require waiting for native composition."""
    started, release = threading.Event(), threading.Event()
    original = preview_module.render_patch_preview

    def delayed(*args):
        started.set()
        assert release.wait(3)
        return original(*args)

    monkeypatch.setattr(preview_module, "render_patch_preview", delayed)
    canvas = ImageCanvas()
    target, source, mask = images()
    canvas.set_image(bgr_to_qpixmap(target))
    controller = PatchPreviewController(canvas)
    try:
        controller.request((1,), PatchPreview(source, mask, 20, 20), None, "albedo", "Detail Preserve")
        wait_until(started.is_set)
        future = controller._future
        canvas.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    finally:
        release.set()
    wait_until(future.done)
    assert future.exception() is None


def test_editor_mode_move_map_change_and_escape(app, tmp_path):
    """Toolbar changes and real keyboard movement refresh native preview pixels."""
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    window = MainWindow()
    target, source, mask = images()
    canvas, manager = window.canvas, window.tool_manager
    canvas.set_image(bgr_to_qpixmap(target))
    tool = manager.tool(ToolMode.PATCH)
    tool.load_selection_patch(source, mask, 40, 40)
    tool.state.placement_active = True
    window.ui_setup.activate_tool(ToolMode.PATCH)
    try:
        window.optionsPoissonMode.setCurrentText("Hard Paste")
        wait_until(lambda: not manager.patch_preview._timer.isActive())
        first = qimage_to_bgr(canvas.patch_preview_pixmap)
        before = canvas.pixmap.cacheKey()
        QTest.keyClick(canvas, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
        assert "계산 중" in canvas.patch_preview_status
        wait_until(lambda: not manager.patch_preview._timer.isActive())
        assert canvas.patch_preview_position.x() == 50
        window.combo_poisson_mode.setCurrentText("Detail Preserve")
        wait_until(lambda: not manager.patch_preview._timer.isActive())
        assert window.optionsPoissonMode.currentText() == "Detail Preserve"
        assert not np.array_equal(first, qimage_to_bgr(canvas.patch_preview_pixmap))
        assert canvas.pixmap.cacheKey() == before
        # A replaced underlying image forces a fresh snapshot and result.
        canvas.set_map_image(bgr_to_qpixmap(np.full_like(target, 40)))
        wait_until(lambda: not manager.patch_preview._timer.isActive())
        preview = tool.preview_payload()
        expected = render_patch_preview(PreviewTarget(canvas.pixmap.toImage()), preview, None, "")
        np.testing.assert_array_equal(qimage_to_bgr(canvas.patch_preview_pixmap), expected)
        QTest.keyClick(canvas, Qt.Key.Key_Escape)
        assert not canvas.has_patch_preview()
        assert manager.patch_preview._key is None
    finally:
        manager.patch_preview.close()
        app.removeEventFilter(window)
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
