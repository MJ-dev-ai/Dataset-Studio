from __future__ import annotations

import random
import shutil
from dataclasses import dataclass
from pathlib import Path

from core.mapset import MapSet
from service.labeling_service import YoloApi


@dataclass
class YoloExportOptions:
    output_root: Path
    class_names: list[str]
    train_ratio: float = 0.8
    val_ratio: float = 0.2
    test_ratio: float = 0.0
    map_keys: list[str] | None = None
    seed: int = 0


class YoloExportApi:
    """YOLOv8 dataset export API."""

    def __init__(self, yolo_api: YoloApi | None = None):
        self.yolo_api = yolo_api or YoloApi()

    def export_dataset(self, mapsets: list[MapSet], options: YoloExportOptions, progress_callback=None) -> dict[str, int]:
        """Export every map with a paired YOLO txt, including empty negative labels."""
        splits = self.split_train_val_test(mapsets, options)
        exported_images = 0
        exported_labels = 0
        total = sum(len(items) for items in splits.values())
        completed = 0
        for split_name, split_items in splits.items():
            for mapset in split_items:
                if progress_callback is not None:
                    progress_callback(completed, total, f"Exporting {mapset.name}")
                label_path = self._label_path_for_mapset(mapset)
                label_lines = self.yolo_api.read_valid_lines(label_path) if label_path is not None else []
                for key, image_path in mapset.maps:
                    if options.map_keys is not None and key not in options.map_keys:
                        continue
                    map_root = options.output_root / key
                    images_dir = map_root / "images" / split_name
                    labels_dir = map_root / "labels" / split_name
                    images_dir.mkdir(parents=True, exist_ok=True)
                    labels_dir.mkdir(parents=True, exist_ok=True)
                    image_out = images_dir / f"{mapset.name}{image_path.suffix.lower()}"
                    label_out = labels_dir / f"{mapset.name}.txt"
                    shutil.copy2(image_path, image_out)
                    label_out.write_text(
                        "\n".join(label_lines) + ("\n" if label_lines else ""),
                        encoding="utf-8",
                    )
                    exported_images += 1
                    exported_labels += 1
                completed += 1
        for map_key in self._exported_map_keys(options.output_root):
            self.write_data_yaml(options.output_root / map_key, options.class_names)
        if progress_callback is not None:
            progress_callback(total, total, "Export complete")
        return {"images": exported_images, "labels": exported_labels}

    def split_train_val_test(self, items: list[MapSet], options: YoloExportOptions) -> dict[str, list[MapSet]]:
        shuffled = list(items)
        random.Random(options.seed).shuffle(shuffled)
        total = len(shuffled)
        train_end = int(total * options.train_ratio)
        val_end = train_end + int(total * options.val_ratio)
        return {
            "train": shuffled[:train_end],
            "val": shuffled[train_end:val_end],
            "test": shuffled[val_end:] if options.test_ratio > 0 else [],
        }

    def write_data_yaml(self, map_root: Path, class_names: list[str]) -> None:
        names = class_names or ["class0"]
        lines = ["path: .", "train: images/train", "val: images/val", "names:"]
        for class_id, class_name in enumerate(names):
            lines.append(f"  {class_id}: {class_name}")
        (map_root / "data.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def validate_export(self, output_root: str | Path) -> bool:
        """Return whether every exported map has a data file and image/label pairs."""
        root = Path(output_root)
        map_keys = self._exported_map_keys(root)
        if not map_keys:
            return False
        for key in map_keys:
            map_root = root / key
            if not (map_root / "data.yaml").is_file():
                return False
            for split in ("train", "val", "test"):
                images = map_root / "images" / split
                labels = map_root / "labels" / split
                if not images.exists():
                    continue
                image_stems = {path.stem for path in images.iterdir() if path.is_file()}
                label_stems = {path.stem for path in labels.iterdir() if path.is_file()} if labels.exists() else set()
                if image_stems != label_stems:
                    return False
        return True

    def _label_path_for_mapset(self, mapset: MapSet) -> Path | None:
        if mapset.label_path is not None and mapset.label_path.is_file():
            return mapset.label_path
        candidate = mapset.folder / f"{mapset.name}.txt"
        return candidate if candidate.is_file() else None

    def _exported_map_keys(self, output_root: Path) -> list[str]:
        if not output_root.exists():
            return []
        return sorted(path.name for path in output_root.iterdir() if path.is_dir())
