from __future__ import annotations

from PyQt6.QtCore import Qt


class NavigationTool:
    """Pan the shared canvas viewport without changing image coordinates."""

    def __init__(self, canvas):
        self.canvas = canvas

    def activate(self) -> None:
        self.canvas.setCursor(Qt.CursorShape.OpenHandCursor)

    def deactivate(self) -> None:
        self.canvas.end_pan()

    def mouse_press_event(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.canvas.begin_pan(event.position())

    def mouse_move_event(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.canvas.update_pan(event.position())

    def mouse_release_event(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.canvas.end_pan()
            self.canvas.setCursor(Qt.CursorShape.OpenHandCursor)
