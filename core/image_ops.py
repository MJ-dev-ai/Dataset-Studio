from __future__ import annotations

import cv2
import numpy as np


def rotate_bound(
    image: np.ndarray,
    angle: float,
    *,
    interpolation: int = cv2.INTER_LINEAR,
) -> np.ndarray:
    """Rotate an image without clipping while preserving its full bounds."""
    height, width = image.shape[:2]
    if angle % 360 == 0:
        return image.copy()
    center = (width / 2.0, height / 2.0)
    matrix = cv2.getRotationMatrix2D(center, -angle, 1.0)
    cos_value = abs(matrix[0, 0])
    sin_value = abs(matrix[0, 1])
    new_width = max(1, int((height * sin_value) + (width * cos_value)))
    new_height = max(1, int((height * cos_value) + (width * sin_value)))
    matrix[0, 2] += (new_width / 2.0) - center[0]
    matrix[1, 2] += (new_height / 2.0) - center[1]
    return cv2.warpAffine(
        image,
        matrix,
        (new_width, new_height),
        flags=interpolation,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
