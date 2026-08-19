from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPainter, QPainterPath


def safe_defect_name(value: str) -> str:
    """Return a filesystem-safe defect name without path separators."""
    value = re.sub(r"\s+", "_", value.strip())
    value = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE)
    value = re.sub(r"_+", "_", value)
    return value.strip("._-")


def next_sample_number(defect_dir: str | os.PathLike, map_stems: Iterable[str]) -> str:
    """Return the first four-digit sample prefix unused by every map stem."""
    directory = Path(defect_dir)
    stems = tuple(map_stems)
    number = 1
    while True:
        candidate = f"{number:04d}"
        if not any((directory / f"{candidate}_{stem}.png").exists() for stem in stems):
            return candidate
        number += 1


def export_defect_maps(
    map_paths: Iterable[tuple[str, str]],
    output_root: str | os.PathLike,
    defect_name: str,
    selection_path: QPainterPath,
    bounds: QRect,
    *,
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[int, str], None] | None = None,
) -> Path:
    """Crop one synchronized selection from every map and save a numbered defect set."""
    maps = tuple((stem, Path(path)) for stem, path in map_paths)
    if not maps:
        raise ValueError("No map images were supplied.")
    if selection_path.isEmpty() or bounds.isNull() or bounds.isEmpty():
        raise ValueError("The defect selection is empty.")

    safe_name = safe_defect_name(defect_name)
    if not safe_name:
        raise ValueError("Defect name is required.")

    missing = [str(path) for _stem, path in maps if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing map files:\n" + "\n".join(missing))

    defect_dir = Path(output_root) / safe_name
    defect_dir.mkdir(parents=True, exist_ok=True)
    sample = next_sample_number(defect_dir, (stem for stem, _path in maps))
    expected_size = None
    written: list[Path] = []

    try:
        for index, (stem, source) in enumerate(maps, start=1):
            if cancelled is not None and cancelled():
                raise InterruptedError("Defect export was cancelled.")
            if progress is not None:
                progress(index - 1, f"Saving {index}/{len(maps)}: {source.name}")

            image = QImage(str(source))
            if image.isNull():
                raise OSError(f"Cannot open map image: {source}")
            if expected_size is None:
                expected_size = image.size()
            elif image.size() != expected_size:
                raise ValueError(f"Map size does not match the active selection: {source.name}")

            clipped_bounds = bounds.intersected(image.rect())
            if clipped_bounds != bounds:
                raise ValueError(f"Selection is outside map bounds: {source.name}")

            mask = QImage(image.size(), QImage.Format.Format_Grayscale8)
            mask.fill(0)
            mask_painter = QPainter(mask)
            mask_painter.fillPath(selection_path, Qt.GlobalColor.white)
            mask_painter.end()

            masked = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
            masked.fill(Qt.GlobalColor.black)
            painter = QPainter(masked)
            painter.setClipPath(selection_path)
            painter.drawImage(0, 0, image)
            painter.end()

            destination = defect_dir / f"{sample}_{stem}.png"
            if not masked.copy(bounds).save(str(destination), "PNG"):
                raise OSError(f"Cannot save defect map: {destination}")
            written.append(destination)

            mask_destination = defect_dir / f"{sample}_{stem}_mask.png"
            if not mask.copy(bounds).save(str(mask_destination), "PNG"):
                raise OSError(f"Cannot save defect mask: {mask_destination}")
            written.append(mask_destination)
            if progress is not None:
                progress(index, f"Saved {index}/{len(maps)}: {source.name}")
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise

    return defect_dir
