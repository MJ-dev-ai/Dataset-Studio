from __future__ import annotations

from enum import Enum
from typing import Callable

import cv2
import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap

from core.geometry import HealingStroke, PaintStroke
from core.patch_clipboard import PatchClip
from core.qt_image import bgr_mask_to_qpixmap, bgr_to_qpixmap, qimage_to_bgr
from service.editing_service import apply_healing_strokes
from tools.label_tools import BBoxTool, BBoxPreview
from tools.paint_tools import (
    BrushTool,
    EraserTool,
    FillTool,
    HealingBrushTool,
    PaintOptions,
)
from tools.patch_tools import PatchState, PatchTool
from tools.selection_tools import (
    LassoSelectionTool,
    PolygonSelectionTool,
    RectSelectionTool,
    SelectionDragResult,
)


class ToolMode(str, Enum):
    """User-facing canvas tool modes."""

    MOVE = "move"
    RECT = "rectangle"
    POLYGON = "polygon"
    LASSO = "lasso"
    BRUSH = "brush"
    HEALING_BRUSH = "healing_brush"
    ERASER = "eraser"
    FILL = "fill"
    PATCH = "patch"
    BBOX = "bbox"

    @classmethod
    def from_value(cls, value: ToolMode | str) -> ToolMode:
        if isinstance(value, cls):
            return value
        normalized = str(value).strip().casefold()
        aliases = {
            "move": cls.MOVE,
            "pan": cls.MOVE,
            "rect": cls.RECT,
            "rectangle": cls.RECT,
            "select": cls.RECT,
            "selection": cls.RECT,
            "polygon": cls.POLYGON,
            "poly": cls.POLYGON,
            "lasso": cls.LASSO,
            "brush": cls.BRUSH,
            "heal": cls.HEALING_BRUSH,
            "healing": cls.HEALING_BRUSH,
            "healing brush": cls.HEALING_BRUSH,
            "healing_brush": cls.HEALING_BRUSH,
            "eraser": cls.ERASER,
            "fill": cls.FILL,
            "patch": cls.PATCH,
            "paste": cls.PATCH,
            "poisson": cls.PATCH,
            "bbox": cls.BBOX,
            "label": cls.BBOX,
        }
        try:
            return aliases[normalized]
        except KeyError as exc:
            raise ValueError(f"Unknown tool mode: {value}") from exc


class ToolController:
    """Translate Qt canvas events into tool state changes and UI updates."""

    SELECTION_MODES = frozenset({ToolMode.RECT, ToolMode.POLYGON, ToolMode.LASSO})
    PAINT_MODES = frozenset({ToolMode.BRUSH, ToolMode.ERASER})

    def __init__(self, window):
        self.window = window
        self.canvas = window.canvas
        self.mode_changed: Callable[[ToolMode], None] | None = None
        self.patch_state_changed: Callable[[PatchState], None] | None = None
        self.current_mode = ToolMode.MOVE
        self._healing_preview_source_image = None
        self._healing_preview_result_image = None
        self._tools = {
            ToolMode.RECT: RectSelectionTool(),
            ToolMode.POLYGON: PolygonSelectionTool(),
            ToolMode.LASSO: LassoSelectionTool(),
            ToolMode.BRUSH: BrushTool(),
            ToolMode.HEALING_BRUSH: HealingBrushTool(),
            ToolMode.ERASER: EraserTool(),
            ToolMode.FILL: FillTool(),
            ToolMode.PATCH: PatchTool(),
            ToolMode.BBOX: BBoxTool(),
        }
        self.canvas.set_tool_controller(self)
        self.canvas.image_changed.connect(self.refresh_patch_preview)


    @property
    def patch_state(self) -> PatchState:
        return self.tool(ToolMode.PATCH).state

    @property
    def show_selection_handles(self) -> bool:
        return self.current_mode == ToolMode.RECT

    @property
    def show_cursor_circle(self) -> bool:
        return self.current_mode in self.PAINT_MODES or self.current_mode == ToolMode.HEALING_BRUSH

    @property
    def cursor_radius(self) -> float:
        if not self.show_cursor_circle:
            return 0.0
        return float(self.tool(self.current_mode).cursor_radius)

    def tool(self, mode: ToolMode | str):
        return self._tools[ToolMode.from_value(mode)]

    def has_patch_preview(self) -> bool:
        return self.tool(ToolMode.PATCH).paste_preview()

    def set_selection_combine_mode(self, mode: str) -> None:
        for tool_mode in (ToolMode.RECT, ToolMode.POLYGON, ToolMode.LASSO):
            self.tool(tool_mode).set_combine_mode(mode)

    def set_paint_size(self, size: int) -> None:
        for tool_mode in (ToolMode.BRUSH, ToolMode.HEALING_BRUSH, ToolMode.ERASER, ToolMode.FILL):
            self.tool(tool_mode).options.size = int(size)
        self.canvas.update()

    def set_paint_opacity(self, opacity: float) -> None:
        value = max(0.0, min(1.0, float(opacity)))
        for tool_mode in (ToolMode.BRUSH, ToolMode.HEALING_BRUSH, ToolMode.ERASER, ToolMode.FILL):
            self.tool(tool_mode).options.opacity = value

    def brush_color(self) -> QColor:
        return QColor(self.tool(ToolMode.BRUSH).options.color)

    def set_brush_color(self, color: QColor) -> None:
        for tool_mode in (ToolMode.BRUSH, ToolMode.HEALING_BRUSH, ToolMode.FILL):
            self.tool(tool_mode).options.color = QColor(color)

    def activate(self, mode: ToolMode | str | None = None) -> None:
        """Activate one tool mode, or re-apply the current cursor after panning."""
        changed = False
        if mode is not None:
            next_mode = ToolMode.from_value(mode)
            if next_mode != self.current_mode:
                self._deactivate_current_mode()
                self.current_mode = next_mode
                changed = True

        self._activate_current_mode()
        self.canvas.set_tool_controller(self)
        if mode is not None and changed and self.mode_changed is not None:
            self.mode_changed(self.current_mode)

    def cancel_current_tool(
        self,
        clear_canvas: bool = True,
        fallback_mode: ToolMode | str | None = ToolMode.MOVE,
    ) -> None:
        """Clear state owned by the active tool, then optionally switch modes."""
        self._clear_active_tool_state(clear_canvas=clear_canvas)
        if fallback_mode is not None:
            self.activate(fallback_mode)

    def complete_current_tool(self, fallback_mode: ToolMode | str = ToolMode.MOVE) -> None:
        """Commit/finish the active one-shot tool and return to a fallback mode."""
        if self.current_mode == ToolMode.PATCH:
            self.clear_active_patch()
        self.activate(fallback_mode)

    def finish_polygon_selection(self) -> None:
        if self.current_mode != ToolMode.POLYGON:
            return
        path = self.tool(ToolMode.POLYGON).finish_polygon()
        self._set_selection_path(path)

    def copy_selection_to_patch(self, source_name: str = "") -> bool:
        if self.canvas.pixmap.isNull() or not self.canvas.has_selection():
            return False
        bounds = self.canvas.selection_bounds().toAlignedRect().intersected(self.canvas.pixmap.rect())
        if bounds.isEmpty():
            return False
        source = qimage_to_bgr(self.canvas.pixmap)
        patch = source[bounds.top():bounds.bottom() + 1, bounds.left():bounds.right() + 1].copy()
        mask = self._selection_mask_array(bounds)
        if mask is None:
            return False
        ok = self.tool(ToolMode.PATCH).load_selection_patch(
            patch,
            mask,
            bounds.x(),
            bounds.y(),
            source_name,
        )
        self._notify_patch_state_changed()
        return ok

    def load_patch_clip(
        self,
        clip: PatchClip,
        center_x: float,
        center_y: float,
        map_key: str,
    ) -> bool:
        target_size = self._patch_target_size()
        if target_size is None:
            return False
        ok = self.tool(ToolMode.PATCH).load_clip(clip, center_x, center_y, map_key, target_size)
        self.refresh_patch_preview()
        return ok

    def set_patch_active_map_key(self, map_key: str) -> bool:
        target_size = self._patch_target_size()
        if target_size is None:
            return False
        ok = self.tool(ToolMode.PATCH).set_active_map_key(map_key, target_size)
        self.refresh_patch_preview()
        return ok

    def set_patch_position(self, x_pos: int, y_pos: int) -> bool:
        ok = self.tool(ToolMode.PATCH).set_position(x_pos, y_pos)
        self.refresh_patch_preview()
        return ok

    def set_patch_rotation(self, degrees: float) -> bool:
        ok = self.tool(ToolMode.PATCH).set_rotation(degrees)
        self.refresh_patch_preview()
        return ok

    def set_patch_scale(self, scale: float) -> bool:
        ok = self.tool(ToolMode.PATCH).set_scale(scale)
        self.refresh_patch_preview()
        return ok

    def rotate_patch(self, degrees: float) -> bool:
        ok = self.tool(ToolMode.PATCH).rotate(degrees)
        self.refresh_patch_preview()
        return ok

    def scale_patch(self, factor: float) -> bool:
        ok = self.tool(ToolMode.PATCH).scale(factor)
        self.refresh_patch_preview()
        return ok

    def reset_patch_transform(self) -> bool:
        ok = self.tool(ToolMode.PATCH).reset_transform()
        self.refresh_patch_preview()
        return ok

    def clear_active_patch(self) -> None:
        self.tool(ToolMode.PATCH).clear_active_patch()
        self.canvas.clear_patch_preview()
        self._notify_patch_state_changed()

    def refresh_patch_preview(self) -> None:
        tool: PatchTool = self.tool(ToolMode.PATCH)
        target_size = self._patch_target_size()
        if target_size is not None:
            tool.set_target_size(*target_size)
        try:
            preview = tool.preview_payload()
        except (ValueError, cv2.error):
            preview = None
        if preview is None:
            self.canvas.clear_patch_preview()
        else:
            self.canvas.set_patch_preview(
                bgr_mask_to_qpixmap(preview.patch, preview.mask),
                preview.x_pos,
                preview.y_pos,
            )
        self._notify_patch_state_changed()

    def patch_mapset_composition_inputs(
        self,
        target_images: dict[str, np.ndarray],
    ) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, int, int]]:
        return self.tool(ToolMode.PATCH).mapset_composition_inputs(target_images)

    def mouse_press_event(self, event) -> None:
        if self.current_mode == ToolMode.MOVE:
            self._press_navigation(event)
        elif self.current_mode == ToolMode.RECT:
            self._press_rect(event)
        elif self.current_mode == ToolMode.POLYGON:
            self._press_polygon(event)
        elif self.current_mode == ToolMode.LASSO:
            self._press_lasso(event)
        elif self.current_mode in self.PAINT_MODES:
            self._press_paint(event)
        elif self.current_mode == ToolMode.HEALING_BRUSH:
            self._press_healing(event)
        elif self.current_mode == ToolMode.FILL:
            self._press_fill(event)
        elif self.current_mode == ToolMode.PATCH:
            self._press_patch(event)
        elif self.current_mode == ToolMode.BBOX:
            self._press_bbox(event)

    def mouse_move_event(self, event) -> None:
        if self.current_mode == ToolMode.MOVE:
            self._move_navigation(event)
        elif self.current_mode == ToolMode.RECT:
            self._move_rect(event)
        elif self.current_mode == ToolMode.LASSO:
            self._move_lasso(event)
        elif self.current_mode in self.PAINT_MODES:
            self._move_paint(event)
        elif self.current_mode == ToolMode.HEALING_BRUSH:
            self._move_healing(event)
        elif self.current_mode == ToolMode.PATCH:
            self._move_patch(event)
        elif self.current_mode == ToolMode.BBOX:
            self._move_bbox(event)

    def mouse_release_event(self, event) -> None:
        if self.current_mode == ToolMode.MOVE:
            self._release_navigation(event)
        elif self.current_mode == ToolMode.RECT:
            self._release_rect(event)
        elif self.current_mode == ToolMode.LASSO:
            self._release_lasso(event)
        elif self.current_mode in self.PAINT_MODES:
            self._release_paint(event)
        elif self.current_mode == ToolMode.HEALING_BRUSH:
            self._release_healing(event)
        elif self.current_mode == ToolMode.PATCH:
            self._release_patch(event)
        elif self.current_mode == ToolMode.BBOX:
            self._release_bbox(event)

    def mouse_double_click_event(self, event) -> None:
        if self.current_mode == ToolMode.POLYGON:
            self.finish_polygon_selection()
            event.accept()

    def _activate_current_mode(self) -> None:
        if self.current_mode == ToolMode.MOVE:
            self.canvas.setCursor(Qt.CursorShape.OpenHandCursor)
        elif self.current_mode in self.SELECTION_MODES:
            self.canvas.setCursor(Qt.CursorShape.CrossCursor)
        elif self.current_mode in self.PAINT_MODES or self.current_mode in {ToolMode.HEALING_BRUSH, ToolMode.FILL, ToolMode.BBOX}:
            self.canvas.setCursor(Qt.CursorShape.CrossCursor)
            if self.current_mode == ToolMode.HEALING_BRUSH and not self.tool(ToolMode.HEALING_BRUSH).has_source_anchor:
                self.window.set_status("Healing Brush: Ctrl+click a clean source area")
        elif self.current_mode == ToolMode.PATCH:
            self.canvas.setCursor(Qt.CursorShape.SizeAllCursor)
            self.refresh_patch_preview()

    def _deactivate_current_mode(self) -> None:
        if self.current_mode == ToolMode.MOVE:
            self.canvas.end_pan()
        elif self.current_mode in self.SELECTION_MODES:
            self.tool(self.current_mode).cancel_selection(clear_canvas=False)
        elif self.current_mode in self.PAINT_MODES or self.current_mode == ToolMode.HEALING_BRUSH:
            self.tool(self.current_mode).reset()
            self._clear_healing_preview_state()
        elif self.current_mode == ToolMode.PATCH:
            self.tool(ToolMode.PATCH).end_move_drag()
            self.tool(ToolMode.PATCH).end_rotation_drag()
            self.canvas.clear_patch_preview()
        elif self.current_mode == ToolMode.BBOX:
            self.tool(ToolMode.BBOX).reset()

    def _press_navigation(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.canvas.begin_pan(event.position())
            event.accept()

    def _move_navigation(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.canvas.update_pan(event.position())
            event.accept()

    def _release_navigation(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.canvas.end_pan()
            self.canvas.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()

    def _press_rect(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        tool: RectSelectionTool = self.tool(ToolMode.RECT)
        point = self._image_point(event)
        combine_mode = tool.combine_mode_from_modifiers(event.modifiers())

        handle = None
        if combine_mode == "replace" and self.canvas.has_selection():
            handle = self.canvas.selection_handle_at(point)
        if handle is not None and tool.begin_existing_selection_drag(
            handle,
            point,
            self.canvas.selection_path,
            self.canvas.selection_edit_bounds(),
            self.canvas.selected_annotation_index,
        ):
            self.canvas.setCursor(self.canvas.cursor_for_selection_handle(handle))
            event.accept()
            return

        annotation_index = self.canvas.annotation_at(point)
        if annotation_index >= 0 and self.canvas.select_annotation(annotation_index):
            tool.mark_annotation_click()
            if combine_mode == "replace" and tool.begin_existing_selection_drag(
                "move",
                point,
                self.canvas.selection_path,
                self.canvas.selection_edit_bounds(),
                self.canvas.selected_annotation_index,
            ):
                self.canvas.setCursor(self.canvas.cursor_for_selection_handle("move"))
                event.accept()
            return

        self.canvas.clear_annotation_selection()
        tool.begin_new_rectangle(point, combine_mode, self.canvas.selection_path)

    def _move_rect(self, event) -> None:
        tool: RectSelectionTool = self.tool(ToolMode.RECT)
        point = self._image_point(event)
        combine_mode = tool.combine_mode_from_modifiers(event.modifiers())
        if tool.is_dragging_selection:
            if event.buttons() & Qt.MouseButton.LeftButton:
                result = tool.preview_existing_selection_drag(point, self._image_rect())
                self._apply_selection_drag_result(result, notify=False)
                event.accept()
            else:
                self._update_rect_hover_cursor(point, combine_mode)
            return
        if tool.is_drawing_rectangle:
            self._set_selection_path(tool.preview_new_rectangle(point))
            return
        self._update_rect_hover_cursor(point, combine_mode)

    def _release_rect(self, event) -> None:
        tool: RectSelectionTool = self.tool(ToolMode.RECT)
        point = self._image_point(event)
        if tool.is_dragging_selection:
            result = tool.finish_existing_selection_drag(point, self._image_rect())
            self._apply_selection_drag_result(result, notify=True)
            self._update_rect_hover_cursor(point, tool.combine_mode_from_modifiers(event.modifiers()))
            event.accept()
            return
        if tool.annotation_click:
            tool.clear_annotation_click()
            return
        self._set_selection_path(tool.finish_new_rectangle(point))

    def _press_polygon(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        tool: PolygonSelectionTool = self.tool(ToolMode.POLYGON)
        point = self._image_point(event)
        if not tool.has_points:
            annotation_index = self.canvas.annotation_at(point)
            if annotation_index >= 0 and self.canvas.select_annotation(annotation_index):
                return
            self.canvas.clear_annotation_selection()
        path = tool.add_point(point, tool.combine_mode_from_modifiers(event.modifiers()), self.canvas.selection_path)
        self._set_selection_path(path)

    def _press_lasso(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        tool: LassoSelectionTool = self.tool(ToolMode.LASSO)
        point = self._image_point(event)
        annotation_index = self.canvas.annotation_at(point)
        if annotation_index >= 0 and self.canvas.select_annotation(annotation_index):
            tool.mark_annotation_click()
            return
        self.canvas.clear_annotation_selection()
        tool.begin_lasso(point, tool.combine_mode_from_modifiers(event.modifiers()), self.canvas.selection_path)

    def _move_lasso(self, event) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        self._set_selection_path(self.tool(ToolMode.LASSO).preview_lasso(self._image_point(event)))

    def _release_lasso(self, event) -> None:
        self._set_selection_path(self.tool(ToolMode.LASSO).finish_lasso(self._image_point(event)))

    def _press_paint(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self.canvas.pixmap.isNull():
            return
        tool = self.tool(self.current_mode)
        self._begin_image_edit_history()
        segment = tool.begin_stroke(self._image_point(event))
        self._paint_segment_on_canvas(segment, tool.options)
        event.accept()

    def _move_paint(self, event) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        tool = self.tool(self.current_mode)
        segment = tool.continue_stroke(self._image_point(event))
        if segment is None:
            return
        self._paint_segment_on_canvas(segment, tool.options)
        event.accept()

    def _release_paint(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        tool = self.tool(self.current_mode)
        finish = tool.finish_stroke(self._image_point(event))
        if finish is None:
            return
        if finish.preview_segment is not None:
            self._paint_segment_on_canvas(finish.preview_segment, tool.options)
        self._commit_paint_strokes(finish.strokes, tool.options)
        event.accept()

    def _press_healing(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self.canvas.pixmap.isNull():
            return
        tool: HealingBrushTool = self.tool(ToolMode.HEALING_BRUSH)
        point = self._image_point(event)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            tool.set_source_anchor(point)
            self.window.set_status("Healing Brush source set")
            event.accept()
            return
        if not tool.has_source_anchor:
            self.window.set_status("Ctrl+click a clean source area before healing")
            return
        self._begin_image_edit_history()
        self._healing_preview_source_image = qimage_to_bgr(self.canvas.pixmap)
        self._healing_preview_result_image = self._healing_preview_source_image.copy()
        stroke = tool.begin_healing_stroke(point)
        if stroke is not None:
            self._apply_healing_preview_strokes([stroke])
            event.accept()

    def _move_healing(self, event) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        stroke = self.tool(ToolMode.HEALING_BRUSH).continue_healing_stroke(self._image_point(event))
        if stroke is None:
            return
        self._apply_healing_preview_strokes([stroke])
        event.accept()

    def _release_healing(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        finish = self.tool(ToolMode.HEALING_BRUSH).finish_healing_stroke(self._image_point(event))
        if finish is None:
            return
        if finish.preview_stroke is not None:
            self._apply_healing_preview_strokes([finish.preview_stroke])
        self._commit_healing_strokes(finish.strokes, self.tool(ToolMode.HEALING_BRUSH).options)
        self._clear_healing_preview_state()
        event.accept()

    def _press_fill(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._apply_fill(self.tool(ToolMode.FILL).options):
            event.accept()
            self.complete_current_tool(ToolMode.MOVE)

    def _press_patch(self, event) -> None:
        tool: PatchTool = self.tool(ToolMode.PATCH)
        point = self._image_point(event)
        if event.button() == Qt.MouseButton.RightButton and tool.begin_rotation_drag(point):
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and tool.begin_move_drag(point):
            event.accept()

    def _move_patch(self, event) -> None:
        tool: PatchTool = self.tool(ToolMode.PATCH)
        point = self._image_point(event)
        if event.buttons() & Qt.MouseButton.RightButton and tool.update_rotation_drag(point):
            self.refresh_patch_preview()
            event.accept()
            return
        if event.buttons() & Qt.MouseButton.LeftButton and tool.update_move_drag(point):
            self.refresh_patch_preview()
            event.accept()

    def _release_patch(self, event) -> None:
        tool: PatchTool = self.tool(ToolMode.PATCH)
        if event.button() == Qt.MouseButton.RightButton:
            tool.end_rotation_drag()
            self._notify_patch_state_changed()
            event.accept()
        elif event.button() == Qt.MouseButton.LeftButton:
            tool.end_move_drag()
            self._notify_patch_state_changed()
            event.accept()

    def _press_bbox(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.tool(ToolMode.BBOX).begin_bbox(self._image_point(event))

    def _move_bbox(self, event) -> None:
        preview = self.tool(ToolMode.BBOX).preview_bbox(self._image_point(event))
        self._apply_bbox_preview(preview)

    def _release_bbox(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        preview = self.tool(ToolMode.BBOX).finish_bbox(self._image_point(event))
        if preview is None:
            return
        self._apply_bbox_preview(preview)
        self.window.show_label_manager()

    def _paint_segment_on_canvas(self, segment: PaintStroke, options: PaintOptions) -> None:
        pixmap = QPixmap(self.canvas.pixmap)
        painter = QPainter(pixmap)
        color = QColor(options.color)
        color.setAlphaF(options.opacity)
        painter.setPen(QPen(
            color,
            options.size,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        ))
        painter.drawLine(
            QPointF(segment[0][0], segment[0][1]),
            QPointF(segment[1][0], segment[1][1]),
        )
        painter.end()
        self.canvas.pixmap = pixmap
        self.canvas.image = pixmap.toImage()
        self.canvas.update()

    def _commit_paint_strokes(self, strokes: list[PaintStroke], options: PaintOptions) -> None:
        if not strokes:
            return
        applied = self.window.apply_mapset_paint_strokes(
            list(strokes),
            QColor(options.color),
            options.size,
            options.opacity,
        )
        if applied:
            return
        self.canvas._revision += 1
        self.canvas.image_changed.emit()

    def _apply_healing_preview_strokes(self, strokes: list[HealingStroke]) -> None:
        image = self._healing_preview_result_image
        if image is None or image.size == 0 or not strokes:
            return
        try:
            result = apply_healing_strokes(
                image,
                list(strokes),
                self.tool(ToolMode.HEALING_BRUSH).options.size,
                self.tool(ToolMode.HEALING_BRUSH).options.opacity,
                source_image=self._healing_preview_source_image,
                inplace=True,
                fast_preview=True,
            )
        except ValueError as exc:
            self.window.set_status(f"Healing Brush failed: {exc}")
            return
        self._healing_preview_result_image = result
        pixmap = bgr_to_qpixmap(result)
        self.canvas.pixmap = pixmap
        self.canvas.image = pixmap.toImage()
        self.canvas.update()

    def _commit_healing_strokes(self, strokes: list[HealingStroke], options: PaintOptions) -> None:
        if not strokes:
            return
        applied = self.window.apply_mapset_healing_strokes(
            list(strokes),
            options.size,
            options.opacity,
        )
        if applied:
            return
        self.canvas._revision += 1
        self.canvas.image_changed.emit()

    def _clear_healing_preview_state(self) -> None:
        self._healing_preview_source_image = None
        self._healing_preview_result_image = None

    def _apply_fill(self, options: PaintOptions) -> bool:
        if self.canvas.pixmap.isNull():
            return False
        if self.canvas.has_selection():
            if self.window.apply_mapset_selection_fill(options.color, options.opacity):
                return True
        self.window.select_all()
        if self.window.apply_mapset_selection_fill(options.color, options.opacity):
            return True
        self._begin_image_edit_history()
        pixmap = QPixmap(self.canvas.pixmap)
        painter = QPainter(pixmap)
        if self.canvas.has_selection():
            painter.fillPath(self.canvas.selection_path, options.color)
        else:
            painter.fillRect(pixmap.rect(), options.color)
        painter.end()
        self.canvas.replace_pixmap(pixmap, record_history=False)
        return True

    def _begin_image_edit_history(self) -> None:
        if self.window.current_mapset is not None:
            self.window.begin_mapset_edit_history()
            return
        self.canvas._push_undo()
        self.canvas._redo.clear()

    def _set_selection_path(self, path: QPainterPath | None) -> None:
        if path is not None:
            self.canvas.set_selection(path)

    def _apply_bbox_preview(self, preview: BBoxPreview | None) -> None:
        if preview is not None:
            self.canvas.set_selection(preview.path)

    def _apply_selection_drag_result(
        self,
        result: SelectionDragResult | None,
        *,
        notify: bool,
    ) -> None:
        if result is None:
            return
        self.canvas.set_selection(result.path)
        if result.annotation_index < 0 or result.annotation_index != self.canvas.selected_annotation_index:
            return
        self.canvas.set_annotation_bounds(
            result.annotation_index,
            result.bounds,
            notify=notify and result.changed,
            sync_selection=False,
        )

    def _update_rect_hover_cursor(self, point, combine_mode) -> None:
        handle = None
        if combine_mode == "replace" and self.canvas.has_selection():
            handle = self.canvas.selection_handle_at(point)
        self.canvas.setCursor(self.canvas.cursor_for_selection_handle(handle))

    def _selection_mask_array(self, bounds) -> np.ndarray | None:
        mask_image = self.canvas.selection_mask(bounds)
        if mask_image.isNull():
            return None
        gray = mask_image.convertToFormat(QImage.Format.Format_Grayscale8)
        bits = gray.bits()
        bits.setsize(gray.sizeInBytes())
        view = np.frombuffer(bits, dtype=np.uint8).reshape(gray.height(), gray.bytesPerLine())
        return np.where(view[:, :gray.width()] > 0, 255, 0).astype(np.uint8).copy()

    def _patch_target_size(self) -> tuple[int, int] | None:
        if self.canvas.pixmap.isNull():
            return None
        return self.canvas.pixmap.width(), self.canvas.pixmap.height()

    def _notify_patch_state_changed(self) -> None:
        if self.patch_state_changed is not None:
            self.patch_state_changed(self.patch_state)

    def _clear_active_tool_state(self, clear_canvas: bool) -> None:
        if self.current_mode in self.SELECTION_MODES:
            self.tool(self.current_mode).cancel_selection(clear_canvas=clear_canvas)
            if clear_canvas:
                self.canvas.clear_selection()
            return
        if self.current_mode in self.PAINT_MODES or self.current_mode == ToolMode.HEALING_BRUSH:
            self.tool(self.current_mode).reset()
            self._clear_healing_preview_state()
        elif self.current_mode == ToolMode.PATCH:
            self.clear_active_patch()
            return
        elif self.current_mode == ToolMode.BBOX:
            self.tool(ToolMode.BBOX).reset()
        if clear_canvas:
            self.canvas.clear_selection()

    def _image_point(self, event):
        return self.canvas.to_image_pos(event.position())

    def _image_rect(self) -> QRectF:
        return QRectF(self.canvas.pixmap.rect()) if not self.canvas.pixmap.isNull() else QRectF()
