from __future__ import annotations

import cv2
import numpy as np

def nonzero_bbox(mask_or_image: np.ndarray) -> tuple[int, int, int, int] | None:
    """Return x, y, w, h for nonzero pixels."""
    if mask_or_image is None or mask_or_image.size == 0:
        return None
    if mask_or_image.ndim == 3:
        mask = np.any(mask_or_image > 0, axis=2).astype(np.uint8)
    else:
        mask = (mask_or_image > 0).astype(np.uint8)
    if cv2.countNonZero(mask) == 0:
        return None
    return cv2.boundingRect(mask)

def make_nonzero_mask(image: np.ndarray) -> np.ndarray:
    """Create a uint8 mask from non-black pixels."""
    if image.ndim == 3:
        return np.where(np.any(image > 0, axis=2), 255, 0).astype(np.uint8)
    return np.where(image > 0, 255, 0).astype(np.uint8)

def morphology(mask: np.ndarray, operation: str, kernel_size: int, iterations: int = 1) -> np.ndarray:
    """Apply a simple OpenCV morphology operation."""
    kernel_size = max(1, int(kernel_size))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    operation_map = {
        "dilate": cv2.MORPH_DILATE,
        "erode": cv2.MORPH_ERODE,
        "open": cv2.MORPH_OPEN,
        "close": cv2.MORPH_CLOSE,
    }
    if operation not in operation_map:
        raise ValueError(f"Unsupported morphology operation: {operation}")
    return cv2.morphologyEx(mask, operation_map[operation], kernel, iterations=iterations)
