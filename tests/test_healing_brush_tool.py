from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QPointF

from tools.paint_tools import HealingBrushTool


class _CanvasStub:
    pass


def test_healing_brush_aligns_source_to_drag_offset():
    tool = HealingBrushTool(_CanvasStub())
    tool._schedule_preview_flush = lambda: None
    tool._source_anchor = QPointF(10.0, 12.0)
    tool._target_anchor = QPointF(30.0, 40.0)

    tool._record_stroke(QPointF(30.0, 40.0), QPointF(35.0, 42.0))

    assert tool._healing_strokes == [
        (
            (10.0, 12.0),
            (15.0, 14.0),
            (30.0, 40.0),
            (35.0, 42.0),
        )
    ]
    assert tool._preview_stroke_queue == [
        (
            (10.0, 12.0),
            (15.0, 14.0),
            (30.0, 40.0),
            (35.0, 42.0),
        )
    ]
