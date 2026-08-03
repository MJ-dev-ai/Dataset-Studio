from __future__ import annotations

import traceback
from dataclasses import dataclass
from time import monotonic

from PyQt6.QtCore import QObject, pyqtSlot
from PyQt6.QtWidgets import QApplication

from service.augmentation_service import AugmentationApi
from service.editing_service import PoissonApi
from service.labeling_service import YoloApi
from service.preprocessing_service import PreprocessApi
from service.yolo_export_service import YoloExportApi
from worker.augmentation_worker import AugmentationWorker
from worker.editing_worker import EditingWorker
from worker.export_worker import ExportWorker
from worker.project_worker import ProjectWorker


@dataclass
class AppContext:
    poisson_api: PoissonApi
    yolo_api: YoloApi
    preprocess_api: PreprocessApi
    augmentation_api: AugmentationApi
    export_api: YoloExportApi


def create_app_context() -> AppContext:
    yolo_api = YoloApi()
    preprocess_api = PreprocessApi()
    poisson_api = PoissonApi()
    return AppContext(
        poisson_api=poisson_api,
        yolo_api=yolo_api,
        preprocess_api=preprocess_api,
        augmentation_api=AugmentationApi(poisson_api=poisson_api, yolo_api=yolo_api),
        export_api=YoloExportApi(yolo_api=yolo_api),
    )


class DatasetEditorApp(QObject):
    """Application owner: creates the window and owns all background task threads."""

    def __init__(self, qt_app: QApplication, logger, parent=None):
        super().__init__(parent)
        from ui.mainwindow import MainWindow

        self.qt_app = qt_app
        self.logger = logger
        self.context = create_app_context()
        self._workers = {}
        self.window = MainWindow(context=self.context)
        self.window.task_requested.connect(self._start_worker)
        self.window.task_cancel_requested.connect(self._cancel_worker)
        self.window.shutdown_requested.connect(self._shutdown_from_window)

    @pyqtSlot(str, str, object)
    def _start_worker(self, task_id: str, operation: str, payload) -> None:
        """Create the feature worker selected by a UI operation request."""
        try:
            if task_id in self._workers:
                raise ValueError(f"Worker id is already active: {task_id}")
            worker = self._create_worker(task_id, operation, payload)
            worker.setObjectName(f"DatasetEditor:{operation}:{task_id[:8]}")
            worker.progress.connect(self.window._on_task_progress)
            worker.succeeded.connect(self.window._on_task_succeeded)
            worker.failed.connect(self.window._on_task_failed)
            worker.cancelled.connect(self.window._on_task_cancelled)
            worker.finished.connect(lambda current=task_id: self._release_worker(current))
            self._workers[task_id] = worker
            self.logger.info("Worker started: %s %s", operation, task_id)
            worker.start()
        except Exception as exc:
            traceback_text = traceback.format_exc()
            self.logger.exception("Failed to start worker: %s %s", operation, task_id)
            self.window._on_task_failed(task_id, str(exc), traceback_text)
            self.window._on_task_finished(task_id)

    def _create_worker(self, task_id: str, operation: str, payload):
        """Build one concrete worker without hiding its feature ownership."""
        if operation in ProjectWorker.OPERATIONS:
            return ProjectWorker(task_id, operation, payload, self)
        if operation in EditingWorker.OPERATIONS:
            return EditingWorker(task_id, operation, payload, self.context.poisson_api, self)
        if operation in AugmentationWorker.OPERATIONS:
            return AugmentationWorker(task_id, operation, payload, self.context.augmentation_api, self)
        if operation in ExportWorker.OPERATIONS:
            return ExportWorker(task_id, operation, payload, self.context.export_api, self)
        raise ValueError(f"Unknown worker operation: {operation}")

    @pyqtSlot(str)
    def _cancel_worker(self, task_id: str) -> None:
        """Forward cancellation to the concrete worker owned by the app."""
        worker = self._workers.get(task_id)
        if worker is not None:
            worker.cancel()

    def _release_worker(self, task_id: str) -> None:
        """Release a worker only after QThread reports that it has stopped."""
        worker = self._workers.pop(task_id, None)
        if worker is not None:
            self.logger.info("Worker finished: %s %s", worker.operation, task_id)
            worker.deleteLater()
        self.window._on_task_finished(task_id)

    @pyqtSlot(int)
    def _shutdown_from_window(self, timeout_ms: int) -> None:
        """Synchronously report app-owned worker shutdown back to the close event."""
        self.window.complete_shutdown(self.shutdown(timeout_ms))

    def shutdown(self, timeout_ms: int = 30000) -> bool:
        """Cancel and join every worker owned by the application."""
        workers = tuple(self._workers.values())
        for worker in workers:
            worker.cancel()
        deadline = monotonic() + max(0, timeout_ms) / 1000.0
        for worker in workers:
            remaining_ms = max(0, int((deadline - monotonic()) * 1000))
            if worker.isRunning() and remaining_ms:
                worker.wait(remaining_ms)
        return not any(worker.isRunning() for worker in workers)
