from __future__ import annotations

from service.yolo_export_service import YoloExportApi
from worker.base_worker import BaseWorker


class ExportWorker(BaseWorker):
    """Run YOLO dataset export and validate its image-label pairs."""

    OPERATIONS = frozenset({"yolo_export"})

    def __init__(self, task_id: str, operation: str, payload: object, api: YoloExportApi, parent=None):
        super().__init__(task_id, operation, payload, parent)
        self.api = api

    def execute(self):
        if self.operation != "yolo_export":
            raise ValueError(f"Unsupported export operation: {self.operation}")
        options = self.payload["options"]
        result = self.api.export_dataset(
            self.payload["mapsets"],
            options,
            progress_callback=self._service_progress,
        )
        if not self.api.validate_export(options.output_root):
            raise RuntimeError("Export validation failed: image/label pairs are incomplete")
        return result

    def _service_progress(self, completed: int, total: int, message: str) -> None:
        self.check_cancelled()
        self.report(round(completed / max(1, total) * 100), message)
