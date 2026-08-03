from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor

from core.geometry import HealingStroke, PaintStroke


@dataclass
class PaintOptions:
    size: int = 20
    hardness: float = 1.0
    opacity: float = 1.0
    color: QColor = field(default_factory=lambda: QColor(255, 255, 255))
    mode: str = "image"


@dataclass
class PaintStrokeFinish:
    strokes: list[PaintStroke]
    preview_segment: PaintStroke | None = None


@dataclass
class HealingStrokeFinish:
    strokes: list[HealingStroke]
    preview_stroke: HealingStroke | None = None


class BasePaintTool:
    """Track brush stroke geometry in image coordinates."""

    show_cursor_circle = True

    def __init__(self):
        self.options = PaintOptions()
        self._last: QPointF | None = None
        self._editing = False
        self._strokes: list[PaintStroke] = []

    @property
    def cursor_radius(self) -> float:
        return max(1.0, float(self.options.size) / 2.0)

    @property
    def is_editing(self) -> bool:
        return self._editing

    def reset(self) -> None:
        self._editing = False
        self._last = None
        self._strokes = []

    def begin_stroke(self, point: QPointF) -> PaintStroke:
        self._editing = True
        self._last = QPointF(point)
        self._strokes = []
        return self.record_stroke(self._last, self._last)

    def continue_stroke(self, point: QPointF) -> PaintStroke | None:
        if not self._editing or self._last is None:
            return None
        segment = self.record_stroke(self._last, point)
        self._last = QPointF(point)
        return segment

    def finish_stroke(self, point: QPointF | None = None) -> PaintStrokeFinish | None:
        if not self._editing:
            return None
        preview_segment = self.continue_stroke(point) if point is not None else None
        result = PaintStrokeFinish(strokes=list(self._strokes), preview_segment=preview_segment)
        self.reset()
        return result

    def record_stroke(self, start: QPointF, end: QPointF) -> PaintStroke:
        segment: PaintStroke = (
            (float(start.x()), float(start.y())),
            (float(end.x()), float(end.y())),
        )
        self._strokes.append(segment)
        return segment


class BrushTool(BasePaintTool):
    pass


class HealingBrushTool(BasePaintTool):
    """Track healing source-to-target stroke geometry."""

    def __init__(self):
        super().__init__()
        self._source_anchor: QPointF | None = None
        self._target_anchor: QPointF | None = None
        self._healing_strokes: list[HealingStroke] = []

    @property
    def has_source_anchor(self) -> bool:
        return self._source_anchor is not None

    @property
    def source_anchor(self) -> QPointF | None:
        """Return the center of the circular source sample, if selected."""
        return QPointF(self._source_anchor) if self._source_anchor is not None else None

    def reset(self) -> None:
        super().reset()
        self._target_anchor = None
        self._healing_strokes = []

    def clear_source_anchor(self) -> None:
        self._source_anchor = None
        self._target_anchor = None

    def set_source_anchor(self, point: QPointF) -> None:
        self._source_anchor = QPointF(point)
        self._target_anchor = None

    def begin_healing_stroke(self, point: QPointF) -> HealingStroke | None:
        if self._source_anchor is None:
            return None
        self._editing = True
        self._last = QPointF(point)
        self._target_anchor = QPointF(point)
        self._healing_strokes = []
        return self.record_healing_stroke(self._last, self._last)

    def continue_healing_stroke(self, point: QPointF) -> HealingStroke | None:
        if not self._editing or self._last is None:
            return None
        stroke = self.record_healing_stroke(self._last, point)
        self._last = QPointF(point)
        return stroke

    def finish_healing_stroke(self, point: QPointF | None = None) -> HealingStrokeFinish | None:
        if not self._editing:
            return None
        preview_stroke = self.continue_healing_stroke(point) if point is not None else None
        result = HealingStrokeFinish(strokes=list(self._healing_strokes), preview_stroke=preview_stroke)
        self.reset()
        return result

    def record_healing_stroke(self, start: QPointF, end: QPointF) -> HealingStroke | None:
        if self._source_anchor is None or self._target_anchor is None:
            return None
        source_start = self._source_for_target(start)
        source_end = self._source_for_target(end)
        stroke: HealingStroke = (
            (float(source_start.x()), float(source_start.y())),
            (float(source_end.x()), float(source_end.y())),
            (float(start.x()), float(start.y())),
            (float(end.x()), float(end.y())),
        )
        self._healing_strokes.append(stroke)
        return stroke

    def _source_for_target(self, target: QPointF) -> QPointF:
        if self._source_anchor is None or self._target_anchor is None:
            return QPointF(target)
        return QPointF(
            self._source_anchor.x() + target.x() - self._target_anchor.x(),
            self._source_anchor.y() + target.y() - self._target_anchor.y(),
        )


class EraserTool(BasePaintTool):
    def __init__(self):
        super().__init__()
        self.options.color = QColor("black")


class FillTool(BasePaintTool):
    show_cursor_circle = False
