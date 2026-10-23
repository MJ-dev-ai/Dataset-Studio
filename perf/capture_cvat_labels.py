"""Render the labeling workflow with synthetic pixels and UTF-8 Korean classes."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from PySide6.QtCore import QEvent, QPointF, QSettings
from PySide6.QtGui import QFont, QFontDatabase, QPainterPath
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.qt_image import bgr_to_qpixmap
from tools.toolmanager import ToolMode
from ui.mainwindow import MainWindow


def main():
    output = Path(__file__).resolve().parent
    app = QApplication([])
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(output / "qt-settings" / "cvat"))
    for name in ("segoeui.ttf", "malgun.ttf"):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name))
    app.setFont(QFont("Malgun Gothic", 9))
    window = MainWindow()
    window.resize(1440, 900)
    window.show()
    QTest.qWait(150)
    y, x = np.mgrid[:600, :800]
    grey = np.clip(140 + 12 * np.sin(x / 23) + 5 * np.cos(y / 11), 0, 255).astype(np.uint8)
    sample = np.repeat(grey[:, :, None], 3, axis=2)
    sample[230:235, 180:380] = 35
    sample[320:350, 470:510] = 65
    window.canvas.set_image(bgr_to_qpixmap(sample))
    window.canvas.fit_to_window()
    window._label_catalog = [(2, "표면 균열"), (7, "찍힘"), (12, "이물질")]
    window.annotation_panel.refresh()
    window.ui_setup.activate_tool(ToolMode.BBOX)
    for class_index, rect in [(0, (150, 190, 260, 90)), (1, (440, 290, 100, 90)), (0, (170, 210, 220, 50))]:
        window.annotationClassCombo.setCurrentIndex(class_index)
        path = QPainterPath()
        path.addRect(*rect)
        window.canvas.set_selection(path)
        window.quick_add_annotation()
    window.canvas.set_tool_cursor_pos(QPointF(390, 260))
    QTest.qWait(150)
    window.grab().save(str(output / "cvat-label-draw.png"))
    window.ui_setup.activate_tool(ToolMode.RECT)
    window.canvas.select_annotation(0)
    QTest.qWait(150)
    window.grab().save(str(output / "cvat-label-edit.png"))
    window.tool_manager.patch_preview.close()
    window.tool_manager.healing_preview.close()
    app.removeEventFilter(window)
    window.hide()
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    main()
