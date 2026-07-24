from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout


class LabelAddDialog(QDialog):
    """Choose one previously managed class for the active selection."""

    def __init__(self, catalog: list[tuple[int, str]], parent=None, initial_class_id: int | None = None):
        super().__init__(parent)
        self.setWindowTitle("Add Label")
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose a label class for the selected area.", self))
        form = QFormLayout()
        self.class_combo = QComboBox(self)
        selected_index = 0
        for index, (class_id, class_name) in enumerate(catalog):
            self.class_combo.addItem(f"[{class_id}]  {class_name}", (class_id, class_name))
            if class_id == initial_class_id:
                selected_index = index
        if self.class_combo.count():
            self.class_combo.setCurrentIndex(selected_index)
        form.addRow("Label", self.class_combo)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.class_combo.count() > 0)
        layout.addWidget(self.buttons)

    def selected_label(self) -> tuple[int, str] | None:
        value = self.class_combo.currentData(Qt.ItemDataRole.UserRole)
        return tuple(value) if value is not None else None
