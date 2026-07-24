from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def read_image(path: str | Path, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    """Read an image from a path that may contain non-ASCII characters."""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, flags)
    except Exception:
        return None


def write_png(path: str | Path, image: np.ndarray) -> bool:
    """Write an image as PNG to a path that may contain non-ASCII characters."""
    try:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        ok, data = cv2.imencode(".png", image)
        if not ok:
            return False
        data.tofile(str(destination))
        return True
    except Exception:
        return False
