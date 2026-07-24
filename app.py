from __future__ import annotations

import threading
import traceback
import uuid
from dataclasses import dataclass
from time import monotonic
from typing import Callable

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from core.logging_setup import get_logger
from service.augmentation_service import AugmentationApi
from service.editing_service import PoissonApi
from service.labeling_service import YoloApi
from service.preprocessing_service import PreprocessApi
from service.yolo_export_service import YoloExportApi


class TaskCancelled(RuntimeError):
    """Raised cooperatively when a background task is cancelled."""


class TaskContext:
    """Cancellation and progress channel passed to background functions."""

    def __init__(self, progress_callback: Callable[[int, str], None]):
        self._cancel_event = threading.Event()
        self._progress_callback = progress_callback

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def cancel(self) -> None:
        self._cancel_event.set()

    def check_cancelled(self) -> None:
        if self.is_cancelled:
            raise TaskCancelled()

    def report(self, value: int, message: str = "") -> None:
        self._progress_callback(max(0, min(100, int(value))), message)


class _TaskWorker(QObject):
    progress = pyqtSignal(str, int, str)
    succeeded = pyqtSignal(str, object)
    failed = pyqtSignal(str, str, str)
    cancelled = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, task_id: str, function: Callable[[TaskContext], object]):
        super().__init__()
        self.task_id = task_id
        self.function = function
        self.context = TaskContext(
            lambda value, message: self.progress.emit(task_id, value, message)
        )

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self.function(self.context)
            self.context.check_cancelled()
        except TaskCancelled:
            self.cancelled.emit(self.task_id)
        except Exception as exc:
            self.failed.emit(self.task_id, str(exc), traceback.format_exc())
        else:
            self.succeeded.emit(self.task_id, result)
        finally:
            self.finished.emit(self.task_id)


@dataclass
class _TaskHandle:
    name: str
    thread: QThread
    worker: _TaskWorker


class TaskManager(QObject):
    """Own all application threads until Qt confirms that they have stopped."""

    task_started = pyqtSignal(str, str)
    task_progress = pyqtSignal(str, int, str)
    task_succeeded = pyqtSignal(str, object)
    task_failed = pyqtSignal(str, str, str)
    task_cancelled = pyqtSignal(str)
    task_finished = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks: dict[str, _TaskHandle] = {}

    @property
    def active_task_ids(self) -> tuple[str, ...]:
        return tuple(self._tasks)

    def start(self, name: str, function: Callable[[TaskContext], object]) -> str:
        task_id = uuid.uuid4().hex
        get_logger().info("Task queued: %s %s", name, task_id)
        thread = QThread(self)
        thread.setObjectName(f"DatasetStudio:{name}:{task_id[:8]}")
        worker = _TaskWorker(task_id, function)
        worker.moveToThread(thread)
        self._tasks[task_id] = _TaskHandle(name, thread, worker)

        thread.started.connect(worker.run)
        worker.progress.connect(self.task_progress)
        worker.succeeded.connect(self.task_succeeded)
        worker.failed.connect(self.task_failed)
        worker.cancelled.connect(self.task_cancelled)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda current=task_id: self._release(current))
        thread.start()
        self.task_started.emit(task_id, name)
        return task_id

    def cancel(self, task_id: str) -> bool:
        handle = self._tasks.get(task_id)
        if handle is None:
            return False
        get_logger().info("Task cancellation requested: %s %s", handle.name, task_id)
        handle.worker.context.cancel()
        return True

    def cancel_all(self) -> None:
        for handle in tuple(self._tasks.values()):
            handle.worker.context.cancel()

    def shutdown(self, timeout_ms: int = 10000) -> bool:
        """Cancel all work and wait for every owned thread within one deadline."""
        get_logger().info("TaskManager shutdown requested: active=%s timeout_ms=%s", len(self._tasks), timeout_ms)
        self.cancel_all()
        deadline = monotonic() + max(0, timeout_ms) / 1000.0
        for handle in tuple(self._tasks.values()):
            remaining_ms = max(0, int((deadline - monotonic()) * 1000))
            if handle.thread.isRunning() and remaining_ms:
                handle.thread.wait(remaining_ms)
        return not any(handle.thread.isRunning() for handle in self._tasks.values())

    @pyqtSlot(str)
    def _release(self, task_id: str) -> None:
        handle = self._tasks.pop(task_id, None)
        if handle is not None:
            get_logger().info("Task released: %s %s", handle.name, task_id)
        self.task_finished.emit(task_id)


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
