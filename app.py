from __future__ import annotations

import traceback
from dataclasses import dataclass
from time import monotonic

from PyQt6.QtCore import QObject, QThread, pyqtSlot

from config.settings import WORKER_SHUTDOWN_TIMEOUT_MS
from worker.augmentation_worker import AugmentationWorker
from worker.editing_worker import EditingWorker
from worker.export_worker import ExportWorker
from worker.project_worker import ProjectWorker


@dataclass
class _WorkerRuntime:
	thread: QThread
	worker: object


class DatasetEditorApp(QObject):
	"""Application coordinator: UI request in, worker thread out."""

	def __init__(self, window, logger, parent=None):
		super().__init__(parent)
		self.window = window
		self.logger = logger
		self._workers: dict[str, _WorkerRuntime] = {}
		self.window.task_requested.connect(self._start_worker)
		self.window.task_cancel_requested.connect(self._cancel_worker)
		self.window.shutdown_requested.connect(self._shutdown_from_window)

	@pyqtSlot(str, str, object)
	def _start_worker(self, task_id: str, operation: str, payload) -> None:
		if operation in ProjectWorker.OPERATIONS:
			self._start_project_worker(task_id, operation, payload)
		elif operation in EditingWorker.OPERATIONS:
			self._start_editing_worker(task_id, operation, payload)
		elif operation in AugmentationWorker.OPERATIONS:
			self._start_augmentation_worker(task_id, operation, payload)
		elif operation in ExportWorker.OPERATIONS:
			self._start_export_worker(task_id, operation, payload)
		else:
			self.window._on_task_failed(task_id, f"Unknown worker operation: {operation}", "")
			self.window._on_task_finished(task_id)

	def _start_project_worker(self, task_id: str, operation: str, payload) -> None:
		worker = ProjectWorker(task_id, operation, payload)
		run_methods = {
			"import_defect_pool": worker._execute_import_defect_pool,
			"scan_dataset": worker._execute_scan_dataset,
			"save_mapset": worker._execute_save_mapset,
			"save_all": worker._execute_save_all,
			"save_mapset_copy": worker._execute_save_mapset_copy,
			"export_defect": worker._execute_export_defect,
		}
		self._start_thread(task_id, worker, run_methods[operation])

	def _start_editing_worker(self, task_id: str, operation: str, payload) -> None:
		worker = EditingWorker(task_id, operation, payload)
		run_methods = {
			"healing": worker._execute_healing,
			"manual_poisson": worker._execute_manual_poisson,
		}
		self._start_thread(task_id, worker, run_methods[operation])

	def _start_augmentation_worker(self, task_id: str, operation: str, payload) -> None:
		worker = AugmentationWorker(task_id, operation, payload)
		run_methods = {
			"augmentation_preview": worker._execute_augmentation_preview,
			"auto_augment": worker._execute_auto_augment,
			"orientation_augment": worker._execute_orientation_augment,
		}
		self._start_thread(task_id, worker, run_methods[operation])

	def _start_export_worker(self, task_id: str, operation: str, payload) -> None:
		worker = ExportWorker(task_id, operation, payload)
		self._start_thread(task_id, worker, worker._execute_yolo_export)

	def _start_thread(self, task_id: str, worker, run_method) -> None:
		try:
			if task_id in self._workers:
				raise ValueError(f"Worker id is already active: {task_id}")
			thread = QThread(self)
			worker.setObjectName(f"DatasetEditor:{worker.operation}:{task_id[:8]}")
			worker.moveToThread(thread)
			thread.started.connect(run_method)
			worker.progress.connect(self.window._on_task_progress)
			worker.succeeded.connect(self.window._on_task_succeeded)
			worker.failed.connect(self.window._on_task_failed)
			worker.cancelled.connect(self.window._on_task_cancelled)
			worker.finished.connect(thread.quit)
			worker.finished.connect(self._release_worker)
			thread.finished.connect(worker.deleteLater)
			thread.finished.connect(thread.deleteLater)
			self._workers[task_id] = _WorkerRuntime(thread, worker)
			self.logger.info("Worker started: %s %s", worker.operation, task_id)
			thread.start()
		except Exception as exc:
			traceback_text = traceback.format_exc()
			self.logger.exception("Failed to start worker: %s", task_id)
			self.window._on_task_failed(task_id, str(exc), traceback_text)
			self.window._on_task_finished(task_id)

	@pyqtSlot(str)
	def _cancel_worker(self, task_id: str) -> None:
		runtime = self._workers.get(task_id)
		if runtime is not None:
			runtime.worker.cancel()

	@pyqtSlot(str)
	def _release_worker(self, task_id: str) -> None:
		runtime = self._workers.pop(task_id, None)
		if runtime is not None:
			self.logger.info("Worker finished: %s %s", runtime.worker.operation, task_id)
		self.window._on_task_finished(task_id)

	@pyqtSlot(int)
	def _shutdown_from_window(self, timeout_ms: int) -> None:
		self.window.complete_shutdown(self.shutdown(timeout_ms))

	def shutdown(self, timeout_ms: int = WORKER_SHUTDOWN_TIMEOUT_MS) -> bool:
		runtimes = tuple(self._workers.values())
		for runtime in runtimes:
			runtime.worker.cancel()
		deadline = monotonic() + max(0, timeout_ms) / 1000.0
		for runtime in runtimes:
			remaining_ms = max(0, int((deadline - monotonic()) * 1000))
			if runtime.thread.isRunning() and remaining_ms:
				runtime.thread.quit()
				runtime.thread.wait(remaining_ms)
		return not any(runtime.thread.isRunning() for runtime in runtimes)
