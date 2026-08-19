from __future__ import annotations

from PySide6.QtCore import Slot

from service import editing_service
from worker.base_worker import BaseWorker, WorkerCancelled


class EditingWorker(BaseWorker):
	"""Run MapSet-wide healing and manual patch composition operations."""

	OPERATIONS = frozenset({"healing", "manual_poisson"})

	@Slot()
	def _execute_healing(self) -> None:
		self._begin()
		try:
			self.report(0, "Healing Brush started")

			def report(completed: int, total: int, key: str) -> None:
				self.report(round(completed / max(1, total) * 100), f"Healing Brush {completed}/{total}: {key}")

			results = editing_service.apply_healing_to_images(
				self.payload["images"],
				self.payload["strokes"],
				self.payload["size"],
				self.payload["opacity"],
				check_cancelled=self.check_cancelled,
				progress=report,
			)
			self.report(100, "Healing Brush complete")
			self._succeed(results)
		except WorkerCancelled:
			self._cancel()
		except Exception as error:
			self._fail(error)
		finally:
			self._finish()

	@Slot()
	def _execute_manual_poisson(self) -> None:
		self._begin()
		try:
			payload = self.payload
			mode = payload["mode"]
			inputs = payload["composition_inputs"]
			results = {}
			total = len(inputs)
			for index, (map_key, values) in enumerate(inputs.items(), start=1):
				self.check_cancelled()
				target, patch, mask, x_pos, y_pos = values
				self.report(round((index - 1) / max(1, total) * 100), f"Applying Poisson to {map_key}")
				if mode == "boundary_mixed":
					result = editing_service.boundary_mixed_blend(target, patch, mask, x_pos, y_pos)
				elif mode == "hard_paste":
					result = editing_service.hard_paste(target, patch, mask, x_pos, y_pos)
				elif mode is None:
					result = editing_service.detail_preserve_blend(target, patch, mask, x_pos, y_pos, adapt_color="normal" not in map_key.casefold())
				else:
					result = editing_service.compose_patch(target, patch, mask, x_pos, y_pos, mode=mode, fallback=False)
				results[map_key] = result
			self.report(100, "Manual Poisson complete")
			self._succeed(results)
		except WorkerCancelled:
			self._cancel()
		except Exception as error:
			self._fail(error)
		finally:
			self._finish()
