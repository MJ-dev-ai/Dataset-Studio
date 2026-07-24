from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QWidget
from core.patch_clipboard import PATCH_MIME_TYPE
from core.logging_setup import get_logger
from ui.themes import theme_colors


HISTORY_MEMORY_BUDGET = 256 * 1024 * 1024


def calculate_history_limit(width: int, height: int, budget_bytes: int = HISTORY_MEMORY_BUDGET) -> int:
    """Return a bounded number of full-image states for the configured budget."""
    bytes_per_state = max(1, width * height * 4)
    return max(1, min(50, budget_bytes // bytes_per_state))


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
    MIN_ZOOM = 0.02
    MAX_ZOOM = 64.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = None
        self.pixmap = QPixmap()
        self.zoom = 1.0
        self.pan_offset = QPointF(0.0, 0.0)
        self.current_tool = None
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
        self._background_color = QColor(theme_colors("dark")["canvas"])
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
        self.zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, float(zoom)))
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
        self.zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, float(zoom)))
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

    def draw_tool_cursor(self, painter: QPainter) -> None:
        active_tool = getattr(self.current_tool, "current_tool", self.current_tool)
        if active_tool is None or not getattr(active_tool, "show_cursor_circle", False):
            return
        if self._tool_cursor_pos is None or self.pixmap.isNull():
            return
        if not QRectF(self.pixmap.rect()).contains(self._tool_cursor_pos):
            return
        radius = float(getattr(active_tool, "cursor_radius", 0.0))
        if radius <= 0:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        dark_pen = QPen(QColor(0, 0, 0, 180), max(2.0 / self.zoom, 0.8))
        light_pen = QPen(QColor(255, 255, 255, 230), max(1.0 / self.zoom, 0.5))
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
        if self.current_tool is not None:
            self._dispatch_tool_event("mouse_press_event", event)

    def mouseMoveEvent(self, event):
        self._tool_cursor_pos = self.to_image_pos(event.position())
        self.update()
        if self._pan_active:
            self.update_pan(event.position())
            event.accept()
            return
        if self.current_tool is not None:
            self._dispatch_tool_event("mouse_move_event", event)

    def mouseReleaseEvent(self, event):
        self._tool_cursor_pos = self.to_image_pos(event.position())
        self.update()
        if self._pan_active and event.button() == Qt.MouseButton.MiddleButton:
            self.end_pan()
            if self.current_tool is not None and hasattr(self.current_tool, "activate"):
                self.current_tool.activate()
            event.accept()
            return
        if self.current_tool is not None:
            self._dispatch_tool_event("mouse_release_event", event)

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
        if self.current_tool is not None and hasattr(self.current_tool, "mouse_double_click_event"):
            self._dispatch_tool_event("mouse_double_click_event", event)

    def _dispatch_tool_event(self, method_name: str, event) -> None:
        """Keep recoverable tool failures from terminating the entire Qt process."""
        method = getattr(self.current_tool, method_name, None)
        if method is None:
            return
        try:
            method(event)
        except Exception as exc:  # Qt event-handler boundary.
            get_logger().exception("Canvas tool event failed: %s", method_name)
            self.tool_error.emit(str(exc))

    def set_tool(self, tool) -> None:
        self.current_tool = tool

    def fit_to_window(self) -> None:
        if self.pixmap.isNull() or self.width() <= 0 or self.height() <= 0:
            return
        self.zoom = max(
            self.MIN_ZOOM,
            min(self.MAX_ZOOM, self.width() / self.pixmap.width(), self.height() / self.pixmap.height()),
        )
        self.pan_offset = QPointF(
            (self.width() - self.pixmap.width() * self.zoom) / 2.0,
            (self.height() - self.pixmap.height() * self.zoom) / 2.0,
        )
        self._emit_view_changed()
        self.update()
