"""Exercise dialog affordances and editor layout with real Qt widgets."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtCore import QEvent, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtGui import QFontDatabase, QFontInfo, QFontMetrics
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QDialogButtonBox, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox, QScrollArea, QTabWidget

from core.qt_image import bgr_to_qpixmap
from core.mapset import MapSet
from core.image_io import write_png
from tools.toolmanager import ToolMode
from ui.exportdialog import ExportDialog
from ui.label_manager_dialog import LabelManagerDialog
from ui.mainwindow import MainWindow
from ui.map_selection_dialog import MapSelectionDialog
from ui.mapset_selection_dialog import MapSetSelectionDialog
from ui.preprocess_dialog import BatchPreprocessDialog, BrightnessContrastDialog, RotateDialog


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def window(app, tmp_path):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    w = MainWindow()
    w.resize(1280, 800)
    w.show()
    QTest.qWait(20)
    w.canvas.set_image(bgr_to_qpixmap(np.full((120, 160, 3), 100, np.uint8)))
    yield w
    w.tool_manager.patch_preview.close()
    w.tool_manager.healing_preview.close()
    app.removeEventFilter(w)
    w.hide()
    w.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_bundled_ui_font_renders_korean_and_requested_weights(window, app):
    assert QFontInfo(window.annotation_panel.apply_button.font()).family() == "Pretendard"
    metrics = QFontMetrics(app.font())
    assert all(metrics.inFontUcs4(ord(char)) for char in "한글가나다0123456789")
    assert {"Regular", "Medium", "SemiBold"} <= set(QFontDatabase.styles("Pretendard"))


@pytest.mark.parametrize("style", ["Fusion", "windows11"])
def test_panel_titles_and_full_numeric_range_fit_without_horizontal_clipping(window, app, style):
    """Check actual laid-out text bounds, including Windows native widget metrics."""
    previous_style = app.style().objectName()
    try:
        if app.setStyle(style) is None:
            pytest.skip(f"Qt style {style} is unavailable on this platform")
        window.ui_setup.activate_tool(ToolMode.BBOX)
        QTest.qWait(20)
        for dock in (window.dockProject, window.dockProperties, window.dockLogs):
            dock.show()
            QTest.qWait(10)
            header = dock.titleBarWidget()
            label = next(label for label in header.findChildren(QLabel) if label.text() == dock.windowTitle())
            assert label.contentsRect().height() >= label.fontMetrics().height()
            assert label.contentsRect().width() >= label.fontMetrics().horizontalAdvance(label.text())
        for field in window.annotation_panel.fields:
            field.setValue(field.maximum())
            edit = field.findChild(QLineEdit)
            margins = edit.textMargins()
            available = edit.contentsRect().width() - margins.left() - margins.right() - 4
            assert available >= edit.fontMetrics().horizontalAdvance(edit.text())
        scroll = window.propertiesScrollArea
        assert scroll.widget().width() <= scroll.viewport().width()
        for mode in (ToolMode.MOVE, ToolMode.BRUSH, ToolMode.PATCH, ToolMode.BBOX):
            window.ui_setup.activate_tool(mode)
            QTest.qWait(10)
            for label in window.dockOptions.findChildren(QLabel):
                if label.isVisible() and label.text() and not label.wordWrap():
                    assert label.width() >= label.sizeHint().width(), label.text()
                    assert label.height() >= label.sizeHint().height(), label.text()
    finally:
        app.setStyle(previous_style)


def test_editor_reclaims_space_and_keeps_resources_accessible(window, tmp_path):
    assert window.resourceTabs.widget(0) is window.treeProject
    assert window.resourceTabs.widget(1) is window.listMasks
    assert window.dockLogs.isHidden()
    assert "160 × 120" in window.documentSummary.text()
    window.action_toggle_logs.trigger()
    assert window.dockLogs.isVisible() and window.action_toggle_logs.isChecked()
    window.action_toggle_logs.trigger()
    assert window.dockLogs.isHidden()
    window.ui_setup.activate_tool(ToolMode.BBOX)
    assert window.spin_label_class_id.isHidden()
    assert window.annotationClassCombo.isVisible()
    assert window.buttonSelectExportDefect.isVisible()
    assert window.buttonSelectReloadLabels.isVisible()
    assert window.width() == 1280
    hint = window.label_property_subtitle.text()
    window._update_image_property_panel(tmp_path / "긴 이름의 이미지.png", window.canvas.pixmap)
    assert window.label_property_subtitle.text() == hint


def test_window_resize_does_not_reset_user_panel_widths(window):
    window.resizeDocks([window.dockProject], [265], Qt.Orientation.Horizontal)
    QTest.qWait(10)
    width = window.dockProject.width()
    window.resize(1440, 900)
    QTest.qWait(20)
    assert abs(window.dockProject.width() - width) <= 3
    window.ui_setup._reset_panel_layout()
    QTest.qWait(20)
    assert window.dockProject.width() < width


@pytest.mark.parametrize("panel", ["tree", "objects", "button", "combo", "log"])
def test_tool_letters_work_after_focusing_editor_panels(window, panel):
    """Tool selection works outside the canvas, including read-only log text."""
    window._label_catalog = [(0, "균열")]
    window.annotation_panel.refresh()
    window.ui_setup.activate_tool(ToolMode.RECT)
    if panel == "log":
        window.dockLogs.show()
    class_button = next(button for button in window.annotation_panel.findChildren(QPushButton) if button.text() == "클래스 관리")
    target = {"tree": window.treeProject, "objects": window.annotation_panel.objects, "button": class_button, "combo": window.annotationClassCombo, "log": window.log_console}[panel]
    target.setFocus()
    assert QApplication.focusWidget() is target
    QTest.keyClick(target, Qt.Key.Key_B)
    assert window.tool_manager.current_mode == ToolMode.BRUSH
    assert QApplication.focusWidget() is window.canvas


@pytest.mark.parametrize("kind", ["text", "multiline", "number", "editable_combo"])
def test_tool_letters_do_not_interrupt_input_fields(window, kind):
    """Typing and spin-box edits retain their own focus and keyboard behavior."""
    field = {"text": QLineEdit, "multiline": QPlainTextEdit, "number": QSpinBox, "editable_combo": QComboBox}[kind](window)
    if kind == "editable_combo":
        field.setEditable(True)
    field.show()
    field.setFocus()
    QTest.keyClicks(QApplication.focusWidget(), "bmj")
    assert window.tool_manager.current_mode == ToolMode.MOVE
    assert QApplication.focusWidget() is not window.canvas
    if kind == "number":
        QTest.keyClick(field, Qt.Key.Key_Up)
        assert field.value() == 1
    else:
        text = field.currentText() if kind == "editable_combo" else field.toPlainText() if kind == "multiline" else field.text()
        assert text == "bmj"
    field.hide()


def test_panel_shortcut_shift_cycles_once_and_keeps_navigation_local(window):
    window.treeProject.setFocus()
    QTest.keyClick(window.treeProject, Qt.Key.Key_L, Qt.KeyboardModifier.ShiftModifier)
    assert window.tool_manager.current_mode == ToolMode.POLYGON
    QTest.keyClick(window.canvas, Qt.Key.Key_L, Qt.KeyboardModifier.ShiftModifier)
    assert window.tool_manager.current_mode == ToolMode.LASSO
    window.treeProject.setFocus()
    QTest.keyClick(window.treeProject, Qt.Key.Key_Down)
    assert QApplication.focusWidget() is window.treeProject
    QTest.keyClick(window.treeProject, Qt.Key.Key_N)
    assert window.tool_manager.current_mode == ToolMode.BBOX


def test_dialog_and_open_combo_popup_keep_their_keys(window):
    dialog = QDialog(window)
    button = QPushButton("닫기", dialog)
    dialog.show()
    dialog.activateWindow()
    QTest.qWait(10)
    button.setFocus()
    assert QApplication.focusWidget() is button
    QTest.keyClick(button, Qt.Key.Key_B)
    assert window.tool_manager.current_mode == ToolMode.MOVE
    dialog.hide()
    window.activateWindow()
    QTest.qWait(10)
    window._label_catalog = [(0, "균열"), (1, "찍힘")]
    window.annotation_panel.refresh()
    window.ui_setup.activate_tool(ToolMode.RECT)
    combo = window.annotationClassCombo
    combo.showPopup()
    QTest.qWait(10)
    assert QApplication.activePopupWidget() is not None
    QTest.keyClick(combo.view(), Qt.Key.Key_J)
    assert window.tool_manager.current_mode == ToolMode.RECT
    combo.hidePopup()


@pytest.mark.parametrize("load_image", [False, True])
def test_tool_shortcuts_work_on_first_show_without_canvas_click(app, tmp_path, load_image):
    """Send keys to the actual initial focus owner, without selecting a tool first."""
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    w = MainWindow()
    try:
        w.show()
        QTest.qWait(20)
        if load_image:
            w.canvas.set_image(bgr_to_qpixmap(np.full((120, 160, 3), 100, np.uint8)))
        for key, mode in ((Qt.Key.Key_B, ToolMode.BRUSH), (Qt.Key.Key_W, ToolMode.BBOX), (Qt.Key.Key_M, ToolMode.RECT), (Qt.Key.Key_J, ToolMode.HEALING_BRUSH)):
            receiver = app.focusWidget() or w
            QTest.keyClick(receiver, key)
            assert w.tool_manager.current_mode == mode, f"Initial keyboard receiver: {receiver.objectName()} ({type(receiver).__name__})"
    finally:
        w.tool_manager.patch_preview.close()
        w.tool_manager.healing_preview.close()
        app.removeEventFilter(w)
        w.hide()
        w.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("dialog_type", [MapSelectionDialog, MapSetSelectionDialog])
def test_map_selection_explains_empty_selection(window, dialog_type):
    dialog = dialog_type({"albedo": 2, "normal": 1}, window)
    dialog._set_all_checked(False)
    ok = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert not ok.isEnabled() and "선택하세요" in dialog.selection_hint.text()
    dialog._checks["normal"].setChecked(True)
    assert ok.isEnabled() and dialog.selected_map_keys() == {"normal"}
    ok.click()
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_batch_ratio_lock_and_enabled_fields_match_options(window):
    dialog = BatchPreprocessDialog(800, 600, 20, window)
    apply = dialog.buttons.button(QDialogButtonBox.StandardButton.Apply)
    assert not apply.isEnabled() and not dialog.spin_width.isEnabled()
    dialog.check_resize.setChecked(True)
    dialog.spin_width.setValue(400)
    assert dialog.options().height == 300 and apply.isEnabled()
    dialog.spin_height.setValue(150)
    assert dialog.options().width == 200
    dialog.check_keep_ratio.setChecked(False)
    dialog.spin_width.setValue(120)
    assert dialog.options().height == 150
    dialog.check_resize.setChecked(False)
    assert not dialog.options().resize_enabled and not apply.isEnabled()
    dialog.show()
    dialog.resize(520, 540)
    QTest.qWait(10)
    assert dialog.height() == 540
    assert apply.mapTo(dialog, apply.rect().bottomRight()).y() < dialog.height()
    dialog.hide()


@pytest.mark.parametrize("dialog_type,field,value", [(RotateDialog, "slider_angle", 30), (BrightnessContrastDialog, "slider_brightness", 25)])
def test_preview_can_show_original_without_losing_values(window, dialog_type, field, value):
    dialog = dialog_type(window)
    dialog.value_changed.connect(window.update_transform_preview)
    dialog.rejected.connect(window.reset_transform_preview)
    original = window.canvas.pixmap.cacheKey()
    getattr(dialog, field).set_value(value)
    assert not window.canvas.preview_pixmap.isNull()
    dialog.preview_check.setChecked(False)
    assert window.canvas.preview_pixmap.isNull()
    assert getattr(dialog, field).value() == value
    dialog.preview_check.setChecked(True)
    assert not window.canvas.preview_pixmap.isNull()
    dialog.reject()
    assert window.canvas.preview_pixmap.isNull() and window.canvas.pixmap.cacheKey() == original


def test_export_requires_project_and_destination_before_submit(window, tmp_path, monkeypatch):
    dialog = ExportDialog(window)
    ok = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert not ok.isEnabled()
    window.project = SimpleNamespace()
    dialog.output_root_edit.setText(str(tmp_path / "한글 결과"))
    assert ok.isEnabled()
    requests = []
    monkeypatch.setattr(window, "start_yolo_export", requests.append)
    ok.click()
    assert len(requests) == 1 and requests[0].output_root.name == "한글 결과"


def test_class_manager_does_not_offer_saving_an_empty_name(window):
    dialog = LabelManagerDialog(window)
    assert not dialog.save_button.isEnabled()
    dialog.class_name_edit.setText("표면 균열")
    assert dialog.save_button.isEnabled()
    dialog.save_button.click()
    assert window.label_catalog() == [(0, "표면 균열")]
    dialog.new_button.click()
    assert not dialog.delete_button.isEnabled() and not dialog.save_button.isEnabled()


def test_augmentation_empty_state_and_result_share_one_screen(window):
    dialog = window.augmentation_page
    assert dialog.planned_base_value.text() == "0"
    assert not dialog.run_button.isEnabled()
    assert not dialog.findChildren(QTabWidget)
    assert not dialog.preview_group.isHidden() and dialog.result_browser.isHidden()
    dialog._target_image_count = 3
    dialog._refresh_expected_counts()
    assert dialog.run_button.isEnabled()
    dialog.set_autoaugment_running(True)
    assert not dialog.run_button.isEnabled() and dialog.cancel_button.isEnabled()
    dialog.complete_autoaugment_progress({"images": 3, "annotations": 2})
    assert dialog.preview_group.isHidden() and not dialog.result_browser.isHidden()
    assert dialog.result_images_value.text() == "3"
    assert dialog.run_button.isEnabled() and not dialog.cancel_button.isEnabled()


@pytest.mark.parametrize("size", [(1080, 720), (1180, 740), (1280, 780)])
def test_augmentation_refresh_preserves_user_settings_and_running_controls(window, tmp_path, size):
    """Project summaries must not overwrite the setting that was actually executed."""
    image = tmp_path / "albedo.png"
    write_png(image, np.full((32, 32, 3), 100, np.uint8))
    label = tmp_path / "labels.txt"
    label.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    window.project = SimpleNamespace(root_path=tmp_path, mapsets=[MapSet(tmp_path, (("albedo_map", image),), label)])
    window._label_catalog = [(0, "균열"), (5, "찍힘")]
    dialog = window.augmentation_page
    dialog.refresh_project_data()
    dialog.generate_slider.set_value(1)
    options = dialog.build_options()
    assert options.class_ids == [0, 5]
    dialog.refresh_project_data()
    assert dialog.generate_slider.value() == 1
    dialog.set_autoaugment_running(True)
    assert not dialog.output_group.isEnabled() and not dialog.sample_count_spin.isEnabled()
    dialog.complete_autoaugment_progress({"images": 2, "labels": 2, "settings": {"generate_samples": 1}, "class_names": ["균열", "찍힘"]})
    assert dialog.generate_slider.value() == 1
    assert dialog.output_group.isEnabled()
    dialog.generate_slider.set_value(266)
    assert dialog.result_browser.result["settings"]["generate_samples"] == 1
    dialog.resize(*size)
    dialog.show()
    QTest.qWait(30)
    assert (dialog.width(), dialog.height()) == size
    assert not dialog.findChildren(QScrollArea)
    assert not dialog.findChildren(QTabWidget)
    for group in (dialog.poisson_settings_group, dialog.augment_group, dialog.output_group, dialog.result_browser):
        assert group.isVisible()
        assert dialog.rect().contains(group.mapTo(dialog, group.rect().bottomRight()))
    assert dialog.result_browser.mapTo(dialog, dialog.result_browser.rect().topLeft()).x() > dialog.output_group.x() + dialog.output_group.width()
    assert not dialog.result_browser.findChildren(QLineEdit)
    button = dialog.result_browser.open_button
    assert dialog.rect().contains(button.mapTo(dialog, button.rect().bottomRight()))
    dialog.begin_autoaugment_progress(tmp_path)
    assert dialog.preview_group.isVisible() and dialog.result_browser.isHidden()
    assert dialog.progress_bar.isVisible()


def test_yaml_classes_reach_export_and_augmentation_even_when_unused(window, tmp_path):
    """Declared classes must survive loading and an already-open augmentation dialog."""
    folder = tmp_path / "sample"
    folder.mkdir()
    image, label = folder / "albedo.png", folder / "sample.txt"
    write_png(image, np.full((32, 32, 3), 100, np.uint8))
    label.write_text("0 0.5 0.5 0.1 0.1\n1 0.7 0.7 0.1 0.1\n", encoding="utf-8")
    (folder / "data.yaml").write_text("names: [Scratch, Dent, Crack, Stain]\n", encoding="utf-8")
    window.map_sets = [MapSet(folder, (("albedo_map", image),), label)]
    window.project = SimpleNamespace(root_path=tmp_path, mapsets=window.map_sets)
    window.project_root_folder = tmp_path
    window._load_label_catalog(tmp_path)
    assert len(window.label_catalog()) == 4
    dialog = ExportDialog(window)
    assert dialog.build_options().class_names == ["Scratch", "Dent", "Crack", "Stain"]
    page = window.augmentation_page
    page.refresh_project_data()
    assert page._class_counts == {0: 1, 1: 1, 2: 0, 3: 0}
    page._class_catalog = [(0, "stale"), (1, "stale")]
    assert page.build_options().class_names == ["Scratch", "Dent", "Crack", "Stain"]
    window._label_catalog.append((5, "새 결함"))
    window._save_label_catalog()
    assert page._class_catalog[-1] == (5, "새 결함")
    assert page._class_counts[5] == 0
