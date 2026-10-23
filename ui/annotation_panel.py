"""Object list and properties backed by the canvas's single annotation state."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSignalBlocker, Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget, QPushButton, QSizePolicy, QVBoxLayout


class AnnotationPanel(QGroupBox):
    """Keep class choice, selected object and numeric edits explicit and synchronized."""

    def __init__(self, window):
        super().__init__("라벨 객체", window)
        self.setObjectName("annotationPanel")
        self.window, self.canvas = window, window.canvas
        self._catalog = None
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 8, 6, 6)
        row = QHBoxLayout()
        self.count = QLabel(self)
        self.visible_check = QCheckBox("라벨 표시", self)
        self.visible_check.setChecked(self.canvas.labels_visible)
        self.visible_check.toggled.connect(window.set_labels_visible)
        row.addWidget(self.count)
        row.addStretch()
        row.addWidget(self.visible_check)
        root.addLayout(row)
        self.objects = QListWidget(self)
        self.objects.setAccessibleName("라벨 객체 목록")
        self.objects.setUniformItemSizes(True)
        self.objects.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.objects.setMinimumHeight(105)
        self.objects.setMaximumHeight(136)
        self.objects.currentRowChanged.connect(self._select_row)
        self.objects.installEventFilter(self)
        root.addWidget(self.objects)
        row = QHBoxLayout()
        for text, callback in [("이전", lambda: self.canvas.cycle_annotation(True)), ("다음", lambda: self.canvas.cycle_annotation()), ("삭제", window.remove_active_annotation)]:
            button = QPushButton(text, self)
            button.clicked.connect(callback)
            row.addWidget(button)
            if text == "삭제":
                self.delete_button = button
        root.addLayout(row)
        self.class_combo = QComboBox(self)
        self.class_combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.class_combo.setAccessibleName("선택한 객체 클래스")
        root.addWidget(self.class_combo)
        grid = QGridLayout()
        self.fields = []
        for index, name in enumerate(("X", "Y", "너비", "높이")):
            field = QDoubleSpinBox(self)
            field.setRange(0 if index < 2 else 1, 1_000_000)
            field.setDecimals(1)
            field.setKeyboardTracking(False)
            # Reserve the full range plus the step buttons without inheriting
            # the native style's oversized spin-box size hint.
            field.setMinimumWidth(field.fontMetrics().horizontalAdvance("1000000.0") + 44)
            field.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            field.setAccessibleName(f"라벨 {name}")
            label = QLabel(name, self)
            label.setBuddy(field)
            grid.addWidget(label, (index // 2) * 2, index % 2)
            grid.addWidget(field, (index // 2) * 2 + 1, index % 2)
            self.fields.append(field)
        root.addLayout(grid)
        self.apply_button = QPushButton("선택 객체에 적용", self)
        self.apply_button.setProperty("uiRole", "primary")
        self.apply_button.clicked.connect(self.apply_properties)
        root.addWidget(self.apply_button)
        row = QHBoxLayout()
        for text, callback in [("클래스 관리", window.show_label_manager), ("라벨 저장", window.save_current_yolo_labels)]:
            button = QPushButton(text, self)
            button.clicked.connect(callback)
            row.addWidget(button)
        root.addLayout(row)
        hint = QLabel("W / N: 새 박스 · M: 선택 / 크기 조절\nCtrl+클릭: 겹친 객체 · Tab: 다음 객체\n방향키: 1px · Shift: 10px · Delete: 삭제", self)
        hint.setWordWrap(True)
        hint.setProperty("uiRole", "hint")
        root.addWidget(hint)
        self.canvas.image_changed.connect(self.refresh)
        self.canvas.annotation_selection_changed.connect(self.sync_selection)
        self.refresh()

    def refresh_catalog(self) -> None:
        """Update drawing choices only when the project catalog changed."""
        catalog = self.window.label_catalog()
        if catalog == self._catalog:
            return
        self._catalog = list(catalog)
        combo = self.window.annotationClassCombo
        previous = combo.currentData()
        with QSignalBlocker(combo):
            combo.clear()
            for class_id, name in catalog:
                combo.addItem(f"[{class_id}] {name}", class_id)
            if not catalog:
                combo.addItem("먼저 클래스를 등록하세요", None)
            index = combo.findData(previous if previous is not None else self.window._last_label_class_id)
            combo.setCurrentIndex(max(0, index))
        combo.setEnabled(bool(catalog))
        self.window._last_label_class_id = combo.currentData()

    def refresh(self) -> None:
        self.refresh_catalog()
        with QSignalBlocker(self.objects):
            self.objects.clear()
            for index, item in enumerate(self.canvas.annotations):
                b = item.bounds
                self.objects.addItem(f"{index + 1}. [{item.class_id}] {item.class_name}  ·  {b.width():.0f} × {b.height():.0f}")
        suffix = " · 미저장" if self.window._labels_modified else ""
        self.count.setText(f"{len(self.canvas.annotations)}개 객체{suffix}")
        self.sync_selection(self.canvas.selected_annotation_index)

    def sync_selection(self, index: int) -> None:
        """Selection alone never emits an annotation edit or changes its class."""
        with QSignalBlocker(self.objects):
            self.objects.setCurrentRow(index)
        valid = 0 <= index < len(self.canvas.annotations)
        for widget in (*self.fields, self.class_combo, self.apply_button, self.delete_button):
            widget.setEnabled(valid)
        with QSignalBlocker(self.class_combo):
            self.class_combo.clear()
            for class_id, name in self.window.label_catalog():
                self.class_combo.addItem(f"[{class_id}] {name}", class_id)
            if valid:
                item = self.canvas.annotations[index]
                if self.class_combo.findData(item.class_id) < 0:
                    self.class_combo.addItem(f"[{item.class_id}] {item.class_name}", item.class_id)
                self.class_combo.setCurrentIndex(self.class_combo.findData(item.class_id))
                b = item.bounds
                for field, value in zip(self.fields, (b.x(), b.y(), b.width(), b.height())):
                    field.setValue(value)
        if valid:
            self.objects.scrollToItem(self.objects.item(index))

    def _select_row(self, row: int) -> None:
        if row >= 0:
            self.window.ui_setup.activate_tool("rectangle")
            self.window.set_labels_visible(True)
            self.canvas.select_annotation(row)

    def apply_properties(self) -> None:
        class_id = self.class_combo.currentData()
        if class_id is not None:
            bounds = QRectF(*(field.value() for field in self.fields))
            self.canvas.update_annotation(self.canvas.selected_annotation_index, bounds, class_id, self.window.class_name_for_id(class_id))
            self.canvas.setFocus()

    def eventFilter(self, watched, event):
        if watched is self.objects and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Delete:
            self.window.remove_active_annotation()
            return True
        return False
