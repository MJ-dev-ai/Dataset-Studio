from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from service.yolo_export_service import YoloExportApi, YoloExportOptions


class ExportDialog(QDialog):
    """Popup dialog for YOLO dataset export."""

    def __init__(self, export_api: YoloExportApi, parent=None):
        super().__init__(parent)
        self.export_api = export_api
        self.output_root_edit = QLineEdit(self)
        self.class_names_edit = QLineEdit(self._default_class_names(), self)
        self._setup_ui()
        self._connect_signals()

    def _default_class_names(self) -> str:
        parent = self.parent()
        catalog = getattr(parent, "_label_catalog", [])
        if catalog:
            ordered = sorted(catalog, key=lambda item: item[0])
            return ", ".join(name for _class_id, name in ordered)
        return "class0"

    def _setup_ui(self) -> None:
        self.setWindowTitle("Export YOLO Dataset")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        browse_button = QPushButton("Browse", self)
        browse_button.clicked.connect(self._browse_output_root)
        form.addRow("Output Root", self.output_root_edit)
        form.addRow("", browse_button)
        form.addRow("Class Names", self.class_names_edit)
        layout.addLayout(form)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(self.buttons)

    def _connect_signals(self) -> None:
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

    def accept(self) -> None:
        parent = self.parent()
        project = getattr(parent, "project", None)
        if project is None:
            QMessageBox.information(self, "Export YOLO Dataset", "Open a dataset folder before exporting.")
            return
        if not self.output_root_edit.text().strip():
            QMessageBox.warning(self, "Export YOLO Dataset", "Select an output folder.")
            return
        if not hasattr(parent, "start_yolo_export"):
            QMessageBox.critical(self, "Export Failed", "The main window cannot start background exports.")
            return
        parent.start_yolo_export(self.build_options())
        super().accept()

    def build_options(self) -> YoloExportOptions:
        class_names = [name.strip() for name in self.class_names_edit.text().split(",") if name.strip()]
        return YoloExportOptions(output_root=Path(self.output_root_edit.text()), class_names=class_names)

    def _browse_output_root(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Export Output Folder",
            str(Path.cwd()),
        )
        if path:
            self.output_root_edit.setText(path)
