"""Transform panels and dialogs for image preprocessing.

Author: TNS AI
"""

from __future__ import annotations

from dataclasses import replace

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
	QButtonGroup,
	QCheckBox,
	QDialog,
	QDialogButtonBox,
	QFormLayout,
	QGroupBox,
	QHBoxLayout,
	QLabel,
	QLineEdit,
	QPushButton,
	QRadioButton,
	QSlider,
	QSpinBox,
	QVBoxLayout,
	QWidget,
)

from service.preprocessing_service import PreprocessOptions


class ValueSlider(QWidget):
	"""Expose one bounded integer value through a slider and spin box."""

	value_changed = pyqtSignal(int)

	def __init__(
		self,
		label: str,
		minimum: int,
		maximum: int,
		value: int = 0,
		suffix: str = "",
		parent=None,
	):
		super().__init__(parent)
		self.label = QLabel(label, self)
		self.slider = QSlider(Qt.Orientation.Horizontal, self)
		self.slider.setRange(minimum, maximum)
		self.slider.setValue(value)
		self.spin = QSpinBox(self)
		self.spin.setRange(minimum, maximum)
		self.spin.setValue(value)
		if suffix:
			self.spin.setSuffix(suffix)

		layout = QHBoxLayout(self)
		layout.setContentsMargins(0, 0, 0, 0)
		layout.addWidget(self.label)
		layout.addWidget(self.slider, 1)
		layout.addWidget(self.spin)

		self.slider.valueChanged.connect(self.spin.setValue)
		self.spin.valueChanged.connect(self.slider.setValue)
		self.spin.valueChanged.connect(self.value_changed.emit)

	def value(self) -> int:
		"""Return the current bounded value."""
		return int(self.spin.value())

	def set_value(self, value: int) -> None:
		"""Set the current value without requiring direct child access."""
		self.spin.setValue(int(value))


class TransformPropertiesPanel(QWidget):
	"""Edit current-image transform options from the Properties dock."""

	preview_requested = pyqtSignal(object)
	apply_requested = pyqtSignal(object)
	reset_requested = pyqtSignal()

	def __init__(self, parent=None):
		super().__init__(parent)
		self._source_width = 1
		self._source_height = 1
		self._updating = False
		self._build_ui()
		self._connect_signals()

	def set_image_info(
		self,
		mapset_name: str,
		map_name: str,
		width: int,
		height: int,
		label_count: int,
		state: str,
	) -> None:
		"""Update displayed image metadata and reset transform fields."""
		self._updating = True
		self._source_width = max(1, int(width))
		self._source_height = max(1, int(height))
		self.label_mapset_value.setText(mapset_name or "-")
		self.label_map_value.setText(map_name or "-")
		self.label_size_value.setText(f"{self._source_width} × {self._source_height} px")
		self.label_labels_value.setText(str(label_count))
		self.label_state_value.setText(state)
		self.spin_width.setValue(self._source_width)
		self.spin_height.setValue(self._source_height)
		self.check_keep_ratio.setChecked(True)
		self.slider_angle.set_value(0)
		self.slider_brightness.set_value(0)
		self.slider_contrast.set_value(0)
		self.check_flip_h.setChecked(False)
		self.check_flip_v.setChecked(False)
		self._updating = False

	def options(self) -> PreprocessOptions:
		"""Return the current transform properties as preprocessing options."""
		width = int(self.spin_width.value())
		height = int(self.spin_height.value())
		return PreprocessOptions(
			resize_enabled=width != self._source_width or height != self._source_height,
			width=width,
			height=height,
			flip_horizontal=self.check_flip_h.isChecked(),
			flip_vertical=self.check_flip_v.isChecked(),
			rotation_degrees=float(self.slider_angle.value()),
			brightness_shift=self.slider_brightness.value(),
			contrast_shift=self.slider_contrast.value(),
		)

	def _build_ui(self) -> None:
		root = QVBoxLayout(self)
		root.setContentsMargins(0, 0, 0, 0)
		root.setSpacing(8)

		image_box = QGroupBox("Image", self)
		image_form = QFormLayout(image_box)
		self.label_mapset_value = QLabel("-", image_box)
		self.label_map_value = QLabel("-", image_box)
		self.label_size_value = QLabel("-", image_box)
		self.label_labels_value = QLabel("0", image_box)
		self.label_state_value = QLabel("Saved", image_box)
		image_form.addRow("MapSet", self.label_mapset_value)
		image_form.addRow("Map", self.label_map_value)
		image_form.addRow("Size", self.label_size_value)
		image_form.addRow("Labels", self.label_labels_value)
		image_form.addRow("State", self.label_state_value)
		root.addWidget(image_box)

		transform_box = QGroupBox("Transform", self)
		transform_layout = QVBoxLayout(transform_box)

		size_form = QFormLayout()
		self.spin_width = QSpinBox(transform_box)
		self.spin_height = QSpinBox(transform_box)
		for spin in (self.spin_width, self.spin_height):
			spin.setRange(1, 50000)
			spin.setSuffix(" px")
		size_form.addRow("W", self.spin_width)
		size_form.addRow("H", self.spin_height)
		self.check_keep_ratio = QCheckBox("Keep ratio", transform_box)
		self.check_keep_ratio.setChecked(True)
		transform_layout.addLayout(size_form)
		transform_layout.addWidget(self.check_keep_ratio)

		self.slider_angle = ValueSlider("Angle", -180, 180, 0, "°", transform_box)
		step_layout = QHBoxLayout()
		self.button_angle_minus = QPushButton("-45", transform_box)
		self.button_angle_plus = QPushButton("+45", transform_box)
		step_layout.addWidget(self.button_angle_minus)
		step_layout.addWidget(self.button_angle_plus)
		transform_layout.addWidget(self.slider_angle)
		transform_layout.addLayout(step_layout)

		flip_layout = QHBoxLayout()
		self.check_flip_h = QCheckBox("Flip H", transform_box)
		self.check_flip_v = QCheckBox("Flip V", transform_box)
		flip_layout.addWidget(self.check_flip_h)
		flip_layout.addWidget(self.check_flip_v)
		transform_layout.addLayout(flip_layout)

		self.slider_brightness = ValueSlider("Brightness", -100, 100, 0, "", transform_box)
		self.slider_contrast = ValueSlider("Contrast", -100, 100, 0, "", transform_box)
		transform_layout.addWidget(self.slider_brightness)
		transform_layout.addWidget(self.slider_contrast)

		button_layout = QHBoxLayout()
		self.button_apply = QPushButton("Apply", transform_box)
		self.button_reset = QPushButton("Reset", transform_box)
		button_layout.addWidget(self.button_apply)
		button_layout.addWidget(self.button_reset)
		transform_layout.addLayout(button_layout)
		root.addWidget(transform_box)
		root.addStretch(1)

	def _connect_signals(self) -> None:
		self.spin_width.valueChanged.connect(self._on_width_changed)
		self.spin_height.valueChanged.connect(self._on_height_changed)
		self.slider_angle.value_changed.connect(lambda _value: self._emit_preview())
		self.slider_brightness.value_changed.connect(lambda _value: self._emit_preview())
		self.slider_contrast.value_changed.connect(lambda _value: self._emit_preview())
		self.check_flip_h.toggled.connect(lambda _checked: self._emit_preview())
		self.check_flip_v.toggled.connect(lambda _checked: self._emit_preview())
		self.button_angle_minus.clicked.connect(lambda: self.slider_angle.set_value(self.slider_angle.value() - 45))
		self.button_angle_plus.clicked.connect(lambda: self.slider_angle.set_value(self.slider_angle.value() + 45))
		self.button_apply.clicked.connect(lambda: self.apply_requested.emit(self.options()))
		self.button_reset.clicked.connect(self.reset_requested.emit)

	def _on_width_changed(self, value: int) -> None:
		if self._updating or not self.check_keep_ratio.isChecked():
			return
		self._updating = True
		ratio = self._source_height / max(1, self._source_width)
		self.spin_height.setValue(max(1, round(value * ratio)))
		self._updating = False

	def _on_height_changed(self, value: int) -> None:
		if self._updating or not self.check_keep_ratio.isChecked():
			return
		self._updating = True
		ratio = self._source_width / max(1, self._source_height)
		self.spin_width.setValue(max(1, round(value * ratio)))
		self._updating = False

	def _emit_preview(self) -> None:
		if not self._updating:
			self.preview_requested.emit(self.options())


class ResizeDialog(QDialog):
	"""Resize the current image using explicit target pixel dimensions."""

	def __init__(self, width: int, height: int, parent=None):
		super().__init__(parent)
		self.setWindowTitle("Resize Image")
		self._source_width = max(1, int(width))
		self._source_height = max(1, int(height))
		self._updating = False
		self._build_ui()
		self._connect_signals()

	def options(self) -> PreprocessOptions:
		"""Return resize-only preprocessing options."""
		return PreprocessOptions(
			resize_enabled=True,
			width=self.spin_width.value(),
			height=self.spin_height.value(),
		)

	def _build_ui(self) -> None:
		layout = QVBoxLayout(self)
		original = QGroupBox("Original Size", self)
		original_form = QFormLayout(original)
		original_form.addRow("Width", QLabel(f"{self._source_width} px", original))
		original_form.addRow("Height", QLabel(f"{self._source_height} px", original))
		layout.addWidget(original)

		target = QGroupBox("Target Size", self)
		target_form = QFormLayout(target)
		self.spin_width = QSpinBox(target)
		self.spin_height = QSpinBox(target)
		for spin, value in ((self.spin_width, self._source_width), (self.spin_height, self._source_height)):
			spin.setRange(1, 50000)
			spin.setValue(value)
			spin.setSuffix(" px")
		target_form.addRow("Width", self.spin_width)
		target_form.addRow("Height", self.spin_height)
		self.check_keep_ratio = QCheckBox("Keep ratio", target)
		self.check_keep_ratio.setChecked(True)
		target_form.addRow("", self.check_keep_ratio)
		self.label_result = QLabel("", target)
		target_form.addRow("Result", self.label_result)
		layout.addWidget(target)

		buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel, self)
		buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
		buttons.rejected.connect(self.reject)
		layout.addWidget(buttons)
		self._update_result_label()

	def _connect_signals(self) -> None:
		self.spin_width.valueChanged.connect(self._on_width_changed)
		self.spin_height.valueChanged.connect(self._on_height_changed)

	def _on_width_changed(self, value: int) -> None:
		if self._updating:
			return
		if self.check_keep_ratio.isChecked():
			self._updating = True
			self.spin_height.setValue(max(1, round(value * self._source_height / self._source_width)))
			self._updating = False
		self._update_result_label()

	def _on_height_changed(self, value: int) -> None:
		if self._updating:
			return
		if self.check_keep_ratio.isChecked():
			self._updating = True
			self.spin_width.setValue(max(1, round(value * self._source_width / self._source_height)))
			self._updating = False
		self._update_result_label()

	def _update_result_label(self) -> None:
		self.label_result.setText(f"{self.spin_width.value()} × {self.spin_height.value()} px")


class RotateDialog(QDialog):
	"""Edit one rotation angle while the canvas previews automatically."""

	value_changed = pyqtSignal(object)

	def __init__(self, parent=None):
		super().__init__(parent)
		self.setWindowTitle("Rotate Image")
		layout = QVBoxLayout(self)
		self.slider_angle = ValueSlider("Angle", -180, 180, 0, "°", self)
		layout.addWidget(self.slider_angle)
		step_layout = QHBoxLayout()
		button_minus = QPushButton("-45", self)
		button_plus = QPushButton("+45", self)
		step_layout.addWidget(button_minus)
		step_layout.addWidget(button_plus)
		layout.addLayout(step_layout)
		layout.addWidget(QLabel("Fill Empty Area: Black", self))
		buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel, self)
		buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
		buttons.rejected.connect(self.reject)
		layout.addWidget(buttons)
		button_minus.clicked.connect(lambda: self.slider_angle.set_value(self.slider_angle.value() - 45))
		button_plus.clicked.connect(lambda: self.slider_angle.set_value(self.slider_angle.value() + 45))
		self.slider_angle.value_changed.connect(lambda _value: self.value_changed.emit(self.options()))

	def options(self) -> PreprocessOptions:
		"""Return rotation-only preprocessing options."""
		return PreprocessOptions(rotation_degrees=float(self.slider_angle.value()))


class BrightnessContrastDialog(QDialog):
	"""Edit brightness and contrast while the canvas previews automatically."""

	value_changed = pyqtSignal(object)

	def __init__(self, parent=None):
		super().__init__(parent)
		self.setWindowTitle("Brightness / Contrast")
		layout = QVBoxLayout(self)
		self.slider_brightness = ValueSlider("Brightness", -100, 100, 0, "", self)
		self.slider_contrast = ValueSlider("Contrast", -100, 100, 0, "", self)
		layout.addWidget(self.slider_brightness)
		layout.addWidget(self.slider_contrast)
		buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel, self)
		buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
		buttons.rejected.connect(self.reject)
		layout.addWidget(buttons)
		self.slider_brightness.value_changed.connect(lambda _value: self.value_changed.emit(self.options()))
		self.slider_contrast.value_changed.connect(lambda _value: self.value_changed.emit(self.options()))

	def options(self) -> PreprocessOptions:
		"""Return brightness and contrast preprocessing options."""
		return PreprocessOptions(
			brightness_shift=self.slider_brightness.value(),
			contrast_shift=self.slider_contrast.value(),
		)


class BatchPreprocessDialog(QDialog):
	"""Configure preprocessing for the current MapSet or all MapSets."""

	def __init__(self, width: int, height: int, total_mapsets: int = 0, parent=None):
		super().__init__(parent)
		self.setWindowTitle("Batch Preprocessing")
		self.resize(420, 520)
		self._source_width = max(1, int(width))
		self._source_height = max(1, int(height))
		self._total_mapsets = int(total_mapsets)
		self._build_ui()
		self._connect_signals()
		self._update_summary()

	def target_scope(self) -> str:
		"""Return the selected batch target scope."""
		return "all_mapsets" if self.radio_all_mapsets.isChecked() else "current_mapset"

	def options(self) -> PreprocessOptions:
		"""Return enabled batch preprocessing options."""
		return PreprocessOptions(
			resize_enabled=self.check_resize.isChecked(),
			width=self.spin_width.value(),
			height=self.spin_height.value(),
			flip_horizontal=self.check_flip.isChecked() and self.check_flip_h.isChecked(),
			flip_vertical=self.check_flip.isChecked() and self.check_flip_v.isChecked(),
			rotation_degrees=float(self.slider_angle.value()) if self.check_rotate.isChecked() else 0.0,
			brightness_shift=self.slider_brightness.value() if self.check_adjust.isChecked() else 0,
			contrast_shift=self.slider_contrast.value() if self.check_adjust.isChecked() else 0,
		)

	def _build_ui(self) -> None:
		layout = QVBoxLayout(self)
		target_box = QGroupBox("Target", self)
		target_layout = QVBoxLayout(target_box)
		self.radio_current_mapset = QRadioButton("Current MapSet", target_box)
		self.radio_all_mapsets = QRadioButton("All MapSets", target_box)
		self.radio_current_mapset.setChecked(True)
		self.target_group = QButtonGroup(target_box)
		self.target_group.addButton(self.radio_current_mapset)
		self.target_group.addButton(self.radio_all_mapsets)
		target_layout.addWidget(self.radio_current_mapset)
		target_layout.addWidget(self.radio_all_mapsets)
		layout.addWidget(target_box)

		resize_box = QGroupBox("Resize", self)
		resize_form = QFormLayout(resize_box)
		self.check_resize = QCheckBox("Enable", resize_box)
		self.spin_width = QSpinBox(resize_box)
		self.spin_height = QSpinBox(resize_box)
		for spin, value in ((self.spin_width, self._source_width), (self.spin_height, self._source_height)):
			spin.setRange(1, 50000)
			spin.setValue(value)
			spin.setSuffix(" px")
		self.check_keep_ratio = QCheckBox("Keep ratio", resize_box)
		self.check_keep_ratio.setChecked(True)
		resize_form.addRow(self.check_resize)
		resize_form.addRow("Width", self.spin_width)
		resize_form.addRow("Height", self.spin_height)
		resize_form.addRow("", self.check_keep_ratio)
		layout.addWidget(resize_box)

		flip_box = QGroupBox("Flip", self)
		flip_layout = QHBoxLayout(flip_box)
		self.check_flip = QCheckBox("Enable", flip_box)
		self.check_flip_h = QCheckBox("Horizontal", flip_box)
		self.check_flip_v = QCheckBox("Vertical", flip_box)
		flip_layout.addWidget(self.check_flip)
		flip_layout.addWidget(self.check_flip_h)
		flip_layout.addWidget(self.check_flip_v)
		layout.addWidget(flip_box)

		rotate_box = QGroupBox("Rotate", self)
		rotate_layout = QVBoxLayout(rotate_box)
		self.check_rotate = QCheckBox("Enable", rotate_box)
		self.slider_angle = ValueSlider("Angle", -180, 180, 0, "°", rotate_box)
		rotate_layout.addWidget(self.check_rotate)
		rotate_layout.addWidget(self.slider_angle)
		rotate_layout.addWidget(QLabel("Fill Empty Area: Black", rotate_box))
		layout.addWidget(rotate_box)

		adjust_box = QGroupBox("Brightness / Contrast", self)
		adjust_layout = QVBoxLayout(adjust_box)
		self.check_adjust = QCheckBox("Enable", adjust_box)
		self.slider_brightness = ValueSlider("Brightness", -100, 100, 0, "", adjust_box)
		self.slider_contrast = ValueSlider("Contrast", -100, 100, 0, "", adjust_box)
		adjust_layout.addWidget(self.check_adjust)
		adjust_layout.addWidget(self.slider_brightness)
		adjust_layout.addWidget(self.slider_contrast)
		layout.addWidget(adjust_box)

		self.summary_label = QLabel("", self)
		layout.addWidget(self.summary_label)
		buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel, self)
		buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
		buttons.rejected.connect(self.reject)
		layout.addWidget(buttons)

	def _connect_signals(self) -> None:
		for widget in (
			self.radio_current_mapset,
			self.radio_all_mapsets,
			self.check_resize,
			self.check_flip,
			self.check_rotate,
			self.check_adjust,
		):
			widget.toggled.connect(self._update_summary)

	def _update_summary(self) -> None:
		target = self._total_mapsets if self.radio_all_mapsets.isChecked() else 1
		self.summary_label.setText(
			"Summary\n"
			f"  Total MapSets: {self._total_mapsets}\n"
			f"  Target MapSets: {target}\n"
		)


PreprocessDialog = BatchPreprocessDialog
