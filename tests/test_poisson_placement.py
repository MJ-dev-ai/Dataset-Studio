import random

import cv2
import numpy as np

from service.augmentation_service import choose_patch_position_in_contour


def test_placement_keeps_active_patch_fully_inside_roi():
    """A placed patch must not extend beyond a non-rectangular ROI."""
    contour = np.array([[5, 5], [35, 5], [20, 35]], dtype=np.int32)
    patch = np.ones((9, 9, 3), dtype=np.uint8)
    mask = np.full((9, 9), 255, dtype=np.uint8)

    position = choose_patch_position_in_contour(contour, (40, 40, 3), patch, random.Random(3), mask)

    assert position is not None
    roi = np.zeros((40, 40), dtype=np.uint8)
    cv2.fillPoly(roi, [contour], 255)
    x, y = position
    assert np.all(roi[y : y + 9, x : x + 9] > 0)


def test_placement_avoids_existing_labels_with_a_gap():
    """Placement retries must reject positions clustered around occupied labels."""
    contour = np.array([[0, 0], [59, 0], [59, 59], [0, 59]], dtype=np.int32)
    patch = np.ones((10, 10, 3), dtype=np.uint8)
    occupied = [(0, 0, 42, 60)]

    position = choose_patch_position_in_contour(
        contour, (60, 60, 3), patch, random.Random(7), occupied_boxes=occupied, max_attempts=500
    )

    assert position is not None
    assert position[0] >= 44


def test_placement_returns_none_when_no_collision_free_space_exists():
    """Generation must skip a defect instead of forcing it onto an occupied area."""
    contour = np.array([[0, 0], [39, 0], [39, 39], [0, 39]], dtype=np.int32)
    patch = np.ones((8, 8, 3), dtype=np.uint8)

    position = choose_patch_position_in_contour(
        contour, (40, 40, 3), patch, random.Random(1), occupied_boxes=[(0, 0, 40, 40)]
    )

    assert position is None
