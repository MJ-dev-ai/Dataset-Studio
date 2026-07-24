from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath

from tools.selection_tools import RectSelectionTool, normalize_selection_combine_mode


class CanvasStub:
    def __init__(self):
        self.selection_path = QPainterPath()

    def set_selection(self, path):
        self.selection_path = QPainterPath(path)


def _rect(left: float, top: float, width: float, height: float) -> QPainterPath:
    path = QPainterPath()
    path.addRect(left, top, width, height)
    return path


def test_selection_add_combines_with_base_path():
    canvas = CanvasStub()
    canvas.selection_path = _rect(0, 0, 10, 10)
    tool = RectSelectionTool(canvas)
    tool._base_selection = QPainterPath(canvas.selection_path)
    tool._active_combine_mode = "add"

    combined = tool._combined_selection(_rect(10, 0, 10, 10))

    assert combined.contains(QPointF(5, 5))
    assert combined.contains(QPointF(15, 5))


def test_selection_subtract_removes_from_base_path():
    canvas = CanvasStub()
    canvas.selection_path = _rect(0, 0, 10, 10)
    tool = RectSelectionTool(canvas)
    tool._base_selection = QPainterPath(canvas.selection_path)
    tool._active_combine_mode = "subtract"

    combined = tool._combined_selection(_rect(5, 0, 5, 10))

    assert combined.contains(QPointF(2, 5))
    assert not combined.contains(QPointF(8, 5))


def test_selection_mode_text_is_normalized():
    assert normalize_selection_combine_mode("Add") == "add"
    assert normalize_selection_combine_mode("Subtract") == "subtract"
    assert normalize_selection_combine_mode("anything else") == "replace"
