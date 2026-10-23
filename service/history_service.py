from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
from PySide6.QtGui import QImage, QPainter


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
    if before.cacheKey() == after.cacheKey():
        return None
    # Keep both QImages alive while viewing their buffers; compare one packed pixel.
    before_rgba = before.convertToFormat(QImage.Format.Format_RGBA8888)
    after_rgba = after.convertToFormat(QImage.Format.Format_RGBA8888)
    before_pixels = np.frombuffer(before_rgba.constBits(), dtype=np.uint32).reshape(before.height(), -1)[:, :before.width()]
    after_pixels = np.frombuffer(after_rgba.constBits(), dtype=np.uint32).reshape(after.height(), -1)[:, :after.width()]
    changed = before_pixels != after_pixels
    rows = np.flatnonzero(np.any(changed, axis=1))
    if not rows.size:
        return None
    cols = np.flatnonzero(np.any(changed, axis=0))
    left, right = int(cols[0]), int(cols[-1])
    top, bottom = int(rows[0]), int(rows[-1])
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
