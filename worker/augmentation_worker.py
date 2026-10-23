from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Slot

from core.image_io import read_image, write_png
from service import augmentation_service, labeling_service
from worker.base_worker import BaseWorker, WorkerCancelled


class AugmentationWorker(BaseWorker):
	"""Run preview, AutoAugment, and orientation generation operations."""

	OPERATIONS = frozenset({"augmentation_preview", "auto_augment", "orientation_augment"})

	@Slot()
	def _execute_augmentation_preview(self) -> None:
		self._begin()
		try:
			pairs = self.payload["pairs"]
			self.report(5, "Creating previews")
			previews = augmentation_service.create_preview_samples(
				[pair[0] for pair in pairs],
				[pair[1] for pair in pairs],
				self.payload["options"],
			)
			self.report(100, "Preview complete")
			self._succeed(previews)
		except WorkerCancelled:
			self._cancel()
		except Exception as error:
			self._fail(error)
		finally:
			self._finish()

	@Slot()
	def _execute_auto_augment(self) -> None:
		"""Keep the worker lifecycle separate from the shared dataset pipeline."""
		self._begin()
		try:
			result = augmentation_service.run_auto_yolo_augmentation(
				self.payload["project"], self.payload["options"],
				progress_callback=lambda done, total, message: self.report(round(100 * done / max(1, total)), message),
				check_cancelled=self.check_cancelled,
			)
			self._succeed(result)
		except WorkerCancelled:
			self._cancel()
		except Exception as error:
			self._fail(error)
		finally:
			self._finish()

	@Slot()
	def _execute_orientation_augment(self) -> None:
		self._begin()
		try:
			options = self.payload["options"]
			mapsets = list(self.payload["mapsets"])
			output_root = Path(getattr(options, "output_root", Path.cwd() / "exports" / "orientation_augmentation"))
			angles = list(getattr(options, "angles", getattr(options, "rotation_angles", [90, 180, 270])))
			flip_codes = list(getattr(options, "flip_codes", [None, 1]))
			keep_size = bool(getattr(options, "keep_size", True))
			total = max(1, len(mapsets) * max(1, len(angles)) * max(1, len(flip_codes)))
			completed = 0
			written = 0
			output_root.mkdir(parents=True, exist_ok=True)
			self.report(0, "Preparing orientation augmentation")
			for mapset in mapsets:
				images = {}
				for key, path in mapset.maps:
					image = read_image(path)
					if image is not None:
						images[key] = image
				if not images:
					continue
				labels = labeling_service.load_txt(mapset.label_path) if mapset.label_path is not None else []
				bboxes = [(label.x_center, label.y_center, label.width, label.height) for label in labels]
				class_ids = [label.class_id for label in labels]
				for angle in angles:
					for flip_code in flip_codes:
						self.check_cancelled()
						completed += 1
						suffix = augmentation_service.orientation_suffix(angle, flip_code)
						sample_root = output_root / f"{mapset.name}_{suffix}"
						sample_root.mkdir(parents=True, exist_ok=True)
						transformed = augmentation_service.transform_mapset_orientation(images, bboxes, class_ids, float(angle), flip_code, keep_size)
						for key, image in transformed.images.items():
							write_png(sample_root / f"{key}.png", image)
						label_lines = [
							f"{class_id} {bbox[0]:.6f} {bbox[1]:.6f} {bbox[2]:.6f} {bbox[3]:.6f}"
							for bbox, class_id in zip(transformed.bboxes, transformed.class_ids)
						]
						(sample_root / f"{sample_root.name}.txt").write_text("\n".join(label_lines) + ("\n" if label_lines else ""), encoding="utf-8")
						written += 1
						self.report(round(completed / total * 100), f"Orientation {completed}/{total}")
			self.report(100, "Orientation augmentation complete")
			self._succeed({"samples": written, "output_root": str(output_root)})
		except WorkerCancelled:
			self._cancel()
		except Exception as error:
			self._fail(error)
		finally:
			self._finish()

