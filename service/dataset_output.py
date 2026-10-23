"""Shared output contracts for dataset export and augmentation runs."""
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import re
import uuid
import yaml

from core.image_io import read_image, write_png
from service.labeling_service import YoloLabel


def source_id(path: Path) -> str:
    """Identify a source independently of its potentially duplicated display name."""
    return hashlib.sha256(str(path.resolve()).casefold().encode("utf-8")).hexdigest()[:20]


def safe_name(name: str) -> str:
    """Keep output names portable without losing their unique source identifier."""
    value = re.sub(r"[^\w.-]+", "_", name).strip("._")[:100] or "sample"
    if value.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        value = "_" + value
    return value


def split_groups(items, ratios, seed):
    """Assign every source group once, distributing rounding remainders deterministically."""
    values = [float(value) for value in ratios]
    if any(not math.isfinite(value) or value < 0 for value in values) or sum(values) <= 0:
        raise ValueError("분할 비율은 0 이상이며 합계가 0보다 커야 합니다.")
    shuffled = list(items)
    random.Random(seed).shuffle(shuffled)
    quotas = [len(shuffled) * value / sum(values) for value in values]
    counts = [int(value) for value in quotas]
    order = sorted(range(3), key=lambda index: (-(quotas[index] - counts[index]), index))
    for index in order[:len(shuffled) - sum(counts)]:
        counts[index] += 1
    result, offset = {}, 0
    for name, count in zip(("train", "val", "test"), counts):
        result[name] = shuffled[offset:offset + count]
        offset += count
    return result


def class_mapping(names, ids=None, observed=()):
    """Resolve sparse source IDs to dense YOLO IDs and retain their display names."""
    names = list(names)
    if not names:
        ids = sorted(set(observed)) or [0]
        names = [f"class {value}" for value in ids]
    ids = list(range(len(names))) if ids is None else list(ids)
    if len(ids) != len(names) or len(set(ids)) != len(ids) or any(value < 0 for value in ids):
        raise ValueError("클래스 ID와 이름의 개수가 맞지 않거나 ID가 중복됐습니다.")
    if any(not str(name).strip() for name in names):
        raise ValueError("클래스 이름을 비워 둘 수 없습니다.")
    return {value: index for index, value in enumerate(ids)}, names


def validate_labels(labels, valid_ids):
    """Reject unknown classes, nonfinite values and boxes outside the image."""
    for label in labels:
        values = (label.x_center, label.y_center, label.width, label.height)
        if label.class_id not in valid_ids:
            raise ValueError(f"등록되지 않은 클래스 ID: {label.class_id}")
        if not all(math.isfinite(value) for value in values) or not all(0 <= value <= 1 for value in values):
            raise ValueError("라벨 좌표가 유효한 0~1 범위를 벗어났습니다.")
        x, y, width, height = values
        if width <= 0 or height <= 0 or min(x - width / 2, y - height / 2) < -1e-6 or max(x + width / 2, y + height / 2) > 1 + 1e-6:
            raise ValueError("라벨 상자가 이미지 밖에 있거나 크기가 0입니다.")


def read_labels(path: Path | None):
    """Read every annotation strictly; missing labels are explicit negative samples."""
    if path is None:
        return []
    labels = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        try:
            if len(parts) != 5:
                raise ValueError()
            labels.append(YoloLabel(int(parts[0]), *(float(value) for value in parts[1:])))
        except ValueError as error:
            raise ValueError(f"{path.name}:{number} — 잘못된 YOLO 라벨") from error
    return labels


def remap_labels(labels, mapping):
    """Validate before remapping so an unregistered label can never disappear silently."""
    validate_labels(labels, mapping)
    return [YoloLabel(mapping[label.class_id], label.x_center, label.y_center, label.width, label.height) for label in labels]


def write_pair(image_path, label_path, image, labels):
    """Write a new pair only; remove this run's incomplete image if label writing fails."""
    if image_path.exists() or label_path.exists():
        raise FileExistsError(f"기존 파일을 덮어쓸 수 없습니다: {image_path}")
    image_path.parent.mkdir(parents=True, exist_ok=True)
    label_path.parent.mkdir(parents=True, exist_ok=True)
    if not write_png(image_path, image):
        image_path.unlink(missing_ok=True)
        raise OSError(f"이미지 저장 실패: {image_path}")
    created_label = False
    try:
        with label_path.open("x", encoding="utf-8") as output:
            created_label = True
            output.write("".join(f"{item.class_id} {item.x_center:.6f} {item.y_center:.6f} {item.width:.6f} {item.height:.6f}\n" for item in labels))
    except Exception:
        image_path.unlink(missing_ok=True)
        if created_label:
            label_path.unlink(missing_ok=True)
        raise


def begin_run(options, kind, names, mapping):
    """Reserve an isolated run and persist its immutable input settings immediately."""
    run_id = datetime.now().strftime("%y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    settings = asdict(options)
    if kind == "augment":
        description = f"{settings['target_map_key']}_{settings['poisson_mode']}_n{settings['generate_samples']}_size{settings['image_size']}_seed{settings['seed']}"
    else:
        description = f"{'-'.join(settings.get('map_keys') or ['all'])}_split{options.train_ratio:g}-{options.val_ratio:g}-{options.test_ratio:g}_seed{options.seed}"
    fingerprint = hashlib.sha256(json.dumps(settings, default=str, sort_keys=True).encode("utf-8")).hexdigest()[:8]
    root = options.output_root.resolve() / f"{kind}_{safe_name(description)[:64]}_{fingerprint}_{run_id}"
    root.mkdir(parents=True, exist_ok=False)
    result = {
        "schema_version": 1, "run_id": run_id, "kind": kind, "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(), "output_root": str(root),
        "settings": json.loads(json.dumps(asdict(options), default=str)), "class_names": names,
        "class_mapping": {str(key): value for key, value in mapping.items()},
        "entries": [], "issues": [], "warnings": [], "failed": 0, "skipped": 0,
        "images": 0, "labels": 0, "annotations": 0, "poisson_samples": 0,
    }
    save_manifest(result)
    return root, result


def add_entry(result, root, image_path, label_path, labels, source, split, kind, map_key):
    """Record only completely written image-label pairs for browsing and auditing."""
    result["entries"].append({"image": image_path.relative_to(root).as_posix(), "label": label_path.relative_to(root).as_posix(), "source_id": source, "split": split, "kind": kind, "map_key": map_key, "annotations": len(labels), "classes": [label.class_id for label in labels]})


def add_issue(result, source, reason, kind="failed"):
    """Count failed/skipped operations independently and preserve a useful reason."""
    result[kind] += 1
    result["issues"].append({"kind": kind, "source": str(source), "reason": str(reason)})


def write_yaml(root, names, splits):
    """Write quoted class names and only splits that actually contain output files."""
    lines = [f"path: {json.dumps(root.resolve().as_posix(), ensure_ascii=False)}"]
    for split in ("train", "val", "test"):
        if split in splits:
            lines.append(f"{split}: images/{split}")
    lines.append("names:")
    lines.extend(f"  {index}: {json.dumps(name, ensure_ascii=False)}" for index, name in enumerate(names))
    (root / "data.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_manifest(result):
    """Atomically checkpoint the run, including settings and partial results."""
    root = Path(result["output_root"])
    temporary = root / "run.json.tmp"
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(root / "run.json")


def finish_run(result, status=None):
    """Derive all displayed totals from written entries and save the final report."""
    entries = result["entries"]
    result.update(images=len(entries), labels=len(entries), annotations=sum(item["annotations"] for item in entries))
    result["split_images"] = dict(Counter(item["split"] for item in entries))
    result["class_distribution"] = dict(Counter(value for item in entries for value in item["classes"]))
    result["failed_or_skipped"] = result["failed"] + result["skipped"]
    result["sample_images"] = [str(Path(result["output_root"]) / item["image"]) for item in sorted(entries, key=lambda item: item["kind"] != "poisson")[:3]]
    result["preview_image"] = next(iter(result["sample_images"]), "")
    result["status"] = status or ("partial" if result["failed"] or result["skipped"] or result["warnings"] else "complete")
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    save_manifest(result)
    return result


def validate_run(result, check_cancelled=None):
    """Verify saved images, label contents, unique paths and source split isolation."""
    root = Path(result["output_root"])
    seen, source_splits, datasets = set(), {}, {}
    for entry in result["entries"]:
        if check_cancelled:
            check_cancelled()
        image_path, label_path = root / entry["image"], root / entry["label"]
        for path in (image_path, label_path):
            if not path.resolve().is_relative_to(root.resolve()) or path in seen:
                raise ValueError("결과 파일 경로가 중복되거나 실행 폴더 밖을 가리킵니다.")
            seen.add(path)
        if read_image(image_path) is None:
            raise ValueError(f"저장된 이미지를 읽을 수 없습니다: {image_path}")
        labels = read_labels(label_path)
        validate_labels(labels, range(len(result["class_names"])))
        if len(labels) != entry["annotations"] or [label.class_id for label in labels] != entry["classes"]:
            raise ValueError(f"저장된 라벨 수 또는 클래스가 실행 기록과 다릅니다: {label_path}")
        previous = source_splits.setdefault(entry["source_id"], entry["split"])
        if previous != entry["split"]:
            raise ValueError("같은 원본이 학습/검증/테스트에 중복 배정됐습니다.")
        dataset_root = image_path.parent.parent.parent
        datasets.setdefault(dataset_root, set()).add(entry["split"])
    for dataset_root, splits in datasets.items():
        yaml_path = dataset_root / "data.yaml"
        if yaml_path.is_file():
            try:
                document = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            except yaml.YAMLError as error:
                raise ValueError(f"데이터셋 설정을 읽을 수 없습니다: {yaml_path}") from error
            if not isinstance(document, dict) or document.get("names") != dict(enumerate(result["class_names"])) or any(document.get(split) != f"images/{split}" for split in splits):
                raise ValueError(f"클래스 또는 분할 설정이 다릅니다: {yaml_path}")
        elif result.get("status") not in ("running", "interrupted"):
            raise ValueError(f"데이터셋 설정 파일이 없습니다: {yaml_path}")
        for directory in (dataset_root / "images", dataset_root / "labels"):
            if any(path not in seen for path in directory.rglob("*") if path.is_file()):
                raise ValueError(f"실행 기록에 없는 파일이 섞여 있습니다: {directory}")
    return True
