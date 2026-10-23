"""Transform panels and dialogs for image preprocessing."""

from __future__ import annotations


from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
	QButtonGroup,
	QCheckBox,
	QDialog,
	QDialogButtonBox,
	QFormLayout,
	QGroupBox,
	QHBoxLayout,
	QLabel,
	QPushButton,
	QRadioButton,
	QScrollArea,
	QSizePolicy,
	QSlider,
	QSpinBox,
	QVBoxLayout,
	QWidget,
)

from service.preprocessing_service import PreprocessOptions
from ui.themes import configure_dialog


class ValueSlider(QWidget):
	"""Expose one bounded integer value through a slider and spin box."""

	value_changed = Signal(int)

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
		self.spin.setKeyboardTracking(False)
		self.spin.setMinimumWidth(84)
		self.spin.setMaximumWidth(110)
		self.slider.setMinimumWidth(35)
		self.slider.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
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

	preview_requested = Signal(object)
	apply_requested = Signal(object)
	reset_requested = Signal()

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

		image_box = QGroupBox("현재 이미지", self)
		image_form = QFormLayout(image_box)
		self.label_mapset_value = QLabel("-", image_box)
		self.label_map_value = QLabel("-", image_box)
		self.label_size_value = QLabel("-", image_box)
		self.label_labels_value = QLabel("0", image_box)
		self.label_state_value = QLabel("Saved", image_box)
		image_form.addRow("MapSet", self.label_mapset_value)
		image_form.addRow("Map", self.label_map_value)
		image_form.addRow("크기", self.label_size_value)
		image_form.addRow("라벨", self.label_labels_value)
		image_form.addRow("상태", self.label_state_value)
		root.addWidget(image_box)

		transform_box = QGroupBox("이미지 변형", self)
		transform_layout = QVBoxLayout(transform_box)

		size_form = QFormLayout()
		self.spin_width = QSpinBox(transform_box)
		self.spin_height = QSpinBox(transform_box)
		for spin in (self.spin_width, self.spin_height):
			spin.setRange(1, 50000)
			spin.setSuffix(" px")
		size_form.addRow("W", self.spin_width)
		size_form.addRow("H", self.spin_height)
		self.check_keep_ratio = QCheckBox("비율 유지", transform_box)
		self.check_keep_ratio.setChecked(True)
		transform_layout.addLayout(size_form)
		transform_layout.addWidget(self.check_keep_ratio)

		self.slider_angle = ValueSlider("각도", -180, 180, 0, "°", transform_box)
		step_layout = QHBoxLayout()
		self.button_angle_minus = QPushButton("-45", transform_box)
		self.button_angle_plus = QPushButton("+45", transform_box)
		step_layout.addWidget(self.button_angle_minus)
		step_layout.addWidget(self.button_angle_plus)
		transform_layout.addWidget(self.slider_angle)
		transform_layout.addLayout(step_layout)

		flip_layout = QHBoxLayout()
		self.check_flip_h = QCheckBox("좌우 반전", transform_box)
		self.check_flip_v = QCheckBox("상하 반전", transform_box)
		flip_layout.addWidget(self.check_flip_h)
		flip_layout.addWidget(self.check_flip_v)
		transform_layout.addLayout(flip_layout)

		self.slider_brightness = ValueSlider("밝기", -100, 100, 0, "", transform_box)
		self.slider_contrast = ValueSlider("대비", -100, 100, 0, "", transform_box)
		transform_layout.addWidget(self.slider_brightness)
		transform_layout.addWidget(self.slider_contrast)

		button_layout = QHBoxLayout()
		self.button_apply = QPushButton("적용", transform_box)
		self.button_apply.setProperty("uiRole", "primary")
		self.button_reset = QPushButton("초기화", transform_box)
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
		self.setWindowTitle("이미지 크기 변경")
		self._source_width = max(1, int(width))
		self._source_height = max(1, int(height))
		self._updating = False
		self._build_ui()
		self._connect_signals()
		configure_dialog(self)

	def options(self) -> PreprocessOptions:
		"""Return resize-only preprocessing options."""
		return PreprocessOptions(
			resize_enabled=True,
			width=self.spin_width.value(),
			height=self.spin_height.value(),
		)

	def _build_ui(self) -> None:
		layout = QVBoxLayout(self)
		original = QGroupBox("원본 크기", self)
		original_form = QFormLayout(original)
		original_form.addRow("너비", QLabel(f"{self._source_width} px", original))
		original_form.addRow("높이", QLabel(f"{self._source_height} px", original))
		layout.addWidget(original)

		target = QGroupBox("변경할 크기", self)
		target_form = QFormLayout(target)
		self.spin_width = QSpinBox(target)
		self.spin_height = QSpinBox(target)
		for spin, value in ((self.spin_width, self._source_width), (self.spin_height, self._source_height)):
			spin.setRange(1, 50000)
			spin.setValue(value)
			spin.setSuffix(" px")
		target_form.addRow("너비", self.spin_width)
		target_form.addRow("높이", self.spin_height)
		self.check_keep_ratio = QCheckBox("비율 유지", target)
		self.check_keep_ratio.setChecked(True)
		target_form.addRow("", self.check_keep_ratio)
		self.label_result = QLabel("", target)
		target_form.addRow("결과", self.label_result)
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

	value_changed = Signal(object)

	def __init__(self, parent=None):
		super().__init__(parent)
		self.setWindowTitle("이미지 회전")
		layout = QVBoxLayout(self)
		self.slider_angle = ValueSlider("각도", -180, 180, 0, "°", self)
		layout.addWidget(self.slider_angle)
		step_layout = QHBoxLayout()
		button_minus = QPushButton("-45", self)
		button_plus = QPushButton("+45", self)
		step_layout.addWidget(button_minus)
		step_layout.addWidget(button_plus)
		layout.addLayout(step_layout)
		layout.addWidget(QLabel("회전으로 생긴 빈 영역은 검정으로 채웁니다.", self))
		self.preview_check = QCheckBox("캔버스에서 미리보기", self)
		self.preview_check.setChecked(True)
		layout.addWidget(self.preview_check)
		buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel, self)
		buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
		buttons.rejected.connect(self.reject)
		layout.addWidget(buttons)
		button_minus.clicked.connect(lambda: self.slider_angle.set_value(self.slider_angle.value() - 45))
		button_plus.clicked.connect(lambda: self.slider_angle.set_value(self.slider_angle.value() + 45))
		self.slider_angle.value_changed.connect(self._emit_preview)
		self.preview_check.toggled.connect(self._emit_preview)
		configure_dialog(self)

	def _emit_preview(self, *_args) -> None:
		"""Toggle the preview without discarding the entered rotation angle."""
		self.value_changed.emit(self.options() if self.preview_check.isChecked() else PreprocessOptions())

	def options(self) -> PreprocessOptions:
		"""Return rotation-only preprocessing options."""
		return PreprocessOptions(rotation_degrees=float(self.slider_angle.value()))


class BrightnessContrastDialog(QDialog):
	"""Edit brightness and contrast while the canvas previews automatically."""

	value_changed = Signal(object)

	def __init__(self, parent=None):
		super().__init__(parent)
		self.setWindowTitle("밝기 / 대비")
		layout = QVBoxLayout(self)
		self.slider_brightness = ValueSlider("밝기", -100, 100, 0, "", self)
		self.slider_contrast = ValueSlider("대비", -100, 100, 0, "", self)
		layout.addWidget(self.slider_brightness)
		layout.addWidget(self.slider_contrast)
		self.preview_check = QCheckBox("캔버스에서 미리보기", self)
		self.preview_check.setChecked(True)
		layout.addWidget(self.preview_check)
		buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel, self)
		buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
		buttons.rejected.connect(self.reject)
		layout.addWidget(buttons)
		self.slider_brightness.value_changed.connect(self._emit_preview)
		self.slider_contrast.value_changed.connect(self._emit_preview)
		self.preview_check.toggled.connect(self._emit_preview)
		configure_dialog(self)

	def _emit_preview(self, *_args) -> None:
		"""Compare with the original while retaining the values used by Apply."""
		self.value_changed.emit(self.options() if self.preview_check.isChecked() else PreprocessOptions())

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
		self.setWindowTitle("일괄 전처리")
		self.resize(540, 640)
		self._updating = False
		self._source_width = max(1, int(width))
		self._source_height = max(1, int(height))
		self._total_mapsets = int(total_mapsets)
		self._build_ui()
		self._connect_signals()
		self._update_summary()
		configure_dialog(self, 500, "전처리 적용")

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
		outer = QVBoxLayout(self)
		scroll = QScrollArea(self)
		scroll.setWidgetResizable(True)
		scroll.setFrameShape(QScrollArea.Shape.NoFrame)
		content = QWidget(scroll)
		layout = QVBoxLayout(content)
		scroll.setWidget(content)
		outer.addWidget(scroll, 1)
		target_box = QGroupBox("적용 대상", self)
		target_layout = QVBoxLayout(target_box)
		self.radio_current_mapset = QRadioButton("현재 MapSet / 이미지", target_box)
		self.radio_all_mapsets = QRadioButton("모든 MapSet", target_box)
		self.radio_current_mapset.setChecked(True)
		self.target_group = QButtonGroup(target_box)
		self.target_group.addButton(self.radio_current_mapset)
		self.target_group.addButton(self.radio_all_mapsets)
		target_layout.addWidget(self.radio_current_mapset)
		target_layout.addWidget(self.radio_all_mapsets)
		layout.addWidget(target_box)

		resize_box = QGroupBox("크기 변경", self)
		resize_form = QFormLayout(resize_box)
		self.check_resize = QCheckBox("사용", resize_box)
		self.spin_width = QSpinBox(resize_box)
		self.spin_height = QSpinBox(resize_box)
		for spin, value in ((self.spin_width, self._source_width), (self.spin_height, self._source_height)):
			spin.setRange(1, 50000)
			spin.setValue(value)
			spin.setSuffix(" px")
		self.check_keep_ratio = QCheckBox("비율 유지", resize_box)
		self.check_keep_ratio.setChecked(True)
		resize_form.addRow(self.check_resize)
		resize_form.addRow("너비", self.spin_width)
		resize_form.addRow("높이", self.spin_height)
		resize_form.addRow("", self.check_keep_ratio)
		layout.addWidget(resize_box)

		flip_box = QGroupBox("뒤집기", self)
		flip_layout = QHBoxLayout(flip_box)
		self.check_flip = QCheckBox("사용", flip_box)
		self.check_flip_h = QCheckBox("좌우", flip_box)
		self.check_flip_v = QCheckBox("상하", flip_box)
		flip_layout.addWidget(self.check_flip)
		flip_layout.addWidget(self.check_flip_h)
		flip_layout.addWidget(self.check_flip_v)
		layout.addWidget(flip_box)

		rotate_box = QGroupBox("회전", self)
		rotate_layout = QVBoxLayout(rotate_box)
		self.check_rotate = QCheckBox("사용", rotate_box)
		self.slider_angle = ValueSlider("각도", -180, 180, 0, "°", rotate_box)
		rotate_layout.addWidget(self.check_rotate)
		rotate_layout.addWidget(self.slider_angle)
		rotate_layout.addWidget(QLabel("회전으로 생긴 빈 영역은 검정으로 채웁니다.", rotate_box))
		layout.addWidget(rotate_box)

		adjust_box = QGroupBox("밝기 / 대비", self)
		adjust_layout = QVBoxLayout(adjust_box)
		self.check_adjust = QCheckBox("사용", adjust_box)
		self.slider_brightness = ValueSlider("밝기", -100, 100, 0, "", adjust_box)
		self.slider_contrast = ValueSlider("대비", -100, 100, 0, "", adjust_box)
		adjust_layout.addWidget(self.check_adjust)
		adjust_layout.addWidget(self.slider_brightness)
		adjust_layout.addWidget(self.slider_contrast)
		layout.addWidget(adjust_box)

		self.summary_label = QLabel("", self)
		outer.addWidget(self.summary_label)
		buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel, self)
		buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
		buttons.rejected.connect(self.reject)
		self.buttons = buttons
		outer.addWidget(buttons)

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
		self.spin_width.valueChanged.connect(lambda value: self._sync_dimensions(value, True))
		self.spin_height.valueChanged.connect(lambda value: self._sync_dimensions(value, False))

	def _sync_dimensions(self, value: int, width_changed: bool) -> None:
		"""Honor the advertised aspect-ratio lock without recursively changing fields."""
		if self._updating or not self.check_keep_ratio.isChecked():
			return
		self._updating = True
		if width_changed:
			self.spin_height.setValue(max(1, round(value * self._source_height / self._source_width)))
		else:
			self.spin_width.setValue(max(1, round(value * self._source_width / self._source_height)))
		self._updating = False

	def _update_summary(self) -> None:
		target = self._total_mapsets if self.radio_all_mapsets.isChecked() else 1
		self.summary_label.setText(f"적용 대상: {target}개 · 사용할 전처리 항목을 켜세요.")
		for enabled, controls in ((self.check_resize.isChecked(), (self.spin_width, self.spin_height, self.check_keep_ratio)), (self.check_flip.isChecked(), (self.check_flip_h, self.check_flip_v)), (self.check_rotate.isChecked(), (self.slider_angle,)), (self.check_adjust.isChecked(), (self.slider_brightness, self.slider_contrast))):
			for control in controls:
				control.setEnabled(enabled)
		self.buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(target > 0 and any(check.isChecked() for check in (self.check_resize, self.check_flip, self.check_rotate, self.check_adjust)))


PreprocessDialog = BatchPreprocessDialog
