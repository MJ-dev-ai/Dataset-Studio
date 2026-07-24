from __future__ import annotations

from enum import Enum
from typing import Callable

from tools.navigation_tools import NavigationTool
from tools.paint_tools import BrushTool, EraserTool, FillTool, HealingBrushTool
from tools.patch_tools import PatchTool
from tools.selection_tools import LassoSelectionTool, PolygonSelectionTool, RectSelectionTool


class ToolMode(str, Enum):
    MOVE = "move"
    RECT = "rect"
    POLYGON = "polygon"
    LASSO = "lasso"
    BRUSH = "brush"
    HEALING_BRUSH = "healing_brush"
    ERASER = "eraser"
    FILL = "fill"
    PATCH = "patch"

    @classmethod
    def from_value(cls, value: ToolMode | str) -> ToolMode:
        if isinstance(value, cls):
            return value
        normalized = str(value).strip().casefold()
        aliases = {
            "select": cls.RECT,
            "selection": cls.RECT,
            "rectangle": cls.RECT,
            "heal": cls.HEALING_BRUSH,
            "healing": cls.HEALING_BRUSH,
            "healing brush": cls.HEALING_BRUSH,
            "poisson": cls.PATCH,
            "paste": cls.PATCH,
        }
        if normalized in aliases:
            return aliases[normalized]
        return cls(normalized)


class ToolManager:
    """Register tool objects and route every canvas event through the active mode."""

    def __init__(self, canvas):
        self.canvas = canvas
        self.current_mode = ToolMode.MOVE
        self.current_tool = None
        self._tools: dict[ToolMode, object] = {}
        self.mode_changed: Callable[[ToolMode], None] | None = None
        self._register_default_tools()
        self.canvas.set_tool(self)

    @property
    def current_name(self) -> str:
        return self.current_mode.value

    def register_tool(self, mode: ToolMode | str, tool) -> None:
        self._tools[ToolMode.from_value(mode)] = tool

    def tool(self, mode: ToolMode | str):
        return self._tools.get(ToolMode.from_value(mode))

    def activate(self, mode: ToolMode | str) -> None:
        next_mode = ToolMode.from_value(mode)
        next_tool = self._tools.get(next_mode)
        if next_tool is None:
            return

        if self.current_tool is not None and self.current_tool is not next_tool:
            self._deactivate_tool(self.current_tool)

        self.current_mode = next_mode
        self.current_tool = next_tool
        self.canvas.set_tool(self)
        if hasattr(next_tool, "activate"):
            next_tool.activate()
        if self.mode_changed is not None:
            self.mode_changed(next_mode)

    def cancel_current_tool(
        self,
        clear_canvas: bool = True,
        fallback_mode: ToolMode = ToolMode.MOVE,
    ) -> None:
        self._clear_tool_state(self.current_tool, clear_canvas=clear_canvas)
        self.activate(fallback_mode)

    def complete_current_tool(self, fallback_mode: ToolMode = ToolMode.MOVE) -> None:
        if isinstance(self.current_tool, PatchTool):
            self.current_tool.clear_active_patch()
        self.activate(fallback_mode)

    def cancel_active_selection(self, clear_canvas: bool = True) -> None:
        self.cancel_current_tool(clear_canvas=clear_canvas, fallback_mode=ToolMode.MOVE)

    def mouse_press_event(self, event) -> None:
        self._dispatch("mouse_press_event", event)

    def mouse_move_event(self, event) -> None:
        self._dispatch("mouse_move_event", event)

    def mouse_release_event(self, event) -> None:
        self._dispatch("mouse_release_event", event)

    def mouse_double_click_event(self, event) -> None:
        self._dispatch("mouse_double_click_event", event)

    def _dispatch(self, method_name: str, event) -> None:
        tool = self._tools.get(self.current_mode)
        method = getattr(tool, method_name, None)
        if method is not None:
            method(event)

    def _deactivate_tool(self, tool) -> None:
        state = getattr(tool, "state", None)
        if isinstance(tool, PatchTool) and getattr(state, "patch", None) is not None:
            tool.clear_active_patch()
        if hasattr(tool, "deactivate"):
            tool.deactivate()

    def _clear_tool_state(self, tool, clear_canvas: bool) -> None:
        if hasattr(tool, "cancel_selection"):
            tool.cancel_selection(clear_canvas=clear_canvas)
        elif isinstance(tool, PatchTool):
            tool.clear_active_patch()
        elif clear_canvas:
            self.canvas.clear_selection()

    def _register_default_tools(self) -> None:
        self.register_tool(ToolMode.MOVE, NavigationTool(self.canvas))
        self.register_tool(ToolMode.RECT, RectSelectionTool(self.canvas))
        self.register_tool(ToolMode.POLYGON, PolygonSelectionTool(self.canvas))
        self.register_tool(ToolMode.LASSO, LassoSelectionTool(self.canvas))
        self.register_tool(ToolMode.BRUSH, BrushTool(self.canvas))
        self.register_tool(ToolMode.HEALING_BRUSH, HealingBrushTool(self.canvas))
        self.register_tool(ToolMode.ERASER, EraserTool(self.canvas))
        self.register_tool(ToolMode.FILL, FillTool(self.canvas))
        self.register_tool(ToolMode.PATCH, PatchTool(self.canvas))
