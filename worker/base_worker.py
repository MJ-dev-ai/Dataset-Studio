from __future__ import annotations

import threading
import traceback

from PyQt6.QtCore import QThread, pyqtSignal


class WorkerCancelled(RuntimeError):
    """Raised cooperatively when a feature worker is cancelled."""


class BaseWorker(QThread):
    """Common QThread lifecycle for one feature-specific background operation."""

    progress = pyqtSignal(str, int, str)
    succeeded = pyqtSignal(str, object)
    failed = pyqtSignal(str, str, str)
    cancelled = pyqtSignal(str)

    def __init__(self, task_id: str, operation: str, payload: object, parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self.operation = operation
        self.payload = payload
        self._cancel_event = threading.Event()

    def run(self) -> None:
        """Execute the feature operation and convert failures into Qt signals."""
        try:
            result = self.execute()
            self.check_cancelled()
        except WorkerCancelled:
            self.cancelled.emit(self.task_id)
        except Exception as exc:
            self.failed.emit(self.task_id, str(exc), traceback.format_exc())
        else:
            self.succeeded.emit(self.task_id, result)

    def execute(self):
        """Run the concrete service operation implemented by a feature worker."""
        raise NotImplementedError

    def cancel(self) -> None:
        """Request cooperative cancellation without terminating the thread."""
        self._cancel_event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def check_cancelled(self) -> None:
        """Raise at a safe service boundary after cancellation was requested."""
        if self.is_cancelled:
            raise WorkerCancelled

    def report(self, value: int, message: str = "") -> None:
        """Emit normalized progress for this worker operation."""
        self.progress.emit(self.task_id, max(0, min(100, int(value))), message)
