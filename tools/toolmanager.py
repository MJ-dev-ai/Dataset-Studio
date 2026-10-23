from __future__ import annotations

from enum import Enum
from typing import Callable

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap

from core.geometry import HealingStroke, PaintStroke
from core.patch_clipboard import PatchClip
from core.qt_image import bgr_mask_to_qpixmap, qimage_to_bgr
from service.editing_service import patch_mode_from_text
from tools.patch_preview import PatchPreviewController
from tools.healing_preview import HealingPreviewController
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


class ToolManager:
    """Single canvas tool router and image-coordinate owner.

    Flow:
    1. MainWindow/UiSetup activates a ToolMode or updates tool options.
    2. ImageCanvas forwards Qt mouse/drop events here.
    3. The active pure tool calculates geometry/state.
    4. ToolManager applies the result to canvas or asks MainWindow to commit data.
    """

    SELECTION_MODES = frozenset({ToolMode.RECT, ToolMode.POLYGON, ToolMode.LASSO})
    PAINT_MODES = frozenset({ToolMode.BRUSH, ToolMode.ERASER})
    TOOL_KEYS = {Qt.Key.Key_V: ToolMode.MOVE, Qt.Key.Key_H: ToolMode.MOVE, Qt.Key.Key_M: ToolMode.RECT, Qt.Key.Key_L: ToolMode.LASSO, Qt.Key.Key_P: ToolMode.POLYGON, Qt.Key.Key_B: ToolMode.BRUSH, Qt.Key.Key_J: ToolMode.HEALING_BRUSH, Qt.Key.Key_E: ToolMode.ERASER, Qt.Key.Key_G: ToolMode.FILL, Qt.Key.Key_K: ToolMode.PATCH, Qt.Key.Key_W: ToolMode.BBOX}

    def __init__(self, window):
        self.window = window
        self.canvas = window.canvas
        self.mode_changed: Callable[[ToolMode], None] | None = None
        self.patch_state_changed: Callable[[PatchState], None] | None = None
        self.current_mode = ToolMode.MOVE
        self._space_pressed = False
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
        self.canvas.set_tool_manager(self)
        self.patch_preview = PatchPreviewController(self.canvas)
        self.healing_preview = HealingPreviewController(self.canvas)
        self._healing_source_identity = None
        self.canvas.image_changed.connect(self.refresh_patch_preview)
        self.canvas.image_changed.connect(self._on_healing_image_changed)
        self.canvas.image_changed.connect(self.cancel_annotation_gesture)

    # UI-visible state queried by ImageCanvas and UiSetup.

    @property
    def patch_state(self) -> PatchState:
        return self.tool(ToolMode.PATCH).state

    @property
    def show_selection_handles(self) -> bool:
        return self.current_mode == ToolMode.RECT

    @property
    def annotation_editing_context(self) -> bool:
        """Route Undo by the active editing tool, keeping pixel history separate."""
        return self.current_mode == ToolMode.BBOX or (self.current_mode in self.SELECTION_MODES and bool(self.canvas.selected_annotation_index >= 0 or self.canvas._annotation_undo or self.canvas._annotation_redo))

    def cancel_annotation_gesture(self) -> bool:
        """Roll back a temporary box drag and discard an unfinished new box."""
        rect = self.tool(ToolMode.RECT)
        bbox = self.tool(ToolMode.BBOX)
        active = rect.is_dragging_selection or bbox.start_pos is not None
        self.canvas.cancel_annotation_edit()
        if rect.is_dragging_selection:
            rect.cancel_selection(False)
        if bbox.start_pos is not None:
            bbox.reset()
            self.canvas.clear_selection()
        return active

    @property
    def show_cursor_circle(self) -> bool:
        return self.current_mode in self.PAINT_MODES or self.current_mode == ToolMode.HEALING_BRUSH

    @property
    def cursor_radius(self) -> float:
        if not self.show_cursor_circle:
            return 0.0
        return float(self.tool(self.current_mode).cursor_radius)

    @property
    def healing_source_anchor(self) -> QPointF | None:
        """Return the Healing Brush source-circle center while that tool is active."""
        if self.current_mode != ToolMode.HEALING_BRUSH:
            return None
        return self.tool(ToolMode.HEALING_BRUSH).sampling_position

    def cancel_healing_preview(self) -> None:
        """Cancel an unfinished gesture without changing pixels or Undo."""
        self.tool(ToolMode.HEALING_BRUSH).reset()
        self.healing_preview.clear()

    def _on_healing_image_changed(self) -> None:
        self.cancel_healing_preview()
        identity = (str(self.window.current_image_path), self.canvas.pixmap.size())
        if not self.canvas.is_modified or identity != self._healing_source_identity:
            self.tool(ToolMode.HEALING_BRUSH).clear_source_anchor()

    def tool(self, mode: ToolMode | str):
        return self._tools[ToolMode.from_value(mode)]

    def has_patch_preview(self) -> bool:
        return self.tool(ToolMode.PATCH).paste_preview()

    # Commands called by UiSetup/MainWindow. These update pure tool state first,
    # then refresh canvas/UI feedback from that state.

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
        self.canvas.set_tool_manager(self)
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
        self.patch_preview.clear()
        self._notify_patch_state_changed()

    def refresh_patch_preview(self) -> None:
        if self.current_mode != ToolMode.PATCH or self.canvas.pixmap.isNull():
            self.patch_preview.clear()
            return
        tool: PatchTool = self.tool(ToolMode.PATCH)
        target_size = self._patch_target_size()
        if target_size is not None:
            tool.set_target_size(*target_size)
        try:
            preview = tool.preview_payload()
        except (ValueError, cv2.error):
            preview = None
        if preview is None:
            self.patch_preview.clear()
        else:
            combo = getattr(self.window, "optionsPoissonMode", None)
            label = combo.currentText() if combo is not None else "Normal"
            mode = patch_mode_from_text(label)
            map_key = self.window._current_map_key() or tool.state.map_key
            key = (
                self.canvas.pixmap.cacheKey(), str(self.window.current_image_path),
                map_key, id(preview.patch), id(preview.mask),
                preview.x_pos, preview.y_pos, mode,
            )
            if self.patch_preview.request(key, preview, mode, map_key, label):
                self.canvas.set_patch_preview(
                    bgr_mask_to_qpixmap(preview.patch, preview.mask), preview.x_pos, preview.y_pos,
                )
        self._notify_patch_state_changed()

    def patch_mapset_composition_inputs(
        self,
        target_images: dict[str, np.ndarray],
    ) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, int, int]]:
        return self.tool(ToolMode.PATCH).mapset_composition_inputs(target_images)

    # Canvas event flow. ImageCanvas forwards Qt mouse events here; each branch
    # converts widget coordinates once, calls the active tool, then applies the
    # result to canvas/window immediately.

    def accepts_key(self, event) -> bool:
        """Reserve editor keys only when the canvas owns keyboard focus."""
        key, mods = event.key(), event.modifiers()
        if mods & (Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier):
            return False
        if mods & Qt.KeyboardModifier.ControlModifier:
            return key in {Qt.Key.Key_A, Qt.Key.Key_D, Qt.Key.Key_T, Qt.Key.Key_0, Qt.Key.Key_1}
        if key in {Qt.Key.Key_Tab, Qt.Key.Key_Backtab, Qt.Key.Key_Delete}:
            return self.current_mode in {ToolMode.RECT, ToolMode.BBOX}
        if key == Qt.Key.Key_N:
            return True
        return key in self.TOOL_KEYS or key in {Qt.Key.Key_Space, Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Backspace, Qt.Key.Key_BracketLeft, Qt.Key.Key_BracketRight, Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down}

    def key_press_event(self, event) -> None:
        """Use contextual editor shortcuts without stealing keys from text fields."""
        key, mods = event.key(), event.modifiers()
        if key == Qt.Key.Key_Escape and self.current_mode in {ToolMode.RECT, ToolMode.BBOX}:
            if not self.cancel_annotation_gesture():
                self.tool(ToolMode.RECT).cancel_selection(False)
                self.canvas.select_annotation(-1)
            event.accept()
            return
        if key == Qt.Key.Key_Escape and self.current_mode == ToolMode.HEALING_BRUSH:
            self.cancel_healing_preview()
            event.accept()
            return
        # Do not abandon a mouse gesture and leave a half-committed edit behind.
        tool = self._tools.get(self.current_mode)
        if getattr(tool, "is_editing", False) or getattr(tool, "is_drawing_rectangle", False) or getattr(tool, "is_dragging_selection", False) or getattr(tool, "is_drawing_lasso", False) or (self.current_mode == ToolMode.BBOX and tool.start_pos is not None):
            return
        if mods & Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_D:
                self.window.clear_active_selection_state()
            elif key == Qt.Key.Key_A and not self.canvas.pixmap.isNull():
                path = QPainterPath()
                path.addRect(self._image_rect())
                self.canvas.set_selection(path)
            elif key == Qt.Key.Key_T and self.has_patch_preview():
                self.activate(ToolMode.PATCH)
            elif key == Qt.Key.Key_0:
                self.canvas.fit_to_window()
            elif key == Qt.Key.Key_1:
                self.canvas.actual_size()
        elif key == Qt.Key.Key_Space:
            self._space_pressed = True
            self.canvas.setCursor(Qt.CursorShape.OpenHandCursor)
        elif key == Qt.Key.Key_N:
            self.activate(ToolMode.BBOX)
        elif key in {Qt.Key.Key_Tab, Qt.Key.Key_Backtab}:
            self.canvas.cycle_annotation(key == Qt.Key.Key_Backtab or bool(mods & Qt.KeyboardModifier.ShiftModifier))
        elif key == Qt.Key.Key_Delete:
            self.window.remove_active_annotation()
        elif key == Qt.Key.Key_Escape:
            if self.current_mode == ToolMode.POLYGON and self.tool(ToolMode.POLYGON).points:
                self.canvas.set_selection(QPainterPath(self.tool(ToolMode.POLYGON)._base_selection))
            self.cancel_current_tool(clear_canvas=False, fallback_mode=None)
            self.patch_preview.clear()
        elif key in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            if not event.isAutoRepeat():
                if self.current_mode == ToolMode.POLYGON:
                    self.finish_polygon_selection()
                elif self.current_mode == ToolMode.PATCH and self.has_patch_preview():
                    self.window.ui_setup._apply_poisson()
        elif key == Qt.Key.Key_Backspace and self.current_mode == ToolMode.POLYGON:
            polygon = self.tool(ToolMode.POLYGON)
            if polygon.points:
                polygon.points.pop()
                self.canvas.set_selection(polygon.preview_polygon() or QPainterPath(polygon._base_selection))
        elif key in {Qt.Key.Key_BracketLeft, Qt.Key.Key_BracketRight} and self.show_cursor_circle:
            current = self.tool(self.current_mode).options.size
            size = max(1, min(1000, current + (1 if key == Qt.Key.Key_BracketRight else -1) * max(1, round(current * .1))))
            self.set_paint_size(size)
            spin = getattr(self.window, "spinOptionsBrushSize", None)
            if spin is not None:
                spin.setValue(size)
        elif self.current_mode == ToolMode.PATCH and key in {Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down}:
            step = 10 if mods & Qt.KeyboardModifier.ShiftModifier else 1
            dx = step * ((key == Qt.Key.Key_Right) - (key == Qt.Key.Key_Left))
            dy = step * ((key == Qt.Key.Key_Down) - (key == Qt.Key.Key_Up))
            self.set_patch_position(self.patch_state.x_pos + dx, self.patch_state.y_pos + dy)
        elif self.current_mode in {ToolMode.RECT, ToolMode.BBOX} and key in {Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down}:
            step = 10 if mods & Qt.KeyboardModifier.ShiftModifier else 1
            self.canvas.move_annotation(step * ((key == Qt.Key.Key_Right) - (key == Qt.Key.Key_Left)), step * ((key == Qt.Key.Key_Down) - (key == Qt.Key.Key_Up)))
        elif key in self.TOOL_KEYS and not event.isAutoRepeat():
            mode = self.TOOL_KEYS[key]
            if mods & Qt.KeyboardModifier.ShiftModifier and key == Qt.Key.Key_L:
                mode = ToolMode.POLYGON if self.current_mode != ToolMode.POLYGON else ToolMode.LASSO
            elif mods & Qt.KeyboardModifier.ShiftModifier and key == Qt.Key.Key_J:
                mode = ToolMode.PATCH if self.current_mode != ToolMode.PATCH else ToolMode.HEALING_BRUSH
            self.activate(mode)
        event.accept()

    def release_temporary_pan(self) -> None:
        """Restore the active tool on Space release or canvas focus loss."""
        if self._space_pressed:
            self._space_pressed = False
            self.canvas.end_pan()
            self._activate_current_mode()

    def image_pos(self, widget_pos) -> QPointF:
        return QPointF(
            (widget_pos.x() - self.canvas.pan_offset.x()) / max(self.canvas.zoom, 1e-6),
            (widget_pos.y() - self.canvas.pan_offset.y()) / max(self.canvas.zoom, 1e-6),
        )

    def mouse_press_event(self, event) -> None:
        self._update_cursor_position(event)
        if event.button() == Qt.MouseButton.MiddleButton or (self._space_pressed and event.button() == Qt.MouseButton.LeftButton):
            self.canvas.begin_pan(event.position())
            event.accept()
            return
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
        self._update_cursor_position(event)
        if self.canvas.is_panning:
            self.canvas.update_pan(event.position())
            event.accept()
            return
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
        self._update_cursor_position(event)
        if self.canvas.is_panning and event.button() in {Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton}:
            self.canvas.end_pan()
            self.activate()
            event.accept()
            return
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

    def wheel_event(self, event) -> bool:
        delta = event.angleDelta().y()
        if not delta:
            return False
        self.canvas.zoom_by(1.2 if delta > 0 else 1 / 1.2, event.position())
        event.accept()
        return True

    def dropped_patch_position(self, event) -> QPointF:
        return self.image_pos(event.position())

    # Mode enter/exit. Keep cursor and temporary tool state consistent whenever
    # UiSetup changes modes or panning re-applies the current mode.

    def _activate_current_mode(self) -> None:
        if self.current_mode == ToolMode.MOVE:
            self.canvas.setCursor(Qt.CursorShape.OpenHandCursor)
        elif self.current_mode in self.SELECTION_MODES:
            self.canvas.setCursor(Qt.CursorShape.CrossCursor)
        elif self.current_mode in self.PAINT_MODES or self.current_mode in {ToolMode.HEALING_BRUSH, ToolMode.FILL, ToolMode.BBOX}:
            self.canvas.setCursor(Qt.CursorShape.CrossCursor)
            if self.current_mode == ToolMode.HEALING_BRUSH and not self.tool(ToolMode.HEALING_BRUSH).has_source_anchor:
                self.window.set_status("Healing Brush: Alt+click to sample • [ / ] brush size • Space to pan")
        elif self.current_mode == ToolMode.PATCH:
            self.canvas.setCursor(Qt.CursorShape.SizeAllCursor)
            self.refresh_patch_preview()

    def _deactivate_current_mode(self) -> None:
        if self.current_mode in {ToolMode.RECT, ToolMode.BBOX}:
            self.cancel_annotation_gesture()
        if self.current_mode == ToolMode.HEALING_BRUSH:
            self.cancel_healing_preview()
        if self.current_mode == ToolMode.MOVE:
            self.canvas.end_pan()
        elif self.current_mode in self.SELECTION_MODES:
            self.tool(self.current_mode).cancel_selection(clear_canvas=False)
        elif self.current_mode in self.PAINT_MODES or self.current_mode == ToolMode.HEALING_BRUSH:
            self.tool(self.current_mode).reset()
        elif self.current_mode == ToolMode.PATCH:
            self.tool(ToolMode.PATCH).end_move_drag()
            self.tool(ToolMode.PATCH).end_rotation_drag()
            self.patch_preview.clear()
        elif self.current_mode == ToolMode.BBOX:
            self.tool(ToolMode.BBOX).reset()

    # Navigation events.

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

    # Selection events.

    def _press_rect(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        tool: RectSelectionTool = self.tool(ToolMode.RECT)
        point = self._image_point(event)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.canvas.cycle_annotation(point=point)
            event.accept()
            return
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
            if self.canvas.selected_annotation_index >= 0:
                self.canvas.begin_annotation_edit()
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
                self.canvas.begin_annotation_edit()
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
        if event.button() != Qt.MouseButton.LeftButton:
            return
        tool: RectSelectionTool = self.tool(ToolMode.RECT)
        point = self._image_point(event)
        if tool.is_dragging_selection:
            result = tool.finish_existing_selection_drag(point, self._image_rect())
            self._apply_selection_drag_result(result, notify=True)
            self.canvas.finish_annotation_edit()
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

    # Paint and healing events.

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
        if not self._image_rect().contains(point):
            return
        if self.window._healing_task_id in self.window._active_task_ids:
            self.window.set_status("힐링 브러시 적용 중입니다. 완료 후 다음 획을 그려 주세요.")
            return
        if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
            self.cancel_healing_preview()
            tool.set_source_anchor(point)
            self._healing_source_identity = (str(self.window.current_image_path), self.canvas.pixmap.size())
            self.canvas.update()
            self.window.set_status("Healing Brush source set")
            event.accept()
            return
        if not tool.has_source_anchor:
            self.window.set_status("Alt+click a clean source area before healing (Ctrl+click also works)")
            return
        stroke = tool.begin_healing_stroke(point)
        if stroke is not None:
            self.healing_preview.begin(tool.stroke_size, tool.stroke_opacity)
            self.healing_preview.request(tool.strokes)
            self.window.set_status("힐링 브러시: 드래그하며 결과 확인 · 놓으면 적용 · Esc 취소")
            event.accept()

    def _move_healing(self, event) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        tool = self.tool(ToolMode.HEALING_BRUSH)
        stroke = tool.continue_healing_stroke(self._image_point(event))
        if stroke is None:
            return
        self.healing_preview.request(tool.strokes)
        event.accept()

    def _release_healing(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        finish = self.tool(ToolMode.HEALING_BRUSH).finish_healing_stroke(self._image_point(event))
        if finish is None:
            return
        self.healing_preview.request(finish.strokes)
        self._commit_healing_strokes(finish.strokes, finish.size, finish.opacity)
        event.accept()

    # Fill, patch placement, and bbox label events.

    def _press_fill(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._apply_fill(self.tool(ToolMode.FILL).options):
            event.accept()

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
        point = self._image_point(event)
        if not self._image_rect().contains(point):
            return
        if self.window.annotationClassCombo.currentData() is None:
            self.window.set_status("먼저 오른쪽 '클래스 관리'에서 클래스를 등록해 주세요.")
            return
        self.canvas.clear_annotation_selection()
        self.tool(ToolMode.BBOX).begin_bbox(point)

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
        bounds = self.canvas.selection_bounds()
        if bounds.width() >= 1 and bounds.height() >= 1:
            self.window.quick_add_annotation()

    # Canvas mutation and MainWindow commit helpers.

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

    def _commit_healing_strokes(self, strokes: list[HealingStroke], size: int, opacity: float) -> None:
        if not strokes:
            return
        applied = self.window.apply_mapset_healing_strokes(list(strokes), size, opacity)
        if applied:
            self.healing_preview.mark_committing()
            return
        self.healing_preview.clear()

    def _apply_fill(self, options: PaintOptions) -> bool:
        """Fill the current selection without widening it on a fallback path."""
        if self.canvas.pixmap.isNull():
            return False
        if not self.canvas.has_selection():
            self.window.select_all()
        if self.window.apply_mapset_selection_fill(options.color, options.opacity):
            return True
        self._begin_image_edit_history()
        pixmap = QPixmap(self.canvas.pixmap)
        painter = QPainter(pixmap)
        painter.setOpacity(options.opacity)
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

    # Small geometry/state helpers.

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
        if self.current_mode == ToolMode.HEALING_BRUSH:
            self.cancel_healing_preview()
        if self.current_mode in self.SELECTION_MODES:
            self.tool(self.current_mode).cancel_selection(clear_canvas=clear_canvas)
            if clear_canvas:
                self.canvas.clear_selection()
            return
        if self.current_mode in self.PAINT_MODES or self.current_mode == ToolMode.HEALING_BRUSH:
            self.tool(self.current_mode).reset()
        elif self.current_mode == ToolMode.PATCH:
            self.clear_active_patch()
            return
        elif self.current_mode == ToolMode.BBOX:
            self.tool(ToolMode.BBOX).reset()
        if clear_canvas:
            self.canvas.clear_selection()

    def _image_point(self, event):
        return self.image_pos(event.position())

    def _update_cursor_position(self, event) -> None:
        self.canvas.set_tool_cursor_pos(self._image_point(event))

    def _image_rect(self) -> QRectF:
        return QRectF(self.canvas.pixmap.rect()) if not self.canvas.pixmap.isNull() else QRectF()
