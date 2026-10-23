from __future__ import annotations

from PySide6.QtCore import Slot

from service import yolo_export_service
from worker.base_worker import BaseWorker, WorkerCancelled


class ExportWorker(BaseWorker):
	"""Run YOLO dataset export and validate its image-label pairs."""

	OPERATIONS = frozenset({"yolo_export"})

	@Slot()
	def _execute_yolo_export(self) -> None:
		self._begin()
		try:
			options = self.payload["options"]
			result = yolo_export_service.export_dataset(
				self.payload["mapsets"],
				options,
				progress_callback=self._service_progress,
				check_cancelled=self.check_cancelled,
			)
			self._succeed(result)
		except WorkerCancelled:
			self._cancel()
		except Exception as error:
			self._fail(error)
		finally:
			self._finish()

	def _service_progress(self, completed: int, total: int, message: str) -> None:
		self.check_cancelled()
		self.report(round(completed / max(1, total) * 100), message)
