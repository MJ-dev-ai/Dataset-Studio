from __future__ import annotations

from service.augmentation_service import AugmentationApi
from worker.base_worker import BaseWorker


class AugmentationWorker(BaseWorker):
    """Run preview, AutoAugment, and orientation generation operations."""

    OPERATIONS = frozenset({"augmentation_preview", "auto_augment", "orientation_augment"})

    def __init__(self, task_id: str, operation: str, payload: object, api: AugmentationApi, parent=None):
        super().__init__(task_id, operation, payload, parent)
        self.api = api

    def execute(self):
        if self.operation == "augmentation_preview":
            return self._preview()
        if self.operation == "auto_augment":
            return self.api.run_auto_yolo_augmentation(
                self.payload["project"],
                self.payload["options"],
                progress_callback=self._service_progress,
            )
        if self.operation == "orientation_augment":
            return self.api.run_orientation_augmentation(
                self.payload["mapsets"],
                self.payload["options"],
                progress_callback=self._service_progress,
            )
        raise ValueError(f"Unsupported augmentation operation: {self.operation}")

    def _preview(self):
        pairs = self.payload["pairs"]
        self.report(5, "Creating previews")
        previews = self.api.create_preview_samples(
            [pair[0] for pair in pairs],
            [pair[1] for pair in pairs],
            self.payload["options"],
        )
        self.report(100, "Preview complete")
        return previews

    def _service_progress(self, completed: int, total: int, message: str) -> None:
        self.check_cancelled()
        self.report(round(completed / max(1, total) * 100), message)
