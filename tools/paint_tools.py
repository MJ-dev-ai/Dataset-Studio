from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtCore import QPointF, QTimer, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap

from core.qt_image import bgr_to_qpixmap, qimage_to_bgr
from service.editing_service import HealingStroke, apply_healing_strokes


@dataclass
class PaintOptions:
    size: int = 20
    hardness: float = 1.0
    opacity: float = 1.0
    color: QColor = field(default_factory=lambda: QColor(255, 255, 255))
    mode: str = "image"


class BasePaintTool:
    show_cursor_circle = True

    def __init__(self, canvas):
        self.canvas = canvas
        self.options = PaintOptions()
        self._last = None
        self._editing = False
        self._strokes = []

    @property
    def cursor_radius(self) -> float:
        return max(1.0, float(self.options.size) / 2.0)

    def activate(self) -> None:
        self.canvas.setCursor(Qt.CursorShape.CrossCursor)

    def deactivate(self) -> None:
        self.canvas.unsetCursor()
        self._last = None
        self._strokes = []

    def mouse_press_event(self, event) -> None:
        if self.canvas.pixmap.isNull():
            return
        window = self.canvas.window()
        if getattr(window, "current_mapset", None) is not None and hasattr(window, "begin_mapset_edit_history"):
            window.begin_mapset_edit_history()
        else:
            self.canvas._push_undo()
            self.canvas._redo.clear()
        self._editing = True
        self._last = self.canvas.to_image_pos(event.position())
        self._strokes = []
        self._record_stroke(self._last, self._last)

    def mouse_move_event(self, event) -> None:
        if not self._editing or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        point = self.canvas.to_image_pos(event.position())
        self._record_stroke(self._last, point)
        self._last = point

    def mouse_release_event(self, event) -> None:
        self.mouse_move_event(event)
        self._editing = False
        self._last = None
        self._apply_strokes()
        self._strokes = []

    def _record_stroke(self, start, end) -> None:
        self._strokes.append(((float(start.x()), float(start.y())), (float(end.x()), float(end.y()))))
        pixmap = QPixmap(self.canvas.pixmap)
        painter = QPainter(pixmap)
        color = QColor(self.options.color)
        color.setAlphaF(self.options.opacity)
        painter.setPen(QPen(color, self.options.size, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawLine(start, end)
        painter.end()
        self.canvas.pixmap = pixmap
        self.canvas.image = pixmap.toImage()
        self.canvas.update()

    def _apply_strokes(self) -> None:
        window = self.canvas.window()
        if hasattr(window, "apply_mapset_paint_strokes"):
            applied = window.apply_mapset_paint_strokes(
                list(self._strokes),
                QColor(self.options.color),
                self.options.size,
                self.options.opacity,
            )
            if applied:
                return
        self.canvas._revision += 1
        self.canvas.image_changed.emit()


class BrushTool(BasePaintTool):
    pass


class HealingBrushTool(BasePaintTool):
    """Heal target pixels by sampling an Alt-click source aligned to the stroke."""

    def __init__(self, canvas):
        super().__init__(canvas)
        self._source_anchor: QPointF | None = None
        self._target_anchor: QPointF | None = None
        self._healing_strokes: list[HealingStroke] = []
        self._preview_stroke_queue: list[HealingStroke] = []
        self._preview_source_image = None
        self._preview_result_image = None
        self._preview_flush_timer: QTimer | None = None
        self._preview_flush_interval_ms = 16

    def activate(self) -> None:
        super().activate()
        window = self.canvas.window()
        if self._source_anchor is None and hasattr(window, "set_status"):
            window.set_status("Healing Brush: Alt+click a clean source area")

    def deactivate(self) -> None:
        super().deactivate()
        self._target_anchor = None
        self._healing_strokes = []
        self._preview_stroke_queue = []
        self._preview_source_image = None
        self._preview_result_image = None
        if self._preview_flush_timer is not None:
            self._preview_flush_timer.stop()

    def mouse_press_event(self, event) -> None:
        if self.canvas.pixmap.isNull() or event.button() != Qt.MouseButton.LeftButton:
            return
        point = self.canvas.to_image_pos(event.position())
        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            self._source_anchor = QPointF(point)
            self._target_anchor = None
            self._set_status("Healing Brush source set")
            event.accept()
            return
        if self._source_anchor is None:
            self._set_status("Alt+click a clean source area before healing")
            event.accept()
            return
        window = self.canvas.window()
        if getattr(window, "current_mapset", None) is not None and hasattr(window, "begin_mapset_edit_history"):
            window.begin_mapset_edit_history()
        else:
            self.canvas._push_undo()
            self.canvas._redo.clear()
        self._editing = True
        self._last = QPointF(point)
        self._target_anchor = QPointF(point)
        self._healing_strokes = []
        self._preview_stroke_queue = []
        self._preview_source_image = qimage_to_bgr(self.canvas.pixmap)
        self._preview_result_image = self._preview_source_image.copy()
        self._record_stroke(self._last, self._last)
        event.accept()

    def mouse_move_event(self, event) -> None:
        if not self._editing or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        point = self.canvas.to_image_pos(event.position())
        self._record_stroke(self._last, point)
        self._last = QPointF(point)
        event.accept()

    def mouse_release_event(self, event) -> None:
        if not self._editing:
            return
        self.mouse_move_event(event)
        self._flush_preview_strokes()
        self._editing = False
        self._last = None
        self._apply_strokes()
        self._target_anchor = None
        self._healing_strokes = []
        self._preview_stroke_queue = []
        self._preview_source_image = None
        self._preview_result_image = None
        event.accept()

    def _record_stroke(self, start, end) -> None:
        if self._source_anchor is None or self._target_anchor is None:
            return
        source_start = self._source_for_target(start)
        source_end = self._source_for_target(end)
        stroke: HealingStroke = (
            (float(source_start.x()), float(source_start.y())),
            (float(source_end.x()), float(source_end.y())),
            (float(start.x()), float(start.y())),
            (float(end.x()), float(end.y())),
        )
        self._healing_strokes.append(stroke)
        self._preview_stroke_queue.append(stroke)
        self._schedule_preview_flush()

    def _source_for_target(self, target: QPointF) -> QPointF:
        """Return the source point aligned to the current stroke drag offset."""
        if self._source_anchor is None or self._target_anchor is None:
            return QPointF(target)
        return QPointF(
            self._source_anchor.x() + target.x() - self._target_anchor.x(),
            self._source_anchor.y() + target.y() - self._target_anchor.y(),
        )

    def _schedule_preview_flush(self) -> None:
        timer = self._ensure_preview_flush_timer()
        if timer is not None and not timer.isActive():
            timer.start(self._preview_flush_interval_ms)

    def _ensure_preview_flush_timer(self) -> QTimer | None:
        if self._preview_flush_timer is not None:
            return self._preview_flush_timer
        if not hasattr(self.canvas, "thread"):
            return None
        self._preview_flush_timer = QTimer(self.canvas)
        self._preview_flush_timer.setSingleShot(True)
        self._preview_flush_timer.timeout.connect(self._flush_preview_strokes)
        return self._preview_flush_timer

    def _flush_preview_strokes(self) -> None:
        if self._preview_flush_timer is not None:
            self._preview_flush_timer.stop()
        if not self._preview_stroke_queue:
            return
        strokes = list(self._preview_stroke_queue)
        self._preview_stroke_queue = []
        self._apply_preview_strokes(strokes)
        if self._preview_stroke_queue:
            self._schedule_preview_flush()

    def _apply_preview_strokes(self, strokes: list[HealingStroke]) -> None:
        image = self._preview_result_image
        if image is None or image.size == 0:
            return
        try:
            result = apply_healing_strokes(
                image,
                strokes,
                self.options.size,
                self.options.opacity,
                source_image=self._preview_source_image,
                inplace=True,
                fast_preview=True,
            )
        except ValueError as exc:
            self._set_status(f"Healing Brush failed: {exc}")
            return
        self._preview_result_image = result
        pixmap = bgr_to_qpixmap(result)
        self.canvas.pixmap = pixmap
        self.canvas.image = pixmap.toImage()
        self.canvas.update()

    def _apply_strokes(self) -> None:
        window = self.canvas.window()
        if hasattr(window, "apply_mapset_healing_strokes"):
            applied = window.apply_mapset_healing_strokes(
                list(self._healing_strokes),
                self.options.size,
                self.options.opacity,
            )
            if applied:
                return
        self.canvas._revision += 1
        self.canvas.image_changed.emit()

    def _set_status(self, message: str) -> None:
        window = self.canvas.window()
        if hasattr(window, "set_status"):
            window.set_status(message)


class EraserTool(BasePaintTool):
    def activate(self) -> None:
        super().activate()
        self.options.color = QColor("black")


class FillTool(BasePaintTool):
    show_cursor_circle = False

    def mouse_press_event(self, event) -> None:
        del event
        if self.canvas.pixmap.isNull():
            return
        window = self.canvas.window()
        if self.canvas.has_selection() and hasattr(window, "apply_mapset_selection_fill"):
            if window.apply_mapset_selection_fill(self.options.color, self.options.opacity):
                self._complete_if_possible()
                return
        if hasattr(window, "select_all") and hasattr(window, "apply_mapset_selection_fill"):
            window.select_all()
            if window.apply_mapset_selection_fill(self.options.color, self.options.opacity):
                self._complete_if_possible()
                return
        self.canvas._push_undo()
        pixmap = QPixmap(self.canvas.pixmap)
        painter = QPainter(pixmap)
        if self.canvas.has_selection():
            painter.fillPath(self.canvas.selection_path, self.options.color)
        else:
            painter.fillRect(pixmap.rect(), self.options.color)
        painter.end()
        self.canvas.replace_pixmap(pixmap, record_history=False)
        self._complete_if_possible()

    def _complete_if_possible(self) -> None:
        manager = getattr(self.canvas, "current_tool", None)
        if manager is not self and hasattr(manager, "complete_current_tool"):
            manager.complete_current_tool()


class BlurTool(BasePaintTool):
    pass


class ThresholdTool(BasePaintTool):
    pass
