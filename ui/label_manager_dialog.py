from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)


class LabelManagerDialog(QDialog):
    """Add, edit, remove, and reorder the project label class catalog."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._original_id: int | None = None
        self.setWindowTitle("Label Class Manager")
        self.resize(520, 520)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        self.class_list = QListWidget(self)
        self.class_list.currentItemChanged.connect(self._class_selected)
        root.addWidget(self.class_list, 1)

        form = QFormLayout()
        self.class_id_spin = QSpinBox(self)
        self.class_id_spin.setRange(0, 9999)
        self.class_name_edit = QLineEdit(self)
        self.class_name_edit.setPlaceholderText("Class name")
        form.addRow("Class ID", self.class_id_spin)
        form.addRow("Name", self.class_name_edit)
        root.addLayout(form)

        edit_buttons = QHBoxLayout()
        self.new_button = QPushButton("New", self)
        self.save_button = QPushButton("Add / Update", self)
        self.delete_button = QPushButton("Delete", self)
        self.new_button.clicked.connect(self._new_class)
        self.save_button.clicked.connect(self._save_class)
        self.delete_button.clicked.connect(self._delete_class)
        edit_buttons.addWidget(self.new_button)
        edit_buttons.addWidget(self.save_button)
        edit_buttons.addWidget(self.delete_button)
        root.addLayout(edit_buttons)

        order_buttons = QHBoxLayout()
        self.up_button = QPushButton("Move Up", self)
        self.down_button = QPushButton("Move Down", self)
        self.up_button.clicked.connect(lambda: self._move(-1))
        self.down_button.clicked.connect(lambda: self._move(1))
        order_buttons.addWidget(self.up_button)
        order_buttons.addWidget(self.down_button)
        root.addLayout(order_buttons)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def refresh(self, selected_class_id: int | None = None) -> None:
        self.class_list.clear()
        selected_row = -1
        for row, (class_id, class_name) in enumerate(self.window.label_catalog()):
            item = QListWidgetItem(f"{row + 1:>2}.   [{class_id}]  {class_name}")
            item.setData(Qt.ItemDataRole.UserRole, (class_id, class_name))
            self.class_list.addItem(item)
            if class_id == selected_class_id:
                selected_row = row
        if self.class_list.count():
            self.class_list.setCurrentRow(selected_row if selected_row >= 0 else 0)
        else:
            self._new_class()

    def _class_selected(self, current, previous) -> None:
        del previous
        if current is None:
            return
        class_id, class_name = current.data(Qt.ItemDataRole.UserRole)
        self._original_id = class_id
        self.delete_button.setEnabled(True)
        self.class_id_spin.setValue(class_id)
        self.class_name_edit.setText(class_name)
        row = self.class_list.currentRow()
        self.up_button.setEnabled(row > 0)
        self.down_button.setEnabled(0 <= row < self.class_list.count() - 1)

    def _new_class(self) -> None:
        self.class_list.clearSelection()
        self.class_list.setCurrentRow(-1)
        self._original_id = None
        self.class_id_spin.setValue(self.window.next_label_class_id())
        self.class_name_edit.clear()
        self.class_name_edit.setFocus()
        self.delete_button.setEnabled(False)
        self.up_button.setEnabled(False)
        self.down_button.setEnabled(False)

    def _save_class(self) -> None:
        name = self.class_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Label Class", "Enter a class name.")
            return
        try:
            self.window.update_label_class(
                self._original_id,
                self.class_id_spin.value(),
                name,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Label Class", str(exc))
            return
        selected_id = self.class_id_spin.value()
        self.refresh(selected_id)

    def _delete_class(self) -> None:
        if self._original_id is not None and self.window.delete_label_class(self._original_id):
            self.refresh()

    def _move(self, offset: int) -> None:
        if self._original_id is None:
            return
        self.window.move_label_class(self._original_id, offset)
        self.refresh(self._original_id)
