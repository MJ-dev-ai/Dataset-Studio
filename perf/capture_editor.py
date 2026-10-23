"""Render UTF-8-labelled tool states and synthetic blend checks without user data."""
import os
import json
import sys
import time
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cv2
import numpy as np
from PySide6.QtCore import QSettings, QEvent, QPointF
from PySide6.QtGui import QFont, QFontDatabase, QPainterPath
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from core.qt_image import bgr_to_qpixmap
from core.image_ops import rotate_bound
from service.editing_service import compose_patch
from tools.patch_tools import transform_patch
from tools.toolmanager import ToolMode
from ui.mainwindow import MainWindow


def main():
    """Save inspectable screenshots while isolating settings from the user's app."""
    output = Path(__file__).resolve().parent
    app = QApplication([])
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(output / "qt-settings"))
    for font in ["segoeui.ttf", "malgun.ttf"]:
        path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont("Malgun Gothic", 9))
    window = MainWindow()
    window.resize(1440, 900)
    window.show()
    y, x = np.mgrid[:600, :800]
    texture = np.clip(120 + 12 * np.sin(x / 15) + 5 * np.cos(y / 9), 0, 255).astype(np.uint8)
    sample = np.repeat(texture[:, :, None], 3, axis=2)
    window.canvas.set_image(bgr_to_qpixmap(sample))
    window.canvas.fit_to_window()
    selection = QPainterPath()
    selection.addRect(220, 180, 200, 150)
    window.canvas.set_selection(selection)
    patch = sample[180:330, 220:420].copy()
    cv2.line(patch, (35, 30), (150, 100), (30, 30, 30), 4)
    tool = window.tool_manager.tool(ToolMode.PATCH)
    tool.load_selection_patch(patch, np.full(patch.shape[:2], 255, np.uint8), 350, 250, "합성 결함 샘플")
    tool.state.placement_active = True
    tool.set_target_size(800, 600)
    for mode in [ToolMode.MOVE, ToolMode.POLYGON, ToolMode.HEALING_BRUSH, ToolMode.PATCH, ToolMode.BBOX]:
        window.ui_setup.activate_tool(mode)
        for _ in range(5):
            app.processEvents()
        deadline = time.monotonic() + 10
        while window.tool_manager.patch_preview._timer.isActive() and time.monotonic() < deadline:
            QTest.qWait(10)
        window.grab().save(str(output / f"ui-{mode.value}.png"))
    window.ui_setup.activate_tool(ToolMode.PATCH)
    window.canvas.clear_selection()
    for label in ["Normal", "Mixed", "Detail Preserve", "Boundary Mixed", "Hard Paste"]:
        window.optionsPoissonMode.setCurrentText(label)
        deadline = time.monotonic() + 10
        while window.tool_manager.patch_preview._timer.isActive() and time.monotonic() < deadline:
            QTest.qWait(10)
        assert "최종 합성" in window.canvas.patch_preview_status
        app.processEvents()
        window.grab().save(str(output / f"live-blend-{label.lower().replace(' ', '-')}.png"))
    window.ui_setup.activate_tool(ToolMode.HEALING_BRUSH)
    window.tool_manager.clear_active_patch()
    scratched = sample.copy()
    cv2.line(scratched, (350, 300), (500, 300), (25, 25, 25), 5)
    window.canvas.set_image(bgr_to_qpixmap(scratched))
    window.canvas.fit_to_window()
    healing = window.tool_manager.tool(ToolMode.HEALING_BRUSH)
    healing.options.size = 50
    window.spinOptionsBrushSize.setValue(50)
    healing.set_source_anchor(QPointF(150, 150))
    window.canvas.set_tool_cursor_pos(QPointF(500, 300))
    app.processEvents()
    window.grab().save(str(output / "healing-before.png"))
    healing.begin_healing_stroke(QPointF(350, 300))
    healing.continue_healing_stroke(QPointF(500, 300))
    controller = window.tool_manager.healing_preview
    controller.begin(healing.stroke_size, healing.stroke_opacity)
    controller.request(healing.strokes)
    deadline = time.monotonic() + 10
    while controller._timer.isActive() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert "최종 합성" in window.canvas.healing_preview_status
    app.processEvents()
    window.grab().save(str(output / "healing-live-preview.png"))
    original = np.load(output / "composite_before.npz")
    after = compose_patch(original["target"], original["patch"], original["mask"], 20, 25, fallback=False)
    images = []
    for name, image in [("BEFORE: shifted", original["result"]), ("AFTER: aligned", after)]:
        panel = cv2.resize(image, (440, 400), interpolation=cv2.INTER_NEAREST)
        cv2.drawMarker(panel, (32 * 4, 43 * 4), (0, 0, 255), cv2.MARKER_CROSS, 25, 1)
        panel = cv2.copyMakeBorder(panel, 35, 0, 0, 0, cv2.BORDER_CONSTANT, value=(245, 245, 245))
        cv2.putText(panel, name, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, .65, (20, 20, 20), 1, cv2.LINE_AA)
        images.append(panel)
    cv2.imwrite(str(output / "blend-alignment.png"), np.hstack(images))
    mask = np.zeros((32, 32), np.uint8)
    mask[8:24, 8:24] = 255
    patch = np.repeat(np.where(mask > 0, 200, 0).astype(np.uint8)[:, :, None], 3, axis=2)
    old = rotate_bound(cv2.resize(patch, (42, 42), interpolation=cv2.INTER_LINEAR), 27)
    new, rotated_mask = transform_patch(patch, 1.3, 27, mask)
    panels = []
    for label, pixels in [("BEFORE: dark edge", old), ("AFTER: clean edge", new)]:
        composite = np.full_like(pixels, 120)
        composite[rotated_mask > 0] = pixels[rotated_mask > 0]
        panel = cv2.resize(composite, (440, 440), interpolation=cv2.INTER_NEAREST)
        panel = cv2.copyMakeBorder(panel, 35, 0, 0, 0, cv2.BORDER_CONSTANT, value=(245, 245, 245))
        cv2.putText(panel, label, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, .65, (20, 20, 20), 1, cv2.LINE_AA)
        panels.append(panel)
    cv2.imwrite(str(output / "transform-edge.png"), np.hstack(panels))
    quality = {"expected_peak_xy": [32, 43], "before_peak_yx": list(map(int, np.unravel_index(original["result"][:, :, 0].argmax(), original["target"].shape[:2]))), "after_peak_yx": list(map(int, np.unravel_index(after[:, :, 0].argmax(), after.shape[:2]))), "uniform_selected_color": 200, "rotated_edge_before_min": int(old[rotated_mask > 0].min()), "rotated_edge_after_min": int(new[rotated_mask > 0].min())}
    (output / "quality.json").write_text(json.dumps(quality, indent=2, ensure_ascii=False), encoding="utf-8")
    window.hide()
    window.tool_manager.patch_preview.close()
    window.tool_manager.healing_preview.close()
    app.removeEventFilter(window)
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    main()
