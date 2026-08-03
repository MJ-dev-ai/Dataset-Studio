from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPainterPath, QPolygonF, QTransform


SelectionCombineMode = Literal["replace", "add", "subtract"]


@dataclass
class ExistingSelectionDrag:
    mode: str
    start_pos: QPointF
    start_path: QPainterPath
    start_bounds: QRectF
    annotation_index: int = -1


@dataclass
class SelectionDragResult:
    path: QPainterPath
    bounds: QRectF
    annotation_index: int
    changed: bool


def normalize_selection_combine_mode(value: str) -> SelectionCombineMode:
    """Normalize user-facing selection combine text to a selection operation."""
    normalized = str(value).strip().casefold()
    if normalized in {"add", "plus", "union"}:
        return "add"
    if normalized in {"subtract", "sub", "minus", "difference"}:
        return "subtract"
    return "replace"


class BaseSelectionTool:
    """Shared selection state and geometry helpers."""

    show_selection_handles = False

    def __init__(self):
        self.combine_mode: SelectionCombineMode = "replace"
        self._active_combine_mode: SelectionCombineMode = "replace"
        self._base_selection = QPainterPath()

    def reset(self) -> None:
        self.cancel_selection(clear_canvas=False)

    def set_combine_mode(self, mode: str) -> None:
        self.combine_mode = normalize_selection_combine_mode(mode)

    def combine_mode_from_modifiers(self, modifiers) -> SelectionCombineMode:
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            return "add"
        if modifiers & Qt.KeyboardModifier.AltModifier:
            return "subtract"
        return self.combine_mode

    def begin_selection(
        self,
        combine_mode: SelectionCombineMode,
        base_selection: QPainterPath,
    ) -> None:
        self._active_combine_mode = combine_mode
        self._base_selection = QPainterPath(base_selection)

    def finish_selection(self) -> None:
        self._base_selection = QPainterPath()
        self._active_combine_mode = self.combine_mode

    def cancel_selection(self, clear_canvas: bool = True) -> None:
        del clear_canvas
        self.finish_selection()

    def combined_selection(self, path: QPainterPath) -> QPainterPath:
        if self._active_combine_mode == "add":
            return self._base_selection.united(path)
        if self._active_combine_mode == "subtract":
            return self._base_selection.subtracted(path)
        return QPainterPath(path)


class RectSelectionTool(BaseSelectionTool):
    """Calculate rectangle selection geometry and existing-selection drags."""

    show_selection_handles = True

    def __init__(self):
        super().__init__()
        self.start_pos: QPointF | None = None
        self.annotation_click = False
        self.drag: ExistingSelectionDrag | None = None

    @property
    def is_drawing_rectangle(self) -> bool:
        return self.start_pos is not None

    @property
    def is_dragging_selection(self) -> bool:
        return self.drag is not None

    def cancel_selection(self, clear_canvas: bool = True) -> None:
        self.start_pos = None
        self.annotation_click = False
        self.drag = None
        super().cancel_selection(clear_canvas=clear_canvas)

    def mark_annotation_click(self) -> None:
        self.start_pos = None
        self.annotation_click = True

    def clear_annotation_click(self) -> None:
        self.annotation_click = False

    def begin_new_rectangle(
        self,
        point: QPointF,
        combine_mode: SelectionCombineMode,
        base_selection: QPainterPath,
    ) -> None:
        self.begin_selection(combine_mode, base_selection)
        self.start_pos = QPointF(point)
        self.annotation_click = False

    def preview_new_rectangle(self, point: QPointF) -> QPainterPath | None:
        if self.start_pos is None:
            return None
        path = QPainterPath()
        path.addRect(QRectF(self.start_pos, point).normalized())
        return self.combined_selection(path)

    def finish_new_rectangle(self, point: QPointF) -> QPainterPath | None:
        path = self.preview_new_rectangle(point)
        self.start_pos = None
        self.finish_selection()
        return path

    def begin_existing_selection_drag(
        self,
        mode: str,
        point: QPointF,
        selection_path: QPainterPath,
        selection_bounds: QRectF,
        selected_annotation_index: int,
    ) -> bool:
        bounds = QRectF(selection_bounds).normalized()
        if bounds.isNull() or bounds.width() < 1.0 or bounds.height() < 1.0:
            return False
        self.start_pos = None
        self.annotation_click = False
        self.drag = ExistingSelectionDrag(
            mode=mode,
            start_pos=QPointF(point),
            start_path=QPainterPath(selection_path),
            start_bounds=bounds,
            annotation_index=int(selected_annotation_index),
        )
        return True

    def preview_existing_selection_drag(
        self,
        point: QPointF,
        image_rect: QRectF,
    ) -> SelectionDragResult | None:
        return self._drag_selection(point, image_rect)

    def finish_existing_selection_drag(
        self,
        point: QPointF,
        image_rect: QRectF,
    ) -> SelectionDragResult | None:
        result = self._drag_selection(point, image_rect)
        self.drag = None
        return result

    def _drag_selection(
        self,
        point: QPointF,
        image_rect: QRectF,
    ) -> SelectionDragResult | None:
        drag = self.drag
        if drag is None:
            return None
        path = self._dragged_path(drag, QPointF(point), QRectF(image_rect))
        if path is None:
            return None
        bounds = path.boundingRect()
        if self._has_image_rect(image_rect):
            bounds = bounds.intersected(QRectF(image_rect))
        return SelectionDragResult(
            path=path,
            bounds=bounds,
            annotation_index=drag.annotation_index,
            changed=not self._rects_close(bounds, drag.start_bounds),
        )

    def _dragged_path(
        self,
        drag: ExistingSelectionDrag,
        point: QPointF,
        image_rect: QRectF,
    ) -> QPainterPath | None:
        start = drag.start_bounds
        if drag.mode == "move":
            dx = point.x() - drag.start_pos.x()
            dy = point.y() - drag.start_pos.y()
            if self._has_image_rect(image_rect):
                if start.left() + dx < image_rect.left():
                    dx = image_rect.left() - start.left()
                if start.top() + dy < image_rect.top():
                    dy = image_rect.top() - start.top()
                if start.right() + dx > image_rect.right():
                    dx = image_rect.right() - start.right()
                if start.bottom() + dy > image_rect.bottom():
                    dy = image_rect.bottom() - start.bottom()
            transform = QTransform()
            transform.translate(dx, dy)
            return transform.map(drag.start_path)

        if start.width() <= 0.0 or start.height() <= 0.0:
            return None
        if self._has_image_rect(image_rect):
            point = QPointF(
                max(image_rect.left(), min(point.x(), image_rect.right())),
                max(image_rect.top(), min(point.y(), image_rect.bottom())),
            )

        min_size = 1.0
        target = QRectF(start)
        if "left" in drag.mode:
            target.setLeft(min(point.x(), target.right() - min_size))
        if "right" in drag.mode:
            target.setRight(max(point.x(), target.left() + min_size))
        if "top" in drag.mode:
            target.setTop(min(point.y(), target.bottom() - min_size))
        if "bottom" in drag.mode:
            target.setBottom(max(point.y(), target.top() + min_size))
        target = target.normalized()
        if target.width() < min_size or target.height() < min_size:
            return None

        transform = QTransform()
        transform.translate(target.left(), target.top())
        transform.scale(target.width() / start.width(), target.height() / start.height())
        transform.translate(-start.left(), -start.top())
        return transform.map(drag.start_path)

    @staticmethod
    def _has_image_rect(image_rect: QRectF) -> bool:
        return not image_rect.isNull() and image_rect.width() > 0.0 and image_rect.height() > 0.0

    @staticmethod
    def _rects_close(left: QRectF, right: QRectF) -> bool:
        tolerance = 1e-6
        return (
            abs(left.left() - right.left()) <= tolerance
            and abs(left.top() - right.top()) <= tolerance
            and abs(left.width() - right.width()) <= tolerance
            and abs(left.height() - right.height()) <= tolerance
        )


class PolygonSelectionTool(BaseSelectionTool):
    def __init__(self):
        super().__init__()
        self.points: list[QPointF] = []

    @property
    def has_points(self) -> bool:
        return bool(self.points)

    def reset(self) -> None:
        self.cancel_selection(clear_canvas=bool(self.points))

    def cancel_selection(self, clear_canvas: bool = True) -> None:
        self.points.clear()
        super().cancel_selection(clear_canvas=clear_canvas)

    def add_point(
        self,
        point: QPointF,
        combine_mode: SelectionCombineMode,
        base_selection: QPainterPath,
    ) -> QPainterPath | None:
        if not self.points:
            self.begin_selection(combine_mode, base_selection)
        self.points.append(QPointF(point))
        return self.preview_polygon()

    def preview_polygon(self) -> QPainterPath | None:
        if len(self.points) < 2:
            return None
        path = QPainterPath(self.points[0])
        for point in self.points[1:]:
            path.lineTo(point)
        return self.combined_selection(path)

    def finish_polygon(self) -> QPainterPath | None:
        path = None
        if len(self.points) >= 3:
            polygon_path = QPainterPath()
            polygon_path.addPolygon(QPolygonF(self.points))
            polygon_path.closeSubpath()
            path = self.combined_selection(polygon_path)
        self.points.clear()
        self.finish_selection()
        return path


class LassoSelectionTool(BaseSelectionTool):
    def __init__(self):
        super().__init__()
        self.points: list[QPointF] = []
        self.annotation_click = False

    @property
    def is_drawing_lasso(self) -> bool:
        return bool(self.points) and not self.annotation_click

    def cancel_selection(self, clear_canvas: bool = True) -> None:
        self.points.clear()
        self.annotation_click = False
        super().cancel_selection(clear_canvas=clear_canvas)

    def mark_annotation_click(self) -> None:
        self.points = []
        self.annotation_click = True

    def clear_annotation_click(self) -> None:
        self.annotation_click = False

    def begin_lasso(
        self,
        point: QPointF,
        combine_mode: SelectionCombineMode,
        base_selection: QPainterPath,
    ) -> None:
        self.begin_selection(combine_mode, base_selection)
        self.points = [QPointF(point)]
        self.annotation_click = False

    def preview_lasso(self, point: QPointF) -> QPainterPath | None:
        if not self.is_drawing_lasso:
            return None
        self.points.append(QPointF(point))
        path = QPainterPath()
        path.addPolygon(QPolygonF(self.points))
        return self.combined_selection(path)

    def finish_lasso(self, point: QPointF) -> QPainterPath | None:
        if self.annotation_click:
            self.annotation_click = False
            return None
        self.preview_lasso(point)
        path = None
        if len(self.points) >= 3:
            lasso_path = QPainterPath()
            lasso_path.addPolygon(QPolygonF(self.points))
            lasso_path.closeSubpath()
            path = self.combined_selection(lasso_path)
        self.points.clear()
        self.finish_selection()
        return path
