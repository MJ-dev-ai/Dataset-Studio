from __future__ import annotations

import threading
import traceback

from PySide6.QtCore import QObject, Signal

from config.flag import WorkerFlag


class WorkerCancelled(RuntimeError):
	"""Raised cooperatively when a feature worker is cancelled."""


class BaseWorker(QObject):
	"""Common QObject worker lifecycle for one feature-specific background operation."""

	progress = Signal(str, int, str)
	succeeded = Signal(str, object)
	failed = Signal(str, str, str)
	cancelled = Signal(str)
	finished = Signal(str)

	def __init__(self, task_id: str, operation: str, payload: object, parent=None):
		super().__init__(parent)
		self.task_id = task_id
		self.operation = operation
		self.payload = payload
		self.flag = WorkerFlag()
		self._cancel_event = threading.Event()

	def _begin(self) -> None:
		self.flag.is_running = True

	def _succeed(self, result) -> None:
		self.succeeded.emit(self.task_id, result)

	def _fail(self, error: Exception) -> None:
		self.failed.emit(self.task_id, str(error), traceback.format_exc())

	def _cancel(self) -> None:
		self.cancelled.emit(self.task_id)

	def _finish(self) -> None:
		self.flag.is_running = False
		self.finished.emit(self.task_id)

	def cancel(self) -> None:
		"""Request cooperative cancellation without terminating the thread."""
		self.flag.stop_requested = True
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
