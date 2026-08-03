from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QWidget

from config.settings import (
    CANVAS_MAX_ZOOM,
    CANVAS_MIN_ZOOM,
    DEFAULT_THEME,
    HISTORY_MAX_STATES,
    HISTORY_MEMORY_BUDGET_BYTES,
    SELECTION_HANDLE_SIZE,
)
from core.logging_setup import get_logger
from core.patch_clipboard import PATCH_MIME_TYPE
from ui.themes import theme_colors


def calculate_history_limit(width: int, height: int, budget_bytes: int = HISTORY_MEMORY_BUDGET_BYTES) -> int:
    """Return a bounded number of full-image states for the configured budget."""
    bytes_per_state = max(1, width * height * 4)
    return max(1, min(HISTORY_MAX_STATES, budget_bytes // bytes_per_state))


@dataclass(frozen=True)
class CanvasAnnotation:
    class_id: int
    bounds: QRectF
    class_name: str = ""


class ImageCanvas(QWidget):
    """Memory-bounded image editor with shared selection and label overlays."""

    image_changed = pyqtSignal()
    selection_changed = pyqtSignal(bool)
    annotations_changed = pyqtSignal()
    view_changed = pyqtSignal(float, float, float)
    patch_dropped = pyqtSignal(str, QPointF)
    tool_error = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = None
        self.pixmap = QPixmap()
        self.zoom = 1.0
        self.pan_offset = QPointF(0.0, 0.0)
        self.tool_controller = None
        self.selection_path = QPainterPath()
        self.annotations: list[CanvasAnnotation] = []
        self.labels_visible = True
        self.selected_annotation_index = -1
        self.preview_pixmap = QPixmap()
        self.preview_annotations: list[CanvasAnnotation] | None = None
        self.patch_preview_pixmap = QPixmap()
        self.patch_preview_position = QPointF()
        self._tool_cursor_pos: QPointF | None = None
        self._undo: list[QImage] = []
        self._redo: list[QImage] = []
        self._revision = 0
        self._pan_active = False
        self._pan_start = QPointF()
        self._pan_origin = QPointF()
        self._background_color = QColor(theme_colors(DEFAULT_THEME)["canvas"])
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

    def set_theme(self, theme: str) -> None:
        """Update non-image canvas chrome without touching image pixels."""
        self._background_color = QColor(theme_colors(theme)["canvas"])
        self.update()

    def set_image(self, image: QImage | QPixmap) -> None:
        self.pixmap = QPixmap(image) if isinstance(image, QPixmap) else QPixmap.fromImage(image)
        self.image = self.pixmap.toImage()
        self._undo.clear()
        self._redo.clear()
        self._revision = 0
        self.clear_selection()
        self.annotations.clear()
        self.selected_annotation_index = -1
        self.clear_preview_image()
        self.image_changed.emit()
        self.update()

    def set_map_image(self, image: QImage | QPixmap, modified: bool = False) -> None:
        """Switch map pixels while preserving shared view, selection, and labels."""
        self.pixmap = QPixmap(image) if isinstance(image, QPixmap) else QPixmap.fromImage(image)
        self.image = self.pixmap.toImage()
        self._undo.clear()
        self._redo.clear()
        self._revision = 1 if modified else 0
        self.image_changed.emit()
        self.update()

    def view_state(self) -> tuple[float, float, float]:
        """Return zoom and normalized image coordinate at the viewport center."""
        if self.pixmap.isNull():
            return self.zoom, 0.5, 0.5
        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        image_center = self.to_image_pos(center)
        return (
            self.zoom,
            image_center.x() / max(1, self.pixmap.width()),
            image_center.y() / max(1, self.pixmap.height()),
        )

    def apply_view_state(self, zoom: float, x_ratio: float, y_ratio: float) -> None:
        """Restore the same normalized image position after a synchronized map switch."""
        if self.pixmap.isNull():
            return
        self.zoom = max(CANVAS_MIN_ZOOM, min(CANVAS_MAX_ZOOM, float(zoom)))
        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        image_point = QPointF(
            x_ratio * self.pixmap.width(),
            y_ratio * self.pixmap.height(),
        )
        self.pan_offset = center - image_point * self.zoom
        self._emit_view_changed()
        self.update()

    def set_zoom(self, zoom: float, anchor: QPointF | None = None) -> None:
        """Set zoom while keeping the image point below anchor stationary."""
        if self.pixmap.isNull():
            return
        anchor = QPointF(anchor) if anchor is not None else QPointF(self.width() / 2.0, self.height() / 2.0)
        image_point = self.to_image_pos(anchor)
        self.zoom = max(CANVAS_MIN_ZOOM, min(CANVAS_MAX_ZOOM, float(zoom)))
        self.pan_offset = anchor - image_point * self.zoom
        self._emit_view_changed()
        self.update()

    def zoom_by(self, factor: float, anchor: QPointF | None = None) -> None:
        self.set_zoom(self.zoom * factor, anchor)

    def actual_size(self) -> None:
        self.set_zoom(1.0)

    def begin_pan(self, position: QPointF) -> None:
        self._pan_active = True
        self._pan_start = QPointF(position)
        self._pan_origin = QPointF(self.pan_offset)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def update_pan(self, position: QPointF) -> None:
        if not self._pan_active:
            return
        self.pan_offset = self._pan_origin + (QPointF(position) - self._pan_start)
        self._emit_view_changed()
        self.update()

    def end_pan(self) -> None:
        self._pan_active = False
        self.unsetCursor()

    def _emit_view_changed(self) -> None:
        zoom, x_ratio, y_ratio = self.view_state()
        self.view_changed.emit(zoom, x_ratio, y_ratio)

    @property
    def is_modified(self) -> bool:
        return self._revision > 0

    @property
    def revision(self) -> int:
        """Return the current committed pixel revision for async edit guards."""
        return self._revision

    def mark_clean(self) -> None:
        """Mark committed pixels as persisted without changing their display."""
        self._revision = 0

    def replace_pixmap(self, pixmap: QPixmap, record_history: bool = True) -> None:
        if record_history and not self.pixmap.isNull():
            self._push_undo()
        self.pixmap = QPixmap(pixmap)
        self.image = self.pixmap.toImage()
        self._redo.clear()
        self.clear_preview_image()
        self._revision += 1
        self.image_changed.emit()
        self.update()


    def set_preview_image(self, image: QImage | QPixmap, annotations: list[CanvasAnnotation] | None = None) -> None:
        """Display temporary pixels and labels without committing image data."""
        self.preview_pixmap = QPixmap(image) if isinstance(image, QPixmap) else QPixmap.fromImage(image)
        self.preview_annotations = list(annotations) if annotations is not None else None
        self.update()

    def clear_preview_image(self) -> None:
        """Remove temporary preview pixels and restore committed image display."""
        if not self.preview_pixmap.isNull() or self.preview_annotations is not None:
            self.preview_pixmap = QPixmap()
            self.preview_annotations = None
            self.update()

    def has_preview_image(self) -> bool:
        """Return whether temporary preview pixels are currently displayed."""
        return not self.preview_pixmap.isNull()

    def set_patch_preview(self, pixmap: QPixmap, x_pos: int, y_pos: int) -> None:
        """Display a movable alpha-masked patch without committing image pixels."""
        self.patch_preview_pixmap = QPixmap(pixmap)
        self.patch_preview_position = QPointF(float(x_pos), float(y_pos))
        self.update()

    def clear_patch_preview(self) -> None:
        """Remove the manual patch overlay."""
        if not self.patch_preview_pixmap.isNull():
            self.patch_preview_pixmap = QPixmap()
            self.update()

    def has_patch_preview(self) -> bool:
        """Return whether a manual patch overlay is visible."""
        return not self.patch_preview_pixmap.isNull()

    def _push_undo(self) -> None:
        self._undo.append(self.pixmap.toImage())
        limit = calculate_history_limit(self.pixmap.width(), self.pixmap.height())
        del self._undo[:-limit]

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.pixmap.toImage())
        self.pixmap = QPixmap.fromImage(self._undo.pop())
        self.image = self.pixmap.toImage()
        self._revision += 1
        self.image_changed.emit()
        self.update()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.pixmap.toImage())
        self.pixmap = QPixmap.fromImage(self._redo.pop())
        self.image = self.pixmap.toImage()
        self._revision += 1
        self.image_changed.emit()
        self.update()
        return True

    def set_selection(self, path: QPainterPath) -> None:
        clipped = path.intersected(self._image_path()) if not self.pixmap.isNull() else path
        self.selection_path = QPainterPath(clipped)
        self.selection_changed.emit(self.has_selection())
        self.update()

    def clear_selection(self) -> None:
        had_selection = self.has_selection()
        self.selection_path = QPainterPath()
        if had_selection:
            self.selection_changed.emit(False)
        self.update()

    def has_selection(self) -> bool:
        return not self.selection_path.isEmpty()

    def selection_bounds(self) -> QRectF:
        return self.selection_path.boundingRect()

    def selection_edit_bounds(self) -> QRectF:
        """Return the visible image-space bounds used for selection handles."""
        if not self.has_selection():
            return QRectF()
        bounds = self.selection_bounds()
        if self.pixmap.isNull():
            return bounds
        return bounds.intersected(QRectF(self.pixmap.rect()))

    def selection_handle_rects(self) -> dict[str, QRectF]:
        bounds = self.selection_edit_bounds()
        if bounds.isNull() or bounds.width() < 1.0 or bounds.height() < 1.0:
            return {}
        size = max(float(SELECTION_HANDLE_SIZE) / max(self.zoom, 1e-6), 1.0)
        half = size / 2.0
        center = bounds.center()
        points = {
            "top_left": bounds.topLeft(),
            "top": QPointF(center.x(), bounds.top()),
            "top_right": bounds.topRight(),
            "right": QPointF(bounds.right(), center.y()),
            "bottom_right": bounds.bottomRight(),
            "bottom": QPointF(center.x(), bounds.bottom()),
            "bottom_left": bounds.bottomLeft(),
            "left": QPointF(bounds.left(), center.y()),
        }
        return {
            name: QRectF(point.x() - half, point.y() - half, size, size)
            for name, point in points.items()
        }

    def selection_handle_at(self, image_point: QPointF) -> str | None:
        """Return the active resize/move handle under an image-space point."""
        for name, rect in self.selection_handle_rects().items():
            if rect.contains(image_point):
                return name
        bounds = self.selection_edit_bounds()
        if not bounds.isNull() and bounds.contains(image_point):
            return "move"
        return None

    @staticmethod
    def cursor_for_selection_handle(handle: str | None) -> Qt.CursorShape:
        cursors = {
            "top_left": Qt.CursorShape.SizeFDiagCursor,
            "bottom_right": Qt.CursorShape.SizeFDiagCursor,
            "top_right": Qt.CursorShape.SizeBDiagCursor,
            "bottom_left": Qt.CursorShape.SizeBDiagCursor,
            "left": Qt.CursorShape.SizeHorCursor,
            "right": Qt.CursorShape.SizeHorCursor,
            "top": Qt.CursorShape.SizeVerCursor,
            "bottom": Qt.CursorShape.SizeVerCursor,
            "move": Qt.CursorShape.SizeAllCursor,
        }
        return cursors.get(handle, Qt.CursorShape.CrossCursor)

    def selection_mask(self, bounds: QRect | None = None) -> QImage:
        """Rasterize the active selection into a grayscale image-space mask."""
        if self.pixmap.isNull():
            return QImage()
        if bounds is None:
            bounds = self.selection_bounds().toAlignedRect().intersected(self.pixmap.rect())
        if bounds.isNull() or bounds.isEmpty():
            return QImage()
        mask = QImage(bounds.size(), QImage.Format.Format_Grayscale8)
        mask.fill(0)
        painter = QPainter(mask)
        painter.translate(-bounds.left(), -bounds.top())
        painter.fillPath(self.selection_path, QColor(255, 255, 255))
        painter.end()
        return mask

    def add_annotation_from_selection(self, class_id: int, class_name: str = "") -> bool:
        if not self.has_selection():
            return False
        bounds = self.selection_bounds().intersected(QRectF(self.pixmap.rect()))
        if bounds.isEmpty():
            return False
        self.annotations.append(CanvasAnnotation(class_id, bounds, class_name))
        self.selected_annotation_index = len(self.annotations) - 1
        self.annotations_changed.emit()
        self.update()
        return True

    def set_annotation_bounds(
        self,
        index: int,
        bounds: QRectF,
        notify: bool = True,
        sync_selection: bool = True,
    ) -> bool:
        """Update one annotation rectangle while preserving its class metadata."""
        if index < 0 or index >= len(self.annotations):
            return False
        rect = QRectF(bounds).normalized()
        if not self.pixmap.isNull():
            rect = rect.intersected(QRectF(self.pixmap.rect()))
        if rect.isNull() or rect.width() <= 0.0 or rect.height() <= 0.0:
            return False
        annotation = self.annotations[index]
        self.annotations[index] = CanvasAnnotation(annotation.class_id, rect, annotation.class_name)
        if sync_selection and self.selected_annotation_index == index:
            path = QPainterPath()
            path.addRect(rect)
            self.selection_path = path
            self.selection_changed.emit(True)
        if notify:
            self.annotations_changed.emit()
        self.update()
        return True

    def select_annotation(self, index: int) -> bool:
        """Select an existing annotation and expose its bounds as the active selection."""
        if index < 0 or index >= len(self.annotations):
            self.selected_annotation_index = -1
            self.update()
            return False
        self.selected_annotation_index = index
        path = QPainterPath()
        path.addRect(self.annotations[index].bounds)
        self.set_selection(path)
        self.update()
        return True

    def annotation_at(self, image_point: QPointF) -> int:
        """Return the topmost annotation containing an image-space point."""
        for index in range(len(self.annotations) - 1, -1, -1):
            if self.annotations[index].bounds.contains(image_point):
                return index
        return -1

    def clear_annotation_selection(self) -> None:
        self.selected_annotation_index = -1
        self.update()

    def set_labels_visible(self, visible: bool) -> None:
        self.labels_visible = bool(visible)
        self.update()

    def remove_annotation(self, index: int) -> bool:
        """Remove one annotation by stable list index."""
        if index < 0 or index >= len(self.annotations):
            return False
        self.annotations.pop(index)
        self.selected_annotation_index = -1
        self.clear_selection()
        self.annotations_changed.emit()
        self.update()
        return True

    def yolo_lines(self) -> list[str]:
        width, height = max(1, self.pixmap.width()), max(1, self.pixmap.height())
        lines = []
        for item in self.annotations:
            rect = item.bounds.intersected(QRectF(0, 0, width, height))
            lines.append(
                f"{item.class_id} {(rect.x() + rect.width()/2)/width:.6f} "
                f"{(rect.y() + rect.height()/2)/height:.6f} "
                f"{rect.width()/width:.6f} {rect.height()/height:.6f}"
            )
        return lines

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._background_color)
        display_pixmap = self.preview_pixmap if not self.preview_pixmap.isNull() else self.pixmap
        if not display_pixmap.isNull():
            painter.save()
            painter.translate(self.pan_offset)
            painter.scale(self.zoom, self.zoom)
            painter.drawPixmap(0, 0, display_pixmap)
            if not self.patch_preview_pixmap.isNull():
                painter.drawPixmap(self.patch_preview_position, self.patch_preview_pixmap)
            self.draw_overlay(painter)
            self.draw_tool_cursor(painter)
            painter.restore()
        painter.end()

    def draw_overlay(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if self.has_selection():
            painter.fillPath(self.selection_path, QColor(37, 99, 235, 35))
            painter.setPen(QPen(QColor("white"), max(1.0 / self.zoom, 0.5), Qt.PenStyle.DashLine))
            painter.drawPath(self.selection_path)
            if self.tool_controller is not None and self.tool_controller.show_selection_handles:
                self._draw_selection_handles(painter)
        pen = QPen(QColor("#ff4040"), max(2.0 / self.zoom, 1.0))
        painter.setPen(pen)
        if not self.labels_visible:
            return
        annotations = self.preview_annotations if self.preview_annotations is not None else self.annotations
        for index, annotation in enumerate(annotations):
            painter.setPen(
                QPen(
                    QColor("#f59e0b") if index == self.selected_annotation_index else QColor("#ff4040"),
                    max(3.0 / self.zoom, 1.0) if index == self.selected_annotation_index else max(2.0 / self.zoom, 1.0),
                )
            )
            painter.drawRect(annotation.bounds)
            painter.drawText(annotation.bounds.topLeft() + QPointF(2, 14), annotation.class_name or str(annotation.class_id))

    def _draw_selection_handles(self, painter: QPainter) -> None:
        handles = self.selection_handle_rects()
        if not handles:
            return
        painter.save()
        painter.setPen(QPen(QColor(37, 99, 235), max(1.0 / self.zoom, 0.5)))
        painter.setBrush(QColor(255, 255, 255))
        for rect in handles.values():
            painter.drawRect(rect)
        painter.restore()

    def draw_tool_cursor(self, painter: QPainter) -> None:
        if self.tool_controller is None or not self.tool_controller.show_cursor_circle:
            return
        if self._tool_cursor_pos is None or self.pixmap.isNull():
            return
        if not QRectF(self.pixmap.rect()).contains(self._tool_cursor_pos):
            return
        radius = float(self.tool_controller.cursor_radius)
        if radius <= 0:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        dark_pen = QPen(QColor(0, 0, 0, 180), max(2.0 / self.zoom, 0.8))
        light_pen = QPen(QColor(255, 255, 255, 230), max(1.0 / self.zoom, 0.5))
        source_anchor = self.tool_controller.healing_source_anchor
        if source_anchor is not None and QRectF(self.pixmap.rect()).contains(source_anchor):
            source_pen = QPen(
                QColor(34, 211, 238, 240),
                max(2.0 / self.zoom, 0.8),
                Qt.PenStyle.DashLine,
            )
            painter.setPen(source_pen)
            painter.drawEllipse(source_anchor, radius, radius)
        painter.setPen(dark_pen)
        painter.drawEllipse(self._tool_cursor_pos, radius, radius)
        painter.setPen(light_pen)
        painter.drawEllipse(self._tool_cursor_pos, radius, radius)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    def _image_path(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(QRectF(self.pixmap.rect()))
        return path

    def to_image_pos(self, widget_pos) -> QPointF:
        return QPointF(
            (widget_pos.x() - self.pan_offset.x()) / max(self.zoom, 1e-6),
            (widget_pos.y() - self.pan_offset.y()) / max(self.zoom, 1e-6),
        )

    def mousePressEvent(self, event):
        self._tool_cursor_pos = self.to_image_pos(event.position())
        self.update()
        if event.button() == Qt.MouseButton.MiddleButton:
            self.begin_pan(event.position())
            event.accept()
            return
        if self.tool_controller is not None:
            self._run_tool_event("mouse_press_event", self.tool_controller.mouse_press_event, event)

    def mouseMoveEvent(self, event):
        self._tool_cursor_pos = self.to_image_pos(event.position())
        self.update()
        if self._pan_active:
            self.update_pan(event.position())
            event.accept()
            return
        if self.tool_controller is not None:
            self._run_tool_event("mouse_move_event", self.tool_controller.mouse_move_event, event)

    def mouseReleaseEvent(self, event):
        self._tool_cursor_pos = self.to_image_pos(event.position())
        self.update()
        if self._pan_active and event.button() == Qt.MouseButton.MiddleButton:
            self.end_pan()
            if self.tool_controller is not None:
                self.tool_controller.activate()
            event.accept()
            return
        if self.tool_controller is not None:
            self._run_tool_event("mouse_release_event", self.tool_controller.mouse_release_event, event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta:
            self.zoom_by(1.2 if delta > 0 else 1 / 1.2, event.position())
            event.accept()
            return
        super().wheelEvent(event)

    def leaveEvent(self, event):
        self._tool_cursor_pos = None
        self.update()
        super().leaveEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(PATCH_MIME_TYPE) and not self.pixmap.isNull():
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(PATCH_MIME_TYPE) and not self.pixmap.isNull():
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(PATCH_MIME_TYPE) or self.pixmap.isNull():
            event.ignore()
            return
        try:
            clip_id = bytes(event.mimeData().data(PATCH_MIME_TYPE)).decode("ascii")
        except (UnicodeDecodeError, ValueError):
            event.ignore()
            return
        self.patch_dropped.emit(clip_id, self.to_image_pos(event.position()))
        event.acceptProposedAction()

    def mouseDoubleClickEvent(self, event):
        if self.tool_controller is not None:
            self._run_tool_event(
                "mouse_double_click_event",
                self.tool_controller.mouse_double_click_event,
                event,
            )

    def _run_tool_event(self, event_name: str, handler, event) -> None:
        """Keep recoverable tool failures from terminating the entire Qt process."""
        try:
            handler(event)
        except Exception as exc:  # Qt event-handler boundary.
            get_logger().exception("Canvas tool event failed: %s", event_name)
            self.tool_error.emit(str(exc))

    def set_tool_controller(self, controller) -> None:
        self.tool_controller = controller

    def fit_to_window(self) -> None:
        if self.pixmap.isNull() or self.width() <= 0 or self.height() <= 0:
            return
        self.zoom = max(
            CANVAS_MIN_ZOOM,
            min(CANVAS_MAX_ZOOM, self.width() / self.pixmap.width(), self.height() / self.pixmap.height()),
        )
        self.pan_offset = QPointF(
            (self.width() - self.pixmap.width() * self.zoom) / 2.0,
            (self.height() - self.pixmap.height() * self.zoom) / 2.0,
        )
        self._emit_view_changed()
        self.update()
