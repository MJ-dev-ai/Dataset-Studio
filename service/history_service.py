from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
from PyQt6.QtGui import QImage, QPainter


@dataclass(frozen=True)
class ImageHistoryPatch:
    """Store one changed image rectangle with pixels for undo and redo."""

    x: int
    y: int
    before: QImage
    after: QImage


@dataclass(frozen=True)
class MapSetHistoryEntry:
    """Store changed rectangles for every touched map in one MapSet edit."""

    patches: dict[str, ImageHistoryPatch]


def changed_image_patch(before: QImage, after: QImage) -> ImageHistoryPatch | None:
    """Return the smallest changed rectangle between two same-sized images."""
    if before.size() != after.size():
        raise ValueError("history images must have the same size")
    before_rgba = _rgba_view(before)
    after_rgba = _rgba_view(after)
    changed = np.any(before_rgba != after_rgba, axis=2)
    if not np.any(changed):
        return None
    ys, xs = np.nonzero(changed)
    left = int(xs.min())
    right = int(xs.max())
    top = int(ys.min())
    bottom = int(ys.max())
    width = right - left + 1
    height = bottom - top + 1
    return ImageHistoryPatch(
        x=left,
        y=top,
        before=before.copy(left, top, width, height),
        after=after.copy(left, top, width, height),
    )


def build_mapset_history_entry(
    before_images: Mapping[str, QImage],
    after_images: Mapping[str, QImage],
) -> MapSetHistoryEntry | None:
    """Build a MapSet history entry containing only maps and rectangles that changed."""
    patches: dict[str, ImageHistoryPatch] = {}
    for key, before in before_images.items():
        after = after_images.get(key)
        if after is None:
            continue
        patch = changed_image_patch(before, after)
        if patch is not None:
            patches[key] = patch
    if not patches:
        return None
    return MapSetHistoryEntry(patches)


def apply_history_entry(
    images: Mapping[str, QImage],
    entry: MapSetHistoryEntry,
    *,
    redo: bool,
) -> dict[str, QImage]:
    """Apply one history entry to the supplied images and return changed image copies."""
    restored: dict[str, QImage] = {}
    for key, patch in entry.patches.items():
        source = images.get(key)
        if source is None:
            continue
        result = QImage(source)
        painter = QPainter(result)
        painter.drawImage(patch.x, patch.y, patch.after if redo else patch.before)
        painter.end()
        restored[key] = result
    return restored


def _rgba_view(image: QImage) -> np.ndarray:
    converted = image.convertToFormat(QImage.Format.Format_RGBA8888)
    bits = converted.bits()
    bits.setsize(converted.sizeInBytes())
    data = np.frombuffer(bytes(bits), dtype=np.uint8).reshape(converted.height(), converted.bytesPerLine())
    return data[:, : converted.width() * 4].reshape(converted.height(), converted.width(), 4)
