"""AutoAugment page for selected-map YOLO dataset generation.

Author: Mingyu Jang
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import QUrl, Qt, QSize
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSlider,
    QWidget,
)

from service.augmentation_service import AutoYoloAugmentOptions, AugmentationApi
from core.image_io import read_image
from core.qt_image import bgr_to_qpixmap

AUTOAUGMENT_UI_PATH = Path(__file__).with_name("autoaugment.ui")
ICON_ROOT = Path(__file__).parent.parent / "assets" / "icons"

class _SliderSpinAdapter:
    """Expose a Designer slider/spin pair through the existing value API."""

    def __init__(self, slider: QSlider, spin: QSpinBox, minimum: int, maximum: int, value: int):
        """Synchronize an existing slider and spin box."""
        self.slider = slider
        self.spin = spin
        self.slider.setRange(minimum, maximum)
        self.spin.setRange(minimum, maximum)
        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self.slider.setValue)
        self.set_value(value)

    @property
    def valueChanged(self):
        """Expose the spin box value-changed signal."""
        return self.spin.valueChanged

    def value(self) -> int:
        """Return the synchronized integer value."""
        return int(self.spin.value())

    def set_value(self, value: int) -> None:
        """Set the synchronized integer value."""
        self.spin.setValue(int(value))


class _NumericComboAdapter:
    """Treat a Designer combo box as an integer setting."""

    def __init__(self, combo: QComboBox, minimum: int, maximum: int, value: int):
        """Populate a combo box with an inclusive integer range."""
        self.combo = combo
        self.combo.clear()
        self.combo.addItems(str(number) for number in range(minimum, maximum + 1))
        self.combo.setCurrentText(str(value))

    @property
    def valueChanged(self):
        """Expose the combo box index-changed signal."""
        return self.combo.currentIndexChanged

    def value(self) -> int:
        """Return the selected integer or zero for invalid text."""
        try:
            return int(self.combo.currentText())
        except ValueError:
            return 0


class _LineRangeAdapter:
    """Read a minimum/maximum pair from two Designer line edits."""

    def __init__(self, low: QLineEdit, high: QLineEdit):
        """Store the two line edits representing a numeric range."""
        self.low = low
        self.high = high

    def values(self) -> tuple[int, int]:
        """Return normalized integer bounds, replacing invalid text with zero."""
        try:
            first = int(self.low.text())
        except ValueError:
            first = 0
        try:
            second = int(self.high.text())
        except ValueError:
            second = 0
        return min(first, second), max(first, second)


class _RandomEnabledAdapter:
    """Use Random × zero as disabled when the Designer form has no checkbox."""

    def __init__(self, value_control: _SliderSpinAdapter):
        """Treat a positive random multiplier as an enabled state."""
        self.value_control = value_control
        self.stateChanged = value_control.valueChanged

    def isChecked(self) -> bool:
        """Return whether random augmentation is enabled."""
        return self.value_control.value() > 0


class _WidgetGroup:
    """Apply visibility or enabled state to an existing group of widgets."""

    def __init__(self, widgets):
        """Store widgets controlled as one logical group."""
        self.widgets = tuple(widgets)

    def setEnabled(self, enabled: bool) -> None:
        """Enable or disable every grouped widget."""
        for widget in self.widgets:
            widget.setEnabled(enabled)

    def hide(self) -> None:
        """Hide every grouped widget."""
        for widget in self.widgets:
            widget.hide()

    def show(self) -> None:
        """Show every grouped widget."""
        for widget in self.widgets:
            widget.show()


class _BalanceBarsAdapter:
    """Render class-balance items into Designer labels and progress bars."""

    def __init__(self, labels, bars, show_expected: bool = True):
        """Bind class labels to their corresponding progress bars."""
        self.labels = tuple(labels)
        self.bars = tuple(bars)
        self.show_expected = show_expected

    def set_items(self, items: list[ClassBalanceItem]) -> None:
        """Render class-balance items into the bound rows."""
        maximum = max((item.expected_count for item in items), default=1)
        for index, (label, bar) in enumerate(zip(self.labels, self.bars)):
            if index >= len(items):
                label.setText("")
                bar.setRange(0, 1)
                bar.setValue(0)
                bar.setFormat("")
                continue
            item = items[index]
            label.setText(item.class_name)
            bar.setRange(0, maximum)
            bar.setValue(item.current_count)
            if self.show_expected:
                bar.setFormat(f"{item.current_count} → {item.expected_count}")
            else:
                bar.setFormat(str(item.current_count))

    def reset_values(self, class_names: list[str], maximum: int = 1) -> None:
        """Keep result rows visible while clearing values and resetting bars."""
        bar_maximum = max(1, int(maximum))
        for index, (label, bar) in enumerate(zip(self.labels, self.bars)):
            label.setText(class_names[index] if index < len(class_names) else "")
            bar.setRange(0, bar_maximum)
            bar.setValue(0)
            bar.setFormat("")


class _PlanOutputAdapter:
    """Populate the Designer planned-output grid from the existing summary text."""

    def __init__(self, base_label, train_label, val_label, test_label):
        """Bind labels used by the planned-output summary."""
        self.base_label = base_label
        self.train_label = train_label
        self.val_label = val_label
        self.test_label = test_label

    def setText(self, text: str) -> None:
        """Parse legacy summary text and update the four count labels."""
        import re

        match = re.search(r"Base (\d+).*Train (\d+) / Val (\d+) / Test (\d+)", text)
        if match is None:
            return
        base, train, val, test = match.groups()
        self.base_label.setText(base)
        self.train_label.setText(train)
        self.val_label.setText(val)
        self.test_label.setText(test)

    def set_counts(self, base: int, train: int, val: int, test: int) -> None:
        """Display final planned output counts after augmentation factors."""
        self.base_label.setText(str(int(base)))
        self.train_label.setText(str(int(train)))
        self.val_label.setText(str(int(val)))
        self.test_label.setText(str(int(test)))


@dataclass(frozen=True)
class ClassBalanceItem:
    """Class count item displayed in the AutoAugment balance view."""

    class_name: str
    current_count: int
    expected_count: int


class SliderSpinBox(QWidget):
    """Compact horizontal slider and spinbox pair for integer settings."""

    def __init__(self, minimum: int, maximum: int, value: int, parent=None):
        """Create a synchronized slider and spin box."""
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.spin = QSpinBox(self)
        self.slider.setRange(minimum, maximum)
        self.spin.setRange(minimum, maximum)
        self.slider.setValue(value)
        self.spin.setValue(value)
        self.spin.setFixedWidth(92)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin)
        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self.slider.setValue)

    def value(self) -> int:
        """Return the current integer value."""
        return int(self.spin.value())

    def set_value(self, value: int) -> None:
        """Set both the slider and spinbox value."""
        self.spin.setValue(int(value))

    @property
    def valueChanged(self):
        """Expose the spin box value-changed signal."""
        return self.spin.valueChanged


class RangeEdit(QWidget):
    """Two spin boxes used for min and max integer ranges."""

    def __init__(self, minimum: int, maximum: int, low: int, high: int, parent=None):
        """Create a compact pair of integer spin boxes."""
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.low = QSpinBox(self)
        self.high = QSpinBox(self)
        self.low.setRange(minimum, maximum)
        self.high.setRange(minimum, maximum)
        self.low.setValue(low)
        self.high.setValue(high)
        self.low.setFixedWidth(92)
        self.high.setFixedWidth(92)
        layout.addWidget(self.low)
        layout.addWidget(QLabel("~", self))
        layout.addWidget(self.high)
        layout.addStretch(1)

    def values(self) -> tuple[int, int]:
        """Return the normalized low and high values."""
        first = int(self.low.value())
        second = int(self.high.value())
        return min(first, second), max(first, second)


class ClassBalanceBarWidget(QWidget):
    """Draw current and expected class counts for AutoAugment planning."""

    def __init__(self, parent=None, accent: str = "#3971FF"):
        """Create an empty class-balance chart."""
        super().__init__(parent)
        self.items: list[ClassBalanceItem] = []
        self.accent = QColor(accent)
        self.setMinimumHeight(150)

    def set_items(self, items: list[ClassBalanceItem]) -> None:
        """Update the balance data and repaint the widget."""
        self.items = list(items)
        self.setMinimumHeight(max(110, min(220, 28 * len(self.items) + 18)))
        self.updateGeometry()
        self.update()

    def paintEvent(self, event):
        """Paint current and expected class counts."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text_color = self.palette().text().color()
        base_color = QColor(self.accent)
        added_color = QColor(self.accent).lighter(145)
        back_color = self.palette().base().color()
        max_count = max((item.expected_count for item in self.items), default=1)
        left = 116
        right = 78
        bar_height = 10
        row_height = 26
        for row, item in enumerate(self.items):
            y = 12 + row * row_height
            painter.setPen(text_color)
            painter.drawText(4, y + 15, item.class_name[:16])
            bar_x = left
            bar_w = max(1, self.width() - left - right)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(back_color.darker(115))
            painter.drawRoundedRect(bar_x, y + 3, bar_w, bar_height, 4, 4)
            current_w = int(bar_w * item.current_count / max_count)
            expected_w = int(bar_w * item.expected_count / max_count)
            painter.setBrush(base_color)
            painter.drawRoundedRect(bar_x, y + 3, current_w, bar_height, 4, 4)
            if expected_w > current_w:
                painter.setBrush(added_color)
                painter.drawRoundedRect(bar_x + current_w, y + 3, expected_w - current_w, bar_height, 4, 4)
            painter.setPen(text_color)
            painter.drawText(bar_x + bar_w + 8, y + 15, f"{item.current_count} → {item.expected_count}")
        painter.end()


class AugmentationPage(QDialog):
    """Modeless AutoAugment dialog for Poisson-based YOLO dataset generation."""

    def __init__(self, augmentation_api: AugmentationApi, parent=None):
        """Initialize the modeless Designer-backed AutoAugment dialog."""
        super().__init__(parent)
        self._main_window = parent
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.augmentation_api = augmentation_api
        self._class_catalog: list[tuple[int, str]] = []
        self._target_image_count = 0
        self._folder_count = 1
        self._class_counts: dict[int, int] = {}
        self._project_root: Path | None = None
        self._preview_source_pixmap = QPixmap()
        self._result_source_pixmap = QPixmap()
        self._result_sample_pixmaps: list[QPixmap] = []
        self._result_output_root: Path | None = None
        self._setup_ui()
        self._connect_signals()
        self._update_stage_enabled()

    def _setup_ui(self) -> None:
        """Load the Qt Designer form and bind it to the AutoAugment behavior."""
        uic.loadUi(str(AUTOAUGMENT_UI_PATH), self)
        self._bind_designer_widgets()
        return

    def _bind_designer_widgets(self) -> None:
        """Bind semantic Designer widgets to the adapters used by AutoAugment."""
        self.generate_slider = _SliderSpinAdapter(
            self.sample_count_slider, self.sample_count_spin, 0, 5000, 300
        )
        self.same_class_spin = self.same_class_max_spin
        self.same_class_spin.setRange(1, 100)
        self.same_class_spin.setValue(1)
        self.poisson_mode_combo = self.blend_mode_combo
        self.poisson_mode_combo.clear()
        self.poisson_mode_combo.addItems(
            ["Boundary Mixed", "Mixed", "Normal", "Detail Preserve"]
        )
        self.poisson_balance_check = QCheckBox(self)
        self.poisson_balance_check.setChecked(True)
        self.poisson_balance_check.hide()
        self.poisson_body = _WidgetGroup(
            (
                self.sample_count_slider,
                self.sample_count_spin,
                self.same_class_max_spin,
                self.blend_mode_combo,
            )
        )

        self.flip_check = self.horizontal_flip_check
        self.rotation_edit = self.rotation_angles_edit
        self.rotation_body = self.rotation_edit
        self.random_multiplier_slider = _SliderSpinAdapter(
            self.random_count_slider, self.random_count_spin, 0, 100, 1
        )
        self.random_check = _RandomEnabledAdapter(self.random_multiplier_slider)
        self.jitter_x_range = _LineRangeAdapter(
            self.jitter_x_min_edit, self.jitter_x_max_edit
        )
        self.jitter_y_range = _LineRangeAdapter(
            self.jitter_y_min_edit, self.jitter_y_max_edit
        )
        self.brightness_range = _LineRangeAdapter(
            self.brightness_min_edit, self.brightness_max_edit
        )
        self.contrast_range = _LineRangeAdapter(
            self.contrast_min_edit, self.contrast_max_edit
        )
        self.random_body = _WidgetGroup(
            (
                self.jitter_x_min_edit,
                self.jitter_x_max_edit,
                self.jitter_y_min_edit,
                self.jitter_y_max_edit,
                self.brightness_min_edit,
                self.brightness_max_edit,
                self.contrast_min_edit,
                self.contrast_max_edit,
            )
        )

        self.defect_root_edit = self.defect_pool_path_edit
        self.output_root_edit = self.output_path_edit
        self.defect_root_edit.clear()
        self.output_root_edit.clear()
        self.browse_defect_button = self.browse_defect_pool_button
        self.format_combo = self.output_format_combo
        self.train_spin = self.train_ratio_spin
        self.val_spin = _NumericComboAdapter(self.validation_ratio_combo, 0, 100, 10)
        self.test_spin = _NumericComboAdapter(self.test_ratio_combo, 0, 100, 10)
        self.train_spin.setRange(0, 100)
        self.train_spin.setValue(80)

        self.balance_widget = _BalanceBarsAdapter(
            (
                self.scratch_balance_label,
                self.crack_balance_label,
                self.dent_balance_label,
                self.contamination_balance_label,
            ),
            (
                self.scratch_balance_bar,
                self.crack_balance_bar,
                self.dent_balance_bar,
                self.contamination_balance_bar,
            ),
        )
        self.planned_base_label.setText("Base")
        self.planned_train_label.setText("Train")
        self.planned_validation_label.setText("Val")
        self.planned_test_label.setText("Test")
        self.expected_value = _PlanOutputAdapter(
            self.planned_base_value,
            self.planned_train_value,
            self.planned_validation_value,
            self.planned_test_value,
        )

        self.result_sample_labels = (
            self.result_sample_one_label,
            self.result_sample_two_label,
            self.result_sample_three_label,
            self.result_sample_remainder_label,
        )
        self.result_image_label = self.result_sample_one_label
        self.result_poisson_value = self.result_generated_value
        self.result_val_value = self.result_validation_value
        for sample_label in self.result_sample_labels:
            sample_label.clear()
            self._set_visual_role(sample_label, "samplePreview")
        self.result_output_value = QLabel(self)
        self.result_output_value.hide()
        self.result_distribution_widget = _BalanceBarsAdapter(
            (
                self.distribution_scratch_label,
                self.distribution_crack_label,
                self.distribution_dent_label,
                self.distribution_contamination_label,
            ),
            (
                self.distribution_scratch_bar,
                self.distribution_crack_bar,
                self.distribution_dent_bar,
                self.distribution_contamination_bar,
            ),
            show_expected=False,
        )
        self.results_content = _WidgetGroup(
            child
            for child in self.results_frame.findChildren(QWidget)
            if child is not self.results_title_label
        )
        self.results_content.show()

        self.progress_panel = self.progress_frame
        self.progress_bar = self.generation_progress_bar
        self.run_button = self.generate_button
        self.progress_panel.show()
        self.progress_status_label.setText("Ready")
        self.progress_bar.setValue(0)
        self.cancel_button.setEnabled(False)

        self.mapsets_value = QLabel(self)
        self.labeled_value = QLabel(self)
        self.total_labels_value = QLabel(self)
        self.target_images_value = QLabel(self)
        self.existing_masks_value = QLabel(self)
        self.missing_masks_value = QLabel(self)
        for label in (
            self.mapsets_value,
            self.labeled_value,
            self.total_labels_value,
            self.target_images_value,
            self.existing_masks_value,
            self.missing_masks_value,
        ):
            label.hide()

        self._preview_source_pixmap = QPixmap()
        self._result_source_pixmap = QPixmap()
        self._result_sample_pixmaps = []
        self._result_output_root = None
        self._reset_result_values()
        self._prepare_autoaugment_visual_state()
        self.apply_theme(getattr(self._main_window, "current_theme", "dark"))
    def _connect_signals(self) -> None:
        """Connect semantic Designer controls to AutoAugment behavior."""
        self.details_button.clicked.connect(self._show_details)
        self.target_map_combo.currentTextChanged.connect(self.refresh_project_data)
        self.generate_slider.valueChanged.connect(self._refresh_expected_counts)
        self.random_multiplier_slider.valueChanged.connect(self._refresh_expected_counts)
        self.poisson_balance_check.stateChanged.connect(self._refresh_expected_counts)
        self.poisson_balance_check.stateChanged.connect(self._update_stage_enabled)
        self.flip_check.stateChanged.connect(self._refresh_expected_counts)
        self.flip_check.stateChanged.connect(self._update_stage_enabled)
        self.rotation_check.stateChanged.connect(self._refresh_expected_counts)
        self.rotation_check.stateChanged.connect(self._update_stage_enabled)
        self.random_check.stateChanged.connect(self._refresh_expected_counts)
        self.random_check.stateChanged.connect(self._update_stage_enabled)
        self.rotation_edit.textChanged.connect(self._refresh_expected_counts)
        self.train_spin.valueChanged.connect(self._refresh_expected_counts)
        self.val_spin.valueChanged.connect(self._refresh_expected_counts)
        self.test_spin.valueChanged.connect(self._refresh_expected_counts)
        self.run_button.clicked.connect(self.run_augmentation)
        self.cancel_button.clicked.connect(self.cancel_augmentation)
        self.back_button.clicked.connect(self._go_back)
        self.browse_output_button.clicked.connect(self._choose_output_root)
        self.browse_defect_button.clicked.connect(self._choose_defect_root)
        self.open_output_button.clicked.connect(self._open_result_output)

    def set_project_defaults(self, project_root: Path) -> None:
        """Populate paths and refresh summary values for the active project."""
        self._project_root = Path(project_root)
        if not self.defect_root_edit.text().strip():
            self.defect_root_edit.setText(str(self._project_root / "exports" / "defects"))
        if not self.output_root_edit.text().strip():
            self.output_root_edit.setText(str(self._project_root / "exports" / "yolo_autoaugment"))
        self.refresh_project_data()

    def refresh_project_data(self) -> None:
        """Refresh target maps, mask counts, and class balance from the current project."""
        window = self._main_window
        project = getattr(window, "project", None)
        if project is None:
            return
        map_keys = self.augmentation_api.project_map_keys(project.mapsets)
        current = self.target_map_combo.currentText()
        self.target_map_combo.blockSignals(True)
        self.target_map_combo.clear()
        self.target_map_combo.addItems(map_keys)
        if current in map_keys:
            self.target_map_combo.setCurrentText(current)
        self.target_map_combo.blockSignals(False)
        catalog = getattr(window, "label_catalog", lambda: [])()
        self._class_catalog = list(catalog)
        target_map = self.target_map_combo.currentText() or (map_keys[0] if map_keys else "")
        summary = self.augmentation_api.auto_yolo_summary(project, target_map)
        class_counts = {int(key): int(value) for key, value in summary.get("class_counts", {}).items()}
        for class_id, _name in self._class_catalog:
            class_counts.setdefault(int(class_id), 0)
        self._class_counts = class_counts
        labeled_count = sum(1 for mapset in project.mapsets if mapset.label_path is not None or (mapset.folder / f"{mapset.name}.txt").is_file())
        self.mapsets_value.setText(str(len(project.mapsets)))
        self.labeled_value.setText(str(labeled_count))
        self.total_labels_value.setText(str(sum(class_counts.values())))
        self._target_image_count = int(summary.get("target_images", 0))
        self._folder_count = max(1, int(summary.get("folder_count", 1)))
        self.target_images_value.setText(str(self._target_image_count))
        self.existing_masks_value.setText(str(summary.get("existing_masks", 0)))
        self.missing_masks_value.setText(str(summary.get("missing_masks", 0)))
        self._refresh_target_preview(project, target_map)
        default_generate = self._default_generate_count(class_counts)
        self.generate_slider.set_value(default_generate)
        self._refresh_expected_counts()
        self._reset_result_values()

    def build_options(self) -> AutoYoloAugmentOptions:
        """Build selected-map AutoAugment options from the UI state."""
        output = self.output_root_edit.text().strip() or "exports/yolo_autoaugment"
        defect = self.defect_root_edit.text().strip()
        train = self.train_spin.value() / 100.0
        val = self.val_spin.value() / 100.0
        test = self.test_spin.value() / 100.0
        total = max(1e-6, train + val + test)
        class_names = [name for _class_id, name in sorted(self._class_catalog, key=lambda item: item[0])]
        return AutoYoloAugmentOptions(
            output_root=Path(output),
            defect_root=Path(defect) if defect else None,
            target_map_key=self.target_map_combo.currentText(),
            class_names=class_names,
            generate_samples=self.generate_slider.value(),
            max_same_class_per_image=self.same_class_spin.value(),
            poisson_mode=self.poisson_mode_combo.currentText(),
            include_original=True,
            enable_poisson=self.poisson_balance_check.isChecked(),
            enable_flip=self.flip_check.isChecked(),
            enable_rotation=self.rotation_check.isChecked(),
            enable_random=self.random_check.isChecked(),
            random_multiplier=self.random_multiplier_slider.value(),
            apply_extra_augment=True,
            rotation_angles=self._rotation_angles(),
            jitter_x_min=self.jitter_x_range.values()[0],
            jitter_x_max=self.jitter_x_range.values()[1],
            jitter_y_min=self.jitter_y_range.values()[0],
            jitter_y_max=self.jitter_y_range.values()[1],
            brightness_min=self.brightness_range.values()[0],
            brightness_max=self.brightness_range.values()[1],
            contrast_min=self.contrast_range.values()[0],
            contrast_max=self.contrast_range.values()[1],
            image_size=self.image_size_spin.value(),
            train_ratio=train / total,
            val_ratio=val / total,
            test_ratio=test / total,
            seed=self.seed_spin.value(),
        )

    def run_augmentation(self) -> None:
        """Start selected-map AutoAugment through the main window task manager."""
        window = self._main_window
        if hasattr(window, "start_auto_augmentation"):
            window.start_auto_augmentation(self.build_options())

    def cancel_augmentation(self) -> None:
        """Request cancellation for the running AutoAugment task."""
        window = self._main_window
        if hasattr(window, "cancel_auto_augmentation"):
            window.cancel_auto_augmentation()

    def set_autoaugment_running(self, running: bool) -> None:
        """Reflect the shared AutoAugment task state in the page controls."""
        self.run_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.run_button.setText("Running..." if running else "Generate")

    def _reset_result_values(self) -> None:
        """Keep the Results panel visible while clearing only generated values."""
        for value_label in (
            self.result_images_value,
            self.result_annotations_value,
            self.result_poisson_value,
            self.result_train_value,
            self.result_val_value,
            self.result_test_value,
            self.result_failed_value,
            self.result_skipped_value,
        ):
            value_label.setText("")
        for sample_label in self.result_sample_labels:
            sample_label.clear()
        self.result_output_value.setText("")
        self._result_source_pixmap = QPixmap()
        self._result_sample_pixmaps = []
        self._result_output_root = None

        class_names = [
            name for _class_id, name in sorted(self._class_catalog, key=lambda item: item[0])
        ]
        if not class_names:
            class_names = [f"class {class_id}" for class_id in sorted(self._class_counts)]
        self.result_distribution_widget.reset_values(
            class_names,
            maximum=max(self._class_counts.values(), default=1),
        )

    def begin_autoaugment_progress(self, output_root: Path) -> None:
        """Show and reset the file-operation style progress panel."""
        self.progress_panel.show()
        self.progress_status_label.setText(f"Queued · Output: {output_root}")
        self.progress_bar.setValue(0)
        self.results_content.show()
        self.set_autoaugment_running(True)

    def update_autoaugment_progress(self, value: int, message: str) -> None:
        """Update overall progress and the current pipeline stage."""
        stage, separator, detail = str(message).partition("|")
        self.progress_panel.show()
        self.progress_bar.setValue(max(0, min(100, int(value))))
        stage_text = stage.strip() or "Working"
        detail_text = detail.strip() if separator else ""
        self.progress_status_label.setText(
            f"{stage_text} · {detail_text}" if detail_text else stage_text
        )

    def complete_autoaugment_progress(self, result: dict) -> None:
        """Populate the Results workspace and leave a concise completion summary."""
        self.progress_panel.show()
        self.progress_bar.setValue(100)
        self.progress_status_label.setText(
            f"Complete · {result.get('images', 0)} images written to {result.get('output_root', '')}"
        )
        self.result_images_value.setText(str(result.get("images", 0)))
        self.result_annotations_value.setText(str(result.get("annotations", 0)))
        self.result_poisson_value.setText(str(result.get("poisson_samples", 0)))
        split_images = result.get("split_images", {})
        self.result_train_value.setText(str(split_images.get("train", 0)))
        self.result_val_value.setText(str(split_images.get("val", 0)))
        self.result_test_value.setText(str(split_images.get("test", 0)))
        self.result_failed_value.setText(str(result.get("failed_or_skipped", 0)))
        self.result_skipped_value.setText("0")
        catalog = dict(self._class_catalog)
        distribution = {
            int(class_id): int(count)
            for class_id, count in result.get("class_distribution", {}).items()
        }
        for class_id, _name in self._class_catalog:
            distribution.setdefault(int(class_id), 0)
        distribution_items = [
            ClassBalanceItem(
                catalog.get(int(class_id), f"class {class_id}"),
                int(count),
                int(count),
            )
            for class_id, count in sorted(distribution.items(), key=lambda item: int(item[0]))
        ]
        self.result_distribution_widget.set_items(distribution_items)
        self.result_output_value.setText(str(result.get("output_root", "")))
        self._result_output_root = Path(result["output_root"]) if result.get("output_root") else None
        sample_paths = list(result.get("sample_images", []))
        if not sample_paths and result.get("preview_image"):
            sample_paths = [result["preview_image"]]
        self._set_result_sample_images(sample_paths, int(result.get("images", 0)))
        self.results_content.show()
        self.set_autoaugment_running(False)

    def fail_autoaugment_progress(self, message: str) -> None:
        """Display a controlled failure state without blocking the GUI thread."""
        self.progress_panel.show()
        self.progress_status_label.setText(f"Failed · {message}")
        self.set_autoaugment_running(False)

    def cancel_autoaugment_progress(self) -> None:
        """Display the final state of a cooperatively cancelled run."""
        self.progress_panel.show()
        self.progress_status_label.setText("Cancelled · AutoAugment was cancelled by the user.")
        self.set_autoaugment_running(False)

    def show_autoaugment_cancelling(self) -> None:
        """Show that cancellation was requested while the worker exits safely."""
        self.progress_panel.show()
        self.progress_status_label.setText(
            "Cancelling · Finishing the current operation and cleaning up…"
        )
        self.cancel_button.setEnabled(False)

    def _show_details(self) -> None:
        """Show dataset and ROI summary without adding more permanent UI."""
        QMessageBox.information(
            self,
            "AutoAugment Details",
            f"MapSets: {self.mapsets_value.text()}\n"
            f"Labeled: {self.labeled_value.text()}\n"
            f"Labels: {self.total_labels_value.text()}\n"
            f"Target images: {self.target_images_value.text()}\n"
            f"ROI existing: {self.existing_masks_value.text()}\n"
            f"ROI missing: {self.missing_masks_value.text()}",
        )

    def _refresh_target_preview(self, project, target_map: str) -> None:
        """Load the first available target-map image into the Preview workspace."""
        for mapset in project.mapsets:
            for map_key, image_path in mapset.maps:
                if map_key != target_map:
                    continue
                image = read_image(image_path)
                if image is not None:
                    self.set_preview_image(bgr_to_qpixmap(image))
                    return
        self.preview_image_label.clear()
        self.preview_image_label.setText("No target preview available")

    def set_preview_image(self, pixmap: QPixmap) -> None:
        """Display an AutoAugment preview in the shared Preview workspace."""
        self._preview_source_pixmap = QPixmap(pixmap)
        self._set_scaled_pixmap(self.preview_image_label, self._preview_source_pixmap)

    def resizeEvent(self, event) -> None:
        """Rescale preview images when the AutoAugment workspace changes size."""
        super().resizeEvent(event)
        self._refresh_scaled_previews()

    def _refresh_scaled_previews(self) -> None:
        """Fit stored preview sources into their current panels."""
        if not self._preview_source_pixmap.isNull():
            self._set_scaled_pixmap(self.preview_image_label, self._preview_source_pixmap)
        for label, pixmap in zip(self.result_sample_labels, self._result_sample_pixmaps):
            if not pixmap.isNull():
                self._set_scaled_pixmap(label, pixmap)

    def _set_result_sample_images(self, image_paths: list[str], total_images: int) -> None:
        """Display up to three generated examples and a remainder count."""
        self._result_sample_pixmaps = []
        for sample_label in self.result_sample_labels:
            sample_label.clear()

        loaded_count = 0
        for label, image_path in zip(self.result_sample_labels[:3], image_paths[:3]):
            image = read_image(image_path)
            if image is None:
                continue
            pixmap = bgr_to_qpixmap(image)
            self._result_sample_pixmaps.append(pixmap)
            self._set_scaled_pixmap(label, pixmap)
            loaded_count += 1

        self._result_source_pixmap = (
            QPixmap(self._result_sample_pixmaps[0]) if self._result_sample_pixmaps else QPixmap()
        )
        remaining = max(0, int(total_images) - loaded_count)
        if remaining:
            self.result_sample_labels[3].setText(f"+{remaining:,}")

    @staticmethod
    def _set_scaled_pixmap(label: QLabel, pixmap: QPixmap) -> None:
        """Fit a pixmap into a preview label while preserving aspect ratio."""
        if pixmap.isNull():
            return
        target = label.size()
        if target.width() <= 1 or target.height() <= 1:
            label.setPixmap(pixmap)
            return
        label.setPixmap(
            pixmap.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _open_result_output(self) -> None:
        """Open the generated dataset folder with the operating system file browser."""
        if self._result_output_root is not None and self._result_output_root.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._result_output_root)))

    def apply_theme(self, theme: str) -> None:
        """Refresh semantic widget roles after the application theme changes."""
        del theme
        for widget in self.findChildren(QWidget):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.update()

    def _update_stage_enabled(self) -> None:
        """Enable or disable stage controls based on each stage checkbox."""
        self.poisson_body.setEnabled(self.poisson_balance_check.isChecked())
        self.rotation_body.setEnabled(self.rotation_check.isChecked())
        self.random_body.setEnabled(self.random_check.isChecked())

    def _refresh_expected_counts(self) -> None:
        """Refresh class balance and projected output counts from current settings."""
        original = self._target_image_count
        poisson = self.generate_slider.value() if self.poisson_balance_check.isChecked() and original else 0
        base_count = original + poisson
        train_count, val_count, test_count = self._estimated_split_counts(base_count)
        flip_factor = 2 if self.flip_check.isChecked() else 1
        rotation_factor = max(1, len(self._rotation_angles())) if self.rotation_check.isChecked() else 1
        random_factor = max(1, self.random_multiplier_slider.value()) if self.random_check.isChecked() else 1
        train_images = train_count * flip_factor * rotation_factor * random_factor
        val_images = val_count * flip_factor * rotation_factor
        test_images = test_count
        output_images = train_images + val_images + test_images

        expected = self._projected_counts(dict(self._class_counts), poisson)
        items = []
        catalog = dict(self._class_catalog)
        for class_id in sorted(expected):
            name = catalog.get(class_id, f"class {class_id}")
            items.append(ClassBalanceItem(name, self._class_counts.get(class_id, 0), expected.get(class_id, 0)))
        self.balance_widget.set_items(items)
        if hasattr(self.expected_value, "set_counts"):
            self.expected_value.set_counts(base_count, train_images, val_images, test_images)
        else:
            self.expected_value.setText(
                f"Policy B: Base {base_count} ({original} original + "
                f"{poisson} poisson total across {self._folder_count} folder groups) → Shuffle/Split "
                f"Train {train_count} / Val {val_count} / Test {test_count}; "
                f"Train × Flip {flip_factor} × Rotation {rotation_factor} × Random {random_factor} = {train_images}; "
                f"Val × Flip {flip_factor} × Rotation {rotation_factor} = {val_images}; "
                f"Test base only = {test_images}; Output images {output_images}"
            )

    def _estimated_split_counts(self, total: int) -> tuple[int, int, int]:
        """Estimate split counts using the same floor-based policy as the API."""
        train = self.train_spin.value() / 100.0
        val = self.val_spin.value() / 100.0
        test = self.test_spin.value() / 100.0
        ratio_total = max(1e-6, train + val + test)
        train_ratio = train / ratio_total
        val_ratio = val / ratio_total
        test_ratio = test / ratio_total
        train_count = min(total, max(0, int(total * train_ratio)))
        remaining = total - train_count
        val_count = min(remaining, max(0, int(total * val_ratio)))
        test_count = max(0, total - train_count - val_count) if test_ratio > 0 else 0
        if test_ratio <= 0:
            val_count += max(0, total - train_count - val_count)
        return train_count, val_count, test_count

    def _default_generate_count(self, counts: dict[int, int]) -> int:
        """Return the samples needed to raise every class to the largest class."""
        if not counts:
            return 0
        target = max(counts.values())
        return sum(max(0, target - value) for value in counts.values())

    def _projected_counts(self, counts: dict[int, int], generate: int) -> dict[int, int]:
        """Distribute generated samples toward the currently smallest classes."""
        if not counts:
            return {}
        result = dict(counts)
        for _index in range(max(0, int(generate))):
            class_id = min(result, key=lambda key: (result[key], key))
            result[class_id] += 1
        return result

    def _rotation_angles(self) -> list[float]:
        """Parse valid comma-separated rotation angles from the editor."""
        values = []
        for text in self.rotation_edit.text().replace(";", ",").split(","):
            text = text.strip()
            if not text:
                continue
            try:
                values.append(float(text))
            except ValueError:
                continue
        return values

    def _choose_output_root(self) -> Path | None:
        """Choose and display the generated dataset output directory."""
        path = QFileDialog.getExistingDirectory(self, "Select YOLO AutoAugment Output Folder", str(Path.cwd()))
        if path:
            self.output_root_edit.setText(path)
            return Path(path)
        return None

    def _choose_defect_root(self) -> Path | None:
        """Choose and display the source Defect Pool directory."""
        path = QFileDialog.getExistingDirectory(self, "Select Defect Pool", str(Path.cwd()))
        if path:
            self.defect_root_edit.setText(path)
            return Path(path)
        return None

    def _go_back(self) -> None:
        """Close the AutoAugment popup without stopping background work."""
        self.close()

    def _set_visual_role(self, widget: QWidget, role: str) -> None:
        """Assign a semantic style role and repolish the widget."""
        widget.setProperty("autoaugmentRole", role)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()


    def _icon_or_empty(self, *names: str) -> QIcon:
        """Return the first available icon or an empty icon."""
        for name in names:
            path = ICON_ROOT / name
            if path.is_file():
                return QIcon(str(path))
        return QIcon()


    def _set_button_icon(self, button: QPushButton, icon: QIcon) -> None:
        """Apply a non-empty icon to a button."""
        if icon.isNull():
            return
        button.setIcon(icon)
        button.setIconSize(QSize(16, 16))


    def _prepare_autoaugment_visual_state(self) -> None:
        """Set initial control state, style roles, and icons before signal binding."""
        self.flip_check.setChecked(True)
        self.rotation_check.setChecked(True)

        outline_buttons = (
            self.details_button,
            self.browse_defect_button,
            self.browse_output_button,
            self.back_button,
            self.open_output_button,
        )

        for button in outline_buttons:
            self._set_visual_role(button, "outlineButton")

        self._set_visual_role(self.cancel_button, "cancelButton")
        self._set_visual_role(self.run_button, "primaryButton")

        # 기존 구조는 그대로 두고 버튼 아이콘만 붙입니다.
        self._set_button_icon(
            self.details_button,
            self._icon_or_empty("info.svg", "details.svg"),
        )
        self._set_button_icon(
            self.browse_defect_button,
            self._icon_or_empty("folder.svg", "folder-open.svg"),
        )
        self._set_button_icon(
            self.browse_output_button,
            self._icon_or_empty("folder.svg", "folder-open.svg"),
        )
        self._set_button_icon(
            self.open_output_button,
            self._icon_or_empty("folder.svg", "folder-open.svg"),
        )
        self._set_button_icon(
            self.run_button,
            self._icon_or_empty("play.svg", "generate.svg"),
        )

        self.progress_bar.setFixedHeight(22)

        for button in (
            self.details_button,
            self.browse_defect_button,
            self.browse_output_button,
            self.back_button,
            self.cancel_button,
            self.open_output_button,
            self.run_button,
        ):
            button.setMinimumHeight(32)
