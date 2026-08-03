from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QPoint, QSignalBlocker, QSize, Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPixmap, QPolygon
from PyQt6.QtWidgets import (
    QAbstractButton,
    QColorDialog,
    QDockWidget,
    QMenu,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from service.editing_service import clone_mode_from_text
from ui.tool_controller import ToolMode
from ui.themes import theme_colors


class UiSetup:
    """Binds loaded Qt Designer UI widgets to Dataset Editor actions."""

    def __init__(self, window):
        self.window = window
        self.actions: dict[str, QAction] = {}
        self.action_icons: dict[str, str] = {}
        self.button_icons: dict[str, str] = {}
        self.tool_page_map: dict[ToolMode, str] = {
            ToolMode.MOVE: "pageOptionsNavigate",
            ToolMode.RECT: "pageOptionsSelect",
            ToolMode.POLYGON: "pageOptionsSelect",
            ToolMode.LASSO: "pageOptionsSelect",
            ToolMode.BRUSH: "pageOptionsBrush",
            ToolMode.HEALING_BRUSH: "pageOptionsBrush",
            ToolMode.ERASER: "pageOptionsBrush",
            ToolMode.FILL: "pageOptionsBrush",
            ToolMode.PATCH: "pageOptionsPaste",
        }
        self.property_page_map: dict[ToolMode, str] = {
            ToolMode.MOVE: "page_info",
            ToolMode.RECT: "page_info",
            ToolMode.POLYGON: "page_info",
            ToolMode.LASSO: "page_info",
            ToolMode.BRUSH: "page_info",
            ToolMode.HEALING_BRUSH: "page_info",
            ToolMode.ERASER: "page_info",
            ToolMode.FILL: "page_info",
            ToolMode.PATCH: "page_info",
        }

    def setup(self) -> None:
        self.window.tool_controller.mode_changed = self.update_tool_ui
        self._setup_action_texts()
        self._setup_file_menu()
        self._setup_edit_menu()
        self._setup_transform_menu()
        self._setup_tools_menu()
        self._setup_label_menu()
        self._setup_augment_menu()
        self._setup_view_menu()
        self._setup_menu_bar_order()
        self._setup_icons()
        self._setup_tool_buttons()
        self._setup_unified_tool_layout()
        self._setup_tool_button_style()
        self._setup_poisson_mode_controls()
        self._setup_manual_poisson_controls()
        self._setup_dock_layout()
        self._setup_properties_scroll_area()
        self._hide_label_tool_widgets()
        self._setup_initial_panel_state()
        self.apply_theme(getattr(self.window, "current_theme", "dark"))

    def _setup_poisson_mode_controls(self) -> None:
        """Keep the compact toolbar and Properties clone-mode controls synchronized."""
        toolbar_combo = getattr(self.window, "optionsPoissonMode", None)
        properties_combo = getattr(self.window, "combo_poisson_mode", None)
        if toolbar_combo is None or properties_combo is None:
            return
        for combo in (toolbar_combo, properties_combo):
            index = combo.findText("Monochrome")
            if index >= 0:
                combo.removeItem(index)
            if combo.findText("Detail Preserve") < 0:
                combo.insertItem(0, "Detail Preserve")
            if combo.findText("Boundary Mixed") < 0:
                combo.insertItem(0, "Boundary Mixed")
        toolbar_combo.setCurrentText(properties_combo.currentText())
        toolbar_combo.currentTextChanged.connect(properties_combo.setCurrentText)
        properties_combo.currentTextChanged.connect(toolbar_combo.setCurrentText)
        for name in ("button_poisson_apply", "optionsApplyPoisson"):
            button = getattr(self.window, name, None)
            if button is not None:
                button.setText("Apply Blend")

    def _setup_manual_poisson_controls(self) -> None:
        """Combine patch transforms and Poisson state into one functional panel."""
        layout = getattr(self.window, "layout_page_poisson", None)
        transform_group = getattr(self.window, "group_paste_transform", None)
        actions_group = getattr(self.window, "group_paste_actions", None)
        if layout is not None:
            if transform_group is not None:
                layout.insertWidget(1, transform_group)
            if actions_group is not None:
                layout.insertWidget(2, actions_group)
            self.window.buttonSavePoissonMapSet = QPushButton(
                "Save as New MapSet...", self.window.page_poisson
            )
            layout.insertWidget(max(0, layout.count() - 1), self.window.buttonSavePoissonMapSet)

        self.window.tool_controller.patch_state_changed = self._sync_manual_poisson_controls

        spin_x = getattr(self.window, "spin_paste_x", None)
        spin_y = getattr(self.window, "spin_paste_y", None)
        rotation = getattr(self.window, "double_paste_rotation", None)
        scale = getattr(self.window, "double_paste_scale", None)
        if spin_x is not None:
            spin_x.valueChanged.connect(
                lambda value: self.window.tool_controller.set_patch_position(
                    value,
                    self.window.tool_controller.patch_state.y_pos,
                )
            )
        if spin_y is not None:
            spin_y.valueChanged.connect(
                lambda value: self.window.tool_controller.set_patch_position(
                    self.window.tool_controller.patch_state.x_pos,
                    value,
                )
            )
        if rotation is not None:
            rotation.valueChanged.connect(self.window.tool_controller.set_patch_rotation)
        if scale is not None:
            scale.valueChanged.connect(self.window.tool_controller.set_patch_scale)
        self._sync_manual_poisson_controls(self.window.tool_controller.patch_state)

    def _sync_manual_poisson_controls(self, state) -> None:
        """Reflect PatchTool state without feeding values back through Qt signals."""
        controls = (
            (getattr(self.window, "spin_paste_x", None), int(state.x_pos)),
            (getattr(self.window, "spin_paste_y", None), int(state.y_pos)),
            (getattr(self.window, "double_paste_rotation", None), float(state.angle)),
            (getattr(self.window, "double_paste_scale", None), float(state.scale)),
        )
        blockers = [QSignalBlocker(widget) for widget, _ in controls if widget is not None]
        try:
            for widget, value in controls:
                if widget is not None:
                    widget.setValue(value)
        finally:
            del blockers

        patch = state.patch
        mask = state.mask
        target_name = (
            self.window.current_image_path.name
            if self.window.current_image_path is not None
            else "-"
        )
        values = {
            "label_poisson_source_value": state.source_name or "-",
            "label_poisson_target_value": target_name,
            "label_poisson_mask_value": (
                f"{mask.shape[1]} × {mask.shape[0]}"
                if mask is not None and mask.size
                else "-"
            ),
            "label_poisson_ready_value": "Yes" if patch is not None and mask is not None else "No",
        }
        for name, text in values.items():
            label = getattr(self.window, name, None)
            if label is not None:
                label.setText(text)

        ready = state.placement_active and patch is not None and mask is not None
        for name in ("button_poisson_apply", "optionsApplyPoisson", "button_paste_confirm", "optionsConfirmPaste"):
            button = getattr(self.window, name, None)
            if button is not None:
                button.setEnabled(ready)
        self._update_patch_action_availability()

    def set_manual_poisson_running(self, running: bool) -> None:
        """Lock commit and transform controls while the background blend runs."""
        for name in (
            "button_poisson_apply", "optionsApplyPoisson", "button_paste_confirm",
            "optionsConfirmPaste", "group_paste_transform", "group_paste_actions",
            "combo_poisson_mode", "optionsPoissonMode",
            "spin_paste_x", "spin_paste_y", "double_paste_rotation", "double_paste_scale",
        ):
            widget = getattr(self.window, name, None)
            if widget is not None:
                widget.setEnabled(not running)
        if not running:
            self._sync_manual_poisson_controls(self.window.tool_controller.patch_state)



    def _setup_properties_scroll_area(self) -> None:
        """Keep the Properties dock usable when its contents exceed the dock height."""
        dock_properties = getattr(self.window, "dockProperties", None)
        dock_contents = getattr(self.window, "dockPropertiesContents", None)
        properties_layout = getattr(self.window, "propertiesLayout", None)
        stack_properties = getattr(self.window, "stack_properties", None)

        if isinstance(dock_properties, QDockWidget):
            dock_properties.setMinimumSize(220, 120)
            dock_properties.setMinimumHeight(120)

        if isinstance(dock_contents, QWidget):
            dock_contents.setMinimumSize(210, 0)
            dock_contents.setMinimumHeight(0)

        if not isinstance(properties_layout, QVBoxLayout):
            return
        if not isinstance(stack_properties, QWidget):
            return
        if getattr(self.window, "propertiesScrollArea", None) is not None:
            return

        index = properties_layout.indexOf(stack_properties)
        if index < 0:
            return

        scroll_area = QScrollArea(self.window)
        scroll_area.setObjectName("propertiesScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setMinimumHeight(80)

        properties_layout.removeWidget(stack_properties)
        scroll_area.setWidget(stack_properties)
        properties_layout.insertWidget(index, scroll_area, 1)
        self.window.propertiesScrollArea = scroll_area

    def _hide_label_tool_widgets(self) -> None:
        """Hide legacy or unavailable tool widgets."""
        for widget_name in ("toolboxLabel", "pageOptionsLabel", "toolboxEyedropper"):
            widget = getattr(self.window, widget_name, None)
            if isinstance(widget, QWidget):
                widget.setEnabled(False)
                widget.hide()
        for action_name in ("action_labeling_tool", "action_eyedropper_tool"):
            action = getattr(self.window, action_name, None)
            if isinstance(action, QAction):
                action.setEnabled(False)
                action.setVisible(False)

    def _setup_action_texts(self) -> None:
        self._ensure_file_project_actions()
        self._ensure_editor_actions()
        self._set_action_text("action_open_project", "Open Project...")
        self._set_action_text("action_open_image", "Open Image...")
        self._set_action_text("action_open_Images", "Open Images as MapSets...")
        self._set_action_text("action_open_folder", "Open Dataset Folder...")
        self._set_action_text("action_save", "Save MapSet")
        self._set_action_text("action_save_all", "Save All")
        self._set_action_text("action_save_as", "Save MapSet As...")
        self._set_action_text("action_save_project", "Save Project")
        self._set_action_text("action_save_project_as", "Save Project As...")
        self._set_action_text("action_export_mask", "Export Selection Mask...")
        self._set_action_text("action_export_result", "Export YOLOv8 Dataset...")
        self._set_action_text("action_export_yolov8_dataset", "Export YOLOv8 Dataset...")
        self._set_action_text("action_auto_augment", "Open Auto Augmentation")
        self._set_action_text("action_export_defect_set", "Export Defect Patch...")
        self._set_action_text("action_auto_ellipse_roi", "Set Auto ROI to All MapSets")
        self._set_action_text("action_preprocess_options", "Preprocessing")
        self._set_action_text("action_label_browser", "Label Class Manager")
        if not isinstance(getattr(self.window, "action_healing_brush_tool", None), QAction):
            self.window.action_healing_brush_tool = QAction("Healing Brush Tool", self.window)
        self._set_action_text("action_healing_brush_tool", "Healing Brush Tool")
        self.window.action_healing_brush_tool.setShortcut("J")
        self._set_action_text("action_point_tool", "Patch Placement Tool")
        self._set_action_text("actionApply_Poisson", "Apply Poisson Blend")
        self._set_action_text("action_confirm", "Apply Hard Paste")
        self._set_action_text("action_copy", "Copy Patch")
        self._set_action_text("action_paste", "Paste Patch")
        self._set_action_text("action_delete", "Delete Selection / Label")
        copy_action = getattr(self.window, "action_copy", None)
        if isinstance(copy_action, QAction):
            copy_action.setShortcut("Ctrl+C")
        paste_action = getattr(self.window, "action_paste", None)
        if isinstance(paste_action, QAction):
            paste_action.setShortcut("Ctrl+V")
        fullscreen = getattr(self.window, "action_fullscreen", None)
        if isinstance(fullscreen, QAction):
            fullscreen.setShortcut("F11")
        self._set_action_text("actionAbout", "About Dataset Editor")
        button = getattr(self.window, "button_label_popup", None)
        if isinstance(button, QAbstractButton):
            button.setText("Manage Label Classes")
        if not hasattr(self.window, "action_fill_tool"):
            self.window.action_fill_tool = QAction("Fill Tool", self.window)
            self.window.action_fill_tool.setShortcut("G")
            menu_tools = getattr(self.window, "menuTools", None)
            if isinstance(menu_tools, QMenu):
                menu_tools.addAction(self.window.action_fill_tool)

    def _ensure_file_project_actions(self) -> None:
        """Create project actions that are not present in the legacy .ui file."""
        if not isinstance(getattr(self.window, "action_open_project", None), QAction):
            self.window.action_open_project = QAction("Load Project...", self.window)
            self.window.action_open_project.setShortcut("Ctrl+Alt+O")
        if not isinstance(getattr(self.window, "action_save_project", None), QAction):
            self.window.action_save_project = QAction("Save Project", self.window)
            self.window.action_save_project.setShortcut("Ctrl+Alt+S")
        if not isinstance(getattr(self.window, "action_save_project_as", None), QAction):
            self.window.action_save_project_as = QAction("Save Project As...", self.window)
            self.window.action_save_project_as.setShortcut("Ctrl+Alt+Shift+S")
        if not isinstance(getattr(self.window, "action_save_labels", None), QAction):
            self.window.action_save_labels = QAction("Save Labels", self.window)
            self.window.action_save_labels.setShortcut("Ctrl+L")
        if not isinstance(getattr(self.window, "action_save_all", None), QAction):
            self.window.action_save_all = QAction("Save All", self.window)
        self.window.action_save_all.setShortcut(QKeySequence())

    def _ensure_editor_actions(self) -> None:
        """Create menu actions for commands that only had screen buttons before."""
        if isinstance(getattr(self.window, "action_undo", None), QAction):
            self.window.action_undo.setText("Undo")
            self.window.action_undo.setShortcut(QKeySequence())
        if isinstance(getattr(self.window, "action_redo", None), QAction):
            self.window.action_redo.setText("Redo")
            self.window.action_redo.setShortcut(QKeySequence())
        action_specs = {
            "action_add_label_from_selection": ("Add Label from Selection", None),
            "action_remove_active_label": ("Remove Active Label", None),
            "action_reload_labels": ("Reload Labels", None),
            "action_copy_patch": ("Copy Patch", None),
            "action_paste_patch": ("Paste Patch", None),
            "action_export_defect": ("Export Defect Patch...", None),
            "action_auto_roi_selection": ("Auto ROI on Selection", None),
            "action_poisson_editing": ("Place Clipboard Patch", None),
        }
        for name, (text, shortcut) in action_specs.items():
            if not isinstance(getattr(self.window, name, None), QAction):
                setattr(self.window, name, QAction(text, self.window))
            action = getattr(self.window, name)
            action.setText(text)
            if shortcut:
                action.setShortcut(shortcut)

        hidden_actions = (
            "action_cut",
            "action_close",
            "action_close_all",
            "action_cascade_windows",
            "action_tile_windows",
            "action_eyedropper_tool",
            "action_labeling_tool",
            "action_brush_tool_2",
            "action_export_result",
            "action_augment_options",
            "action_augment_preview",
            "action_augment_resize",
            "action_augment_flip_horizontal",
            "action_augment_flip_vertical",
            "action_augment_rotate_cw",
            "action_augment_rotate_ccw",
            "action_augment_rotate_180",
        )
        for name in hidden_actions:
            action = getattr(self.window, name, None)
            if isinstance(action, QAction):
                action.setEnabled(False)
                action.setVisible(False)

    def _setup_file_menu(self) -> None:
        """Expose file workflows directly without unnecessary submenus."""
        self._ensure_file_project_actions()
        self._ensure_editor_actions()
        menu = getattr(self.window, "menuFile", None)
        if not isinstance(menu, QMenu):
            return

        menu.clear()
        menu.setTitle("File")
        menu.addAction(self.window.action_open_project)
        menu.addAction(self.window.action_open_folder)
        menu.addSeparator()
        menu.addAction(self.window.action_open_image)
        menu.addAction(self.window.action_open_Images)
        menu.addSeparator()
        menu.addAction(self.window.action_save_project)
        menu.addAction(self.window.action_save_project_as)
        menu.addSeparator()
        menu.addAction(self.window.action_save)
        menu.addAction(self.window.action_save_all)
        menu.addAction(self.window.action_save_as)
        menu.addAction(self.window.action_save_labels)
        menu.addSeparator()
        menu.addAction(self.window.action_export_mask)
        menu.addAction(self.window.action_export_defect)
        menu.addAction(self.window.action_export_yolov8_dataset)
        menu.addSeparator()
        menu.addAction(self.window.action_exit)

    def _setup_edit_menu(self) -> None:
        """Keep Edit focused on history, mapset clipboard, and selection edits."""
        self._ensure_editor_actions()
        menu = getattr(self.window, "menuEdit", None)
        if not isinstance(menu, QMenu):
            return

        menu.clear()
        menu.addAction(self.window.action_undo)
        menu.addAction(self.window.action_redo)
        menu.addSeparator()
        menu.addAction(self.window.action_copy)
        menu.addAction(self.window.action_paste)
        menu.addSeparator()
        menu.addAction(self.window.action_select_all)
        menu.addAction(self.window.action_deselect)
        menu.addAction(self.window.action_delete)


    def _setup_transform_menu(self) -> None:
        """Replace the legacy Image menu with the current Transform menu."""
        menu = getattr(self.window, "menuImage", None)
        if not isinstance(menu, QMenu):
            menu = self.window.menuBar().addMenu("Transform")
            self.window.menuImage = menu
        menu.setTitle("Transform")
        menu.clear()

        actions = {
            "action_transform_resize": "Resize...",
            "action_transform_rotate": "Rotate...",
            "action_transform_rotate_180": "Rotate 180°",
            "action_transform_rotate_90_cw": "Rotate 90° CW",
            "action_transform_rotate_90_ccw": "Rotate 90° CCW",
            "action_transform_flip_horizontal": "Flip Horizontal",
            "action_transform_flip_vertical": "Flip Vertical",
            "action_transform_adjust": "Brightness / Contrast...",
            "action_transform_batch_preprocess": "Batch Preprocessing...",
        }
        for name, text in actions.items():
            if not isinstance(getattr(self.window, name, None), QAction):
                setattr(self.window, name, QAction(text, self.window))
            getattr(self.window, name).setText(text)

        menu.addAction(self.window.action_transform_resize)
        menu.addSeparator()
        menu.addAction(self.window.action_transform_rotate)
        menu.addAction(self.window.action_transform_rotate_180)
        menu.addAction(self.window.action_transform_rotate_90_cw)
        menu.addAction(self.window.action_transform_rotate_90_ccw)
        menu.addAction(self.window.action_transform_flip_horizontal)
        menu.addAction(self.window.action_transform_flip_vertical)
        menu.addSeparator()
        menu.addAction(self.window.action_transform_adjust)
        menu.addSeparator()
        menu.addAction(self.window.action_transform_batch_preprocess)


    def _setup_roi_actions(self) -> None:
        """Create ROI actions shared by menus and toolbar buttons."""
        actions = {
            "action_auto_roi_all_mapsets": "Set Auto ROI to All MapSets",
            "action_set_placement_mask": "Set ROI Contour",
            "action_clear_placement_mask": "Clear ROI Contour",
        }
        for name, text in actions.items():
            if not isinstance(getattr(self.window, name, None), QAction):
                setattr(self.window, name, QAction(text, self.window))
            getattr(self.window, name).setText(text)

    def _setup_tools_menu(self) -> None:
        """Expose active canvas modes and patch operations directly."""
        self._ensure_editor_actions()
        menu = getattr(self.window, "menuTools", None)
        if not isinstance(menu, QMenu):
            return
        menu.setTitle("Tools")
        menu.clear()

        menu.addAction(self.window.action_move_tool)
        menu.addSeparator()
        menu.addAction(self.window.action_rectangle_tool)
        menu.addAction(self.window.action_lasso_tool)
        menu.addAction(self.window.action_polygon_tool)
        menu.addSeparator()
        menu.addAction(self.window.action_brush_tool)
        menu.addAction(self.window.action_healing_brush_tool)
        menu.addAction(self.window.action_eraser_tool)
        menu.addAction(self.window.action_fill_tool)
        menu.addSeparator()
        menu.addAction(self.window.action_point_tool)
        menu.addAction(self.window.action_poisson_editing)
        menu.addSeparator()
        menu.addAction(self.window.action_rotate_left)
        menu.addAction(self.window.action_rotate_right)
        menu.addAction(self.window.action_scale_up)
        menu.addAction(self.window.action_scale_down)
        menu.addAction(self.window.action_reset_transform)
        menu.addSeparator()
        menu.addAction(self.window.action_confirm)
        menu.addAction(self.window.actionApply_Poisson)

    def _setup_label_menu(self) -> None:
        """Make label commands available from the same slots as selection buttons."""
        self._ensure_editor_actions()
        menu = getattr(self.window, "menuLabel", None)
        if not isinstance(menu, QMenu):
            return
        menu.setTitle("Label")
        menu.clear()
        menu.addAction(self.window.action_label_browser)
        menu.addAction(self.window.action_show_labels)
        menu.addSeparator()
        menu.addAction(self.window.action_add_label_from_selection)
        menu.addAction(self.window.action_remove_active_label)
        menu.addSeparator()
        menu.addAction(self.window.action_save_labels)
        menu.addAction(self.window.action_reload_labels)
        menu.addSeparator()
        menu.addAction(self.window.action_export_yolov8_dataset)

    def _setup_augment_menu(self) -> None:
        """Expose augmentation and ROI workflow entry points directly."""
        self._setup_roi_actions()
        self._ensure_editor_actions()
        menu = getattr(self.window, "menuAugment", None)
        if not isinstance(menu, QMenu):
            return
        menu.setTitle("Augment")
        menu.clear()
        menu.addAction(self.window.action_auto_augment)
        menu.addSeparator()
        menu.addAction(self.window.action_auto_roi_selection)
        menu.addAction(self.window.action_set_placement_mask)
        menu.addAction(self.window.action_clear_placement_mask)
        menu.addAction(self.window.action_auto_roi_all_mapsets)
        menu.addSeparator()
        menu.addAction(self.window.action_export_defect_set)

        legacy_action = getattr(self.window, "action_auto_ellipse_roi", None)
        if isinstance(legacy_action, QAction):
            legacy_action.setVisible(False)
            legacy_action.setEnabled(False)

    def _setup_view_menu(self) -> None:
        """Use View for zoom, panel visibility, workspace presets, and theme."""
        menu = getattr(self.window, "menuView", None)
        if not isinstance(menu, QMenu):
            return
        menu.setTitle("View")
        menu.clear()

        theme_menu = QMenu("Theme", menu)
        for action in getattr(self.window, "theme_actions", {}).values():
            theme_menu.addAction(action)

        menu.addAction(self.window.action_zoom_in)
        menu.addAction(self.window.action_zoom_out)
        menu.addAction(self.window.action_actual_size)
        menu.addAction(self.window.action_fit_to_window)
        menu.addSeparator()
        menu.addAction(self.window.action_toggle_tools)
        menu.addAction(self.window.action_toggle_project_pannel)
        menu.addAction(self.window.action_toggle_properties_pannel)
        menu.addAction(self.window.action_toggle_logs)
        menu.addSeparator()
        menu.addAction(self.window.action_workspace_default)
        menu.addAction(self.window.action_workspace_labeling)
        menu.addAction(self.window.action_workspace_augmentation)
        menu.addAction(self.window.action_workspace_review)
        menu.addSeparator()
        menu.addAction(self.window.action_fullscreen)
        menu.addSeparator()
        menu.addMenu(theme_menu)

    def _setup_menu_bar_order(self) -> None:
        """Remove legacy top-level menus after their actions have been regrouped."""
        bar = self.window.menuBar()
        bar.clear()
        for name in (
            "menuFile",
            "menuEdit",
            "menuImage",
            "menuTools",
            "menuLabel",
            "menuAugment",
            "menuView",
            "menuHelp",
        ):
            menu = getattr(self.window, name, None)
            if isinstance(menu, QMenu):
                bar.addMenu(menu)

    @property
    def _assets_dir(self) -> Path:
        return Path(__file__).resolve().parents[1] / "assets"

    @property
    def _icons_dir(self) -> Path:
        return self._assets_dir / "icons"

    def _setup_icons(self) -> None:
        """Apply icons from dataset_studio/assets without requiring qrc compile."""
        self._set_window_icon("app.png")

        action_icons = {
            "action_open_image": "fileopen.svg",
            "action_open_Images": "fileopen_mult.svg",
            "action_open_folder": "folderopen.svg",
            "action_open_project": "folderopen.svg",
            "action_save_project": "save.png",
            "action_save_project_as": "saveas.png",
            "action_save": "save.png",
            "action_save_all": "save.png",
            "action_save_as": "saveas.png",
            "action_export_mask": "dataset_export.svg",
            "action_export_result": "dataset_export.svg",
            "action_export_yolov8_dataset": "dataset_export.svg",
            "action_close": "close.svg",
            "action_close_all": "xmark-circle.svg",
            "action_exit": "exit.svg",
            "action_undo": "Undo--Streamline-Rounded-Streamline-Material.png",
            "action_redo": "redo.png",
            "action_cut": "cut.svg",
            "action_copy": "copy.png",
            "action_paste": "paste.png",
            "action_delete": "trash-3.svg",
            "action_select_all": "check-circle-1.svg",
            "action_deselect": "xmark-circle.svg",
            "action_zoom_in": "zoomin.svg",
            "action_zoom_out": "zoomout.svg",
            "action_actual_size": "actual_size.png",
            "action_fit_to_window": "fit.svg",
            "action_cascade_windows": "cascade.png",
            "action_tile_windows": "tile_window.png",
            "action_fullscreen": "fullscreen.png",
            "action_move_tool": "move.svg",
            "action_rectangle_tool": "rectangle.svg",
            "action_lasso_tool": "lasso.svg",
            "action_polygon_tool": "polygon.svg",
            "action_brush_tool": "brush-2.svg",
            "action_brush_tool_2": "brush-2.svg",
            "action_healing_brush_tool": "brush-2.svg",
            "action_eraser_tool": "eraser.png",
            "action_fill_tool": "fill_bucket.svg",
            "action_eyedropper_tool": "eyedropper.svg",
            "action_point_tool": "point.png",
            "action_rotate_left": "rotate_left.png",
            "action_rotate_right": "rotate_right.png",
            "action_scale_up": "plus.svg",
            "action_scale_down": "minus.svg",
            "action_reset_transform": "reset_transform.png",
            "action_confirm": "check-circle-1.svg",
            "action_add_label_from_selection": "plus.svg",
            "action_remove_active_label": "trash-3.svg",
            "action_reload_labels": "reset_transform.png",
            "action_copy_patch": "copy.png",
            "action_paste_patch": "paste.png",
            "action_export_defect": "dataset_export.svg",
            "action_auto_roi_selection": "morphology.svg",
            "action_augment_resize": "preprocessing_sliders.svg",
            "action_augment_flip_horizontal": "toggleleft.png",
            "action_augment_flip_vertical": "toggleright.png",
            "action_augment_rotate_cw": "rotate_right.png",
            "action_augment_rotate_ccw": "rotate_left.png",
            "action_augment_rotate_180": "reset_transform.png",
            "action_auto_ellipse_roi": "morphology.svg",
            "action_export_defect_set": "dataset_export.svg",
            "action_auto_augment": "magic_wand.svg",
            "action_show_labels": "labeling.png",
            "action_label_browser": "bbox.svg",
            "action_augment_options": "magic_wand.svg",
            "action_augment_preview": "actual_size.png",
            "action_preprocess_options": "preprocessing_sliders.svg",
            "action_transform_resize": "preprocessing_sliders.svg",
            "action_transform_rotate": "rotate_right.png",
            "action_transform_rotate_180": "reset_transform.png",
            "action_transform_rotate_90_cw": "rotate_right.png",
            "action_transform_rotate_90_ccw": "rotate_left.png",
            "action_transform_flip_horizontal": "toggleleft.png",
            "action_transform_flip_vertical": "toggleright.png",
            "action_transform_adjust": "preprocessing_sliders.svg",
            "action_transform_batch_preprocess": "preprocessing_sliders.svg",
            "action_toggle_tools": "grid.svg",
            "action_toggle_project_pannel": "folderopen.svg",
            "action_toggle_properties_pannel": "question.svg",
            "action_toggle_logs": "about.png",

            # Extra Dataset Editor tool icons. These actions/buttons are applied only if the .ui file contains them.
            "action_fill_bucket": "fill_bucket.svg",
            "action_blur_tool": "blur.svg",
            "action_threshold_tool": "threshold.svg",
            "action_morphology_tool": "morphology.svg",
            "action_class_balance": "class_balance.svg",
            "action_poisson_editing": "blend_poisson.svg",
            "action_export_dataset": "dataset_export.svg",
            "action_workspace_default": "app.png",
            "action_workspace_labeling": "labeling.png",
            "action_workspace_augmentation": "magic_wand.svg",
            "action_workspace_review": "check-circle-1.svg",
            "action_workspace_save": "save.png",
            "action_workspace_restore": "reset_transform.png",
            "action_workspace_reset": "xmark-circle.svg",
        }
        self.action_icons = action_icons
        for action_name, icon_name in action_icons.items():
            self._set_action_icon(action_name, icon_name)

        button_icons = {
            "toolboxMove": "move.svg",
            "toolboxRectangle": "rectangle.svg",
            "toolboxLasso": "lasso.svg",
            "toolboxPolygon": "polygon.svg",
            "toolboxBrush": "brush-2.svg",
            "toolboxEraser": "eraser.png",
            "toolboxFill": "fill_bucket.svg",
            "toolboxEyedropper": "eyedropper.svg",
            "optionsZoomOut": "zoomout.svg",
            "optionsZoomIn": "zoomin.svg",
            "optionsFit": "fit.svg",
            "optionsRectangle": "rectangle.svg",
            "optionsLasso": "lasso.svg",
            "optionsPolygon": "polygon.svg",
            "optionsClearSelection": "xmark-circle.svg",
            "optionsAutoROI": "morphology.svg",
            "optionsFinishSelection": "check-circle-1.svg",
            "optionsBrush": "brush-2.svg",
            "optionsEraser": "eraser.png",
            "optionsFill": "fill_bucket.svg",
            "optionsShowLabels": "bbox.svg",
            "optionsRotateLeft": "rotate_left.png",
            "optionsRotateRight": "rotate_right.png",
            "optionsScaleDown": "minus.svg",
            "optionsScaleUp": "plus.svg",
            "optionsResetTransform": "reset_transform.png",
            "optionsConfirmPaste": "apply.png",
            "optionsApplyPoisson": "blend_poisson.svg",

            # Extra Dataset Editor buttons. These are ignored if not present in the loaded .ui file.
            "button_preprocess_apply": "preprocessing_sliders.svg",
            "button_threshold_apply": "threshold.svg",
            "button_blur_apply": "blur.svg",
            "button_morphology_apply": "morphology.svg",
            "button_augmentation_preview": "magic_wand.svg",
            "button_augmentation_run": "class_balance.svg",
            "button_export_dataset": "dataset_export.svg",
            "button_selection_clear": "xmark-circle.svg",
            "button_selection_finish": "check-circle-1.svg",
            "button_label_add": "plus.svg",
            "button_label_export_yolo": "dataset_export.svg",
            "button_label_popup": "bbox.svg",
            "button_poisson_apply": "blend_poisson.svg",
            "button_paste_confirm": "apply.png",
        }
        self.button_icons = button_icons
        for button_name, icon_name in button_icons.items():
            self._set_button_icon(button_name, icon_name)

    def _setup_tool_button_style(self) -> None:
        """Apply sizing only; colors are controlled by the active theme."""
        for button in self.window.findChildren(QToolButton):
            button.setIconSize(QSize(20, 20))
            button.setMinimumSize(28, 28)

    def apply_theme(self, theme: str) -> None:
        """Re-render every toolbar icon with theme-appropriate contrast."""
        tint = QColor(theme_colors(theme)["icon"])
        for action_name, icon_name in self.action_icons.items():
            self._set_action_icon(action_name, icon_name, tint)
        for button_name, icon_name in self.button_icons.items():
            self._set_button_icon(button_name, icon_name, tint)

    def _setup_tool_buttons(self) -> None:
        self._ensure_auto_roi_button()
        button_texts = {
            "toolboxMove": "M",
            "toolboxRectangle": "R",
            "toolboxLasso": "L",
            "toolboxPolygon": "P",
            "toolboxBrush": "B",
            "toolboxEraser": "E",
            "toolboxFill": "F",
            "optionsZoomOut": "-",
            "optionsZoomIn": "+",
            "optionsFit": "Fit",
            "optionsRectangle": "Rect",
            "optionsLasso": "Lasso",
            "optionsPolygon": "Poly",
            "optionsClearSelection": "Clear",
            "optionsAutoROI": "Auto ROI",
            "optionsFinishSelection": "Finish",
            "optionsBrush": "Brush",
            "optionsEraser": "Eraser",
            "optionsFill": "Fill",
            "optionsShowLabels": "Labels",
            "optionsRotateLeft": "⟲",
            "optionsRotateRight": "⟳",
            "optionsScaleDown": "Scale -",
            "optionsScaleUp": "Scale +",
            "optionsResetTransform": "Reset",
            "optionsConfirmPaste": "Confirm",
            "optionsApplyPoisson": "Poisson",
        }
        for object_name, text in button_texts.items():
            button = getattr(self.window, object_name, None)
            if isinstance(button, QToolButton):
                button.setText(text)
                if object_name.startswith("toolbox"):
                    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                    button.setCheckable(True)
                elif button.icon().isNull():
                    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
                else:
                    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._setup_brush_tool_menu()

    def _setup_brush_tool_menu(self) -> None:
        brush_action = getattr(self.window, "action_brush_tool", None)
        healing_action = getattr(self.window, "action_healing_brush_tool", None)
        if not isinstance(brush_action, QAction) or not isinstance(healing_action, QAction):
            return
        for button_name in ("toolboxBrush", "optionsBrush"):
            button = getattr(self.window, button_name, None)
            if isinstance(button, QToolButton):
                menu = QMenu("Brush Tools", button)
                menu.addAction(brush_action)
                menu.addAction(healing_action)
                button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                button.customContextMenuRequested.connect(
                    lambda _position, menu=menu, button=button: self._show_button_context_menu(button, menu)
                )
                button.setToolTip("Left click: Brush Tool / Right click: choose brush")
                if button_name == "toolboxBrush":
                    button.setFixedSize(28, 28)

    def _show_button_context_menu(self, button: QToolButton, menu: QMenu) -> None:
        menu.exec(button.mapToGlobal(button.rect().topRight() + QPoint(6, 0)))

    def _setup_unified_tool_layout(self) -> None:
        """Keep tool controls in the top options bar and non-tool details on the right."""
        self._move_right_side_detail_groups()
        self._setup_top_brush_options()
        self._setup_top_selection_options()
        self._setup_top_patch_options()
        self._hide_right_side_tool_groups()

    def _move_right_side_detail_groups(self) -> None:
        info_layout = getattr(self.window, "layout_page_info", None)
        if info_layout is None:
            return
        for name in ("group_labeling", "group_poisson_state"):
            widget = getattr(self.window, name, None)
            if isinstance(widget, QWidget):
                self._insert_before_last_spacer(info_layout, widget)

    def _setup_top_brush_options(self) -> None:
        layout = getattr(self.window, "layoutOptionsBrush", None)
        if layout is None:
            return
        opacity_label = getattr(self.window, "label_brush_opacity", None)
        opacity_spin = getattr(self.window, "spin_brush_opacity", None)
        color_button = getattr(self.window, "buttonOptionsBrushColor", None)
        if isinstance(opacity_label, QWidget) and isinstance(opacity_spin, QWidget):
            opacity_label.setText("Opacity")
            opacity_spin.setMaximumWidth(76)
            insert_at = self._layout_index_of(layout, color_button)
            self._insert_widget(layout, opacity_label, insert_at)
            self._insert_widget(layout, opacity_spin, insert_at + 1 if insert_at >= 0 else -1)
            if hasattr(opacity_spin, "valueChanged"):
                opacity_spin.valueChanged.connect(self._set_brush_opacity)
            self._set_brush_opacity(opacity_spin.value())
        size_spin = getattr(self.window, "spinOptionsBrushSize", None)
        if size_spin is not None:
            self.window.tool_controller.set_paint_size(size_spin.value())

    def _setup_top_selection_options(self) -> None:
        layout = getattr(self.window, "layoutOptionsSelect", None)
        if layout is None:
            return
        if getattr(self.window, "optionsFinishSelection", None) is None:
            button = QToolButton(self.window)
            button.setObjectName("optionsFinishSelection")
            button.setText("Finish")
            button.setToolTip("Finish polygon selection")
            self.window.optionsFinishSelection = button
        button = self.window.optionsFinishSelection
        clear_button = getattr(self.window, "optionsClearSelection", None)
        insert_at = self._layout_index_of(layout, clear_button)
        self._insert_widget(layout, button, insert_at)
        self._set_button_icon("optionsFinishSelection", "check-circle-1.svg")
        combo = getattr(self.window, "comboOptionsSelectionMode", None)
        if combo is not None:
            combo.setToolTip("Selection combine mode. Shift adds, Alt subtracts for one gesture.")
            if hasattr(combo, "setMaximumWidth"):
                combo.setMaximumWidth(116)
            if hasattr(combo, "currentTextChanged"):
                combo.currentTextChanged.connect(self.window.set_selection_combine_mode)
            self.window.set_selection_combine_mode(combo.currentText())

    def _setup_top_patch_options(self) -> None:
        layout = getattr(self.window, "layoutOptionsPaste", None)
        if layout is None:
            return
        widgets = (
            ("label_paste_x", "X", 34),
            ("spin_paste_x", None, 76),
            ("label_paste_y", "Y", 34),
            ("spin_paste_y", None, 76),
            ("label_paste_rotation", "Rot", 38),
            ("double_paste_rotation", None, 82),
            ("label_paste_scale", "Scale", 48),
            ("double_paste_scale", None, 82),
        )
        insert_at = self._layout_index_of(layout, getattr(self.window, "optionsRotateLeft", None))
        for name, text, width in widgets:
            widget = getattr(self.window, name, None)
            if not isinstance(widget, QWidget):
                continue
            if text is not None and hasattr(widget, "setText"):
                widget.setText(text)
            if hasattr(widget, "setMaximumWidth"):
                widget.setMaximumWidth(width)
            self._insert_widget(layout, widget, insert_at)
            if insert_at >= 0:
                insert_at += 1

    def _hide_right_side_tool_groups(self) -> None:
        for name in (
            "group_brush_options",
            "group_selection_options",
            "group_selection_actions",
            "group_paste_transform",
            "group_paste_actions",
            "group_poisson_options",
            "button_poisson_apply",
        ):
            widget = getattr(self.window, name, None)
            if isinstance(widget, QWidget):
                widget.hide()

    def _insert_before_last_spacer(self, layout, widget: QWidget) -> None:
        index = max(0, layout.count() - 1)
        layout.insertWidget(index, widget)
        widget.show()

    def _layout_index_of(self, layout, widget) -> int:
        if widget is None:
            return -1
        for index in range(layout.count()):
            item = layout.itemAt(index)
            if item is not None and item.widget() is widget:
                return index
        return -1

    def _insert_widget(self, layout, widget: QWidget, index: int = -1) -> None:
        if self._layout_index_of(layout, widget) >= 0:
            return
        if index is None or index < 0:
            index = max(0, layout.count() - 1)
        layout.insertWidget(index, widget)
        widget.show()

    def _ensure_auto_roi_button(self) -> None:
        layout = getattr(self.window, "layoutOptionsSelect", None)
        if layout is None or getattr(self.window, "optionsAutoROI", None) is not None:
            return
        button = QToolButton(self.window)
        button.setObjectName("optionsAutoROI")
        button.setToolTip("Select Auto ROI on the current map")
        self.window.optionsAutoROI = button
        insert_index = max(0, layout.count() - 1)
        layout.insertWidget(insert_index, button)

    def _setup_dock_layout(self) -> None:
        """Stabilize the Qt Designer dock layout using proportional resizing.

        This keeps the original .ui structure and stylesheet intact. It does not
        move dock contents into a separate splitter, because that can detach or
        hide panels depending on how the .ui file was generated.
        """
        self.window.setDockNestingEnabled(True)

        dock_options = getattr(self.window, "dockOptions", None)
        dock_tools = getattr(self.window, "dockTools", None)
        dock_project = getattr(self.window, "dockProject", None)
        dock_properties = getattr(self.window, "dockProperties", None)
        dock_logs = getattr(self.window, "dockLogs", None)

        if isinstance(dock_options, QDockWidget):
            dock_options.setAllowedAreas(Qt.DockWidgetArea.TopDockWidgetArea)
            dock_options.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
            self.window.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, dock_options)

        if isinstance(dock_tools, QDockWidget):
            dock_tools.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)
            dock_tools.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
            title_bar = QWidget(dock_tools)
            title_bar.setFixedHeight(0)
            dock_tools.setTitleBarWidget(title_bar)
            self.window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock_tools)

        if isinstance(dock_project, QDockWidget):
            dock_project.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)
            dock_project.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
            self.window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock_project)

        if isinstance(dock_tools, QDockWidget) and isinstance(dock_project, QDockWidget):
            self.window.splitDockWidget(
                dock_tools,
                dock_project,
                Qt.Orientation.Horizontal,
            )

        if isinstance(dock_properties, QDockWidget):
            dock_properties.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
            dock_properties.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
            self.window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock_properties)

        if isinstance(dock_logs, QDockWidget):
            dock_logs.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
            dock_logs.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
            self.window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock_logs)

        self.window._queue_panel_ratio_update()

    def _setup_initial_panel_state(self) -> None:
        self.update_tool_ui(ToolMode.MOVE)
        if hasattr(self.window, "label_property_title"):
            self.window.label_property_title.setText("Dataset Editor")
        if hasattr(self.window, "label_property_subtitle"):
            self.window.label_property_subtitle.setText("Ready")

    def connect_actions(self) -> None:
        self._connect_file_actions()
        self._connect_edit_actions()
        self._connect_view_actions()
        self._connect_tool_actions()
        self._connect_page_actions()
        self._connect_transform_actions()
        self._connect_panel_buttons()

    def _connect_file_actions(self) -> None:
        self._connect_action("action_open_project", self.window.open_project)
        self._connect_action("action_open_folder", self.window.open_dataset_folder)
        self._connect_action("action_open_image", self.window.open_image)
        self._connect_action("action_open_Images", self.window.open_images)
        self._connect_action("action_save_project", self.window.save_project)
        self._connect_action("action_save_project_as", self.window.save_project_as)
        self._connect_action("action_save", self.window.save_current_mapset)
        self._connect_action("action_save_all", self.window.save_all)
        self._connect_action("action_save_as", self.window.save_current_as_new_mapset)
        self._connect_action("action_save_labels", self.window.save_current_yolo_labels)
        self._connect_action("action_export_yolov8_dataset", self.window.export_yolo_dataset)
        self._connect_action("action_export_result", self.window.export_yolo_dataset)
        self._connect_action("action_exit", self.window.close)

    def _connect_view_actions(self) -> None:
        self._connect_action("action_zoom_in", lambda: self.window.canvas.zoom_by(1.25))
        self._connect_action("action_zoom_out", lambda: self.window.canvas.zoom_by(0.8))
        self._connect_action("action_actual_size", self.window.canvas.actual_size)
        self._connect_action("action_fit_to_window", self.window.canvas.fit_to_window)
        self._connect_button("optionsZoomIn", lambda: self.window.canvas.zoom_by(1.25))
        self._connect_button("optionsZoomOut", lambda: self.window.canvas.zoom_by(0.8))
        self._connect_button("optionsFit", self.window.canvas.fit_to_window)
        self._connect_action("action_toggle_project_pannel", lambda: self._toggle_dock("dockProject"))
        self._connect_action("action_toggle_properties_pannel", lambda: self._toggle_dock("dockProperties"))
        self._connect_action("action_toggle_tools", lambda: self._toggle_dock("dockTools"))
        self._connect_action("action_toggle_logs", lambda: self._toggle_dock("dockLogs"))
        self._connect_action("action_fullscreen", self._toggle_fullscreen)
        self._connect_action("action_workspace_default", self.window.show_main_page)
        self._connect_action("action_workspace_labeling", self._show_labeling_workspace)
        self._connect_action("action_workspace_augmentation", self.window.show_augmentation_page)
        self._connect_action("action_workspace_review", self._show_review_workspace)

    def _connect_edit_actions(self) -> None:
        self._connect_action("action_undo", self.window.undo_edit)
        self._connect_action("action_redo", self.window.redo_edit)
        self._connect_action("action_copy", self._copy_for_current_mode)
        self._connect_action("action_copy_patch", self._copy_for_current_mode)
        self._connect_action("action_paste", self.window.place_clipboard_patch)
        self._connect_action("action_paste_patch", self.window.place_clipboard_patch)
        self._connect_action("action_delete", self._delete_for_current_mode)
        self._connect_action("action_select_all", self.window.select_all)
        self._connect_action("action_deselect", self.window.clear_active_selection_state)

    def _connect_page_actions(self) -> None:
        self._connect_action("action_auto_augment", self.window.show_augmentation_page)
        self._connect_action("action_augment_preview", self.window.show_augmentation_page)
        self._connect_action("action_export_mask", self.window.export_selection_mask)
        self._connect_action("action_export_defect", self.window.export_selected_defect)
        self._connect_action("action_auto_roi_all_mapsets", self.window.auto_roi_all_mapsets)
        self._connect_action("action_auto_roi_selection", self.window.auto_roi_selection)
        self._connect_action("action_set_placement_mask", self.window.set_current_selection_as_placement_mask)
        self._connect_action("action_clear_placement_mask", self.window.clear_current_placement_mask)
        self._connect_action("action_export_defect_set", self.window.export_selected_defect)
        self._connect_action("action_preprocess_options", self.window.start_preprocessing_dialog)
        self._connect_action("action_label_browser", self.window.show_label_manager)
        self._connect_action("action_add_label_from_selection", self.window.add_label_from_selection)
        self._connect_action("action_remove_active_label", self.window.remove_active_annotation)
        self._connect_action("action_reload_labels", self.window.reload_current_yolo_labels)
        self._connect_action("action_show_labels", self.window.set_labels_visible)
        self._connect_action("actionAbout", lambda: self.window.set_status("Dataset Editor"))


    def _connect_transform_actions(self) -> None:
        self._connect_action("action_transform_resize", self.window.show_resize_dialog)
        self._connect_action("action_transform_rotate", self.window.show_rotate_dialog)
        self._connect_action("action_transform_rotate_180", lambda: self.window.apply_fixed_transform("rotate_180"))
        self._connect_action("action_transform_rotate_90_cw", lambda: self.window.apply_fixed_transform("rotate_90_cw"))
        self._connect_action("action_transform_rotate_90_ccw", lambda: self.window.apply_fixed_transform("rotate_90_ccw"))
        self._connect_action("action_transform_flip_horizontal", lambda: self.window.apply_fixed_transform("flip_horizontal"))
        self._connect_action("action_transform_flip_vertical", lambda: self.window.apply_fixed_transform("flip_vertical"))
        self._connect_action("action_transform_adjust", self.window.show_brightness_contrast_dialog)
        self._connect_action("action_transform_batch_preprocess", self.window.start_preprocessing_dialog)

    def _connect_tool_actions(self) -> None:
        action_to_tool = {
            "action_move_tool": ToolMode.MOVE,
            "action_rectangle_tool": ToolMode.RECT,
            "action_lasso_tool": ToolMode.LASSO,
            "action_polygon_tool": ToolMode.POLYGON,
            "action_brush_tool": ToolMode.BRUSH,
            "action_brush_tool_2": ToolMode.BRUSH,
            "action_healing_brush_tool": ToolMode.HEALING_BRUSH,
            "action_eraser_tool": ToolMode.ERASER,
            "action_fill_tool": ToolMode.FILL,
            "action_point_tool": ToolMode.PATCH,
        }
        for action_name, tool_name in action_to_tool.items():
            self._connect_action(action_name, lambda checked=False, name=tool_name: self.activate_tool(name))

        button_to_tool = {
            "toolboxMove": ToolMode.MOVE,
            "toolboxRectangle": ToolMode.RECT,
            "toolboxLasso": ToolMode.LASSO,
            "toolboxPolygon": ToolMode.POLYGON,
            "toolboxBrush": ToolMode.BRUSH,
            "toolboxEraser": ToolMode.ERASER,
            "toolboxFill": ToolMode.FILL,
            "optionsRectangle": ToolMode.RECT,
            "optionsLasso": ToolMode.LASSO,
            "optionsPolygon": ToolMode.POLYGON,
            "optionsBrush": ToolMode.BRUSH,
            "optionsEraser": ToolMode.ERASER,
            "optionsFill": ToolMode.FILL,
        }
        for button_name, tool_name in button_to_tool.items():
            self._connect_button(button_name, lambda checked=False, name=tool_name: self.activate_tool(name))

    def _connect_panel_buttons(self) -> None:
        self._connect_action("actionApply_Poisson", self._apply_poisson)
        self._connect_action("action_confirm", self._apply_hard_paste)
        self._connect_action("action_poisson_editing", self.window.place_clipboard_patch)
        self._connect_action("action_rotate_left", lambda: self._patch_transform("rotate", -15))
        self._connect_action("action_rotate_right", lambda: self._patch_transform("rotate", 15))
        self._connect_action("action_scale_down", lambda: self._patch_transform("scale", 0.9))
        self._connect_action("action_scale_up", lambda: self._patch_transform("scale", 1.1))
        self._connect_action("action_reset_transform", lambda: self._patch_transform("reset", 0))
        self._connect_button("button_selection_clear", self.window.clear_active_selection_state)
        self._connect_button("optionsClearSelection", self.window.clear_active_selection_state)
        self._connect_button("optionsAutoROI", self.window.auto_roi_selection)
        self._connect_button("optionsFinishSelection", self._finish_polygon)
        self._connect_button("button_selection_finish", self._finish_polygon)
        self._connect_button("button_label_add", self.window.add_label_from_selection)
        self._connect_button("buttonOptionsAddLabel", self.window.add_label_from_selection)
        self._connect_button("button_label_export_yolo", self.window.export_yolo_dataset)
        self._connect_button("button_label_popup", self.window.show_label_manager)
        self._connect_button("button_poisson_apply", self._apply_poisson)
        self._connect_button("optionsApplyPoisson", self._apply_poisson)
        self._connect_button("optionsRotateLeft", lambda: self._patch_transform("rotate", -15))
        self._connect_button("optionsRotateRight", lambda: self._patch_transform("rotate", 15))
        self._connect_button("optionsScaleDown", lambda: self._patch_transform("scale", 0.9))
        self._connect_button("optionsScaleUp", lambda: self._patch_transform("scale", 1.1))
        self._connect_button("optionsResetTransform", lambda: self._patch_transform("reset", 0))
        self._connect_button("button_paste_confirm", self._apply_hard_paste)
        self._connect_button("optionsConfirmPaste", self._apply_hard_paste)
        self._connect_button("button_paste_rotate_left", lambda: self._patch_transform("rotate", -15))
        self._connect_button("button_paste_rotate_right", lambda: self._patch_transform("rotate", 15))
        self._connect_button("button_paste_scale_down", lambda: self._patch_transform("scale", 0.9))
        self._connect_button("button_paste_scale_up", lambda: self._patch_transform("scale", 1.1))
        self._connect_button("button_paste_reset", lambda: self._patch_transform("reset", 0))
        self._connect_button("buttonSavePoissonMapSet", self.window.save_current_as_new_mapset)
        self._connect_button("buttonOptionsBrushColor", self._choose_brush_color)
        self._connect_button("button_brush_color", self._choose_brush_color)
        spin = getattr(self.window, "spinOptionsBrushSize", None)
        if spin is not None:
            spin.valueChanged.connect(self.window.tool_controller.set_paint_size)

    def _finish_polygon(self) -> None:
        if self.window.tool_controller.current_mode != ToolMode.POLYGON:
            self.window.set_status("Polygon finish is available in polygon mode")
            return
        self.window.tool_controller.finish_polygon_selection()

    def _apply_poisson(self) -> None:
        if not self._require_mode(ToolMode.PATCH, "Poisson blend"):
            return
        mode_combo = getattr(self.window, "optionsPoissonMode", None)
        if mode_combo is None:
            mode_combo = getattr(self.window, "combo_poisson_mode", None)
        mode_text = mode_combo.currentText() if mode_combo is not None else "Normal"
        try:
            if mode_text == "Detail Preserve":
                mode = None
            elif mode_text == "Boundary Mixed":
                mode = "boundary_mixed"
            else:
                mode = clone_mode_from_text(mode_text)
            applied = self.window.start_manual_poisson(mode=mode, mode_name=mode_text)
        except (ValueError, RuntimeError) as exc:
            self.window.set_status(f"Poisson failed: {exc}")
            return
        if not applied and not self.window.tool_controller.has_patch_preview():
            self.window.set_status("Copy a selection first")

    def _apply_hard_paste(self) -> None:
        if not self._require_mode(ToolMode.PATCH, "Hard paste"):
            return
        try:
            applied = self.window.start_manual_poisson(mode="hard_paste", mode_name="Hard Paste")
        except (ValueError, RuntimeError) as exc:
            self.window.set_status(f"Patch failed: {exc}")
            return
        if not applied and not self.window.tool_controller.has_patch_preview():
            self.window.set_status("Copy a selection first")

    def _patch_transform(self, operation: str, value: float) -> None:
        if not self._require_mode(ToolMode.PATCH, "Patch transform"):
            return
        if not self.window.tool_controller.has_patch_preview():
            self.window.set_status("Paste a patch before transforming it")
            return
        if operation == "reset":
            self.window.tool_controller.reset_patch_transform()
        elif operation == "rotate":
            self.window.tool_controller.rotate_patch(value)
        elif operation == "scale":
            self.window.tool_controller.scale_patch(value)

    def _copy_for_current_mode(self) -> None:
        if self.window.tool_controller.current_mode == ToolMode.PATCH:
            self.window.set_status("Switch to a selection mode before copying a patch")
            return
        self.window.copy_selection_to_patch()

    def _delete_for_current_mode(self) -> None:
        if self.window.tool_controller.current_mode == ToolMode.PATCH:
            if self.window.tool_controller.has_patch_preview():
                self.window.tool_controller.cancel_current_tool(
                    clear_canvas=False,
                    fallback_mode=ToolMode.MOVE,
                )
                self.window.set_status("Patch placement cancelled")
                return
        self.window.delete_active_selection()

    def _require_mode(self, mode: ToolMode, command_name: str) -> bool:
        if self.window.tool_controller.current_mode == mode:
            return True
        self.window.set_status(f"{command_name} is available in {mode.value} mode")
        return False

    def _set_brush_opacity(self, value: int) -> None:
        self.window.tool_controller.set_paint_opacity(float(value) / 100.0)

    def _choose_brush_color(self) -> None:
        current = self.window.tool_controller.brush_color()
        color = QColorDialog.getColor(current, self.window, "Brush Color")
        if not color.isValid():
            return
        self.window.tool_controller.set_brush_color(color)
        text = color.name().upper()
        for name in ("buttonOptionsBrushColor", "button_brush_color"):
            button = getattr(self.window, name, None)
            if isinstance(button, QAbstractButton):
                button.setText(text)
                button.setStyleSheet(f"background-color: {color.name()};")

    def activate_tool(self, mode: ToolMode | str) -> None:
        tool_mode = ToolMode.from_value(mode)
        self.window.tool_controller.activate(tool_mode)
        self.window.set_status(f"Tool: {tool_mode.value}")

    def update_tool_ui(self, mode: ToolMode | str) -> None:
        tool_mode = ToolMode.from_value(mode)
        self._set_stacked_page("toolOptionsStack", self.tool_page_map.get(tool_mode))
        self._set_stacked_page("stack_properties", self.property_page_map.get(tool_mode))
        self._update_tool_button_checks(tool_mode)
        self._update_patch_action_availability()
        if hasattr(self.window, "label_info_tool_value"):
            self.window.label_info_tool_value.setText(tool_mode.value)
        if hasattr(self.window, "label_property_subtitle"):
            self.window.label_property_subtitle.setText(f"Active tool: {tool_mode.value}")

    def _update_tool_button_checks(self, mode: ToolMode | str) -> None:
        tool_mode = ToolMode.from_value(mode)
        button_to_tool = {
            "toolboxMove": ToolMode.MOVE,
            "toolboxRectangle": ToolMode.RECT,
            "toolboxLasso": ToolMode.LASSO,
            "toolboxPolygon": ToolMode.POLYGON,
            "toolboxBrush": (ToolMode.BRUSH, ToolMode.HEALING_BRUSH),
            "toolboxEraser": ToolMode.ERASER,
            "toolboxFill": ToolMode.FILL,
        }
        for button_name, mapped_tool in button_to_tool.items():
            button = getattr(self.window, button_name, None)
            if isinstance(button, QAbstractButton):
                if isinstance(mapped_tool, tuple):
                    button.setChecked(tool_mode in mapped_tool)
                else:
                    button.setChecked(mapped_tool == tool_mode)
        action_to_tool = {
            "action_move_tool": ToolMode.MOVE,
            "action_rectangle_tool": ToolMode.RECT,
            "action_lasso_tool": ToolMode.LASSO,
            "action_polygon_tool": ToolMode.POLYGON,
            "action_brush_tool": ToolMode.BRUSH,
            "action_healing_brush_tool": ToolMode.HEALING_BRUSH,
            "action_eraser_tool": ToolMode.ERASER,
            "action_fill_tool": ToolMode.FILL,
            "action_point_tool": ToolMode.PATCH,
        }
        for action_name, mapped_tool in action_to_tool.items():
            action = getattr(self.window, action_name, None)
            if isinstance(action, QAction):
                action.setCheckable(True)
                action.setChecked(mapped_tool == tool_mode)

    def _update_patch_action_availability(self) -> None:
        patch_mode = self.window.tool_controller.current_mode == ToolMode.PATCH
        ready = patch_mode and self.window.tool_controller.has_patch_preview()
        for action_name in (
            "action_rotate_left",
            "action_rotate_right",
            "action_scale_down",
            "action_scale_up",
            "action_reset_transform",
        ):
            action = getattr(self.window, action_name, None)
            if isinstance(action, QAction):
                action.setEnabled(ready)
        for action_name in ("action_confirm", "actionApply_Poisson"):
            action = getattr(self.window, action_name, None)
            if isinstance(action, QAction):
                action.setEnabled(ready)

    def _set_stacked_page(self, stack_name: str, page_name: str | None) -> None:
        if page_name is None:
            return
        stack = getattr(self.window, stack_name, None)
        page = getattr(self.window, page_name, None)
        if stack is not None and page is not None:
            stack.setCurrentWidget(page)

    def _toggle_dock(self, dock_name: str) -> None:
        dock = getattr(self.window, dock_name, None)
        if dock is not None:
            dock.setVisible(not dock.isVisible())
            self.window._queue_panel_ratio_update()

    def _toggle_fullscreen(self) -> None:
        if self.window.isFullScreen():
            self.window.showNormal()
        else:
            self.window.showFullScreen()

    def _show_labeling_workspace(self) -> None:
        self.window.show_main_page()
        self.activate_tool(ToolMode.RECT)

    def _show_review_workspace(self) -> None:
        self.window.show_main_page()
        self.window.set_status("Review workspace")

    def _set_action_text(self, action_name: str, text: str) -> None:
        action = getattr(self.window, action_name, None)
        if isinstance(action, QAction):
            action.setText(text)

    def _set_window_icon(self, icon_name: str) -> None:
        icon_path = self._assets_dir / icon_name
        if icon_path.exists():
            self.window.setWindowIcon(QIcon(str(icon_path)))

    def _set_action_icon(self, action_name: str, icon_name: str, tint: QColor | None = None) -> None:
        action = getattr(self.window, action_name, None)
        icon = self._icon(icon_name, tint)
        if isinstance(action, QAction) and not icon.isNull():
            action.setIcon(icon)

    def _set_button_icon(self, button_name: str, icon_name: str, tint: QColor | None = None) -> None:
        button = getattr(self.window, button_name, None)
        icon = self._icon(icon_name, tint)
        if button_name in {"toolboxBrush", "optionsBrush"}:
            icon = self._icon_with_menu_corner(icon, tint)
        if isinstance(button, QAbstractButton) and not icon.isNull():
            button.setIcon(icon)

    def _icon_with_menu_corner(self, icon: QIcon, tint: QColor | None = None) -> QIcon:
        if icon.isNull():
            return icon
        size = QSize(24, 24)
        source = icon.pixmap(size)
        if source.isNull():
            return icon
        marked = QPixmap(size)
        marked.fill(Qt.GlobalColor.transparent)
        painter = QPainter(marked)
        painter.drawPixmap(0, 0, source)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tint or QColor(theme_colors(getattr(self.window, "current_theme", "dark"))["icon"]))
        painter.drawPolygon(QPolygon([QPoint(17, 23), QPoint(23, 23), QPoint(23, 17)]))
        painter.end()
        return QIcon(marked)

    def _icon(self, icon_name: str, tint: QColor | None = None) -> QIcon:
        candidates = [self._icons_dir / icon_name, self._assets_dir / icon_name]
        for path in candidates:
            if path.exists():
                icon = QIcon(str(path))
                if tint is None:
                    return icon
                source = icon.pixmap(QSize(24, 24))
                if source.isNull():
                    return icon
                themed = QPixmap(source.size())
                themed.fill(Qt.GlobalColor.transparent)
                painter = QPainter(themed)
                painter.drawPixmap(0, 0, source)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                painter.fillRect(themed.rect(), tint)
                painter.end()
                return QIcon(themed)
        return QIcon()

    def _connect_action(self, action_name: str, callback: Callable) -> None:
        action = getattr(self.window, action_name, None)
        if isinstance(action, QAction):
            action.triggered.connect(callback)

    def _connect_button(self, button_name: str, callback: Callable) -> None:
        button = getattr(self.window, button_name, None)
        if isinstance(button, QAbstractButton):
            button.clicked.connect(callback)
