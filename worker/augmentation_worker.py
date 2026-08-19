from __future__ import annotations

import random
from collections import Counter
from pathlib import Path

from PyQt6.QtCore import pyqtSlot

from core.image_io import read_image, write_png
from core.logging_setup import get_logger
from service import augmentation_service, labeling_service
from worker.base_worker import BaseWorker, WorkerCancelled


class AugmentationWorker(BaseWorker):
	"""Run preview, AutoAugment, and orientation generation operations."""

	OPERATIONS = frozenset({"augmentation_preview", "auto_augment", "orientation_augment"})

	@pyqtSlot()
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

	@pyqtSlot()
	def _execute_auto_augment(self) -> None:
		self._begin()
		try:
			project = self.payload["project"]
			options = self.payload["options"]
			logger = get_logger()
			self.report(0, "Preparing inputs | Scanning target images and defect patches")
			logger.info("AutoAugment started: target_map=%s samples=%s poisson_mode=%s output=%s", options.target_map_key, options.generate_samples, options.poisson_mode, options.output_root)

			items = augmentation_service.collect_auto_yolo_items(project.mapsets, options.target_map_key)
			patches = augmentation_service.collect_target_map_patches(options.defect_root, options.target_map_key, project.root_path)
			logger.info("AutoAugment inputs: target_images=%s patches=%s", len(items), len(patches))
			if not items:
				self.report(100, "Complete | No target images were found")
				self._succeed({"images": 0, "labels": 0, "annotations": 0, "poisson_samples": 0, "split_images": {}, "class_distribution": {}, "failed_or_skipped": 0, "preview_image": "", "sample_images": [], "output_root": str(options.output_root)})
				return

			options.output_root.mkdir(parents=True, exist_ok=True)
			for split in ("train", "val", "test"):
				(options.output_root / "images" / split).mkdir(parents=True, exist_ok=True)
				(options.output_root / "labels" / split).mkdir(parents=True, exist_ok=True)

			rng = random.Random(options.seed)
			catalog = augmentation_service.class_catalog(project.root_path)
			patches_by_class: dict[int, list[Path]] = {}
			for patch_path in patches:
				class_id = augmentation_service.defect_class_id(patch_path, catalog)
				patches_by_class.setdefault(class_id, []).append(patch_path)

			output_written = 0
			annotations_written = 0
			split_images: Counter[str] = Counter()
			class_distribution: Counter[int] = Counter()
			preview_image: Path | None = None
			sample_images: list[Path] = []
			total_outputs = max(1, augmentation_service.estimate_auto_yolo_outputs(len(items), options, bool(patches_by_class)))
			poisson_total = max(0, int(options.generate_samples)) if options.enable_poisson and patches_by_class else 0

			def report_poisson(current: int, message: str) -> None:
				self.check_cancelled()
				percent = 5 + round(min(1.0, current / max(1, poisson_total)) * 30)
				self.report(percent, f"Generating Poisson samples | {message}")

			self.report(5, "Generating Poisson samples | Preparing base records")
			base_records = augmentation_service.build_base_records(items, patches_by_class, options, rng, report_poisson)
			poisson_written = sum(1 for record in base_records if record["kind"] == "poisson")

			self.report(36, "Shuffling and splitting dataset | Assigning base records to train, val, and test")
			split_records = augmentation_service.split_base_records(base_records, options, rng)
			for split, records in split_records.items():
				stage_name = {"train": "Writing train outputs", "val": "Writing val outputs", "test": "Writing test outputs"}.get(split, "Writing outputs")
				self.report(max(40, 40 + round(min(1.0, output_written / total_outputs) * 55)), f"{stage_name} | 0/{len(records)} base samples")
				for record_index, record in enumerate(records, start=1):
					self.check_cancelled()
					sample = augmentation_service.load_base_record_sample(record, options)
					if sample is None:
						continue
					name, image, labels = sample
					for staged_name, staged_image, staged_labels in augmentation_service.iter_staged_samples(split, name, image, labels, options, rng):
						self.check_cancelled()
						image_out, _label_out = augmentation_service.write_auto_yolo_sample(options, split, staged_name, staged_image, staged_labels)
						output_written += 1
						annotations_written += len(staged_labels)
						class_distribution.update(label.class_id for label in staged_labels)
						split_images[split] += 1
						if preview_image is None:
							preview_image = image_out
						if len(sample_images) < 3:
							sample_images.append(image_out)
						if output_written % 25 == 0 or output_written == total_outputs:
							self.report(40 + round(min(1.0, output_written / total_outputs) * 55), f"{stage_name} | {output_written}/{total_outputs} files")
					if record_index % 10 == 0:
						self.report(40 + round(min(1.0, output_written / total_outputs) * 55), f"{stage_name} | {record_index}/{len(records)} base samples")

			self.report(97, "Finalizing dataset | Removing temporary files and writing data.yaml")
			augmentation_service.cleanup_base_records(base_records)
			augmentation_service.write_yolo_yaml(options.output_root, options.class_names)
			logger.info("AutoAugment complete: images=%s labels=%s poisson_samples=%s output=%s", output_written, output_written, poisson_written, options.output_root)
			self.report(100, "Complete | AutoAugment dataset is ready")
			self._succeed({
				"images": output_written,
				"labels": output_written,
				"annotations": annotations_written,
				"poisson_samples": poisson_written,
				"split_images": dict(split_images),
				"class_distribution": dict(class_distribution),
				"failed_or_skipped": max(0, total_outputs - output_written),
				"preview_image": str(preview_image) if preview_image is not None else "",
				"sample_images": [str(path) for path in sample_images],
				"output_root": str(options.output_root),
			})
		except WorkerCancelled:
			self._cancel()
		except Exception as error:
			self._fail(error)
		finally:
			self._finish()

	@pyqtSlot()
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

