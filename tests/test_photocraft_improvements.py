"""Regression coverage for measured hot paths and spatially faithful blending."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import cv2
import numpy as np
import pytest
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication
from core.qt_image import bgr_to_qpixmap, qimage_to_bgr
from service import editing_service as edit
from service.history_service import changed_image_patch
from service.preprocessing_service import PreprocessOptions, apply_options
from tools.patch_tools import PatchTool


@pytest.fixture(scope="module")
def app():
    """Keep a single Qt application alive for image ownership tests."""
    return QApplication.instance() or QApplication([])


def test_qt_roundtrip_owns_data_with_padded_rows(app):
    source = np.arange(7 * 5 * 3, dtype=np.uint8).reshape(7, 5, 3)
    image = bgr_to_qpixmap(source)
    result = qimage_to_bgr(image)
    image.fill(QColor("black"))
    assert np.array_equal(result, source)


@pytest.mark.parametrize("brightness,contrast", [(12, 20), (-90, -75), (200, 99), (0, -100), (1, 1)])
def test_lut_matches_old_float_arithmetic(brightness, contrast):
    source = np.tile(np.arange(256, dtype=np.uint8), (4, 1))
    expected = np.clip(source.astype(np.float32) * (1.0 + contrast / 100.0) + float(brightness), 0, 255).astype(np.uint8)
    actual, matrix = apply_options(source, PreprocessOptions(brightness_shift=brightness, contrast_shift=contrast))
    assert np.array_equal(actual, expected)
    assert np.array_equal(matrix, np.eye(3))


def test_history_sees_alpha_changes_and_ignores_unchanged(app):
    before = QImage(7, 9, QImage.Format.Format_RGBA8888)
    before.fill(QColor(10, 20, 30, 255))
    assert changed_image_patch(before, QImage(before)) is None
    assert changed_image_patch(before, before.copy()) is None
    after = before.copy()
    after.setPixelColor(3, 5, QColor(10, 20, 30, 100))
    patch = changed_image_patch(before, after)
    assert (patch.x, patch.y, patch.after.width(), patch.after.height()) == (3, 5, 1, 1)
    assert patch.before.pixelColor(0, 0).alpha() == 255
    assert patch.after.pixelColor(0, 0).alpha() == 100


@pytest.mark.parametrize("opacity", [0, .35, 1])
def test_roi_paint_matches_full_frame(opacity):
    source = np.random.default_rng(7).integers(0, 256, (83, 97, 3), dtype=np.uint8)
    strokes = [((-10.3, 5.8), (30.5, 15.1)), ((40, 40), (55, 70))]
    overlay = source.copy()
    for start, end in strokes:
        cv2.line(overlay, tuple(round(v) for v in start), tuple(round(v) for v in end), (10, 20, 30), 9, cv2.LINE_8)
    expected = cv2.addWeighted(overlay, opacity, source, 1 - opacity, 0)
    assert np.array_equal(edit.apply_paint_strokes(source, strokes, (10, 20, 30), 9, opacity), expected)


def test_patch_cache_reuses_translation_but_invalidates_transform_and_source():
    tool = PatchTool()
    image = np.full((12, 20, 3), 120, np.uint8)
    mask = np.full((12, 20), 255, np.uint8)
    tool.load_selection_patch(image, mask, 0, 0)
    tool.set_target_size(200, 200)
    first = tool.transformed_patch()
    tool.set_position(20, 30)
    assert tool.transformed_patch() is first
    tool.set_rotation(20)
    second = tool.transformed_patch()
    assert second is not first
    tool.load_selection_patch(image + 10, mask, 0, 0)
    assert tool.transformed_patch() is not second


@pytest.mark.parametrize("mode", [cv2.NORMAL_CLONE, cv2.MIXED_CLONE])
def test_offcenter_poisson_keeps_landmark_and_mask(mode):
    y, x = np.mgrid[:48, :48]
    patch = np.repeat(np.clip(90 + 100 * np.exp(-((x - 12) ** 2 + (y - 18) ** 2) / 12), 0, 255).astype(np.uint8)[:, :, None], 3, axis=2)
    mask = np.zeros((48, 48), np.uint8)
    mask[8:30, 4:24] = 255
    target = np.full((100, 110, 3), 100, np.uint8)
    result = edit.compose_patch(target, patch, mask, 20, 25, mode=mode, fallback=False)
    peak = np.unravel_index(result[:, :, 0].argmax(), result.shape[:2])
    assert peak == (43, 32)
    selected = np.zeros(target.shape[:2], bool)
    selected[25:73, 20:68] = mask > 0
    assert np.array_equal(result[~selected], target[~selected])
    assert np.all(target == 100)


def test_poisson_invalid_placement_still_rejected():
    with pytest.raises(ValueError):
        edit.compose_patch(np.zeros((10, 10, 3), np.uint8), np.zeros((8, 8, 3), np.uint8), np.ones((8, 8), np.uint8), 9, 9, fallback=False)
