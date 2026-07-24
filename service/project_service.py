from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import os
import re
import shutil
import uuid

import cv2
import numpy as np
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QImage, QPainter, QPainterPath


@dataclass(frozen=True)
class MapSetSaveRequest:
    """Serializable snapshot required to create one independent MapSet copy."""

    destination_root: Path
    mapset_name: str
    maps: tuple[tuple[str, Path], ...]
    edited_maps: tuple[tuple[str, np.ndarray], ...]
    label_text: str


@dataclass(frozen=True)
class MapSetUpdateRequest:
    """Complete current MapSet pixel and label snapshot for in-place Save."""

    maps: tuple[tuple[str, Path, np.ndarray | None], ...]
    label_path: Path
    label_text: str


@dataclass(frozen=True)
class SavedMapSet:
    """Filesystem result returned after the atomic MapSet save completes."""

    folder: Path
    maps: tuple[tuple[str, Path], ...]
    label_path: Path

    @property
    def map_paths(self) -> dict[str, Path]:
        return dict(self.maps)


def normalize_mapset_name(value: str) -> str:
    """Return a Windows-safe folder name without allowing path traversal."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value)).strip(" .")
    if not name or name in {".", ".."}:
        raise ValueError("MapSet name is empty or invalid")
    return name


def save_mapset_copy(
    request: MapSetSaveRequest,
    *,
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> SavedMapSet:
    """Create a complete MapSet in a temporary folder and publish it atomically."""
    root = Path(request.destination_root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"MapSet root does not exist: {root}")
    name = normalize_mapset_name(request.mapset_name)
    destination = (root / name).resolve()
    if destination.parent != root:
        raise ValueError("MapSet destination must stay inside the project root")
    if destination.exists():
        raise FileExistsError(f"MapSet already exists: {destination}")

    edited = {key: np.ascontiguousarray(image.copy()) for key, image in request.edited_maps}
    unknown = set(edited).difference(key for key, _path in request.maps)
    if unknown:
        raise ValueError(f"Edited map keys are not present in source MapSet: {sorted(unknown)}")

    temporary = root / f".{name}.{uuid.uuid4().hex}.tmp"
    temporary.mkdir(parents=False, exist_ok=False)
    saved_maps: list[tuple[str, Path]] = []
    total = len(request.maps) + 1
    try:
        for index, (map_key, source_path) in enumerate(request.maps, start=1):
            if cancelled is not None and cancelled():
                raise RuntimeError("MapSet save cancelled")
            source = Path(source_path).resolve()
            if not source.is_file():
                raise FileNotFoundError(f"Map image not found: {source}")
            target = temporary / source.name
            if map_key in edited:
                _write_image(target, edited[map_key])
            else:
                shutil.copy2(source, target)
            saved_maps.append((map_key, destination / source.name))
            if progress is not None:
                progress(index, total, f"Saving {source.name}")

        label_target = temporary / f"{name}.txt"
        label_target.write_text(str(request.label_text), encoding="utf-8")
        if progress is not None:
            progress(total, total, "Saving labels")
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return SavedMapSet(
        folder=destination,
        maps=tuple(saved_maps),
        label_path=destination / f"{name}.txt",
    )


def save_mapset_in_place(
    request: MapSetUpdateRequest,
    *,
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> None:
    """Stage every map and label, then replace the current MapSet with rollback."""
    if not request.maps:
        raise ValueError("MapSet contains no maps")
    token = uuid.uuid4().hex
    staged: list[tuple[Path, Path]] = []
    backups: list[tuple[Path, Path]] = []
    published: list[Path] = []
    committed = False
    total = len(request.maps) + 1

    try:
        for index, (_map_key, target_path, image) in enumerate(request.maps, start=1):
            if cancelled is not None and cancelled():
                raise RuntimeError("MapSet save cancelled")
            target = Path(target_path).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.{token}.tmp")
            if image is None:
                if not target.is_file():
                    raise FileNotFoundError(f"Map image not found: {target}")
                shutil.copy2(target, temporary)
            else:
                _write_image(temporary, image, extension=target.suffix)
            staged.append((temporary, target))
            if progress is not None:
                progress(index, total, f"Staging {target.name}")

        label_target = Path(request.label_path).resolve()
        label_target.parent.mkdir(parents=True, exist_ok=True)
        label_temporary = label_target.with_name(f".{label_target.name}.{token}.tmp")
        label_temporary.write_text(str(request.label_text), encoding="utf-8")
        staged.append((label_temporary, label_target))
        if progress is not None:
            progress(total, total, "Staging labels")

        for temporary, target in staged:
            backup = target.with_name(f".{target.name}.{token}.bak")
            if target.exists():
                os.replace(target, backup)
                backups.append((backup, target))
            os.replace(temporary, target)
            published.append(target)
        committed = True
    except Exception:
        for target in reversed(published):
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
        for backup, target in reversed(backups):
            try:
                os.replace(backup, target)
            except OSError:
                pass
        raise
    finally:
        for temporary, _target in staged:
            temporary.unlink(missing_ok=True)
        if committed:
            for backup, _target in backups:
                backup.unlink(missing_ok=True)


def _write_image(path: Path, image: np.ndarray, *, extension: str | None = None) -> None:
    """Encode an edited map using its original filename extension."""
    extension = (extension or path.suffix).casefold()
    if extension not in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}:
        extension = ".png"
    ok, data = cv2.imencode(extension, image)
    if not ok:
        raise RuntimeError(f"Failed to encode map image: {path.name}")
    data.tofile(str(path))


def safe_defect_name(value: str) -> str:
    """Return a filesystem-safe defect name without path separators."""
    value = re.sub(r"\s+", "_", value.strip())
    value = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE)
    value = re.sub(r"_+", "_", value)
    return value.strip("._-")


def next_sample_number(defect_dir: str | os.PathLike, map_stems) -> str:
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
    map_paths,
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
