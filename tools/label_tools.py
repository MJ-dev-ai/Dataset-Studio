from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath


@dataclass
class BBoxPreview:
    bounds: QRectF
    path: QPainterPath


class BBoxTool:
    """Calculate YOLO bounding-box selection geometry."""

    def __init__(self):
        self.start_pos: QPointF | None = None

    def reset(self) -> None:
        self.start_pos = None

    def begin_bbox(self, point: QPointF) -> None:
        self.start_pos = QPointF(point)

    def preview_bbox(self, point: QPointF) -> BBoxPreview | None:
        if self.start_pos is None:
            return None
        bounds = QRectF(self.start_pos, point).normalized()
        path = QPainterPath()
        path.addRect(bounds)
        return BBoxPreview(bounds=bounds, path=path)

    def finish_bbox(self, point: QPointF) -> BBoxPreview | None:
        preview = self.preview_bbox(point)
        self.start_pos = None
        if preview is None or preview.bounds.isEmpty():
            return None
        return preview
