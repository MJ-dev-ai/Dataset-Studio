"""Render editor and dialog states using synthetic data and isolated settings."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PySide6.QtCore import QEvent, QSettings
from PySide6.QtGui import QFont, QFontDatabase, QPainterPath
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.qt_image import bgr_to_qpixmap
from tools.toolmanager import ToolMode
from ui.augmentationpage import AugmentationPage
from ui.exportdialog import ExportDialog
from ui.label_add_dialog import LabelAddDialog
from ui.label_manager_dialog import LabelManagerDialog
from ui.mainwindow import MainWindow
from ui.map_selection_dialog import MapSelectionDialog
from ui.mapset_selection_dialog import MapSetSelectionDialog
from ui.preprocess_dialog import BatchPreprocessDialog, BrightnessContrastDialog, ResizeDialog, RotateDialog


def main():
    output = Path(__file__).resolve().parent
    stage = sys.argv[1] if len(sys.argv) > 1 else "after"
    app = QApplication([])
    if os.environ.get("DATASET_AUDIT_STYLE"):
        app.setStyle(os.environ["DATASET_AUDIT_STYLE"])
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(output / "qt-settings" / "ui-audit"))
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/malgun.ttf")
    app.setFont(QFont("Malgun Gothic", 9))
    window = MainWindow()
    window.resize(1440, 900)
    window.show()
    QTest.qWait(100)
    window.grab().save(str(output / f"audit-{stage}-empty.png"))
    y, x = np.mgrid[:600, :800]
    gray = np.clip(145 + 14 * np.sin(x / 28) + 4 * np.cos(y / 9), 0, 255).astype(np.uint8)
    window.canvas.set_image(bgr_to_qpixmap(np.repeat(gray[:, :, None], 3, axis=2)))
    window._label_catalog = [(0, "표면 균열"), (1, "찍힘"), (2, "이물질")]
    window.annotation_panel.refresh()
    path = QPainterPath()
    path.addRect(140, 180, 240, 100)
    window.canvas.set_selection(path)
    window.quick_add_annotation()
    for theme, width, height in [("light", 1440, 900), ("dark", 1280, 800)]:
        window.apply_theme(theme, persist=False)
        window.resize(width, height)
        for mode in [ToolMode.BBOX, ToolMode.PATCH, ToolMode.HEALING_BRUSH, ToolMode.MOVE]:
            window.ui_setup.activate_tool(mode)
            QTest.qWait(100)
            window.canvas.fit_to_window()
            window.grab().save(str(output / f"audit-{stage}-{theme}-{mode.value}.png"))
        dialogs = [LabelManagerDialog(window), LabelAddDialog(window.label_catalog(), window), ResizeDialog(800, 600, window), RotateDialog(window), BrightnessContrastDialog(window), BatchPreprocessDialog(800, 600, 24, window), ExportDialog(window), MapSelectionDialog({"albedo": 24, "normal": 24, "curvature": 18}, window), MapSetSelectionDialog({"albedo": 24, "normal": 24}, window), AugmentationPage(window)]
        for dialog in dialogs:
            dialog.show()
            QTest.qWait(50)
            name = type(dialog).__name__
            dialog.grab().save(str(output / f"audit-{stage}-{theme}-{name}.png"))
            print(f"{theme} {name}: {dialog.width()}x{dialog.height()}")
            dialog.hide()
            dialog.deleteLater()
    window.tool_manager.patch_preview.close()
    window.tool_manager.healing_preview.close()
    app.removeEventFilter(window)
    window.hide()
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    main()
