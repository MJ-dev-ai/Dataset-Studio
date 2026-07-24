from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QRectF


@dataclass
class BBoxModel:
    class_id: int
    bounds: QRectF
    class_name: str = ""


class BBoxTool:
    """Tool for creating and editing YOLO bounding boxes."""

    def __init__(self, canvas):
        self.canvas = canvas
        self.start_pos = None
        self.labels: list[BBoxModel] = []
        self.class_id = 0
        self.class_name = ""

    def activate(self) -> None:
        self.start_pos = None

    def deactivate(self) -> None:
        self.start_pos = None

    def mouse_press_event(self, event) -> None:
        self.start_pos = self.canvas.to_image_pos(event.position())

    def mouse_move_event(self, event) -> None:
        if self.start_pos is None:
            return
        from PyQt6.QtGui import QPainterPath

        path = QPainterPath()
        path.addRect(QRectF(self.start_pos, self.canvas.to_image_pos(event.position())).normalized())
        self.canvas.set_selection(path)

    def mouse_release_event(self, event) -> None:
        if self.start_pos is None:
            return
        end_pos = self.canvas.to_image_pos(event.position())
        bounds = QRectF(self.start_pos, end_pos).normalized()
        if bounds.isEmpty():
            return
        from PyQt6.QtGui import QPainterPath

        path = QPainterPath()
        path.addRect(bounds)
        self.canvas.set_selection(path)
        self.start_pos = None
        self.canvas.update()
        window = self.canvas.window()
        if hasattr(window, "show_label_manager"):
            window.show_label_manager()

    def delete_selected_label(self) -> None:
        if self.canvas.annotations:
            self.canvas.annotations.pop()
            self.canvas.annotations_changed.emit()
            self.canvas.update()

    def set_class(self, class_id: int, class_name: str = "") -> None:
        self.class_id = int(class_id)
        self.class_name = class_name.strip()
