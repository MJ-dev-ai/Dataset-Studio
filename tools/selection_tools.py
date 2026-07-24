from __future__ import annotations

from typing import Literal

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPainterPath, QPolygonF


SelectionCombineMode = Literal["replace", "add", "subtract"]


def normalize_selection_combine_mode(value: str) -> SelectionCombineMode:
    """Normalize user-facing selection combine text to a tool operation."""
    normalized = str(value).strip().casefold()
    if normalized in {"add", "plus", "union"}:
        return "add"
    if normalized in {"subtract", "sub", "minus", "difference"}:
        return "subtract"
    return "replace"


class BaseSelectionTool:
    """Base class for tools that write to the canvas-wide selection model."""

    def __init__(self, canvas):
        self.canvas = canvas
        self.combine_mode: SelectionCombineMode = "replace"
        self._active_combine_mode: SelectionCombineMode = "replace"
        self._base_selection = QPainterPath()

    def activate(self) -> None:
        self.canvas.setCursor(Qt.CursorShape.CrossCursor)

    def deactivate(self) -> None:
        self.canvas.unsetCursor()

    def cancel_selection(self, clear_canvas: bool = True) -> None:
        """Cancel temporary selection state owned by the active tool."""
        self._base_selection = QPainterPath()
        self._active_combine_mode = self.combine_mode
        if clear_canvas:
            self.canvas.clear_selection()

    def set_combine_mode(self, mode: str) -> None:
        """Set the default operation used by new selection gestures."""
        self.combine_mode = normalize_selection_combine_mode(mode)

    def _begin_selection(self, event) -> None:
        self._active_combine_mode = self._mode_from_event(event)
        self._base_selection = QPainterPath(self.canvas.selection_path)

    def _mode_from_event(self, event) -> SelectionCombineMode:
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            return "add"
        if modifiers & Qt.KeyboardModifier.AltModifier:
            return "subtract"
        return self.combine_mode

    def _set_combined_selection(self, path: QPainterPath) -> None:
        self.canvas.set_selection(self._combined_selection(path))

    def _combined_selection(self, path: QPainterPath) -> QPainterPath:
        if self._active_combine_mode == "add":
            return self._base_selection.united(path)
        if self._active_combine_mode == "subtract":
            return self._base_selection.subtracted(path)
        return QPainterPath(path)

    def _end_selection(self) -> None:
        self._base_selection = QPainterPath()
        self._active_combine_mode = self.combine_mode


class RectSelectionTool(BaseSelectionTool):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.start_pos = None
        self._annotation_click = False

    def mouse_press_event(self, event) -> None:
        point = self.canvas.to_image_pos(event.position())
        annotation_index = self.canvas.annotation_at(point)
        if annotation_index >= 0:
            self.canvas.select_annotation(annotation_index)
            self.start_pos = None
            self._annotation_click = True
            return
        self.canvas.clear_annotation_selection()
        self._begin_selection(event)
        self.start_pos = point
        self._annotation_click = False

    def mouse_move_event(self, event) -> None:
        if self.start_pos is None:
            return
        path = QPainterPath()
        path.addRect(QRectF(self.start_pos, self.canvas.to_image_pos(event.position())).normalized())
        self._set_combined_selection(path)

    def mouse_release_event(self, event) -> None:
        if self._annotation_click:
            self._annotation_click = False
            return
        self.mouse_move_event(event)
        self.start_pos = None
        self._end_selection()

    def cancel_selection(self, clear_canvas: bool = True) -> None:
        """Cancel rectangle drawing state and optionally clear the active selection."""
        self.start_pos = None
        self._annotation_click = False
        super().cancel_selection(clear_canvas=clear_canvas)


class PolygonSelectionTool(BaseSelectionTool):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.points: list[QPointF] = []

    def deactivate(self) -> None:
        self.cancel_selection(clear_canvas=bool(self.points))
        super().deactivate()

    def mouse_press_event(self, event) -> None:
        point = self.canvas.to_image_pos(event.position())
        annotation_index = self.canvas.annotation_at(point)
        if annotation_index >= 0 and not self.points:
            self.canvas.select_annotation(annotation_index)
            return
        self.canvas.clear_annotation_selection()
        if not self.points:
            self._begin_selection(event)
        self.points.append(point)
        self._preview()

    def mouse_move_event(self, event) -> None:
        del event

    def mouse_release_event(self, event) -> None:
        del event

    def mouse_double_click_event(self, event) -> None:
        del event
        self.finish_polygon()

    def finish_polygon(self) -> None:
        if len(self.points) >= 3:
            path = QPainterPath()
            path.addPolygon(QPolygonF(self.points))
            path.closeSubpath()
            self._set_combined_selection(path)
        self.points.clear()
        self._end_selection()

    def cancel_selection(self, clear_canvas: bool = True) -> None:
        """Cancel polygon point accumulation and optionally clear the active selection."""
        self.points.clear()
        super().cancel_selection(clear_canvas=clear_canvas)

    def _preview(self) -> None:
        if len(self.points) < 2:
            return
        path = QPainterPath(self.points[0])
        for point in self.points[1:]:
            path.lineTo(point)
        self._set_combined_selection(path)


class LassoSelectionTool(BaseSelectionTool):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.points: list[QPointF] = []
        self._annotation_click = False

    def mouse_press_event(self, event) -> None:
        point = self.canvas.to_image_pos(event.position())
        annotation_index = self.canvas.annotation_at(point)
        if annotation_index >= 0:
            self.canvas.select_annotation(annotation_index)
            self.points = []
            self._annotation_click = True
            return
        self.canvas.clear_annotation_selection()
        self._begin_selection(event)
        self.points = [point]
        self._annotation_click = False

    def mouse_move_event(self, event) -> None:
        if self._annotation_click or not self.points:
            return
        self.points.append(self.canvas.to_image_pos(event.position()))
        path = QPainterPath()
        path.addPolygon(QPolygonF(self.points))
        self._set_combined_selection(path)

    def mouse_release_event(self, event) -> None:
        if self._annotation_click:
            self._annotation_click = False
            return
        self.mouse_move_event(event)
        if len(self.points) >= 3:
            path = QPainterPath()
            path.addPolygon(QPolygonF(self.points))
            path.closeSubpath()
            self._set_combined_selection(path)
        self.points.clear()
        self._end_selection()

    def cancel_selection(self, clear_canvas: bool = True) -> None:
        """Cancel lasso drawing state and optionally clear the active selection."""
        self.points.clear()
        self._annotation_click = False
        super().cancel_selection(clear_canvas=clear_canvas)
