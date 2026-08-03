from __future__ import annotations

import random
import re
import shutil
import threading
import json
import os
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from core.image_io import read_image, write_png
from core.image_ops import rotate_bound
from core.logging_setup import get_logger
from core.mask_ops import make_nonzero_mask, nonzero_bbox
from service.editing_service import PoissonApi, clone_mode_from_text
from service.labeling_service import (
    YoloApi,
    YoloLabel,
    box_to_yolo_line,
    clip_bbox,
    parse_yolo_line,
    transform_bbox_affine,
    xyxy_to_yolo,
    yolo_to_xyxy,
)
from service.roi_service import roi_contour

os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
try:
    import albumentations as A
except ImportError:  # pragma: no cover
    A = None

@dataclass
class AutoYoloAugmentOptions:
    """Options for selected-map Poisson generation into a YOLO dataset."""

    output_root: Path
    defect_root: Path | None
    target_map_key: str
    class_names: list[str] = field(default_factory=list)
    generate_samples: int = 300
    max_same_class_per_image: int = 1
    poisson_mode: str = "Detail Preserve"
    include_original: bool = True
    enable_poisson: bool = True
    enable_flip: bool = True
    enable_rotation: bool = True
    enable_random: bool = True
    random_multiplier: int = 1
    apply_extra_augment: bool = True
    rotation_angles: list[float] = field(default_factory=lambda: [45, 90, 135, 180, 225, 270, 315])
    jitter_x_min: int = -20
    jitter_x_max: int = 20
    jitter_y_min: int = -20
    jitter_y_max: int = 20
    brightness_min: int = -20
    brightness_max: int = 20
    contrast_min: int = -10
    contrast_max: int = 10
    outside_tolerance: float = 0.02
    image_size: int = 2048
    train_ratio: float = 0.8
    val_ratio: float = 0.1
    test_ratio: float = 0.1
    seed: int = 0


@dataclass(frozen=True)
class AugmentationPreview:
    """Preview result produced before running a full augmentation task."""

    defect_path: Path
    target_path: Path
    result_image: np.ndarray


@dataclass(frozen=True)
class SyncedTransformResult:
    """Spatial transform result shared by all maps in one MapSet."""

    images: dict[str, np.ndarray]
    bboxes: list[tuple[float, float, float, float]]
    class_ids: list[int]

class BoundedImageCache:
    """LRU cache for decoded OpenCV images with a strict byte budget."""

    def __init__(self, max_bytes: int = 512 * 1024 * 1024):
        self.max_bytes = max(0, max_bytes)
        self.size_bytes = 0
        self._items: OrderedDict[str, np.ndarray] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, path: str | Path) -> np.ndarray | None:
        key = str(Path(path).resolve())
        with self._lock:
            value = self._items.get(key)
            if value is not None:
                self._items.move_to_end(key)
            return value

    def put(self, path: str | Path, image: np.ndarray) -> None:
        key = str(Path(path).resolve())
        with self._lock:
            previous = self._items.pop(key, None)
            if previous is not None:
                self.size_bytes -= previous.nbytes
            self._items[key] = image
            self.size_bytes += image.nbytes
            while self.size_bytes > self.max_bytes and self._items:
                _key, removed = self._items.popitem(last=False)
                self.size_bytes -= removed.nbytes

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self.size_bytes = 0

class AugmentationApi:
    """Auto-augmentation API used by the dedicated augmentation page."""

    def __init__(self, poisson_api: PoissonApi | None = None, yolo_api: YoloApi | None = None):
        self.poisson_api = poisson_api or PoissonApi()
        self.yolo_api = yolo_api or YoloApi()
        self.image_cache = BoundedImageCache()

    def discover_defect_paths(self, defect_root: str | Path | None) -> list[Path]:
        """Return usable defect patch images under a defect pool root."""
        if defect_root is None:
            return []
        root = Path(defect_root)
        if not root.is_dir():
            return []
        paths = []
        for path in root.rglob("*.png"):
            if path.stem.casefold().endswith("_mask"):
                continue
            paths.append(path.resolve())
        return sorted(paths, key=lambda path: str(path).casefold())

    def create_preview_samples(self, defect_paths, target_paths, options) -> list[AugmentationPreview]:
        """Create quick Poisson previews from patch/target path pairs."""
        previews: list[AugmentationPreview] = []
        mode = clone_mode_from_text(getattr(options, "poisson_mode", "Mixed"))
        for defect_path, target_path in zip(defect_paths, target_paths):
            defect = self._read_cached(defect_path)
            target = self._read_cached(target_path)
            if defect is None or target is None:
                continue
            mask = self._read_patch_mask(Path(defect_path), defect)
            if mask is None or cv2.countNonZero(mask) == 0:
                continue
            if defect.shape[0] > target.shape[0] or defect.shape[1] > target.shape[1]:
                scale = min(target.shape[0] / max(1, defect.shape[0]), target.shape[1] / max(1, defect.shape[1]), 1.0)
                size = (max(1, int(defect.shape[1] * scale)), max(1, int(defect.shape[0] * scale)))
                defect = cv2.resize(defect, size, interpolation=cv2.INTER_AREA)
                mask = cv2.resize(mask, size, interpolation=cv2.INTER_NEAREST)
            x_pos = max(0, (target.shape[1] - defect.shape[1]) // 2)
            y_pos = max(0, (target.shape[0] - defect.shape[0]) // 2)
            try:
                result = self.poisson_api.poisson_blend(target, defect, x_pos, y_pos, mask, mode=mode)
            except (cv2.error, ValueError):
                result = self.poisson_api.detail_preserve_blend(target, defect, mask, x_pos, y_pos)
            previews.append(AugmentationPreview(Path(defect_path), Path(target_path), result))
        return previews

    def run_orientation_augmentation(self, mapsets, options, progress_callback=None) -> dict[str, object]:
        """Generate orientation variants for full MapSets and their YOLO labels."""
        output_root = Path(getattr(options, "output_root", Path.cwd() / "exports" / "orientation_augmentation"))
        output_root.mkdir(parents=True, exist_ok=True)
        angles = list(getattr(options, "angles", getattr(options, "rotation_angles", [90, 180, 270])))
        flip_codes = list(getattr(options, "flip_codes", [None, 1]))
        keep_size = bool(getattr(options, "keep_size", True))
        mapsets = list(mapsets)
        total = max(1, len(mapsets) * max(1, len(angles)) * max(1, len(flip_codes)))
        completed = 0
        written = 0

        for mapset in mapsets:
            images = {}
            for key, path in mapset.maps:
                image = self._read_cached(path)
                if image is not None:
                    images[key] = image
            if not images:
                continue

            labels = self.yolo_api.load_txt(mapset.label_path) if mapset.label_path is not None else []
            bboxes = [(label.x_center, label.y_center, label.width, label.height) for label in labels]
            class_ids = [label.class_id for label in labels]
            for angle in angles:
                for flip_code in flip_codes:
                    completed += 1
                    suffix = self._orientation_suffix(angle, flip_code)
                    sample_root = output_root / f"{mapset.name}_{suffix}"
                    sample_root.mkdir(parents=True, exist_ok=True)
                    transformed = self._transform_mapset_orientation(
                        images,
                        bboxes,
                        class_ids,
                        float(angle),
                        flip_code,
                        keep_size,
                    )
                    for key, image in transformed.images.items():
                        write_png(sample_root / f"{key}.png", image)
                    label_lines = [
                        f"{class_id} {bbox[0]:.6f} {bbox[1]:.6f} {bbox[2]:.6f} {bbox[3]:.6f}"
                        for bbox, class_id in zip(transformed.bboxes, transformed.class_ids)
                    ]
                    (sample_root / f"{sample_root.name}.txt").write_text(
                        "\n".join(label_lines) + ("\n" if label_lines else ""),
                        encoding="utf-8",
                    )
                    written += 1
                    if progress_callback is not None:
                        progress_callback(completed, total, f"Orientation {completed}/{total}")

        return {"samples": written, "output_root": str(output_root)}

    def run_auto_yolo_augmentation(self, project, options: AutoYoloAugmentOptions, progress_callback=None):
        """Generate a YOLO dataset from global Poisson-balanced base samples."""
        logger = get_logger()

        def emit_progress(percent: int, message: str) -> None:
            """Emit monotonic, stage-weighted progress through the worker callback."""
            if progress_callback is not None:
                progress_callback(max(0, min(100, int(percent))), 100, message)

        emit_progress(0, "Preparing inputs | Scanning target images and defect patches")
        logger.info(
            "AutoAugment started: target_map=%s samples=%s poisson_mode=%s output=%s",
            options.target_map_key,
            options.generate_samples,
            options.poisson_mode,
            options.output_root,
        )
        items = self._collect_auto_yolo_items(project.mapsets, options.target_map_key)
        patches = self._collect_target_map_patches(options.defect_root, options.target_map_key, project.root_path)
        logger.info("AutoAugment inputs: target_images=%s patches=%s", len(items), len(patches))
        if not items:
            emit_progress(100, "Complete | No target images were found")
            return {
                "images": 0,
                "labels": 0,
                "annotations": 0,
                "poisson_samples": 0,
                "split_images": {},
                "class_distribution": {},
                "failed_or_skipped": 0,
                "preview_image": "",
                "sample_images": [],
                "output_root": str(options.output_root),
            }

        options.output_root.mkdir(parents=True, exist_ok=True)
        for split in self._split_names(options):
            (options.output_root / "images" / split).mkdir(parents=True, exist_ok=True)
            (options.output_root / "labels" / split).mkdir(parents=True, exist_ok=True)

        rng = random.Random(options.seed)
        catalog = self._class_catalog(project.root_path)
        patches_by_class: dict[int, list[Path]] = {}
        for patch_path in patches:
            class_id = self._defect_class_id(patch_path, catalog)
            patches_by_class.setdefault(class_id, []).append(patch_path)

        output_written = 0
        annotations_written = 0
        poisson_written = 0
        split_images: Counter[str] = Counter()
        class_distribution: Counter[int] = Counter()
        preview_image: Path | None = None
        sample_images: list[Path] = []
        total_outputs = max(1, self._estimate_auto_yolo_outputs(len(items), options, bool(patches_by_class)))
        poisson_total = (
            max(0, int(options.generate_samples))
            if options.enable_poisson and patches_by_class
            else 0
        )

        def report_poisson(current: int, message: str) -> None:
            fraction = current / max(1, poisson_total)
            percent = 5 + round(min(1.0, fraction) * 30)
            emit_progress(percent, f"Generating Poisson samples | {message}")

        def write_staged(split: str, name: str, image: np.ndarray, labels: list[YoloLabel]) -> None:
            nonlocal output_written, annotations_written, preview_image
            stage_name = {
                "train": "Writing train outputs",
                "val": "Writing val outputs",
                "test": "Writing test outputs",
            }.get(split, "Writing outputs")
            for staged_name, staged_image, staged_labels in self._iter_staged_samples(split, name, image, labels, options, rng):
                image_out, _label_out = self._write_auto_yolo_sample(
                    options, split, staged_name, staged_image, staged_labels
                )
                output_written += 1
                annotations_written += len(staged_labels)
                class_distribution.update(label.class_id for label in staged_labels)
                split_images[split] += 1
                if preview_image is None:
                    preview_image = image_out
                if len(sample_images) < 3:
                    sample_images.append(image_out)
                if output_written % 25 == 0 or output_written == total_outputs:
                    percent = 40 + round(min(1.0, output_written / total_outputs) * 55)
                    emit_progress(
                        percent,
                        f"{stage_name} | {output_written}/{total_outputs} files",
                    )

        emit_progress(5, "Generating Poisson samples | Preparing base records")
        base_records = self._build_base_records(items, patches_by_class, options, rng, report_poisson)
        poisson_written = sum(1 for record in base_records if record["kind"] == "poisson")

        emit_progress(36, "Shuffling and splitting dataset | Assigning base records to train, val, and test")
        split_records = self._split_base_records(base_records, options, rng)
        for split, records in split_records.items():
            stage_name = {
                "train": "Writing train outputs",
                "val": "Writing val outputs",
                "test": "Writing test outputs",
            }.get(split, "Writing outputs")
            emit_progress(
                max(40, 40 + round(min(1.0, output_written / total_outputs) * 55)),
                f"{stage_name} | 0/{len(records)} base samples",
            )
            for record_index, record in enumerate(records, start=1):
                sample = self._load_base_record_sample(record, options)
                if sample is None:
                    continue
                name, image, labels = sample
                write_staged(split, name, image, labels)
                if record_index % 10 == 0:
                    percent = 40 + round(min(1.0, output_written / total_outputs) * 55)
                    emit_progress(
                        percent,
                        f"{stage_name} | {record_index}/{len(records)} base samples",
                    )

        emit_progress(97, "Finalizing dataset | Removing temporary files and writing data.yaml")
        self._cleanup_base_records(base_records)
        self._write_yolo_yaml(options.output_root, options.class_names)
        logger.info(
            "AutoAugment complete: images=%s labels=%s poisson_samples=%s output=%s",
            output_written,
            output_written,
            poisson_written,
            options.output_root,
        )
        emit_progress(100, "Complete | AutoAugment dataset is ready")
        return {
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
        }

    def auto_yolo_summary(self, project, target_map_key: str, defect_root: Path | None = None) -> dict:
        """Return selected-map counts used by the AutoAugment page."""
        items = self._collect_auto_yolo_items(project.mapsets, target_map_key)
        grouped_items = self._group_auto_yolo_items(project.root_path, items)
        class_counts, _image_counts = self._auto_class_counts(items)
        existing_contours = 0
        for item in items:
            if self._mapset_contour(item["mapset"], target_map_key) is not None:
                existing_contours += 1
        return {
            "target_images": len(items),
            "folder_count": len(grouped_items),
            "existing_masks": existing_contours,
            "missing_masks": max(0, len(items) - existing_contours),
            "class_counts": dict(class_counts),
        }

    def project_map_keys(self, mapsets) -> list[str]:
        """Return stable map keys discovered in the current project."""
        keys = []
        seen = set()
        for mapset in mapsets:
            for key, _path in mapset.maps:
                if key not in seen:
                    seen.add(key)
                    keys.append(key)
        return keys

    def _collect_auto_yolo_items(self, mapsets, target_map_key: str) -> list[dict]:
        items = []
        for mapset in mapsets:
            paths = mapset.map_paths
            image_path = paths.get(target_map_key)
            label_path = self._label_path_for_mapset(mapset)
            if image_path is None or label_path is None:
                continue
            labels = self.yolo_api.load_txt(label_path)
            items.append({"mapset": mapset, "image_path": image_path, "label_path": label_path, "labels": labels})
        return items

    def _collect_target_map_patches(self, defect_root: Path | None, target_map_key: str, project_root: Path) -> list[Path]:
        if defect_root is None or not Path(defect_root).is_dir():
            defect_root = project_root / "exports" / "defects"
        root = Path(defect_root)
        if not root.is_dir():
            return []
        target = target_map_key.casefold()
        patches = []
        for path in root.rglob("*.png"):
            stem = path.stem.casefold()
            if stem.endswith("_mask"):
                continue
            if target in stem or stem.endswith(target.replace("_map", "")):
                patches.append(path.resolve())
        return sorted(patches, key=lambda path: str(path).casefold())

    def _auto_class_counts(self, items: list[dict]) -> tuple[dict[int, int], dict[str, dict[int, int]]]:
        class_counts: dict[int, int] = {}
        image_counts: dict[str, dict[int, int]] = {}
        for item in items:
            counts: dict[int, int] = {}
            for label in item["labels"]:
                counts[label.class_id] = counts.get(label.class_id, 0) + 1
                class_counts[label.class_id] = class_counts.get(label.class_id, 0) + 1
            image_counts[item["mapset"].name] = counts
        return class_counts, image_counts

    def _choose_lowest_count_class(self, class_counts: dict[int, int], patches_by_class: dict[int, list[Path]]) -> int:
        return min(patches_by_class, key=lambda class_id: (class_counts.get(class_id, 0), class_id))

    def _choose_target_item(self, items: list[dict], image_class_counts: dict[str, dict[int, int]], class_id: int, options: AutoYoloAugmentOptions, rng) -> dict | None:
        candidates = []
        for item in items:
            counts = image_class_counts.get(item["mapset"].name, {})
            same_count = counts.get(class_id, 0)
            if same_count >= max(1, int(options.max_same_class_per_image)):
                continue
            candidates.append((same_count, sum(counts.values()), item))
        if not candidates:
            return None
        candidates.sort(key=lambda value: (value[0], value[1], value[2]["mapset"].name))
        best_same = candidates[0][0]
        best_total = candidates[0][1]
        best = [item for same, total, item in candidates if same == best_same and total == best_total]
        return rng.choice(best)


    def _choose_weighted_low_label_item(self, items: list[dict], image_class_counts: dict[str, dict[int, int]], rng) -> dict | None:
        candidates = []
        for item in items:
            counts = image_class_counts.get(item["mapset"].name, {})
            candidates.append((sum(counts.values()), item["mapset"].name, item))
        if not candidates:
            return None
        candidates.sort(key=lambda value: (value[0], value[1]))
        weights = list(range(len(candidates), 0, -1))
        return rng.choices([item for _count, _name, item in candidates], weights=weights, k=1)[0]

    def _compose_auto_yolo_sample(self, item: dict, patch_path: Path, class_id: int, options: AutoYoloAugmentOptions, rng) -> tuple[np.ndarray, list[YoloLabel]] | None:
        target = self._read_cached(item["image_path"])
        if target is None:
            return None
        applied = self._apply_poisson_defect(
            item,
            np.ascontiguousarray(target),
            list(item["labels"]),
            patch_path,
            class_id,
            options,
            rng,
        )
        if applied[0] is None:
            return None
        blended, labels = applied[0]
        output_image, output_labels = self._resize_for_yolo(blended, labels, options.image_size)
        return output_image, output_labels

    def _apply_poisson_defect(self, item: dict, target: np.ndarray, labels: list[YoloLabel], patch_path: Path, class_id: int, options: AutoYoloAugmentOptions, rng) -> tuple[tuple[np.ndarray, list[YoloLabel]] | None, str]:
        patch = self._read_cached(patch_path)
        if patch is None:
            return None, "patch_read_failed"

        patch_mask = self._read_patch_mask(patch_path, patch)
        if patch_mask is None or cv2.countNonZero(patch_mask) == 0:
            return None, "empty_patch_mask"

        patch, patch_mask = self._auto_transform_patch_and_mask(patch, patch_mask, options, rng)
        if patch is None or patch_mask is None or cv2.countNonZero(patch_mask) == 0:
            return None, "empty_transformed_mask"

        target_h, target_w = target.shape[:2]
        patch_h, patch_w = patch.shape[:2]
        if patch_h > target_h or patch_w > target_w:
            return None, "patch_larger_than_target"

        roi_contour = self._load_or_create_placement_contour(item, target, options.target_map_key)
        if roi_contour is None:
            return None, "roi_missing"

        occupied_boxes = [
            (
                int(round((label.x_center - label.width * 0.5) * target_w)),
                int(round((label.y_center - label.height * 0.5) * target_h)),
                int(round((label.x_center + label.width * 0.5) * target_w)),
                int(round((label.y_center + label.height * 0.5) * target_h)),
            )
            for label in labels
        ]
        position = choose_patch_position_in_contour(
            roi_contour,
            target.shape,
            patch,
            rng,
            patch_mask=patch_mask,
            occupied_boxes=occupied_boxes,
        )
        if position is None:
            return None, "placement_failed"

        x_pos, y_pos = position
        try:
            composition_mode = options.poisson_mode.strip().casefold()
            if composition_mode == "boundary mixed":
                blended = self.poisson_api.boundary_mixed_blend(
                    target, patch, patch_mask, x_pos, y_pos
                )
            elif composition_mode in {"detail preserve", "copy paste", "copypaste"}:
                blended = self.poisson_api.detail_preserve_blend(
                    target,
                    patch,
                    patch_mask,
                    x_pos,
                    y_pos,
                    adapt_color="normal" not in options.target_map_key.casefold(),
                )
            else:
                mode = clone_mode_from_text(options.poisson_mode)
                blended = self.poisson_api.poisson_blend(target, patch, x_pos, y_pos, patch_mask, mode=mode)
        except ValueError:
            return None, "invalid_poisson_mode"
        except (cv2.error, ValueError):
            return None, "poisson_blend_failed"

        box = nonzero_bbox(patch_mask)
        if box is None:
            return None, "label_bbox_failed"

        local_x, local_y, width, height = box
        new_line = box_to_yolo_line(
            class_id,
            (x_pos + local_x, y_pos + local_y, x_pos + local_x + width, y_pos + local_y + height),
            target.shape[1],
            target.shape[0],
        )
        parsed = parse_yolo_line(new_line)
        output_labels = list(labels)
        if parsed:
            output_labels.append(YoloLabel(*parsed))

        return (blended, output_labels), "success"

    def _load_original_auto_sample(self, item: dict, options: AutoYoloAugmentOptions) -> tuple[str, np.ndarray, list[YoloLabel]] | None:
        """Load one original target image and resize it for YOLO output."""
        image = self._read_cached(item["image_path"])
        if image is None:
            return None
        image, labels = self._resize_for_yolo(np.ascontiguousarray(image), list(item["labels"]), options.image_size)
        return item["mapset"].name, image, labels

    def _build_base_records(self, items: list[dict], patches_by_class: dict[int, list[Path]], options: AutoYoloAugmentOptions, rng, report) -> list[dict]:
        records = []
        if options.include_original:
            for item in items:
                records.append({
                    "kind": "original",
                    "name": item["mapset"].name,
                    "item": item,
                })

        if not options.enable_poisson or not patches_by_class or options.generate_samples <= 0 or not items:
            return records

        class_counts, image_class_counts = self._auto_class_counts(items)
        for class_id in patches_by_class:
            class_counts.setdefault(class_id, 0)

        cache_dir = options.output_root / "_autoaugment_base_cache" / "poisson"
        shutil.rmtree(cache_dir, ignore_errors=True)
        cache_dir.mkdir(parents=True, exist_ok=True)

        written = 0
        attempts = 0
        failure_counts: Counter[str] = Counter()
        num_poisson = max(0, int(options.generate_samples))
        num_defects = max(1, int(options.max_same_class_per_image))
        max_attempts = max(num_poisson * 3, num_poisson + 20)

        while written < num_poisson and attempts < max_attempts:
            attempts += 1

            target_item = self._choose_weighted_low_label_item(items, image_class_counts, rng)
            if target_item is None:
                failure_counts["target_select_failed"] += 1
                continue

            target = self._read_cached(target_item["image_path"])
            if target is None:
                failure_counts["target_read_failed"] += 1
                continue

            result_image = np.ascontiguousarray(target)
            result_labels = list(target_item["labels"])
            target_name = target_item["mapset"].name

            working_class_counts = dict(class_counts)
            working_image_counts = dict(image_class_counts.get(target_name, {}))
            for label in result_labels:
                working_class_counts[label.class_id] = working_class_counts.get(label.class_id, 0) + 1
                working_image_counts[label.class_id] = working_image_counts.get(label.class_id, 0) + 1
            for class_id in patches_by_class:
                working_class_counts.setdefault(class_id, 0)

            success_count = 0
            for _defect_index in range(num_defects):
                class_id = self._choose_lowest_count_class(working_class_counts, patches_by_class)
                patch_path = rng.choice(patches_by_class[class_id])
                applied, reason = self._apply_poisson_defect(target_item, result_image, result_labels, patch_path, class_id, options, rng)
                if applied is None:
                    failure_counts[reason] += 1
                    continue

                result_image, result_labels = applied
                working_class_counts[class_id] = working_class_counts.get(class_id, 0) + 1
                working_image_counts[class_id] = working_image_counts.get(class_id, 0) + 1
                success_count += 1

            if success_count <= 0:
                failure_counts["sample_failed"] += 1
                if attempts % 10 == 0:
                    report(written, self._format_poisson_debug_message("Poisson attempt", attempts, max_attempts, written, num_poisson, failure_counts))
                continue

            resized, labels = self._resize_for_yolo(result_image, result_labels, options.image_size)
            written += 1
            class_counts = working_class_counts
            image_class_counts[target_name] = working_image_counts

            base_name = f"{target_name}_poisson_{written:06d}"
            image_path = cache_dir / f"{_safe_output_name(base_name)}.png"
            write_png(image_path, resized)
            records.append({
                "kind": "poisson",
                "name": base_name,
                "image_path": image_path,
                "labels": labels,
            })

            if written % 10 == 0 or written == num_poisson:
                report(written, self._format_poisson_debug_message("Poisson base", attempts, max_attempts, written, num_poisson, failure_counts))

        if written < num_poisson:
            message = self._format_poisson_debug_message("Poisson incomplete", attempts, max_attempts, written, num_poisson, failure_counts)
            get_logger().warning(message)
            report(written, message)
        else:
            message = self._format_poisson_debug_message("Poisson complete", attempts, max_attempts, written, num_poisson, failure_counts)
            get_logger().info(message)
            report(written, message)

        return records

    @staticmethod
    def _format_poisson_debug_message(prefix: str, attempts: int, max_attempts: int, written: int, requested: int, failure_counts: Counter[str]) -> str:
        if failure_counts:
            details = ", ".join(f"{key}={value}" for key, value in failure_counts.most_common(4))
        else:
            details = "none"
        return f"{prefix}: generated {written}/{requested}, attempts {attempts}/{max_attempts}, failures [{details}]"

    def _load_base_record_sample(self, record: dict, options: AutoYoloAugmentOptions) -> tuple[str, np.ndarray, list[YoloLabel]] | None:
        if record["kind"] == "original":
            item = record["item"]
            image = self._read_cached(item["image_path"])
            if image is None:
                return None
            image, labels = self._resize_for_yolo(np.ascontiguousarray(image), list(item["labels"]), options.image_size)
            return record["name"], image, labels

        image = self._read_cached(record["image_path"])
        if image is None:
            return None
        return record["name"], np.ascontiguousarray(image), list(record["labels"])

    @staticmethod
    def _cleanup_base_records(base_records: list[dict]) -> None:
        cache_roots = set()
        for record in base_records:
            image_path = record.get("image_path")
            if image_path is not None:
                cache_roots.add(Path(image_path).parent)
        for cache_root in cache_roots:
            shutil.rmtree(cache_root, ignore_errors=True)

    def _iter_staged_samples(self, split: str, name: str, image: np.ndarray, labels: list[YoloLabel], options: AutoYoloAugmentOptions, rng):
        split_key = str(split).casefold()
        enable_flip = options.enable_flip and split_key in {"train", "val"}
        enable_rotation = options.enable_rotation and split_key in {"train", "val"}
        enable_random = options.enable_random and split_key == "train"

        flip_variants = [("", image, labels)]
        if enable_flip:
            flipped_image, flipped_labels = self._flip_yolo_sample(image, labels)
            flip_variants.append(("_hflip", flipped_image, flipped_labels))

        angles = [float(angle) for angle in options.rotation_angles] if enable_rotation else []
        if not angles:
            angles = [None]
        random_count = self._random_factor(options) if enable_random else 1

        for flip_suffix, flip_image, flip_labels in flip_variants:
            for angle in angles:
                if angle is None:
                    staged_name = f"{name}{flip_suffix}"
                    staged_image = flip_image
                    staged_labels = flip_labels
                else:
                    staged_image, staged_labels = self._rotate_yolo_sample(flip_image, flip_labels, angle)
                    staged_name = f"{name}{flip_suffix}_rot{int(round(angle)) % 360:03d}"

                if enable_random:
                    for random_index in range(random_count):
                        random_image, random_labels = self._random_yolo_sample(staged_image, staged_labels, options, rng)
                        yield f"{staged_name}_rand{random_index + 1:03d}", random_image, random_labels
                else:
                    yield staged_name, staged_image, staged_labels

    def _write_auto_yolo_sample(
        self,
        options: AutoYoloAugmentOptions,
        split: str,
        name: str,
        image: np.ndarray,
        labels: list[YoloLabel],
    ) -> tuple[Path, Path]:
        """Write one generated sample and return its image and label paths."""
        safe_name = _safe_output_name(name)
        image_out = options.output_root / "images" / split / f"{safe_name}.png"
        label_out = options.output_root / "labels" / split / f"{safe_name}.txt"
        if not write_png(image_out, image):
            raise OSError(f"Failed to write AutoAugment image: {image_out}")
        label_out.write_text("\n".join(self._labels_to_yolo_lines(labels)) + ("\n" if labels else ""), encoding="utf-8")
        return image_out, label_out

    def _flip_yolo_sample(self, image: np.ndarray, labels: list[YoloLabel]) -> tuple[np.ndarray, list[YoloLabel]]:
        """Horizontally flip one YOLO image and labels."""
        flipped = cv2.flip(image, 1)
        flipped_labels = [
            YoloLabel(label.class_id, 1.0 - label.x_center, label.y_center, label.width, label.height)
            for label in labels
        ]
        return flipped, flipped_labels

    def _rotate_yolo_sample(self, image: np.ndarray, labels: list[YoloLabel], angle: float) -> tuple[np.ndarray, list[YoloLabel]]:
        """Rotate one square YOLO image and transform labels in the same coordinate space."""
        height, width = image.shape[:2]
        center = ((width - 1) * 0.5, (height - 1) * 0.5)
        matrix_2x3 = cv2.getRotationMatrix2D(center, angle, 1.0).astype(np.float32)
        rotated = cv2.warpAffine(image, matrix_2x3, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        matrix = np.eye(3, dtype=np.float32)
        matrix[:2, :] = matrix_2x3
        return rotated, self._transform_labels(labels, matrix, width, height)

    def _random_yolo_sample(self, image: np.ndarray, labels: list[YoloLabel], options: AutoYoloAugmentOptions, rng) -> tuple[np.ndarray, list[YoloLabel]]:
        """Apply random jitter, brightness, and contrast to one YOLO sample."""
        result = image
        height, width = result.shape[:2]
        matrix = np.eye(3, dtype=np.float32)
        dx = rng.randint(min(options.jitter_x_min, options.jitter_x_max), max(options.jitter_x_min, options.jitter_x_max))
        dy = rng.randint(min(options.jitter_y_min, options.jitter_y_max), max(options.jitter_y_min, options.jitter_y_max))
        if dx or dy:
            matrix_2x3 = np.array([[1, 0, dx], [0, 1, dy]], dtype=np.float32)
            result = cv2.warpAffine(result, matrix_2x3, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            matrix[:2, :] = matrix_2x3
            labels = self._transform_labels(labels, matrix, width, height)
        brightness = rng.randint(min(options.brightness_min, options.brightness_max), max(options.brightness_min, options.brightness_max))
        contrast = rng.randint(min(options.contrast_min, options.contrast_max), max(options.contrast_min, options.contrast_max))
        if brightness or contrast:
            alpha = 1.0 + float(contrast) / 100.0
            result = np.clip(result.astype(np.float32) * alpha + float(brightness), 0, 255).astype(np.uint8)
        return result, labels

    @staticmethod
    def _estimate_auto_yolo_outputs(original_count: int, options: AutoYoloAugmentOptions) -> int:
        """Return the expected final output count for progress and UI summary."""
        base_count = (original_count if options.include_original else 0) + (options.generate_samples if options.enable_poisson else 0)
        return base_count * AugmentationApi._flip_factor(options) * AugmentationApi._rotation_factor(options) * AugmentationApi._random_factor(options)

    @staticmethod
    def _flip_factor(options: AutoYoloAugmentOptions) -> int:
        return 2 if options.enable_flip else 1

    @staticmethod
    def _rotation_factor(options: AutoYoloAugmentOptions) -> int:
        return max(1, len(options.rotation_angles)) if options.enable_rotation else 1

    @staticmethod
    def _random_factor(options: AutoYoloAugmentOptions) -> int:
        return max(1, int(options.random_multiplier)) if options.enable_random else 1

    @staticmethod
    def _labels_to_yolo_lines(labels: list[YoloLabel]) -> list[str]:
        """Convert YOLO label objects to txt lines."""
        return [
            f"{label.class_id} {label.x_center:.6f} {label.y_center:.6f} {label.width:.6f} {label.height:.6f}"
            for label in labels
        ]

    def _read_patch_mask(self, patch_path: Path, patch: np.ndarray) -> np.ndarray:
        mask_path = patch_path.with_name(f"{patch_path.stem}_mask.png")
        if mask_path.is_file():
            mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            if mask is not None:
                if mask.shape[:2] != patch.shape[:2]:
                    mask = cv2.resize(mask, (patch.shape[1], patch.shape[0]), interpolation=cv2.INTER_NEAREST)
                return np.where(mask > 0, 255, 0).astype(np.uint8)
        return make_nonzero_mask(patch)

    def _auto_transform_patch_and_mask(self, patch: np.ndarray, patch_mask: np.ndarray, options: AutoYoloAugmentOptions, rng) -> tuple[np.ndarray, np.ndarray]:
        scale = rng.uniform(0.9, 1.1)
        size = (max(1, round(patch.shape[1] * scale)), max(1, round(patch.shape[0] * scale)))
        result = cv2.resize(patch, size, interpolation=cv2.INTER_LINEAR)
        result_mask = cv2.resize(patch_mask, size, interpolation=cv2.INTER_NEAREST)
        if options.apply_extra_augment and options.rotation_angles:
            angle = float(rng.choice(options.rotation_angles))
            result = rotate_bound(result, angle)
            result_mask = rotate_bound(result_mask, angle)
        result_mask = np.where(result_mask > 0, 255, 0).astype(np.uint8)
        return result, result_mask

    def _load_or_create_placement_contour(self, item: dict, image: np.ndarray, target_map_key: str) -> np.ndarray | None:
        contour = self._mapset_contour(item["mapset"], target_map_key)
        if contour is not None:
            return contour

        source_image = self._auto_roi_reference_image_for_item(item, image, target_map_key)
        contours = roi_contour(source_image, mode="auto", image_shape=source_image.shape[:2])
        if not contours:
            get_logger().warning("AutoAugment ROI creation failed: mapset=%s target_map=%s", item["mapset"].name, target_map_key)
            return None
        get_logger().info("AutoAugment ROI created from reference image: mapset=%s target_map=%s", item["mapset"].name, target_map_key)
        return np.asarray(contours[0], dtype=np.float32).reshape(-1, 2)

    def _auto_roi_reference_image_for_item(self, item: dict, fallback_image: np.ndarray, target_map_key: str) -> np.ndarray:
        """Return the current target map image used when a saved ROI contour is missing."""
        image_path = item["mapset"].map_paths.get(target_map_key)
        if image_path is None:
            return fallback_image
        image = self._read_cached(image_path)
        if image is None or image.shape[:2] != fallback_image.shape[:2]:
            return fallback_image
        return image

    def _mapset_contour(self, mapset, target_map_key: str) -> np.ndarray | None:
        contours = getattr(mapset, "roi_contour", tuple())
        if not contours:
            return None
        points = contours[0]
        if not points or len(points) < 3:
            return None
        return np.asarray(points, dtype=np.float32).reshape(-1, 2)

    def _resize_for_yolo(self, image: np.ndarray, labels: list[YoloLabel], image_size: int) -> tuple[np.ndarray, list[YoloLabel]]:
        size = max(1, int(image_size))
        height, width = image.shape[:2]
        result = cv2.resize(image, (size, size), interpolation=cv2.INTER_AREA)
        scale = np.array([[size / max(1, width), 0, 0], [0, size / max(1, height), 0], [0, 0, 1]], dtype=np.float32)
        return result, self._transform_labels(labels, scale, size, size, source_width=width, source_height=height)

    def _transform_labels(self, labels: list[YoloLabel], matrix: np.ndarray, width: int, height: int, source_width: int | None = None, source_height: int | None = None) -> list[YoloLabel]:
        src_w = source_width or width
        src_h = source_height or height
        output = []
        for label in labels:
            box = yolo_to_xyxy(label.x_center, label.y_center, label.width, label.height, src_w, src_h)
            transformed = transform_bbox_affine(box, matrix)
            clipped = clip_bbox(transformed, width, height)
            if clipped is None:
                continue
            x_center, y_center, box_width, box_height = xyxy_to_yolo(clipped, width, height)
            if box_width <= 0 or box_height <= 0:
                continue
            output.append(YoloLabel(label.class_id, x_center, y_center, box_width, box_height))
        return output

    def _split_names(self, options: AutoYoloAugmentOptions) -> tuple[str, ...]:
        return ("train", "val", "test") if options.test_ratio > 0 else ("train", "val")

    def _group_auto_yolo_items(self, project_root: Path, items: list[dict]) -> OrderedDict[str, list[dict]]:
        groups: OrderedDict[str, list[dict]] = OrderedDict()
        for item in items:
            group_name = self._item_group_name(project_root, item)
            groups.setdefault(group_name, []).append(item)
        return groups

    @staticmethod
    def _item_group_name(project_root: Path, item: dict) -> str:
        image_path = Path(item["image_path"]).resolve()
        try:
            relative = image_path.relative_to(Path(project_root).resolve())
        except ValueError:
            return image_path.parent.name or "root"
        if len(relative.parts) <= 1:
            return "root"
        return relative.parts[0]

    @staticmethod
    def _output_base_name(group_name: str, name: str) -> str:
        if group_name in {"", ".", "root"}:
            return name
        return f"{group_name}_{name}"

    def _split_base_records(self, records: list[dict], options: AutoYoloAugmentOptions, rng) -> dict[str, list[dict]]:
        shuffled = list(records)
        rng.shuffle(shuffled)
        total = len(shuffled)
        train_count = min(total, max(0, int(total * options.train_ratio)))
        remaining = total - train_count
        val_count = min(remaining, max(0, int(total * options.val_ratio)))
        splits = {
            "train": shuffled[:train_count],
            "val": shuffled[train_count:train_count + val_count],
        }
        if options.test_ratio > 0:
            splits["test"] = shuffled[train_count + val_count:]
        elif train_count + val_count < total:
            splits["val"].extend(shuffled[train_count + val_count:])
        return splits

    @staticmethod
    def _estimate_auto_yolo_outputs(original_count: int, options: AutoYoloAugmentOptions, has_patches: bool = True) -> int:
        train_stage_factor = AugmentationApi._flip_factor(options) * AugmentationApi._rotation_factor(options) * AugmentationApi._random_factor(options)
        val_stage_factor = AugmentationApi._flip_factor(options) * AugmentationApi._rotation_factor(options)
        poisson_count = options.generate_samples if options.enable_poisson and has_patches else 0
        train_count, val_count, test_count = AugmentationApi._split_count_values(original_count + poisson_count, options)
        return train_count * train_stage_factor + val_count * val_stage_factor + test_count

    @staticmethod
    def _estimate_auto_yolo_outputs_by_group(grouped_items: OrderedDict[str, list[dict]], options: AutoYoloAugmentOptions, has_patches: bool = True) -> int:
        original_count = sum(len(group_items) for group_items in grouped_items.values()) if options.include_original else 0
        return AugmentationApi._estimate_auto_yolo_outputs(original_count, options, has_patches)


    @staticmethod
    def _split_count_values(total: int, options: AutoYoloAugmentOptions) -> tuple[int, int, int]:
        train_count = min(total, max(0, int(total * options.train_ratio)))
        remaining = total - train_count
        val_count = min(remaining, max(0, int(total * options.val_ratio)))
        if options.test_ratio > 0:
            test_count = max(0, total - train_count - val_count)
        else:
            test_count = 0
            val_count += max(0, total - train_count - val_count)
        return train_count, val_count, test_count

    def _write_yolo_yaml(self, root: Path, class_names: list[str]) -> None:
        names = class_names or ["class0"]
        lines = ["path: .", "train: images/train", "val: images/val", "test: images/test", "names:"]
        for class_id, class_name in enumerate(names):
            lines.append(f"  {class_id}: {class_name}")
        (root / "data.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _label_path_for_mapset(self, mapset) -> Path | None:
        if mapset.label_path is not None and Path(mapset.label_path).is_file():
            return Path(mapset.label_path)
        candidate = mapset.folder / f"{mapset.name}.txt"
        return candidate if candidate.is_file() else None

    def _class_catalog(self, project_root: Path) -> dict[str, int]:
        """Load class-name to ID mappings used by exported defect folders."""
        path = project_root / "labels.json"
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        items = payload.get("labels", payload) if isinstance(payload, dict) else payload
        catalog = {}
        for index, item in enumerate(items if isinstance(items, list) else []):
            if isinstance(item, dict):
                name = str(item.get("class_name", item.get("name", ""))).strip()
                class_id = int(item.get("class_id", item.get("id", index)))
                if name:
                    catalog[name.casefold()] = class_id
        return catalog

    @staticmethod
    def _defect_class_id(path: Path, catalog: dict[str, int]) -> int:
        return catalog.get(path.parent.name.casefold(), 0)

    def _read_cached(self, path: str | Path) -> np.ndarray | None:
        cached = self.image_cache.get(path)
        if cached is not None:
            return cached
        image = read_image(path)
        if image is not None:
            self.image_cache.put(path, image)
        return image

    def _transform_mapset_orientation(
        self,
        images: dict[str, np.ndarray],
        bboxes: list[tuple[float, float, float, float]],
        class_ids: list[int],
        angle: float,
        flip_code,
        keep_size: bool,
    ) -> SyncedTransformResult:
        if albumentations_available() and keep_size:
            return apply_synced_orientation(images, bboxes, class_ids, angle, flip_code)

        output_images = {}
        label_matrix = None
        for key, image in images.items():
            transformed, matrix = orient_image(image, int(round(angle)), flip_code, keep_size)
            output_images[key] = transformed
            if label_matrix is None:
                label_matrix = matrix
                label_shape = transformed.shape[:2]
                source_shape = image.shape[:2]
        if label_matrix is None:
            return SyncedTransformResult({}, [], [])
        width = label_shape[1]
        height = label_shape[0]
        source_width = source_shape[1]
        source_height = source_shape[0]
        labels = [
            YoloLabel(class_id, bbox[0], bbox[1], bbox[2], bbox[3])
            for bbox, class_id in zip(bboxes, class_ids)
        ]
        transformed_labels = self._transform_labels(
            labels,
            label_matrix,
            width,
            height,
            source_width=source_width,
            source_height=source_height,
        )
        return SyncedTransformResult(
            output_images,
            [(label.x_center, label.y_center, label.width, label.height) for label in transformed_labels],
            [label.class_id for label in transformed_labels],
        )

    @staticmethod
    def _orientation_suffix(angle: float, flip_code) -> str:
        flip_name = {None: "noflip", 1: "hflip", 0: "vflip", -1: "hvflip"}.get(flip_code, f"flip{flip_code}")
        return f"rot{int(round(angle)) % 360:03d}_{flip_name}"

def _safe_output_name(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]+", "_", str(name)).strip("._") or "sample"


def albumentations_available() -> bool:
    return A is not None


def apply_synced_orientation(
    images: dict[str, np.ndarray],
    bboxes: list[tuple[float, float, float, float]],
    class_ids: list[int],
    angle: float,
    flip_code,
) -> SyncedTransformResult:
    """Apply one spatial transform to every map and its YOLO boxes with Albumentations."""
    if A is None:
        raise RuntimeError("Albumentations is not installed")
    if not images:
        return SyncedTransformResult({}, [], [])
    if len(bboxes) != len(class_ids):
        raise ValueError("bboxes and class_ids must have the same length")

    base_key = "albedo_map" if "albedo_map" in images else next(iter(images))
    base = images[base_key]
    transforms = []
    if flip_code in (1, -1):
        transforms.append(A.HorizontalFlip(p=1.0))
    if flip_code in (0, -1):
        transforms.append(A.VerticalFlip(p=1.0))
    if angle % 360:
        transforms.append(
            A.Rotate(
                limit=(-float(angle), -float(angle)),
                interpolation=cv2.INTER_LINEAR,
                border_mode=cv2.BORDER_CONSTANT,
                fill=0,
                fill_mask=0,
                rotate_method="largest_box",
                crop_border=False,
                p=1.0,
            )
        )

    other_keys = [key for key in images if key != base_key]
    compose = A.Compose(
        transforms,
        bbox_params=A.BboxParams(
            format="yolo",
            label_fields=["class_ids"],
            clip=True,
            filter_invalid_bboxes=True,
        ),
        additional_targets={key: "image" for key in other_keys},
        is_check_shapes=True,
        seed=0,
    )
    payload = {
        "image": base,
        "mask": np.full(base.shape[:2], 255, dtype=np.uint8),
        "bboxes": bboxes,
        "class_ids": class_ids,
    }
    payload.update({key: images[key] for key in other_keys})
    transformed = compose(**payload)
    valid_mask = transformed["mask"] > 0

    outputs = {base_key: transformed["image"]}
    outputs.update({key: transformed[key] for key in other_keys})
    if not np.all(valid_mask):
        for key, output in outputs.items():
            output[~valid_mask] = _background_color(images[key])

    return SyncedTransformResult(
        images=outputs,
        bboxes=[tuple(float(value) for value in bbox) for bbox in transformed["bboxes"]],
        class_ids=[int(class_id) for class_id in transformed["class_ids"]],
    )


def rotate_image(image: np.ndarray, angle: float, keep_size: bool) -> tuple[np.ndarray, np.ndarray]:
    """Rotate an image and return the 3x3 affine matrix."""
    height, width = image.shape[:2]
    if angle % 360 == 0:
        return image.copy(), np.eye(3, dtype=np.float32)
    center = (width / 2.0, height / 2.0)
    matrix_2x3 = cv2.getRotationMatrix2D(center, -angle, 1.0)
    if keep_size:
        new_width, new_height = width, height
    else:
        cos_v = abs(matrix_2x3[0, 0])
        sin_v = abs(matrix_2x3[0, 1])
        new_width = max(1, int((height * sin_v) + (width * cos_v)))
        new_height = max(1, int((height * cos_v) + (width * sin_v)))
        matrix_2x3[0, 2] += (new_width / 2.0) - center[0]
        matrix_2x3[1, 2] += (new_height / 2.0) - center[1]
    rotated = cv2.warpAffine(image, matrix_2x3, (new_width, new_height), flags=cv2.INTER_LINEAR)
    matrix = np.eye(3, dtype=np.float32)
    matrix[:2, :] = matrix_2x3
    return rotated, matrix


def orient_image(image: np.ndarray, angle: int, flip_code, keep_size: bool) -> tuple[np.ndarray, np.ndarray]:
    """Apply optional flip and rotation, returning transformed image and 3x3 matrix."""
    height, width = image.shape[:2]
    matrix = np.eye(3, dtype=np.float32)
    working = image
    if flip_code is not None:
        working = cv2.flip(working, flip_code)
        if flip_code == 1:
            flip_matrix = np.array([[-1, 0, width], [0, 1, 0], [0, 0, 1]], dtype=np.float32)
        elif flip_code == 0:
            flip_matrix = np.array([[1, 0, 0], [0, -1, height], [0, 0, 1]], dtype=np.float32)
        else:
            flip_matrix = np.array([[-1, 0, width], [0, -1, height], [0, 0, 1]], dtype=np.float32)
        matrix = flip_matrix @ matrix
    rotated, rotate_matrix = rotate_image(working, angle, keep_size)
    return rotated, rotate_matrix @ matrix


def _background_color(image: np.ndarray) -> tuple[int, ...]:
    height, width = image.shape[:2]
    patch = max(1, min(64, max(1, height // 20), max(1, width // 20)))
    corners = (
        image[:patch, :patch],
        image[:patch, width - patch:width],
        image[height - patch:height, :patch],
        image[height - patch:height, width - patch:width],
    )
    pixels = np.concatenate([corner.reshape(-1, image.shape[2]) for corner in corners], axis=0)
    return tuple(int(value) for value in np.median(pixels, axis=0))


def choose_patch_position_in_contour(
    roi_contour: np.ndarray,
    image_shape: tuple[int, int] | tuple[int, int, int],
    patch: np.ndarray,
    rng,
    patch_mask: np.ndarray | None = None,
    occupied_boxes: list[tuple[int, int, int, int]] | None = None,
    max_attempts: int = 96,
    min_gap_ratio: float = 0.25,
) -> tuple[int, int] | None:
    """Choose a collision-free position whose active patch pixels stay inside the ROI."""
    if roi_contour is None or patch is None or patch.size == 0:
        return None

    contour = np.asarray(roi_contour, dtype=np.float32).reshape(-1, 2)
    if contour.shape[0] < 3:
        return None

    image_h, image_w = image_shape[:2]
    patch_h, patch_w = patch.shape[:2]
    if patch_h > image_h or patch_w > image_w:
        return None

    if patch_mask is None:
        active = np.any(patch > 0, axis=2) if patch.ndim == 3 else patch > 0
    else:
        active = patch_mask > 0
    if not np.any(active):
        return None

    patch_x, patch_y, patch_w_box, patch_h_box = cv2.boundingRect(active.astype(np.uint8))
    if patch_w_box <= 0 or patch_h_box <= 0:
        return None

    roi_mask = np.zeros((image_h, image_w), dtype=np.uint8)
    cv2.fillPoly(roi_mask, [np.rint(contour).astype(np.int32)], 255)

    kernel = np.ones((patch_h_box, patch_w_box), dtype=np.uint8)
    valid = cv2.erode(roi_mask, kernel, anchor=(0, 0), borderType=cv2.BORDER_CONSTANT, borderValue=0)
    valid[:patch_y, :] = 0
    valid[:, :patch_x] = 0
    valid[image_h - (patch_h - patch_y) + 1 :, :] = 0
    valid[:, image_w - (patch_w - patch_x) + 1 :] = 0
    point_ys, point_xs = np.nonzero(valid)
    if point_xs.size == 0 or max_attempts <= 0:
        return None

    candidate_count = min(int(point_xs.size), int(max_attempts))
    indices = rng.sample(range(int(point_xs.size)), candidate_count)
    gap = max(2, int(round(min(patch_w_box, patch_h_box) * max(0.0, min_gap_ratio))))
    occupied = occupied_boxes or []
    for selected in indices:
        x_pos = int(point_xs[selected]) - patch_x
        y_pos = int(point_ys[selected]) - patch_y
        candidate = (
            x_pos + patch_x - gap,
            y_pos + patch_y - gap,
            x_pos + patch_x + patch_w_box + gap,
            y_pos + patch_y + patch_h_box + gap,
        )
        if not any(_boxes_intersect(candidate, box) for box in occupied):
            return x_pos, y_pos
    return None


def _boxes_intersect(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> bool:
    """Return whether two half-open pixel rectangles overlap."""
    return first[0] < second[2] and first[2] > second[0] and first[1] < second[3] and first[3] > second[1]
