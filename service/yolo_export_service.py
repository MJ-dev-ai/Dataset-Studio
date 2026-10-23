from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from core.image_io import read_image
from core.mapset import MapSet
from service import dataset_output as output


@dataclass
class YoloExportOptions:
    output_root: Path
    class_names: list[str]
    train_ratio: float = 0.8
    val_ratio: float = 0.2
    test_ratio: float = 0.0
    map_keys: list[str] | None = None
    seed: int = 0
    class_ids: list[int] | None = None


def export_dataset(mapsets: list[MapSet], options: YoloExportOptions, progress_callback=None, check_cancelled=None) -> dict:
    """Export isolated, validated runs without dropping sources or replacing prior output."""
    mapping, names = output.class_mapping(options.class_names, options.class_ids)
    eligible = [item for item in mapsets if any(options.map_keys is None or key in options.map_keys for key, _ in item.maps)]
    groups = {output.source_id(item.folder): item for item in eligible}
    splits = split_train_val_test(list(groups.values()), options)
    root, result = output.begin_run(options, "export", names, mapping)
    result["original_sources"] = len(groups)
    completed, total = 0, len(groups)
    try:
        for split, items in splits.items():
            for item in items:
                if check_cancelled:
                    check_cancelled()
                if progress_callback:
                    progress_callback(completed, max(1, total), f"내보내는 중: {item.name}")
                source = output.source_id(item.folder)
                try:
                    labels = output.remap_labels(output.read_labels(_label_path_for_mapset(item)), mapping)
                except (ValueError, OSError) as error:
                    output.add_issue(result, item.folder, error)
                    completed += 1
                    continue
                for key, image_path in item.maps:
                    if options.map_keys is not None and key not in options.map_keys:
                        continue
                    if check_cancelled:
                        check_cancelled()
                    directory = key if output.safe_name(key) == key else output.safe_name(key) + "-" + output.source_id(Path(key))[:8]
                    map_root = root / directory
                    stem = output.safe_name(item.name)[:32] + "-" + source
                    image_out = map_root / "images" / split / f"{stem}.png"
                    label_out = map_root / "labels" / split / f"{stem}.txt"
                    try:
                        image = read_image(image_path)
                        if image is None:
                            raise ValueError(f"이미지를 읽을 수 없습니다: {image_path}")
                        output.write_pair(image_out, label_out, image, labels)
                        output.add_entry(result, root, image_out, label_out, labels, source, split, "original", key)
                    except (ValueError, OSError) as error:
                        output.add_issue(result, image_path, error)
                completed += 1
                if completed % 25 == 0:
                    output.save_manifest(result)
        map_roots = {Path(entry["image"]).parts[0] for entry in result["entries"]}
        for map_dir in map_roots:
            used = {entry["split"] for entry in result["entries"] if Path(entry["image"]).parts[0] == map_dir}
            output.write_yaml(root / map_dir, names, used)
        if not result["entries"]:
            result["warnings"].append("저장된 이미지가 없습니다. 대상 맵과 오류 내역을 확인하세요.")
        output.validate_run(result, check_cancelled)
        result = output.finish_run(result)
        if progress_callback:
            progress_callback(total, max(1, total), "내보내기 완료" if result["status"] == "complete" else "일부 완료: 오류 내역을 확인하세요")
        return result
    except Exception as error:
        result["warnings"].append(str(error) or "작업이 중단됐습니다.")
        output.finish_run(result, "interrupted")
        raise


def split_train_val_test(items: list[MapSet], options: YoloExportOptions) -> dict[str, list[MapSet]]:
    """Use whole-source splits with exact accounting of all rounding remainders."""
    return output.split_groups(items, (options.train_ratio, options.val_ratio, options.test_ratio), options.seed)


def write_data_yaml(map_root: Path, class_names: list[str]) -> None:
    """Write correctly escaped names and available split paths."""
    splits = [name for name in ("train", "val", "test") if any((map_root / "images" / name).glob("*.png"))]
    output.write_yaml(map_root, class_names or ["class0"], splits)


def validate_export(output_root: str | Path) -> bool:
    """Validate a completed run using its explicit file and class manifest."""
    path = Path(output_root) / "run.json"
    if not path.is_file():
        return False
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        output.validate_run(result)
        return bool(result["entries"])
    except (ValueError, OSError, KeyError):
        return False


def _label_path_for_mapset(mapset: MapSet) -> Path | None:
    if mapset.label_path is not None:
        return mapset.label_path
    candidate = mapset.folder / f"{mapset.name}.txt"
    return candidate if candidate.is_file() else None
