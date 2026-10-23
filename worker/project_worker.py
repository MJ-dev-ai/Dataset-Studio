from __future__ import annotations

from PySide6.QtCore import Slot

from core.mapset import discover_map_sets
from core.patch_clipboard import read_defect_pool
from service.project_service import export_defect_maps, save_mapset_copy, save_mapset_in_place
from service.labeling_service import load_class_catalog
from worker.base_worker import BaseWorker, WorkerCancelled


class ProjectWorker(BaseWorker):
	"""Run dataset discovery, MapSet persistence, and defect file operations."""

	OPERATIONS = frozenset({
		"import_defect_pool",
		"scan_dataset",
		"save_mapset",
		"save_all",
		"save_mapset_copy",
		"export_defect",
	})

	@Slot()
	def _execute_import_defect_pool(self) -> None:
		self._begin()
		try:
			self.report(0, "Reading Defect Pool")
			payloads = read_defect_pool(self.payload["root"])
			self.report(100, f"Loaded {len(payloads)} defects")
			self._succeed(payloads)
		except WorkerCancelled:
			self._cancel()
		except Exception as error:
			self._fail(error)
		finally:
			self._finish()

	@Slot()
	def _execute_scan_dataset(self) -> None:
		self._begin()
		try:
			mapsets = discover_map_sets(
				root=self.payload["folder"],
				map_specs=self.payload["map_specs"],
				image_extensions=self.payload["image_extensions"],
				cancelled=lambda: self.is_cancelled,
				progress=lambda count, path: self.report(min(99, count), path),
			)
			catalog = load_class_catalog(self.payload["folder"], mapsets, self.check_cancelled)
			self._succeed({"mapsets": mapsets, "class_catalog": catalog})
		except WorkerCancelled:
			self._cancel()
		except Exception as error:
			self._fail(error)
		finally:
			self._finish()

	@Slot()
	def _execute_save_mapset(self) -> None:
		self._begin()
		try:
			save_mapset_in_place(
				self.payload["request"],
				cancelled=lambda: (self.check_cancelled() or False),
				progress=self._report_units,
			)
			self._succeed(self.payload["label_path"])
		except WorkerCancelled:
			self._cancel()
		except Exception as error:
			self._fail(error)
		finally:
			self._finish()

	@Slot()
	def _execute_save_all(self) -> None:
		self._begin()
		try:
			targets = self.payload["targets"]
			total_units = self.payload["total_units"]
			completed_units = 0
			saved: list[tuple[str, str]] = []
			for mapset, request in targets:
				self.check_cancelled()

				def report(completed: int, total: int, message: str) -> None:
					del total
					value = round((completed_units + completed) / max(1, total_units) * 100)
					self.report(value, f"{mapset.name}: {message}")

				save_mapset_in_place(
					request,
					cancelled=lambda: (self.check_cancelled() or False),
					progress=report,
				)
				completed_units += len(request.maps) + 1
				saved.append((str(mapset.folder.resolve()), str(request.label_path)))
			self._succeed(saved)
		except WorkerCancelled:
			self._cancel()
		except Exception as error:
			self._fail(error)
		finally:
			self._finish()

	@Slot()
	def _execute_save_mapset_copy(self) -> None:
		self._begin()
		try:
			saved = save_mapset_copy(
				self.payload["request"],
				cancelled=lambda: (self.check_cancelled() or False),
				progress=self._report_units,
			)
			self._succeed(saved)
		except WorkerCancelled:
			self._cancel()
		except Exception as error:
			self._fail(error)
		finally:
			self._finish()

	@Slot()
	def _execute_export_defect(self) -> None:
		self._begin()
		try:
			payload = self.payload
			exported = export_defect_maps(
				payload["map_paths"],
				payload["output_root"],
				payload["defect_name"],
				payload["selection"],
				payload["bounds"],
				cancelled=lambda: self.is_cancelled,
				progress=lambda value, message: self.report(
					round(value / max(1, len(payload["map_paths"])) * 100), message
				),
			)
			self._succeed(exported)
		except WorkerCancelled:
			self._cancel()
		except Exception as error:
			self._fail(error)
		finally:
			self._finish()

	def _report_units(self, completed: int, total: int, message: str) -> None:
		self.report(round(completed / max(1, total) * 100), message)

