from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtGui import QColor, QImage

from service.history_service import (
    apply_history_entry,
    build_mapset_history_entry,
    changed_image_patch,
)


def _image(width: int, height: int, color: str) -> QImage:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    return image


def test_changed_image_patch_keeps_only_changed_bounds():
    before = _image(8, 8, "black")
    after = QImage(before)
    for x in range(2, 5):
        for y in range(3, 7):
            after.setPixelColor(x, y, QColor("white"))

    patch = changed_image_patch(before, after)

    assert patch is not None
    assert (patch.x, patch.y) == (2, 3)
    assert (patch.before.width(), patch.before.height()) == (3, 4)
    assert patch.before.pixelColor(0, 0) == QColor("black")
    assert patch.after.pixelColor(0, 0) == QColor("white")


def test_mapset_history_entry_replays_undo_and_redo_patches():
    before = {"map-a": _image(6, 6, "black")}
    after_image = QImage(before["map-a"])
    after_image.setPixelColor(4, 1, QColor("red"))
    after = {"map-a": after_image}

    entry = build_mapset_history_entry(before, after)
    assert entry is not None

    undone = apply_history_entry(after, entry, redo=False)
    redone = apply_history_entry(undone, entry, redo=True)

    assert undone["map-a"].pixelColor(4, 1) == QColor("black")
    assert redone["map-a"].pixelColor(4, 1) == QColor("red")


def test_mapset_history_entry_is_none_when_pixels_do_not_change():
    image = _image(4, 4, "black")

    assert build_mapset_history_entry({"map-a": image}, {"map-a": QImage(image)}) is None
