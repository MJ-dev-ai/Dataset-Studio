from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

@dataclass(frozen=True)
class YoloLabel:
    class_id: int
    x_center: float
    y_center: float
    width: float
    height: float

class YoloApi:
    """YOLO label loading, saving, and conversion helpers."""

    def load_txt(self, path: str | Path) -> list[YoloLabel]:
        label_path = Path(path)
        if not label_path.exists():
            return []
        labels = []
        with label_path.open("r", encoding="utf-8") as file:
            for line in file:
                parsed = parse_yolo_line(line)
                if parsed is None:
                    continue
                labels.append(YoloLabel(*parsed))
        return labels

    def save_txt(self, path: str | Path, labels: list[YoloLabel]) -> None:
        label_path = Path(path)
        label_path.parent.mkdir(parents=True, exist_ok=True)
        with label_path.open("w", encoding="utf-8") as file:
            for label in labels:
                file.write(
                    f"{label.class_id} {label.x_center:.6f} {label.y_center:.6f} "
                    f"{label.width:.6f} {label.height:.6f}\n"
                )

    def read_valid_lines(self, path: str | Path) -> list[str]:
        return [
            f"{label.class_id} {label.x_center:.6f} {label.y_center:.6f} {label.width:.6f} {label.height:.6f}"
            for label in self.load_txt(path)
        ]

    def auto_label_from_threshold(self, image: np.ndarray, class_id: int) -> list[YoloLabel]:
        """Create one YOLO label per external foreground contour in a thresholded image."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        _value, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        contours, _hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        labels = []
        height, width = gray.shape[:2]
        for contour in contours:
            x_pos, y_pos, box_width, box_height = cv2.boundingRect(contour)
            if box_width * box_height < 4:
                continue
            line = box_to_yolo_line(
                class_id,
                (x_pos, y_pos, x_pos + box_width, y_pos + box_height),
                width,
                height,
            )
            parsed = parse_yolo_line(line)
            if parsed is not None:
                labels.append(YoloLabel(*parsed))
        return labels


LabelCatalog = list[tuple[int, str]]


def parse_yolo_line(line: str) -> tuple[int, float, float, float, float] | None:
    parts = line.strip().split()
    if len(parts) < 5:
        return None
    try:
        class_id = int(float(parts[0]))
        values = [float(value) for value in parts[1:5]]
    except ValueError:
        return None
    if any(value < 0 or value > 1 for value in values) or values[2] <= 0 or values[3] <= 0:
        return None
    return class_id, values[0], values[1], values[2], values[3]


def xyxy_to_yolo(box: tuple[float, float, float, float], width: int, height: int) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = box
    image_width = max(1, width)
    image_height = max(1, height)
    x_center = ((x1 + x2) / 2.0) / image_width
    y_center = ((y1 + y2) / 2.0) / image_height
    box_width = (x2 - x1) / image_width
    box_height = (y2 - y1) / image_height
    return x_center, y_center, box_width, box_height


def yolo_to_xyxy(x_center: float, y_center: float, box_width: float, box_height: float, width: int, height: int):
    pixel_width = box_width * width
    pixel_height = box_height * height
    x1 = x_center * width - pixel_width / 2.0
    y1 = y_center * height - pixel_height / 2.0
    return x1, y1, x1 + pixel_width, y1 + pixel_height


def box_to_yolo_line(class_id: int, box: tuple[float, float, float, float], width: int, height: int) -> str:
    x_center, y_center, box_width, box_height = xyxy_to_yolo(box, width, height)
    return f"{class_id} {x_center:.6f} {y_center:.6f} {box_width:.6f} {box_height:.6f}"


def transform_bbox_affine(box: tuple[float, float, float, float], matrix: np.ndarray) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = box
    points = np.array([[x1, y1, 1], [x2, y1, 1], [x2, y2, 1], [x1, y2, 1]], dtype=np.float32).T
    transformed = matrix @ points
    xs = transformed[0]
    ys = transformed[1]
    return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


def clip_bbox(box: tuple[float, float, float, float], width: int, height: int) -> tuple[float, float, float, float] | None:
    x1, y1, x2, y2 = box
    x1 = max(0.0, min(float(width), x1))
    y1 = max(0.0, min(float(height), y1))
    x2 = max(0.0, min(float(width), x2))
    y2 = max(0.0, min(float(height), y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def normalize_catalog(items) -> LabelCatalog:
    """Normalize label items while preserving their first-seen display order."""
    result = []
    positions = {}
    for class_id, class_name in items:
        class_id = int(class_id)
        value = (class_id, str(class_name).strip() or f"class {class_id}")
        if class_id in positions:
            result[positions[class_id]] = value
        else:
            positions[class_id] = len(result)
            result.append(value)
    return result


def update_catalog(
    catalog: LabelCatalog,
    original_id: int | None,
    class_id: int,
    class_name: str,
) -> LabelCatalog:
    """Append or edit one class without reordering unrelated classes."""
    result = list(catalog)
    class_id = int(class_id)
    class_name = class_name.strip() or f"class {class_id}"
    if original_id is None:
        for index, (item_id, _name) in enumerate(result):
            if item_id == class_id:
                result[index] = (class_id, class_name)
                return result
        result.append((class_id, class_name))
        return result

    target_index = next((index for index, item in enumerate(result) if item[0] == original_id), None)
    if target_index is None:
        raise ValueError(f"Unknown class ID: {original_id}")
    if class_id != original_id and any(item_id == class_id for item_id, _name in result):
        raise ValueError(f"Class ID {class_id} already exists")
    result[target_index] = (class_id, class_name)
    return result


def remove_from_catalog(catalog: LabelCatalog, class_id: int) -> LabelCatalog:
    """Remove one class without renumbering the remaining class IDs."""
    return [item for item in catalog if item[0] != class_id]


def move_in_catalog(catalog: LabelCatalog, class_id: int, offset: int) -> LabelCatalog:
    """Move one class by offset while preserving its explicit class ID."""
    result = list(catalog)
    index = next((index for index, item in enumerate(result) if item[0] == class_id), None)
    if index is None:
        return result
    destination = max(0, min(len(result) - 1, index + offset))
    if destination != index:
        result.insert(destination, result.pop(index))
    return result
