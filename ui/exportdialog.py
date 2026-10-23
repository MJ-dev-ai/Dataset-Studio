from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
)

from service.yolo_export_service import YoloExportOptions
from ui.themes import configure_dialog


class ExportDialog(QDialog):
    """Popup dialog for YOLO dataset export."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.output_root_edit = QLineEdit(self)
        self.class_names_edit = QLineEdit(self._default_class_names(), self)
        self._setup_ui()
        self._connect_signals()
        configure_dialog(self, 640, "내보내기")
        self.resize(700, 650)
        self.output_root_edit.setPlaceholderText("데이터셋을 저장할 폴더")
        self.output_root_edit.textChanged.connect(self._update_availability)
        self._update_availability()

    def _default_class_names(self) -> str:
        parent = self.parent()
        catalog = getattr(parent, "_label_catalog", [])
        if catalog:
            ordered = sorted(catalog, key=lambda item: item[0])
            return ", ".join(name for _class_id, name in ordered)
        return "class0"

    def _setup_ui(self) -> None:
        self.setWindowTitle("YOLO 데이터셋 내보내기")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        browse_button = QPushButton("찾아보기…", self)
        browse_button.clicked.connect(self._browse_output_root)
        path_row = QHBoxLayout()
        path_row.addWidget(self.output_root_edit, 1)
        path_row.addWidget(browse_button)
        form.addRow("저장 폴더", path_row)
        self.class_names_edit.hide()
        self.map_list = QListWidget(self)
        self.map_list.setMaximumHeight(100)
        project = getattr(self.parent(), "project", None)
        keys = sorted({key for item in getattr(project, "mapsets", []) for key, _path in item.maps})
        for key in keys:
            item = QListWidgetItem(key, self.map_list)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
        form.addRow("대상 맵", self.map_list)
        self.ratios = []
        ratio_row = QHBoxLayout()
        for name, value in (("Train", 80), ("Val", 20), ("Test", 0)):
            ratio_row.addWidget(QLabel(name, self))
            spin = QSpinBox(self)
            spin.setRange(0, 100)
            spin.setValue(value)
            spin.setSuffix(" %")
            self.ratios.append(spin)
            ratio_row.addWidget(spin)
        form.addRow("원본별 분할", ratio_row)
        self.seed_spin = QSpinBox(self)
        self.seed_spin.setRange(0, 2_147_483_647)
        form.addRow("분할 시드", self.seed_spin)
        self.class_table = QTableWidget(0, 3, self)
        self.class_table.setHorizontalHeaderLabels(["원본 ID", "출력 ID", "클래스 이름"])
        catalog = sorted(getattr(self.parent(), "_label_catalog", [])) or [(0, "class0")]
        self.class_table.setRowCount(len(catalog))
        for row, (class_id, name) in enumerate(catalog):
            for column, text in enumerate((str(class_id), str(row), name)):
                item = QTableWidgetItem(text)
                if column < 2:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.class_table.setItem(row, column, item)
        self.class_table.horizontalHeader().setStretchLastSection(True)
        form.addRow("클래스 매핑", self.class_table)
        layout.addLayout(form)
        self.validation_hint = QLabel(self)
        self.validation_hint.setWordWrap(True)
        self.validation_hint.setProperty("uiRole", "hint")
        layout.addWidget(self.validation_hint)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(self.buttons)
        for spin in self.ratios:
            spin.valueChanged.connect(self._update_availability)
        self.map_list.itemChanged.connect(self._update_availability)
        self.class_table.itemChanged.connect(self._update_availability)

    def _update_availability(self) -> None:
        """Explain missing prerequisites before the user submits the dialog."""
        project_ready = getattr(self.parent(), "project", None) is not None
        path_ready = bool(self.output_root_edit.text().strip())
        valid_ratios = sum(spin.value() for spin in self.ratios) == 100
        maps_ready = self.map_list.count() == 0 or any(self.map_list.item(row).checkState() == Qt.CheckState.Checked for row in range(self.map_list.count()))
        names_ready = all(self.class_table.item(row, 2).text().strip() for row in range(self.class_table.rowCount()))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(project_ready and path_ready and valid_ratios and maps_ready and names_ready)
        self.validation_hint.setText("먼저 데이터셋 프로젝트를 여세요." if not project_ready else "저장할 폴더를 선택하세요." if not path_ready else "분할 비율 합계를 100%로 맞추세요." if not valid_ratios else "대상 맵과 클래스 이름을 확인하세요." if not maps_ready or not names_ready else "선택한 폴더 아래 설정별 새 실행 폴더에 저장합니다. 기존 파일을 덮어쓰지 않습니다. 클래스 ID는 위 표대로 재매핑됩니다.")

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
        """Snapshot selected maps, sparse class IDs and reproducible split settings."""
        class_names = [self.class_table.item(row, 2).text().strip() for row in range(self.class_table.rowCount())]
        class_ids = [int(self.class_table.item(row, 0).text()) for row in range(self.class_table.rowCount())]
        keys = [self.map_list.item(row).text() for row in range(self.map_list.count()) if self.map_list.item(row).checkState() == Qt.CheckState.Checked]
        return YoloExportOptions(output_root=Path(self.output_root_edit.text().strip()), class_names=class_names, class_ids=class_ids, map_keys=keys if self.map_list.count() else None, train_ratio=self.ratios[0].value() / 100, val_ratio=self.ratios[1].value() / 100, test_ratio=self.ratios[2].value() / 100, seed=self.seed_spin.value())

    def _browse_output_root(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Export Output Folder",
            str(Path.cwd()),
        )
        if path:
            self.output_root_edit.setText(path)
