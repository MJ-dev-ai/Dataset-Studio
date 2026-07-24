from pathlib import Path
import re


def test_autoaugment_uses_yolo_worker_and_progress_panel():
    window_text = Path("ui/mainwindow.py").read_text(encoding="utf-8")
    page_text = Path("ui/augmentationpage.py").read_text(encoding="utf-8")
    assert "run_auto_yolo_augmentation" in window_text
    assert 'task_manager.start("AutoAugment"' in window_text
    assert "update_autoaugment_progress" in window_text
    assert "QProgressBar" in page_text
    assert "uic.loadUi(str(AUTOAUGMENT_UI_PATH), self)" in page_text
    assert 'AUTOAUGMENT_UI_PATH = Path(__file__).with_name("autoaugment.ui")' in page_text


def test_autoaugment_is_a_modeless_dialog_not_a_workspace_page():
    page_text = Path("ui/augmentationpage.py").read_text(encoding="utf-8")
    window_text = Path("ui/mainwindow.py").read_text(encoding="utf-8")
    ui_text = Path("ui/autoaugment.ui").read_text(encoding="utf-8")
    assert "class AugmentationPage(QDialog):" in page_text
    assert '<widget class="QDialog" name="autoaugment_dialog">' in ui_text
    assert "stack.addWidget(self.augmentation_page)" not in window_text
    assert "self.augmentation_page.show()" in window_text
    assert "self.augmentation_page.raise_()" in window_text
    assert "self.close()" in page_text
    assert "progress_status_label" in page_text
    assert "progress_title_label" not in page_text
    assert "progress_cancel_button" not in page_text
    assert 'name="progress_frame"' in ui_text
    assert ui_text.index('name="progress_frame"') < ui_text.index('name="generate_button"')


def test_autoaugment_split_controls_use_one_horizontal_row():
    ui_text = Path("ui/autoaugment.ui").read_text(encoding="utf-8")
    for name in ("train_ratio_spin", "validation_ratio_combo", "test_ratio_combo"):
        assert f'name="{name}"' in ui_text
    assert 'name="split_values_layout"' in ui_text


def test_autoaugment_uses_persistent_target_map_and_preview_results_workspace():
    text = Path("ui/augmentationpage.py").read_text(encoding="utf-8")
    ui_text = Path("ui/autoaugment.ui").read_text(encoding="utf-8")
    assert '<string>Details</string>' in ui_text
    assert "self.details_button.clicked.connect(self._show_details)" in text
    assert "QMessageBox.information" in text
    assert 'name="target_map_combo"' in ui_text
    assert 'QTabWidget' not in ui_text
    assert 'name="preview_frame"' in ui_text
    assert 'name="results_frame"' in ui_text
    assert "self.random_check = _RandomEnabledAdapter" in text


def test_autoaugment_result_panel_has_split_and_annotation_statistics():
    page_text = Path("ui/augmentationpage.py").read_text(encoding="utf-8")
    api_text = Path("service/augmentation_service.py").read_text(encoding="utf-8")
    for name in (
        "result_images_value",
        "result_annotations_value",
        "result_train_value",
        "result_val_value",
        "result_test_value",
        "result_failed_value",
    ):
        assert name in page_text
    assert "self.results_content.show()" in page_text
    assert '"split_images"' in api_text
    assert '"annotations"' in api_text
    assert '"preview_image"' in api_text


def test_autoaugment_workspace_follows_theme_with_green_success_accent():
    page_text = Path("ui/augmentationpage.py").read_text(encoding="utf-8")
    window_text = Path("ui/mainwindow.py").read_text(encoding="utf-8")
    theme_text = Path("ui/themes.py").read_text(encoding="utf-8")
    assert "def apply_theme(self, theme: str)" in page_text
    assert "widget.style().polish(widget)" in page_text
    assert '"success_border": "#22A06B"' in theme_text
    assert "QDialog#autoaugment_dialog" in theme_text
    assert "augmentation_page.apply_theme(theme)" in window_text


def test_autoaugment_preview_rescales_with_the_window():
    text = Path("ui/augmentationpage.py").read_text(encoding="utf-8")
    assert "self._preview_source_pixmap" in text
    assert "self._result_source_pixmap" in text
    assert "def resizeEvent" in text
    assert "self._refresh_scaled_previews()" in text


def test_poisson_samples_output_multiplier_ui_text():
    text = Path("ui/augmentationpage.py").read_text(encoding="utf-8")
    assert "Policy B:" in text
    assert "Output images" in text
    assert "_refresh_expected_counts" in text


def test_auto_yolo_generates_variants_after_poisson_resize():
    text = Path("service/augmentation_service.py").read_text(encoding="utf-8")
    assert "_iter_staged_samples" in text
    poisson = text.index("blended = self.poisson_api.poisson_blend")
    resize = text.index("resized, labels = self._resize_for_yolo")
    assert poisson < resize
    load = text.index("sample = self._load_base_record_sample")
    variants = text.index("write_staged(split", load)
    assert load < variants


def test_autoaugment_designer_uses_semantic_object_names():
    """Designer-generated placeholder names must not return to the dialog UI."""
    ui_text = Path("ui/autoaugment.ui").read_text(encoding="utf-8")
    generic_name = re.compile(
        r'name="(?:label|comboBox|pushButton|lineEdit|spinBox|progressBar|horizontalSlider)'
        r'(?:_\d+)?"'
    )

    assert generic_name.search(ui_text) is None
    assert 'name="target_map_combo"' in ui_text
    assert 'name="generation_progress_bar"' in ui_text


def test_designer_files_do_not_own_runtime_stylesheets():
    """Runtime colors and component styling must remain centralized in themes.py."""
    for path in (Path("ui/mainwindow.ui"), Path("ui/autoaugment.ui")):
        assert 'name="styleSheet"' not in path.read_text(encoding="utf-8")
