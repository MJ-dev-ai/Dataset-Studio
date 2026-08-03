from __future__ import annotations

import json
import uuid
from dataclasses import replace

import numpy as np
from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import QEvent, QRect, QRectF, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QColor, QIcon, QImage, QKeySequence, QPainter, QPainterPath, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTabBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config.default_presets import IMAGE_EXTENSIONS, MAP_SPECS
from core.geometry import HealingStroke
from service.project_service import safe_defect_name
from core.mapset import MapSet, ROI_CONTOUR_KEY, discover_map_sets, mapset_from_image_path
from service.project_service import (
    MapSetSaveRequest,
    MapSetUpdateRequest,
)
from core.patch_clipboard import PatchClipboard
from core.pixmap_cache import PixmapCache
from core.image_io import read_image
from core.logging_setup import append_crash_report, get_logger
from core.project import DatasetProject, PROJECT_MANIFEST
from service.labeling_service import move_in_catalog, normalize_catalog, remove_from_catalog, update_catalog
from ui.tool_controller import ToolController, ToolMode
from tools.selection_tools import normalize_selection_combine_mode
from service.editing_service import (
    apply_paint_strokes,
    apply_selection_delete,
    apply_selection_fill,
)
from service.history_service import (
    MapSetHistoryEntry,
    apply_history_entry,
    build_mapset_history_entry,
)
from ui.augmentationpage import AugmentationPage
from ui.imagecanvas import CanvasAnnotation, ImageCanvas
from ui.label_add_dialog import LabelAddDialog
from ui.label_manager_dialog import LabelManagerDialog
from ui.mapset_selection_dialog import MapSetSelectionDialog
from ui.preprocess_dialog import (
    BatchPreprocessDialog,
    BrightnessContrastDialog,
    ResizeDialog,
    RotateDialog,
    TransformPropertiesPanel,
)
from ui.patch_clipboard_widget import PatchClipboardWidget
from ui.uisetup import UiSetup
from ui.themes import THEME_NAMES, theme_colors, theme_stylesheet
from service.preprocessing_service import PreprocessOptions
from service.roi_service import roi_contour
from core.qt_image import bgr_to_qpixmap, qimage_to_bgr


UI_PATH = Path(__file__).with_name("mainwindow.ui")
APP_NAME = "Dataset Editor"
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff);;All Files (*)"
PROJECT_FILTER = f"{APP_NAME} Project (*{PROJECT_MANIFEST});;JSON Files (*.json);;All Files (*)"


class MainWindow(QMainWindow):
    """Main application window for Dataset Editor."""

    task_requested = pyqtSignal(str, str, object)
    task_cancel_requested = pyqtSignal(str)
    shutdown_requested = pyqtSignal(int)

    MAPSET_ROLE = int(Qt.ItemDataRole.UserRole) + 100
    PATH_ROLE = int(Qt.ItemDataRole.UserRole) + 101
    ICON_ROLE = int(Qt.ItemDataRole.UserRole) + 102

    DATASET_MAP_SPECS = MAP_SPECS
    IMAGE_EXTENSIONS = IMAGE_EXTENSIONS

    def __init__(self, context):
        super().__init__()
        self.context = context
        self.project = None
        self.current_mapset: MapSet | None = None
        self.current_image_path: Path | None = None
        self.project_path: Path | None = None
        self.project_root_folder: Path | None = None
        self.map_sets: list[MapSet] = []
        self._project_root_item: QTreeWidgetItem | None = None
        self._panel_ratio_pending = False
        self.pixmap_cache = PixmapCache(max_bytes=384 * 1024 * 1024)
        self._active_task_ids: set[str] = set()
        self._shutdown_succeeded = False
        self._task_handlers: dict[str, callable] = {}
        self._auto_augment_task_id: str | None = None
        self._manual_poisson_task_id: str | None = None
        self._healing_task_id: str | None = None
        self._healing_restore_images: dict[str, QImage] | None = None
        self._mapset_save_task_id: str | None = None
        self._mapset_update_task_id: str | None = None
        self._save_all_task_id: str | None = None
        self.patch_clipboard = PatchClipboard()
        self._map_edit_states: dict[str, QImage] = {}
        self._mapset_undo: list[MapSetHistoryEntry] = []
        self._mapset_redo: list[MapSetHistoryEntry] = []
        self._pending_mapset_history_before: dict[str, QImage] | None = None
        self._switching_map = False
        self._label_catalog: list[tuple[int, str]] = []
        self._label_dialog: LabelManagerDialog | None = None
        self._last_label_class_id: int | None = None
        self._labels_modified = False
        self._loading_labels = False
        self._loaded_label_path: Path | None = None
        self._loaded_label_snapshot: tuple[int, int] | None = None
        self._label_edit_states: dict[str, dict[str, object]] = {}
        self._selection_combine_mode = "replace"
        self.transform_properties: TransformPropertiesPanel | None = None

        self._load_ui()
        self._setup_theme_actions()
        self._setup_pages()
        self._setup_project_explorer()
        self._setup_patch_clipboard()
        self._setup_selection_actions()
        self._setup_log_console()

        self.tool_controller = ToolController(self)
        self.ui_setup = UiSetup(self)
        self.ui_setup.setup()
        self._setup_transform_properties_panel()
        self._setup_shortcuts()
        self.tool_controller.activate(ToolMode.MOVE)
        self.apply_theme(self.current_theme, persist=False)
        self._connect_signals()
        self._queue_panel_ratio_update()

    def _request_worker(self, operation: str, payload: object) -> str:
        """Request one feature worker and return its correlation identifier."""
        task_id = uuid.uuid4().hex
        self._active_task_ids.add(task_id)
        self.task_requested.emit(task_id, operation, payload)
        return task_id

    def complete_shutdown(self, succeeded: bool) -> None:
        """Receive the synchronous app-owned worker shutdown result."""
        self._shutdown_succeeded = bool(succeeded)
        if self._shutdown_succeeded:
            self.pixmap_cache.clear()


    def _setup_log_console(self) -> None:
        """Install the Jobs log console."""
        layout = getattr(self, "logConsoleLayout", None)
        if layout is None:
            self.log_console = None
            return
        self.log_console = QPlainTextEdit(self.dockLogsContents)
        self.log_console.setReadOnly(True)
        self.log_console.setMaximumBlockCount(500)
        layout.addWidget(self.log_console)

    def _append_log(self, message: str) -> None:
        """Append a progress line to the Jobs log panel and application log."""
        get_logger().info(message)
        console = getattr(self, "log_console", None)
        if console is not None:
            console.appendPlainText(message)

    def _on_task_progress(self, task_id: str, value: int, message: str) -> None:
        """Route AutoAugment progress to its panel and other tasks to the Jobs log."""
        line = f"{value}% {message}"
        self.set_status(line)
        if task_id == self._auto_augment_task_id and hasattr(self, "augmentation_page"):
            self.augmentation_page.update_autoaugment_progress(value, message)
            return
        self._append_log(line)

    def _setup_transform_properties_panel(self) -> None:
        """Install the current-image transform panel into the Properties dock."""
        layout = getattr(self, "layout_page_info", None)
        if layout is None:
            return
        self.transform_properties = TransformPropertiesPanel(self.page_info)
        self.transform_properties.preview_requested.connect(self.update_transform_preview)
        self.transform_properties.apply_requested.connect(self.apply_transform_options)
        self.transform_properties.reset_requested.connect(self.reset_transform_preview)
        insert_index = max(0, layout.count() - 1)
        layout.insertWidget(insert_index, self.transform_properties)

    def _setup_shortcuts(self) -> None:
        """Bind global edit keys before focused child widgets can swallow them."""
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.escape_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.escape_shortcut.activated.connect(self._activate_move_from_edit_tool)

    def _activate_move_from_edit_tool(self) -> None:
        self.tool_controller.cancel_current_tool(clear_canvas=True, fallback_mode=ToolMode.MOVE)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            focus_widget = QApplication.focusWidget()
            if focus_widget is not None and focus_widget.window() is not self:
                return super().eventFilter(watched, event)
            modifiers = event.modifiers() & (
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.ShiftModifier
                | Qt.KeyboardModifier.AltModifier
                | Qt.KeyboardModifier.MetaModifier
            )
            if modifiers == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_Z:
                self.undo_edit()
                return True
            if modifiers == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_Y:
                self.redo_edit()
                return True
            if (
                modifiers
                == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
                and event.key() == Qt.Key.Key_Z
            ):
                self.redo_edit()
                return True
        return super().eventFilter(watched, event)

    def clear_active_selection_state(self) -> None:
        """Clear selection geometry and temporary points from the active selection tool."""
        if hasattr(self, "tool_controller"):
            self.tool_controller.cancel_current_tool(clear_canvas=True, fallback_mode=None)
        else:
            self.canvas.clear_selection()
        self.canvas.clear_annotation_selection()

    def set_selection_combine_mode(self, mode: str) -> None:
        """Apply the default replace/add/subtract mode to every selection tool."""
        normalized = normalize_selection_combine_mode(mode)
        self._selection_combine_mode = normalized
        if not hasattr(self, "tool_controller"):
            return
        self.tool_controller.set_selection_combine_mode(normalized)

    def _load_ui(self) -> None:
        uic.loadUi(str(UI_PATH), self)
        self.setWindowTitle(APP_NAME)

    def _setup_theme_actions(self) -> None:
        """Create persistent Dark/Light theme actions in the View menu."""
        settings = QSettings("TNSAI", APP_NAME)
        current = str(settings.value("appearance/theme", "dark"))
        if current not in THEME_NAMES:
            current = "dark"
        menu = getattr(self, "menuView", None)
        if menu is None:
            menu = self.menuBar().addMenu("View")
        menu.addSeparator()
        theme_menu = menu.addMenu("Theme")
        self.theme_action_group = QActionGroup(self)
        self.theme_action_group.setExclusive(True)
        self.theme_actions = {}
        for name in THEME_NAMES:
            action = QAction(name.title(), self, checkable=True)
            action.setChecked(name == current)
            action.triggered.connect(lambda checked=False, value=name: self.apply_theme(value))
            self.theme_action_group.addAction(action)
            theme_menu.addAction(action)
            self.theme_actions[name] = action
        self.apply_theme(current, persist=False)

    def apply_theme(self, theme: str, persist: bool = True) -> None:
        """Apply one high-contrast theme to the app and all owned popups."""
        stylesheet = theme_stylesheet(theme)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet)
        self.current_theme = theme
        self._apply_project_tree_branch_style(theme)
        canvas = getattr(self, "canvas", None)
        if canvas is not None:
            canvas.set_theme(theme)
        augmentation_page = getattr(self, "augmentation_page", None)
        if augmentation_page is not None:
            augmentation_page.apply_theme(theme)
        ui_setup = getattr(self, "ui_setup", None)
        if ui_setup is not None:
            ui_setup.apply_theme(theme)
        self._refresh_project_tree_icons()
        action = getattr(self, "theme_actions", {}).get(theme)
        if action is not None:
            action.setChecked(True)
        if persist:
            QSettings("TNSAI", APP_NAME).setValue("appearance/theme", theme)

    def _setup_pages(self) -> None:
        self.canvas = ImageCanvas(self)
        self.augmentation_page = AugmentationPage(self.context.augmentation_api, self)
        self.editor_page = QWidget(self)
        editor_layout = QVBoxLayout(self.editor_page)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        self.map_switch_tabs = QTabBar(self.editor_page)
        self.map_switch_tabs.setObjectName("mapSwitchTabs")
        self.map_switch_tabs.setDocumentMode(True)
        self.map_switch_tabs.setExpanding(False)
        self.map_switch_tabs.setMovable(False)
        self.map_switch_tabs.currentChanged.connect(self._on_map_tab_changed)
        self.map_switch_tabs.hide()
        editor_layout.addWidget(self.map_switch_tabs)
        editor_layout.addWidget(self.canvas, 1)

        stack = getattr(self, "workspaceStack", None)
        if not isinstance(stack, QStackedWidget):
            stack = QStackedWidget(self)
            self.setCentralWidget(stack)
            self.workspaceStack = stack

        stack.addWidget(self.editor_page)
        stack.setCurrentWidget(self.editor_page)

    def _setup_project_explorer(self) -> None:
        tree = getattr(self, "treeProject", None)
        if not isinstance(tree, QTreeWidget):
            return
        tree.clear()
        tree.setColumnCount(1)
        tree.setHeaderLabels(["MapSets"])
        tree.itemDoubleClicked.connect(self._on_project_item_open_requested)
        tree.itemActivated.connect(self._on_project_item_open_requested)
        tree.currentItemChanged.connect(self._on_project_item_selected)
        tree.setUniformRowHeights(True)
        tree.setAnimated(True)
        tree.setIndentation(18)
        self._apply_project_tree_branch_style(getattr(self, "current_theme", "dark"))

    def _setup_patch_clipboard(self) -> None:
        """Replace the Designer placeholder with the draggable thumbnail clipboard."""
        placeholder = getattr(self, "listMasks", None)
        if placeholder is None or placeholder.parentWidget() is None:
            return
        parent = placeholder.parentWidget()
        layout = parent.layout()
        if layout is None:
            return
        index = layout.indexOf(placeholder)
        layout.removeWidget(placeholder)
        placeholder.deleteLater()
        self.listMasks = PatchClipboardWidget(parent)
        self.listMasks.set_clipboard(self.patch_clipboard)
        layout.insertWidget(max(0, index), self.listMasks)
        self.listMasks.clip_activated.connect(self.place_clipboard_patch)
        self.listMasks.clipboard_changed.connect(self._on_patch_clipboard_changed)
        self.listMasks.import_requested.connect(self.import_defect_pool_to_clipboard)
        self.canvas.patch_dropped.connect(self._on_patch_dropped)

    def import_defect_pool_to_clipboard(self) -> None:
        """Load exported defects off the GUI thread and append them to the patch clipboard."""
        root = QFileDialog.getExistingDirectory(self, "Import Defect Pool", str(Path.cwd()))
        if not root:
            return

        task_id = self._request_worker("import_defect_pool", {"root": Path(root)})

        def apply_result(payloads):
            last_id = None
            for payload in payloads:
                clip = self.patch_clipboard.add_mapset(
                    payload["maps"], payload["mask"], payload["name"],
                    payload["source_path"], preview_key=payload["preview_key"],
                )
                last_id = clip.clip_id
            self.listMasks.refresh(select_id=last_id)
            self.set_status(f"Imported {len(payloads)} defects to Patch Clipboard")

        self._task_handlers[task_id] = apply_result

    def _on_patch_clipboard_changed(self) -> None:
        """Cancel placement if its backing clipboard clip was removed."""
        tool = getattr(self, "tool_controller", None)
        if tool is None or not tool.patch_state.clip_id:
            return
        if self.patch_clipboard.get(tool.patch_state.clip_id) is None:
            if tool.current_mode == ToolMode.PATCH:
                tool.cancel_current_tool(clear_canvas=False, fallback_mode=ToolMode.MOVE)
            else:
                tool.clear_active_patch()

    def _apply_project_tree_branch_style(self, theme: str) -> None:
        """Refresh project-tree branch assets supplied by the application stylesheet."""
        tree = getattr(self, "treeProject", None)
        if not isinstance(tree, QTreeWidget):
            return
        tree.style().unpolish(tree)
        tree.style().polish(tree)
        tree.viewport().update()

    def _setup_selection_actions(self) -> None:
        """Add selection-dependent operations to the top Select tool options."""
        layout = getattr(self, "layoutOptionsSelect", None)
        if layout is None:
            return
        self.buttonSelectAddLabel = QPushButton("Add Label", self.pageOptionsSelect)
        self.buttonSelectExportDefect = QPushButton("Export Defect", self.pageOptionsSelect)
        self.buttonSelectCopyPatch = QPushButton("Copy Patch", self.pageOptionsSelect)
        self.buttonSelectSaveLabels = QPushButton("Save MapSet", self.pageOptionsSelect)
        self.buttonSelectRemoveLabel = QPushButton("Remove Label", self.pageOptionsSelect)
        self.buttonSelectReloadLabels = QPushButton("Reload Labels", self.pageOptionsSelect)
        self.buttonSelectSetPlacementMask = QPushButton("Set ROI Contour", self.pageOptionsSelect)
        self.buttonSelectClearPlacementMask = QPushButton("Clear ROI Contour", self.pageOptionsSelect)
        insert_at = max(0, layout.count() - 1)
        for button in (
            self.buttonSelectAddLabel,
            self.buttonSelectExportDefect,
            self.buttonSelectCopyPatch,
            self.buttonSelectSaveLabels,
            self.buttonSelectRemoveLabel,
            self.buttonSelectReloadLabels,
            self.buttonSelectSetPlacementMask,
            self.buttonSelectClearPlacementMask,
        ):
            button.setEnabled(False)
            layout.insertWidget(insert_at, button)
            insert_at += 1
        self.buttonSelectAddLabel.clicked.connect(self.add_label_from_selection)
        self.buttonSelectExportDefect.clicked.connect(self.export_selected_defect)
        self.buttonSelectCopyPatch.clicked.connect(self.copy_selection_to_patch)
        self.buttonSelectSaveLabels.clicked.connect(self.save_current_mapset)
        self.buttonSelectRemoveLabel.clicked.connect(self.remove_active_annotation)
        self.buttonSelectReloadLabels.clicked.connect(self.reload_current_yolo_labels)
        self.buttonSelectSetPlacementMask.clicked.connect(self.set_current_selection_as_placement_mask)
        self.buttonSelectClearPlacementMask.clicked.connect(self.clear_current_placement_mask)

    def _connect_signals(self) -> None:
        self.ui_setup.connect_actions()
        self.canvas.selection_changed.connect(self._on_selection_changed)
        self.canvas.view_changed.connect(self._on_canvas_view_changed)
        self.canvas.annotations_changed.connect(self._on_annotations_changed)
        self.canvas.tool_error.connect(lambda message: self.set_status(f"Tool error: {message}"))

    def _on_selection_changed(self, available: bool) -> None:
        for name in (
            "buttonSelectAddLabel",
            "buttonSelectExportDefect",
            "buttonSelectCopyPatch",
            "buttonSelectSaveLabels",
            "buttonSelectSetPlacementMask",
        ):
            button = getattr(self, name, None)
            if button is not None:
                button.setEnabled(available)
        if hasattr(self, "buttonSelectRemoveLabel"):
            self.buttonSelectRemoveLabel.setEnabled(bool(self.canvas.annotations))

    def _on_canvas_view_changed(self, zoom: float, x_ratio: float, y_ratio: float) -> None:
        del x_ratio, y_ratio
        if hasattr(self, "label_info_zoom_value"):
            self.label_info_zoom_value.setText(f"{zoom * 100:.0f}%")

    def _on_annotations_changed(self) -> None:
        if not self._loading_labels:
            self._labels_modified = True
        if hasattr(self, "label_annotation_count_value"):
            self.label_annotation_count_value.setText(str(len(self.canvas.annotations)))
        if hasattr(self, "buttonSelectRemoveLabel"):
            self.buttonSelectRemoveLabel.setEnabled(bool(self.canvas.annotations))
        if hasattr(self, "buttonSelectReloadLabels"):
            self.buttonSelectReloadLabels.setEnabled(self.current_mapset is not None)
        if hasattr(self, "buttonSelectClearPlacementMask"):
            self.buttonSelectClearPlacementMask.setEnabled(self.current_image_path is not None)
        self._refresh_current_project_tree_item()
        self._refresh_transform_properties()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._queue_panel_ratio_update()

    def _queue_panel_ratio_update(self) -> None:
        if self._panel_ratio_pending:
            return
        self._panel_ratio_pending = True
        QTimer.singleShot(0, self._apply_panel_ratio)

    def _apply_panel_ratio(self) -> None:
        """Apply proportional dock sizes without replacing the .ui layout."""
        self._panel_ratio_pending = False

        width = max(1, self.width())
        height = max(1, self.height())

        left_tools = int(width * 0.035)
        left_project = int(width * 0.14)
        right_properties = int(width * 0.17)
        bottom_logs = int(height * 0.15)
        top_options = int(height * 0.045)

        dock_tools = getattr(self, "dockTools", None)
        dock_project = getattr(self, "dockProject", None)
        dock_properties = getattr(self, "dockProperties", None)
        dock_logs = getattr(self, "dockLogs", None)
        dock_options = getattr(self, "dockOptions", None)

        left_docks = []
        left_sizes = []
        if dock_tools is not None and dock_tools.isVisible():
            left_docks.append(dock_tools)
            left_sizes.append(left_tools)
        if dock_project is not None and dock_project.isVisible():
            left_docks.append(dock_project)
            left_sizes.append(left_project)
        if left_docks:
            self.resizeDocks(left_docks, left_sizes, Qt.Orientation.Horizontal)

        if dock_properties is not None and dock_properties.isVisible():
            self.resizeDocks([dock_properties], [right_properties], Qt.Orientation.Horizontal)

        vertical_docks = []
        vertical_sizes = []
        if dock_options is not None and dock_options.isVisible():
            vertical_docks.append(dock_options)
            vertical_sizes.append(top_options)
        if dock_logs is not None and dock_logs.isVisible():
            vertical_docks.append(dock_logs)
            vertical_sizes.append(bottom_logs)
        if vertical_docks:
            self.resizeDocks(vertical_docks, vertical_sizes, Qt.Orientation.Vertical)

    def show_main_page(self) -> None:
        if hasattr(self, "augmentation_page"):
            self.augmentation_page.close()
        self.workspaceStack.setCurrentWidget(self.editor_page)
        self.set_status("Main editor")

    def show_augmentation_page(self) -> None:
        if self.project_root_folder is not None:
            self.augmentation_page.set_project_defaults(self.project_root_folder)
        self.augmentation_page.set_autoaugment_running(self.is_auto_augmentation_running())
        self.augmentation_page.show()
        self.augmentation_page.raise_()
        self.augmentation_page.activateWindow()
        self.set_status("Auto augmentation dialog")

    def set_labels_visible(self, visible: bool) -> None:
        self.canvas.set_labels_visible(visible)
        self.set_status("Labels shown" if visible else "Labels hidden")

    def set_status(self, message: str) -> None:
        self.statusBar().showMessage(message)
        get_logger().info(message)

    def open_dataset_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open Dataset Folder", "")
        if not folder:
            return
        self.start_dataset_scan(Path(folder))

    def start_dataset_scan(
        self,
        folder: Path,
        project_path: Path | None = None,
        project_payload: dict | None = None,
    ) -> None:
        """Scan a dataset without blocking Qt's event loop."""
        folder = folder.resolve()
        if not folder.is_dir():
            QMessageBox.warning(self, "Open Dataset Folder", f"Folder not found:\n{folder}")
            return

        task_id = self._request_worker(
            "scan_dataset",
            {
                "folder": folder,
                "map_specs": self.DATASET_MAP_SPECS,
                "image_extensions": self.IMAGE_EXTENSIONS,
            },
        )

        def apply(map_sets):
            if project_payload is not None:
                map_sets = self._apply_project_mapsets_to_discovery(map_sets, project_payload)
                map_sets = self._apply_project_roi_contours_to_mapsets(map_sets, project_payload)
            else:
                map_sets = self._select_mapsets_to_load(map_sets)
                if not map_sets:
                    self.set_status("Dataset load cancelled")
                    return
            self.project_root_folder = folder
            self.project_path = project_path or folder / PROJECT_MANIFEST
            self.current_mapset = None
            self.current_image_path = None
            self._map_edit_states.clear()
            self._clear_mapset_history()
            self._apply_discovered_map_sets(map_sets)
            self.project = DatasetProject(folder, map_sets)
            self._load_label_catalog(folder)
            if project_payload is not None:
                self._restore_project_state(project_payload)
                self.set_status(f"Loaded project: {self.project_path}")
            else:
                self._write_project_manifest(self.project_path, quiet=True)
                self.set_status(f"Loaded {len(map_sets)} MapSet(s): {folder}")

        self._task_handlers[task_id] = apply

    def open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Project", "", PROJECT_FILTER)
        if not path:
            return
        source = Path(path).resolve()
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Load Project", f"Failed to read project file:\n{exc}")
            return
        root = payload.get("root_folder") or payload.get("root_path")
        if not root:
            QMessageBox.warning(self, "Load Project", "Project file does not contain a root folder.")
            return
        self.start_dataset_scan(Path(root), project_path=source, project_payload=payload)

    def save_current_mapset(self) -> bool:
        """Persist all current MapSet maps and labels through one staged transaction."""
        if self.current_mapset is None or self.current_image_path is None:
            QMessageBox.warning(self, "Save MapSet", "Open a MapSet first.")
            return False
        if self._mapset_update_task_id in self._active_task_ids:
            self.set_status("Current MapSet is already being saved")
            return False
        if self._save_all_task_id in self._active_task_ids:
            self.set_status("Wait for Save All to finish")
            return False
        if self._mapset_save_task_id in self._active_task_ids:
            self.set_status("Wait for Save as New MapSet to finish")
            return False
        mapset = self.current_mapset
        label_path = self._effective_label_path(mapset)
        label_lines = self.canvas.yolo_lines()
        current_path = self.current_image_path.resolve()
        map_snapshots: list[tuple[str, Path, np.ndarray | None]] = []
        for map_key, map_path in mapset.maps:
            resolved = map_path.resolve()
            if resolved == current_path and self.canvas.is_modified:
                image = qimage_to_bgr(self.canvas.pixmap)
            else:
                stored = self._map_edit_states.get(str(resolved))
                image = qimage_to_bgr(stored) if stored is not None else None
            map_snapshots.append((map_key, map_path, image))
        request = MapSetUpdateRequest(
            maps=tuple(map_snapshots),
            label_path=label_path,
            label_text="\n".join(label_lines) + ("\n" if label_lines else ""),
        )
        task_id = self._request_worker(
            "save_mapset",
            {"request": request, "label_path": label_path},
        )
        self._mapset_update_task_id = task_id
        self.set_status(f"Saving MapSet: {mapset.name}")

        def apply_saved(saved_label_path):
            for _map_key, map_path in mapset.maps:
                self._map_edit_states.pop(str(map_path.resolve()), None)
            self.canvas.mark_clean()
            self.pixmap_cache.clear()
            self._labels_modified = False
            self._loaded_label_path = Path(saved_label_path)
            self._loaded_label_snapshot = self._label_file_snapshot(Path(saved_label_path))
            self.current_mapset = self._update_mapset_label_path(mapset, Path(saved_label_path))
            self._replace_project_tree_mapset(self.current_mapset)
            self._update_mapset_property_panel(self.current_mapset)
            if self.project_path is not None:
                self._write_project_manifest(self.project_path, quiet=True)
            self._refresh_transform_properties()
            self.set_status(f"Saved complete MapSet: {mapset.name}")

        self._task_handlers[task_id] = apply_saved
        return True

    def save_all(self) -> bool:
        """Persist every MapSet that has cached map edits or label edits."""
        if not self.map_sets:
            QMessageBox.warning(self, "Save All", "Open a dataset or MapSet first.")
            return False
        if self._save_all_task_id in self._active_task_ids:
            self.set_status("Save All is already running")
            return False
        if self._mapset_update_task_id in self._active_task_ids:
            self.set_status("Wait for the current MapSet save to finish")
            return False
        if self._mapset_save_task_id in self._active_task_ids:
            self.set_status("Wait for Save as New MapSet to finish")
            return False

        self._save_current_map_edit()
        self._cache_current_label_state()
        try:
            targets = self._save_all_update_requests()
        except OSError as exc:
            QMessageBox.critical(self, "Save All", str(exc))
            return False
        if not targets:
            self.set_status("Nothing to save")
            return False

        total_units = sum(len(request.maps) + 1 for _mapset, request in targets)

        task_id = self._request_worker(
            "save_all",
            {"targets": targets, "total_units": total_units},
        )
        self._save_all_task_id = task_id
        self.set_status(f"Saving {len(targets)} modified MapSet(s)...")

        def apply_saved(saved: list[tuple[str, str]]) -> None:
            saved_labels = {folder: Path(label_path) for folder, label_path in saved}
            current_key = self._mapset_state_key(self.current_mapset) if self.current_mapset is not None else None
            saved_count = 0
            for mapset, _request in targets:
                key = self._mapset_state_key(mapset)
                label_path = saved_labels.get(key)
                if label_path is None:
                    continue
                for _map_key, map_path in mapset.maps:
                    self._map_edit_states.pop(str(map_path.resolve()), None)
                self._label_edit_states.pop(key, None)
                updated = self._update_mapset_label_path(mapset, label_path)
                self._replace_project_tree_mapset(updated)
                if key == current_key:
                    self.current_mapset = updated
                    self.canvas.mark_clean()
                    self._labels_modified = False
                    self._loaded_label_path = label_path
                    self._loaded_label_snapshot = self._label_file_snapshot(label_path)
                    self._update_mapset_property_panel(updated)
                saved_count += 1
            self.pixmap_cache.clear()
            self._save_label_catalog()
            if self.project_path is not None:
                self._write_project_manifest(self.project_path, quiet=True)
            self.set_status(f"Saved {saved_count} modified MapSet(s)")

        self._task_handlers[task_id] = apply_saved
        return True

    def _save_all_update_requests(self) -> list[tuple[MapSet, MapSetUpdateRequest]]:
        """Build in-place save requests for only MapSets with cached edits."""
        requests: list[tuple[MapSet, MapSetUpdateRequest]] = []
        for mapset in self.map_sets:
            key = self._mapset_state_key(mapset)
            label_state = self._label_edit_states.get(key)
            labels_modified = bool(label_state and label_state.get("modified"))
            maps_modified = any(str(path.resolve()) in self._map_edit_states for _map_key, path in mapset.maps)
            if not maps_modified and not labels_modified:
                continue
            map_snapshots = []
            for map_key, map_path in mapset.maps:
                stored = self._map_edit_states.get(str(map_path.resolve()))
                image = qimage_to_bgr(stored) if stored is not None else None
                map_snapshots.append((map_key, map_path, image))
            label_path = self._effective_label_path(mapset)
            label_text = self._save_all_label_text(mapset, label_state, labels_modified)
            requests.append((
                mapset,
                MapSetUpdateRequest(
                    maps=tuple(map_snapshots),
                    label_path=label_path,
                    label_text=label_text,
                ),
            ))
        return requests

    def _save_all_label_text(
        self,
        mapset: MapSet,
        label_state: dict[str, object] | None,
        labels_modified: bool,
    ) -> str:
        """Return the label text that should be persisted during Save All."""
        if labels_modified and label_state is not None:
            annotations = label_state.get("annotations", [])
            if not isinstance(annotations, list):
                annotations = []
            width, height = self._mapset_label_image_size(mapset)
            lines = self._annotations_to_yolo_lines(annotations, width, height)
            return "\n".join(lines) + ("\n" if lines else "")
        label_path = self._effective_label_path(mapset)
        if label_path.is_file():
            return label_path.read_text(encoding="utf-8")
        return ""

    def _mapset_label_image_size(self, mapset: MapSet) -> tuple[int, int]:
        """Return image dimensions used to convert cached annotations to YOLO."""
        reference = mapset.reference_path or (mapset.maps[0][1] if mapset.maps else None)
        if reference is None:
            raise OSError(f"MapSet has no image for label size: {mapset.name}")
        key = str(reference.resolve())
        stored = self._map_edit_states.get(key)
        if stored is not None:
            return max(1, stored.width()), max(1, stored.height())
        if self.current_mapset is not None and self._mapset_state_key(self.current_mapset) == self._mapset_state_key(mapset):
            if not self.canvas.pixmap.isNull():
                return max(1, self.canvas.pixmap.width()), max(1, self.canvas.pixmap.height())
        pixmap = self.pixmap_cache.load(key)
        if not pixmap.isNull():
            return max(1, pixmap.width()), max(1, pixmap.height())
        image = QImage(str(reference))
        if image.isNull():
            raise OSError(f"Cannot read label image size: {reference}")
        return max(1, image.width()), max(1, image.height())

    @staticmethod
    def _annotations_to_yolo_lines(
        annotations: list[CanvasAnnotation],
        width: int,
        height: int,
    ) -> list[str]:
        """Convert cached canvas annotations to YOLO txt lines."""
        image_rect = QRectF(0, 0, max(1, width), max(1, height))
        lines = []
        for item in annotations:
            if not isinstance(item, CanvasAnnotation):
                continue
            rect = item.bounds.intersected(image_rect)
            if rect.isEmpty():
                continue
            lines.append(
                f"{item.class_id} {(rect.x() + rect.width()/2)/image_rect.width():.6f} "
                f"{(rect.y() + rect.height()/2)/image_rect.height():.6f} "
                f"{rect.width()/image_rect.width():.6f} {rect.height()/image_rect.height():.6f}"
            )
        return lines

    def _restore_project_state(self, payload: dict) -> None:
        """Restore the last open MapSet and map path from a project manifest."""
        current_mapset_text = payload.get("current_mapset") or payload.get("current_mapset_folder")
        current_image_text = payload.get("current_image") or payload.get("current_image_path")

        target_mapset = None
        if current_mapset_text:
            try:
                current_mapset_path = Path(current_mapset_text).resolve()
                for map_set in self.map_sets:
                    if map_set.folder.resolve() == current_mapset_path:
                        target_mapset = map_set
                        break
            except OSError:
                target_mapset = None

        if target_mapset is None and current_image_text:
            try:
                current_image_path = Path(current_image_text).resolve()
                for map_set in self.map_sets:
                    if any(path.resolve() == current_image_path for _key, path in map_set.maps):
                        target_mapset = map_set
                        break
            except OSError:
                target_mapset = None

        if target_mapset is None:
            return

        self.open_mapset(target_mapset)
        if current_image_text:
            try:
                self.switch_to_map_path(Path(current_image_text))
            except OSError:
                pass

    def save_project(self) -> None:
        if self.project_path is None:
            self.save_project_as()
            return
        self._write_project_manifest(self.project_path)

    def save_project_as(self) -> None:
        initial = ""
        if self.project_root_folder is not None:
            initial = str(self.project_root_folder / PROJECT_MANIFEST)
        path, _ = QFileDialog.getSaveFileName(self, "Save Project As", initial, PROJECT_FILTER)
        if not path:
            return
        destination = Path(path)
        if destination.suffix != ".json" and not destination.name.endswith(PROJECT_MANIFEST):
            destination = destination.with_suffix(PROJECT_MANIFEST)
        self._write_project_manifest(destination)

    def open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Image", "", IMAGE_FILTER)
        if path:
            self._clear_map_tabs()
            self._load_image_to_canvas(Path(path))

    def open_images(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Open Images", "", IMAGE_FILTER)
        if not paths:
            return
        self.add_image_mapsets([Path(path) for path in paths])

    def add_image_mapsets(self, image_paths: list[Path]) -> list[MapSet]:
        """Add explicitly selected images as single-image MapSets."""
        extensions = {extension.casefold() for extension in self.IMAGE_EXTENSIONS}
        created = []
        skipped = 0
        existing = {str(map_set.folder.resolve()).casefold() for map_set in self.map_sets}
        for image_path in image_paths:
            path = image_path.resolve()
            if path.suffix.casefold() not in extensions or not path.is_file():
                skipped += 1
                continue
            if str(path).casefold() in existing:
                skipped += 1
                continue
            map_set = mapset_from_image_path(path)
            created.append(map_set)
            existing.add(str(map_set.folder.resolve()).casefold())

        if not created:
            self.set_status("No new image MapSets were added")
            return []

        if self.project_root_folder is None:
            self.project_root_folder = created[0].folder.parent
            self.project_path = self.project_root_folder / PROJECT_MANIFEST
            self._load_label_catalog(self.project_root_folder)

        self.map_sets = sorted(
            [*self.map_sets, *created],
            key=lambda item: str(item.folder).casefold(),
        )
        if self.project is None:
            self.project = DatasetProject(self.project_root_folder, self.map_sets)
        else:
            self.project.mapsets = self.map_sets

        self._apply_discovered_map_sets(self.map_sets)
        if self.current_mapset is None:
            self.open_mapset(created[0])
        if self.project_path is not None:
            self._write_project_manifest(self.project_path, quiet=True)

        message = f"Added {len(created)} image MapSet(s)"
        if skipped:
            message += f", skipped {skipped}"
        self.set_status(message)
        return created

    def load_dataset_folder(self, folder: Path) -> bool:
        folder = folder.resolve()
        if not folder.is_dir():
            QMessageBox.warning(self, "Open Dataset Folder", f"Folder not found:\n{folder}")
            return False

        self.project_root_folder = folder
        self.project_path = folder / PROJECT_MANIFEST
        self.current_mapset = None
        self.current_image_path = None
        self._map_edit_states.clear()
        self._clear_mapset_history()
        self.set_status(f"Scanning MapSets: {folder}")

        try:
            map_sets = discover_map_sets(
                root=folder,
                map_specs=self.DATASET_MAP_SPECS,
                image_extensions=self.IMAGE_EXTENSIONS,
            )
        except Exception as exc:  # pragma: no cover - user-facing fallback.
            QMessageBox.critical(self, "Open Dataset Folder", f"Failed to scan dataset folder:\n{exc}")
            return False

        map_sets = self._select_mapsets_to_load(map_sets)
        if not map_sets:
            self.set_status("Dataset load cancelled")
            return False

        self._apply_discovered_map_sets(map_sets)
        self.project = DatasetProject(folder, map_sets)
        self._load_label_catalog(folder)
        self._write_project_manifest(self.project_path, quiet=True)
        self.set_status(f"Loaded {len(map_sets)} MapSet(s): {folder}")
        return True

    def load_project_manifest(self, path: Path) -> bool:
        path = path.resolve()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Load Project", f"Failed to read project file:\n{exc}")
            return False

        root = payload.get("root_folder") or payload.get("root_path") or payload.get("root")
        if not root:
            QMessageBox.warning(self, "Load Project", "Project file does not contain a root folder.")
            return False

        self.start_dataset_scan(Path(root), project_path=path, project_payload=payload)
        return True

    def _write_project_manifest(self, path: Path, quiet: bool = False) -> None:
        if self.project_root_folder is None:
            if not quiet:
                QMessageBox.warning(self, "Save Project", "Open a dataset folder first.")
            return

        payload = {
            "project_type": "Dataset Editor",
            "root_folder": str(self.project_root_folder),
            "current_mapset": str(self.current_mapset.folder) if self.current_mapset is not None else None,
            "current_image": str(self.current_image_path) if self.current_image_path is not None else None,
            "mapsets": [
                {
                    "name": map_set.name,
                    "folder": str(map_set.folder),
                    "maps": {key: str(map_path) for key, map_path in map_set.maps},
                    "label_path": str(map_set.label_path) if map_set.label_path is not None else None,
                    "roi_contours": self._mapset_roi_contours_payload(map_set),
                }
                for map_set in self.map_sets
            ],
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            if not quiet:
                QMessageBox.critical(self, "Save Project", f"Failed to save project:\n{exc}")
            return

        self.project_path = path
        if not quiet:
            self.set_status(f"Project saved: {path}")

    def _select_mapsets_to_load(self, map_sets: list[MapSet]) -> list[MapSet]:
        """Show detected map keys only when folder-backed MapSets are available."""
        if not map_sets or self._all_single_image_mapsets(map_sets):
            return map_sets
        map_counts = self._map_key_counts(map_sets)
        if len(map_counts) <= 1:
            return map_sets
        dialog = MapSetSelectionDialog(map_counts, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return []
        return self._filter_map_sets_by_keys(map_sets, dialog.selected_map_keys())

    @staticmethod
    def _map_key_counts(map_sets: list[MapSet]) -> dict[str, int]:
        """Return detected map key counts across MapSets."""
        counts: dict[str, int] = {}
        for map_set in map_sets:
            for map_key, _path in map_set.maps:
                counts[map_key] = counts.get(map_key, 0) + 1
        return counts

    @staticmethod
    def _filter_map_sets_by_keys(map_sets: list[MapSet], selected_keys: set[str]) -> list[MapSet]:
        """Keep only selected map keys in each MapSet."""
        filtered = []
        for map_set in map_sets:
            maps = tuple((key, path) for key, path in map_set.maps if key in selected_keys)
            if maps:
                filtered.append(replace(map_set, maps=maps))
        return filtered

    @staticmethod
    def _all_single_image_mapsets(map_sets: list[MapSet]) -> bool:
        """Return whether all MapSets came from root-level single image files."""
        return all(
            len(map_set.maps) == 1
            and map_set.maps[0][0] == "image"
            and map_set.folder == map_set.maps[0][1]
            for map_set in map_sets
        )

    def _apply_discovered_map_sets(self, map_sets: list[MapSet]) -> None:
        self.map_sets = map_sets
        tree = getattr(self, "treeProject", None)
        if not isinstance(tree, QTreeWidget):
            return

        tree.clear()
        root_name = self.project_root_folder.name if self.project_root_folder is not None else "Dataset"
        self._project_root_item = self._create_project_root_item(root_name)
        tree.addTopLevelItem(self._project_root_item)

        for map_set in map_sets:
            self._project_root_item.addChild(self._create_mapset_item(map_set))

        self._project_root_item.setExpanded(True)
        tree.resizeColumnToContents(0)
        if map_sets:
            tree.setCurrentItem(self._project_root_item.child(0))

    def _create_project_root_item(self, label: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([f"{label}  [{len(self.map_sets)} MapSet(s)]"])
        self._set_tree_item_icon(item, "folderopen.svg")
        if self.project_root_folder is not None:
            item.setData(0, self.PATH_ROLE, str(self.project_root_folder))
            item.setToolTip(0, str(self.project_root_folder))
        return item

    def _create_mapset_item(self, map_set: MapSet) -> QTreeWidgetItem:
        label_count = self._mapset_label_count(map_set)
        map_count = len(map_set.maps)
        suffix = f"  [{map_count} map(s)"
        if label_count:
            suffix += f", {label_count} label(s)"
        suffix += "]"

        item = QTreeWidgetItem([f"{map_set.name}{suffix}"])
        self._set_tree_item_icon(item, "grid.svg")
        item.setData(0, self.MAPSET_ROLE, map_set)
        item.setData(0, self.PATH_ROLE, str(map_set.folder))
        item.setToolTip(0, self._mapset_tooltip(map_set))
        for map_key, map_path in map_set.maps:
            child = QTreeWidgetItem([map_key.replace("_", " ").title()])
            self._set_tree_item_icon(child, "fileopen.svg")
            child.setData(0, self.PATH_ROLE, str(map_path))
            child.setToolTip(0, str(map_path))
            item.addChild(child)
        if map_set.label_path is not None:
            label_item = QTreeWidgetItem([map_set.label_path.name])
            self._set_tree_item_icon(label_item, "labeling.png")
            label_item.setData(0, self.PATH_ROLE, str(map_set.label_path))
            label_item.setToolTip(0, str(map_set.label_path))
            item.addChild(label_item)
        return item

    def _mapset_tooltip(self, map_set: MapSet) -> str:
        lines = [str(map_set.folder), ""]
        lines.extend(f"{key}: {path.name}" for key, path in map_set.maps)
        if map_set.label_path is not None:
            lines.extend(["", f"labels: {map_set.label_path.name}"])
        return "\n".join(lines)

    def _count_label_lines(self, path: Path | None) -> int:
        if path is None or not path.is_file():
            return 0
        try:
            return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        except OSError:
            return 0

    def _mapset_label_count(self, map_set: MapSet) -> int:
        """Return the label count visible to the user, including unsaved edits."""
        if self.current_mapset is not None and self.current_mapset.folder == map_set.folder:
            return len(self.canvas.annotations)

        state = self._label_edit_states.get(self._mapset_state_key(map_set))
        annotations = state.get("annotations") if state is not None and state.get("modified") else None
        if isinstance(annotations, list):
            return len(annotations)

        return self._count_label_lines(map_set.label_path)

    def _on_project_item_selected(
        self,
        current: QTreeWidgetItem | None,
        previous: QTreeWidgetItem | None,
    ) -> None:
        del previous
        map_set = self._project_item_mapset(current)
        if map_set is None:
            return
        self._update_mapset_property_panel(map_set)

    def _on_project_item_open_requested(self, item: QTreeWidgetItem, column: int = 0) -> None:
        del column
        map_set = self._project_item_mapset(item)
        path = item.data(0, self.PATH_ROLE) if item is not None else None
        if path and Path(path).suffix.casefold() in self.IMAGE_EXTENSIONS:
            if map_set is not None and map_set is not self.current_mapset:
                self.open_mapset(map_set)
            if not self.switch_to_map_path(Path(path)):
                self._load_image_to_canvas(Path(path))
            return
        if path and Path(path).suffix.casefold() == ".txt":
            if map_set is not None and map_set is not self.current_mapset:
                self.open_mapset(map_set)
            else:
                self.reload_current_yolo_labels()
            return
        if map_set is not None:
            self.open_mapset(map_set)
        elif item is not None and item.childCount():
            item.setExpanded(not item.isExpanded())

    def _project_item_mapset(self, item: QTreeWidgetItem | None) -> MapSet | None:
        current = item
        while current is not None:
            value = current.data(0, self.MAPSET_ROLE)
            if isinstance(value, MapSet):
                return value
            current = current.parent()
        return None

    def open_mapset(self, map_set: MapSet) -> None:
        changing_mapset = self.current_mapset is not map_set
        if changing_mapset:
            self._cache_current_label_state()
            self._save_current_map_edit()
            self._clear_mapset_history()
        self.current_mapset = map_set
        self.show_main_page()
        if changing_mapset:
            self.canvas.clear_selection()
            self.canvas.annotations.clear()
        self._populate_map_tabs(map_set)
        self._load_current_yolo_labels()
        self._update_mapset_property_panel(map_set)
        self.set_status(f"Opened MapSet: {map_set.name}")

    @staticmethod
    def _map_display_name(map_key: str) -> str:
        aliases = {
            "albedo_map": "Albedo",
            "normal_map": "Normal",
            "curvature_map": "Curvature",
            "depth_map": "Depth",
        }
        return aliases.get(map_key, map_key.replace("_", " ").title())

    def _clear_map_tabs(self) -> None:
        self._switching_map = True
        while self.map_switch_tabs.count():
            self.map_switch_tabs.removeTab(self.map_switch_tabs.count() - 1)
        self.map_switch_tabs.hide()
        self._switching_map = False

    def _populate_map_tabs(self, map_set: MapSet) -> None:
        """Create one cached map tab and activate the reference map."""
        self._save_current_map_edit()
        self._switching_map = True
        while self.map_switch_tabs.count():
            self.map_switch_tabs.removeTab(self.map_switch_tabs.count() - 1)
        reference_index = 0
        for index, (map_key, path) in enumerate(map_set.maps):
            self.map_switch_tabs.addTab(self._map_display_name(map_key))
            self.map_switch_tabs.setTabData(index, (map_key, str(path)))
            if path == map_set.reference_path:
                reference_index = index
        self.map_switch_tabs.setVisible(self.map_switch_tabs.count() > 1)
        self.map_switch_tabs.setCurrentIndex(reference_index)
        self._switching_map = False
        self._activate_map_tab(reference_index, preserve_view=False)

    def _on_map_tab_changed(self, index: int) -> None:
        if self._switching_map or index < 0:
            return
        self._save_current_map_edit()
        self._activate_map_tab(index, preserve_view=True)

    def _activate_map_tab(self, index: int, preserve_view: bool) -> None:
        data = self.map_switch_tabs.tabData(index)
        if not data:
            return
        _map_key, path_text = data
        path = Path(path_text).resolve()
        stored = self._map_edit_states.get(str(path))
        pixmap = QPixmap.fromImage(stored) if stored is not None else self.pixmap_cache.load(str(path))
        if pixmap.isNull():
            QMessageBox.warning(self, "Open Map", f"Cannot load map:\n{path}")
            return
        view_state = self.canvas.view_state() if preserve_view else None
        self.current_image_path = path
        if preserve_view:
            self.canvas.set_map_image(pixmap, modified=stored is not None)
            self.canvas.apply_view_state(*view_state)
        else:
            self.canvas.set_map_image(pixmap, modified=stored is not None)
            self.canvas.fit_to_window()
        if hasattr(self, "tool_controller") and self.tool_controller.patch_state.placement_active:
            self.tool_controller.set_patch_active_map_key(_map_key)
        self._update_image_property_panel(path, pixmap)
        self.set_status(f"Map: {self.map_switch_tabs.tabText(index)}")

    def _save_current_map_edit(self) -> None:
        if self.current_image_path is None or not self.canvas.is_modified:
            return
        self._map_edit_states[str(self.current_image_path.resolve())] = self.canvas.pixmap.toImage()

    def switch_to_map_path(self, path: Path) -> bool:
        """Activate a map tab from Project Explorer without resetting the viewport."""
        normalized = str(path.resolve())
        for index in range(self.map_switch_tabs.count()):
            data = self.map_switch_tabs.tabData(index)
            if data and str(Path(data[1]).resolve()) == normalized:
                self.map_switch_tabs.setCurrentIndex(index)
                return True
        return False

    def _load_image_to_canvas(self, path: Path) -> bool:
        path = path.resolve()
        pixmap = self.pixmap_cache.load(str(path))
        if pixmap.isNull():
            QMessageBox.warning(self, "Open Image", f"Cannot load image:\n{path}")
            return False
        self.current_image_path = path
        self.canvas.set_image(pixmap)
        self.canvas.fit_to_window()
        self._update_image_property_panel(path, pixmap)
        return True

    def add_label_from_selection(self) -> None:
        """Choose one existing class and apply it to the active selection."""
        if not self.canvas.has_selection():
            self.set_status("Select an area before adding a label")
            return
        if not self._label_catalog:
            QMessageBox.information(
                self,
                "Add Label",
                "No label classes exist. Add classes from Label Class Manager first.",
            )
            self.show_label_manager()
            return
        dialog = LabelAddDialog(
            self._label_catalog,
            self,
            initial_class_id=self._last_label_class_id,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected = dialog.selected_label()
        if selected is None:
            return
        class_id, class_name = selected
        if self.add_annotation_with_class(class_id, class_name):
            self._last_label_class_id = class_id

    def show_label_manager(self) -> None:
        if self.project_root_folder is None:
            QMessageBox.warning(self, "Label Class Manager", "Open a dataset project first.")
            return
        self._label_dialog = LabelManagerDialog(self)
        self._label_dialog.exec()

    def label_catalog(self) -> list[tuple[int, str]]:
        return list(self._label_catalog)

    def class_name_for_id(self, class_id: int) -> str:
        for item_id, item_name in self._label_catalog:
            if item_id == class_id:
                return item_name
        return ""

    def _load_label_catalog(self, root: Path) -> None:
        path = root / "labels.json"
        catalog = []
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                items = payload.get("labels", payload) if isinstance(payload, dict) else payload
                for index, item in enumerate(items if isinstance(items, list) else []):
                    if isinstance(item, dict):
                        class_id = int(item.get("class_id", item.get("id", index)))
                        class_name = str(item.get("class_name", item.get("name", f"class {class_id}"))).strip()
                    else:
                        class_id, class_name = index, str(item).strip()
                    catalog.append((class_id, class_name))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                catalog = []
        self._label_catalog = normalize_catalog(catalog)

    def _save_label_catalog(self) -> None:
        if self.project_root_folder is None:
            return
        payload = {
            "labels": [
                {"class_id": class_id, "class_name": class_name}
                for class_id, class_name in self._label_catalog
            ]
        }
        try:
            (self.project_root_folder / "labels.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            QMessageBox.critical(self, "Save Label Classes", str(exc))

    def next_label_class_id(self) -> int:
        used = {class_id for class_id, _name in self._label_catalog}
        candidate = 0
        while candidate in used:
            candidate += 1
        return candidate

    def _class_id_used(self, class_id: int) -> bool:
        if any(item.class_id == class_id for item in self.canvas.annotations):
            return True
        for map_set in self.map_sets:
            path = map_set.label_path or (map_set.folder / f"{map_set.name}.txt")
            if not path.is_file():
                continue
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    parts = line.split()
                    if parts and int(float(parts[0])) == class_id:
                        return True
            except (OSError, ValueError):
                continue
        return False

    def update_label_class(
        self,
        original_id: int | None,
        class_id: int,
        class_name: str,
    ) -> None:
        """Add or edit one class in place without implicitly renumbering others."""
        if original_id is not None and original_id != class_id and self._class_id_used(original_id):
            raise ValueError("A class ID used by YOLO annotations cannot be changed.")
        self._label_catalog = update_catalog(
            self._label_catalog,
            original_id,
            class_id,
            class_name,
        )
        if original_id == class_id:
            self.canvas.annotations = [
                CanvasAnnotation(item.class_id, item.bounds, class_name)
                if item.class_id == class_id else item
                for item in self.canvas.annotations
            ]
            self.canvas.annotations_changed.emit()
        self._save_label_catalog()

    def upsert_label_class(self, class_id: int, class_name: str) -> None:
        original = class_id if any(item_id == class_id for item_id, _name in self._label_catalog) else None
        self.update_label_class(original, class_id, class_name)

    def delete_label_class(self, class_id: int) -> bool:
        if self._class_id_used(class_id):
            QMessageBox.warning(self, "Delete Class", "This class is used by YOLO annotations.")
            return False
        if not any(item_id == class_id for item_id, _name in self._label_catalog):
            return False
        self._label_catalog = remove_from_catalog(self._label_catalog, class_id)
        self._save_label_catalog()
        return True

    def move_label_class(self, class_id: int, offset: int) -> None:
        self._label_catalog = move_in_catalog(self._label_catalog, class_id, offset)
        self._save_label_catalog()

    def add_annotation_with_class(self, class_id: int, class_name: str) -> bool:
        if not self.canvas.add_annotation_from_selection(class_id, class_name):
            return False
        self.set_status(f"Added annotation: [{class_id}] {class_name}")
        return True

    def remove_annotation(self, index: int) -> bool:
        removed = self.canvas.remove_annotation(index)
        if removed:
            self.set_status("Annotation removed")
        return removed

    def remove_active_annotation(self) -> bool:
        """Remove the selected label or the topmost label overlapping the active selection."""
        if self.canvas.selected_annotation_index >= 0:
            return self.remove_annotation(self.canvas.selected_annotation_index)
        index = self._annotation_index_from_selection()
        if index >= 0:
            return self.remove_annotation(index)
        self.set_status("Select an existing label before removing it")
        return False

    def _annotation_index_from_selection(self) -> int:
        if not self.canvas.has_selection():
            return -1
        selection = self.canvas.selection_bounds()
        for index in range(len(self.canvas.annotations) - 1, -1, -1):
            if self.canvas.annotations[index].bounds.intersects(selection):
                return index
        return -1

    @staticmethod
    def _label_file_snapshot(path: Path) -> tuple[int, int] | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def _label_file_changed_on_disk(self, label_path: Path) -> bool:
        if self._loaded_label_path != label_path:
            return False
        return self._label_file_snapshot(label_path) != self._loaded_label_snapshot

    def _effective_label_path(self, map_set: MapSet) -> Path:
        return map_set.label_path or (map_set.folder / f"{map_set.name}.txt")

    def _update_mapset_label_path(self, map_set: MapSet, label_path: Path) -> MapSet:
        if map_set.label_path == label_path:
            return map_set
        updated = replace(map_set, label_path=label_path.resolve())
        for index, item in enumerate(self.map_sets):
            if item.folder == map_set.folder:
                self.map_sets[index] = updated
                break
        if self.project is not None:
            for index, item in enumerate(self.project.mapsets):
                if item.folder == map_set.folder:
                    self.project.mapsets[index] = updated
                    break
        if self.current_mapset is not None and (
            self.current_mapset is map_set or self.current_mapset.folder == map_set.folder
        ):
            self.current_mapset = updated
        return updated

    @staticmethod
    def _mapset_state_key(map_set: MapSet) -> str:
        return str(map_set.folder.resolve())

    @staticmethod
    def _copy_annotations(annotations: list[CanvasAnnotation]) -> list[CanvasAnnotation]:
        return [
            CanvasAnnotation(item.class_id, QRectF(item.bounds), item.class_name)
            for item in annotations
        ]

    def _cache_current_label_state(self) -> None:
        if self.current_mapset is None:
            return
        key = self._mapset_state_key(self.current_mapset)
        if not self._labels_modified:
            self._label_edit_states.pop(key, None)
            return
        self._label_edit_states[key] = {
            "annotations": self._copy_annotations(self.canvas.annotations),
            "modified": True,
            "loaded_label_path": self._loaded_label_path,
            "loaded_label_snapshot": self._loaded_label_snapshot,
        }

    def _restore_cached_label_state(self, map_set: MapSet) -> bool:
        state = self._label_edit_states.get(self._mapset_state_key(map_set))
        if state is None:
            return False
        annotations = state.get("annotations", [])
        self._loading_labels = True
        try:
            self.canvas.annotations = self._copy_annotations(annotations)
            self.canvas.selected_annotation_index = -1
            self.canvas.update()
            self._on_annotations_changed()
        finally:
            self._loading_labels = False
        self._labels_modified = bool(state.get("modified", False))
        loaded_path = state.get("loaded_label_path")
        self._loaded_label_path = Path(loaded_path) if loaded_path is not None else None
        snapshot = state.get("loaded_label_snapshot")
        self._loaded_label_snapshot = snapshot if isinstance(snapshot, tuple) else None
        return True

    def _save_current_yolo_labels_if_needed(self) -> bool:
        if self.current_mapset is None:
            return True
        label_path = self._effective_label_path(self.current_mapset)
        if not self._labels_modified and self._label_file_changed_on_disk(label_path):
            self._load_current_yolo_labels(force_disk=True)
            return True
        if not self._labels_modified:
            return True
        QMessageBox.warning(
            self,
            "Unsaved Labels",
            "YOLO labels have unsaved edits. Save labels manually before continuing.",
        )
        return False

    def _load_current_yolo_labels(self, force_disk: bool = False) -> None:
        if (
            not force_disk
            and self.current_mapset is not None
            and self._restore_cached_label_state(self.current_mapset)
        ):
            return
        self._loading_labels = True
        self.canvas.annotations = []
        try:
            if self.current_mapset is None:
                self.canvas.update()
                self._labels_modified = False
                return
            label_path = self._effective_label_path(self.current_mapset)
            self._loaded_label_path = label_path
            self._loaded_label_snapshot = self._label_file_snapshot(label_path)
            if not label_path.is_file():
                self.canvas.selected_annotation_index = -1
                self.canvas.update()
                self._labels_modified = False
                return
            width, height = self.canvas.pixmap.width(), self.canvas.pixmap.height()
            annotations = []
            catalog = dict(self._label_catalog)
            for label in self.context.yolo_api.load_txt(label_path):
                if label.class_id not in catalog:
                    catalog[label.class_id] = f"class {label.class_id}"
                    self._label_catalog.append((label.class_id, catalog[label.class_id]))
                x1 = (label.x_center - label.width / 2) * width
                y1 = (label.y_center - label.height / 2) * height
                annotations.append(CanvasAnnotation(
                    label.class_id,
                    QRectF(x1, y1, label.width * width, label.height * height),
                    catalog.get(label.class_id, ""),
                ))
            self.canvas.annotations = annotations
            self.canvas.selected_annotation_index = -1
            self.canvas.update()
            self._labels_modified = False
        finally:
            self._loading_labels = False
        self._on_annotations_changed()
        self._labels_modified = False

    def reload_current_yolo_labels(self) -> bool:
        """Reload YOLO labels from disk and discard only the label overlay cache."""
        if self.current_mapset is None:
            self.set_status("Open a MapSet before reloading labels")
            return False
        self._label_edit_states.pop(self._mapset_state_key(self.current_mapset), None)
        self._load_current_yolo_labels(force_disk=True)
        self.set_status("Reloaded YOLO labels from file")
        return True

    def save_current_yolo_labels(self) -> bool:
        if self.current_mapset is None:
            self.set_status("Open a MapSet before saving labels")
            return False
        destination = self._effective_label_path(self.current_mapset)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                "\n".join(self.canvas.yolo_lines()) + ("\n" if self.canvas.annotations else ""),
                encoding="utf-8",
            )
        except OSError as exc:
            QMessageBox.critical(self, "Save YOLO Labels", str(exc))
            return False
        self.current_mapset = self._update_mapset_label_path(self.current_mapset, destination)
        if self.current_mapset is not None:
            self._replace_project_tree_mapset(self.current_mapset)
            self._update_mapset_property_panel(self.current_mapset)
        self._loaded_label_path = destination
        self._loaded_label_snapshot = self._label_file_snapshot(destination)
        self._labels_modified = False
        self._cache_current_label_state()
        self._save_label_catalog()
        if self.project_path is not None:
            self._write_project_manifest(self.project_path, quiet=True)
        self.set_status(f"Saved YOLO labels: {destination}")
        return True

    def copy_selection_to_patch(self) -> bool:
        if self.current_mapset is None or self.current_image_path is None:
            self.set_status("Open a MapSet before copying a patch")
            return False
        source_name = self.current_image_path.name if self.current_image_path is not None else "Current image"
        bounds = self.canvas.selection_bounds().toAlignedRect().intersected(self.canvas.pixmap.rect())
        if not self.tool_controller.copy_selection_to_patch(source_name):
            self.set_status("Select an area before copying a patch")
            return False
        try:
            source_images = self._mapset_image_snapshots(self.current_mapset)
            mask = self.tool_controller.patch_state.mask
            if mask is None:
                raise ValueError("Selection mask is empty")
            map_patches = {
                map_key: image[
                    bounds.top():bounds.bottom() + 1,
                    bounds.left():bounds.right() + 1,
                ].copy()
                for map_key, image in source_images.items()
            }
            clip = self.patch_clipboard.add_mapset(
                map_patches,
                mask,
                "",
                self.current_mapset.folder,
                preview_key=self._current_map_key() or "",
            )
        except (OSError, ValueError) as exc:
            self.tool_controller.clear_active_patch()
            self.set_status(f"Failed to copy MapSet patch: {exc}")
            return False
        self.tool_controller.clear_active_patch()
        self.listMasks.refresh(select_id=clip.clip_id)
        self.canvas.clear_selection()
        self.set_status(
            f"Copied {clip.name} to Patch Clipboard ({len(self.patch_clipboard)} total)"
        )
        return True

    def _mapset_image_snapshots(self, map_set: MapSet) -> dict[str, np.ndarray]:
        """Capture owned current pixels for every map in one MapSet on the GUI thread."""
        snapshots: dict[str, np.ndarray] = {}
        expected_shape: tuple[int, int] | None = None
        current_path = self.current_image_path.resolve() if self.current_image_path is not None else None
        for map_key, map_path in map_set.maps:
            resolved = map_path.resolve()
            if current_path is not None and resolved == current_path:
                image = qimage_to_bgr(self.canvas.pixmap)
            else:
                stored = self._map_edit_states.get(str(resolved))
                image = qimage_to_bgr(stored) if stored is not None else read_image(resolved)
            if image is None or image.size == 0:
                raise OSError(f"Cannot read MapSet map: {resolved}")
            if expected_shape is None:
                expected_shape = image.shape[:2]
            elif image.shape[:2] != expected_shape:
                raise ValueError("MapSet maps do not share one coordinate system")
            snapshots[map_key] = image.copy()
        return snapshots

    def _clear_mapset_history(self) -> None:
        self._mapset_undo.clear()
        self._mapset_redo.clear()
        self._pending_mapset_history_before = None

    def _mapset_edit_snapshot(self, map_set: MapSet) -> dict[str, QImage]:
        """Capture current pixels for every map only long enough to build a delta."""
        snapshot: dict[str, QImage] = {}
        current_path = self.current_image_path.resolve() if self.current_image_path is not None else None
        for _map_key, map_path in map_set.maps:
            resolved = map_path.resolve()
            key = str(resolved)
            if current_path is not None and resolved == current_path:
                snapshot[key] = self.canvas.pixmap.toImage()
                continue
            stored = self._map_edit_states.get(key)
            if stored is not None:
                snapshot[key] = QImage(stored)
                continue
            pixmap = self.pixmap_cache.load(key)
            if pixmap.isNull():
                raise OSError(f"Cannot load MapSet map for history: {resolved}")
            snapshot[key] = pixmap.toImage()
        return snapshot

    def begin_mapset_edit_history(self) -> None:
        """Remember pre-edit pixels so the final commit can store changed patches only."""
        if self.current_mapset is None:
            return
        self._save_current_map_edit()
        try:
            self._pending_mapset_history_before = self._mapset_edit_snapshot(self.current_mapset)
        except OSError as exc:
            self._pending_mapset_history_before = None
            self.set_status(str(exc))

    def _take_mapset_history_before(self) -> dict[str, QImage] | None:
        before = self._pending_mapset_history_before
        self._pending_mapset_history_before = None
        if before is not None:
            return before
        if self.current_mapset is None:
            return None
        try:
            return self._mapset_edit_snapshot(self.current_mapset)
        except OSError as exc:
            self.set_status(str(exc))
            return None

    def _push_mapset_history_entry(
        self,
        before: dict[str, QImage] | None,
        after_updates: dict[str, QImage],
    ) -> bool:
        if before is None or not after_updates:
            return False
        after = {key: QImage(image) for key, image in before.items()}
        for key, image in after_updates.items():
            if key in after:
                after[key] = QImage(image)
        try:
            entry = build_mapset_history_entry(before, after)
        except ValueError as exc:
            self.set_status(f"History skipped: {exc}")
            return False
        if entry is None:
            return False
        self._mapset_undo.append(entry)
        del self._mapset_undo[:-5]
        self._mapset_redo.clear()
        return True

    def undo_mapset_edit(self) -> bool:
        if self.current_mapset is None or not self._mapset_undo:
            return False
        self._save_current_map_edit()
        entry = self._mapset_undo.pop()
        if not self._apply_mapset_history_entry(entry, redo=False):
            self._mapset_undo.append(entry)
            return False
        self._mapset_redo.append(entry)
        self.set_status("Undo MapSet edit")
        return True

    def redo_mapset_edit(self) -> bool:
        if self.current_mapset is None or not self._mapset_redo:
            return False
        self._save_current_map_edit()
        entry = self._mapset_redo.pop()
        if not self._apply_mapset_history_entry(entry, redo=True):
            self._mapset_redo.append(entry)
            return False
        self._mapset_undo.append(entry)
        del self._mapset_undo[:-5]
        self.set_status("Redo MapSet edit")
        return True

    def undo_edit(self) -> bool:
        """Undo a MapSet edit, falling back to the canvas history when needed."""
        if self.current_mapset is not None and self.undo_mapset_edit():
            return True
        if self.canvas.undo():
            self._save_current_map_edit()
            self._update_image_property_panel(self.current_image_path, self.canvas.pixmap)
            self.set_status("Undo image edit")
            return True
        self.set_status("Nothing to undo")
        return False

    def redo_edit(self) -> bool:
        """Redo a MapSet edit, falling back to the canvas history when needed."""
        if self.current_mapset is not None and self.redo_mapset_edit():
            return True
        if self.canvas.redo():
            self._save_current_map_edit()
            self._update_image_property_panel(self.current_image_path, self.canvas.pixmap)
            self.set_status("Redo image edit")
            return True
        self.set_status("Nothing to redo")
        return False

    def _apply_mapset_history_entry(self, entry: MapSetHistoryEntry, *, redo: bool) -> bool:
        if self.current_mapset is None:
            return False
        current_images = self._current_images_for_history_entry(entry)
        restored = apply_history_entry(current_images, entry, redo=redo)
        if not restored:
            return False
        self._map_edit_states.update(restored)
        current_key = str(self.current_image_path.resolve()) if self.current_image_path is not None else None
        if current_key in restored:
            view_state = self.canvas.view_state()
            self.canvas.set_map_image(restored[current_key], modified=True)
            self.canvas.apply_view_state(*view_state)
            self._update_image_property_panel(self.current_image_path, self.canvas.pixmap)
        return True

    def _current_images_for_history_entry(self, entry: MapSetHistoryEntry) -> dict[str, QImage]:
        images: dict[str, QImage] = {}
        current_key = str(self.current_image_path.resolve()) if self.current_image_path is not None else None
        for key in entry.patches:
            if current_key is not None and key == current_key:
                images[key] = self.canvas.pixmap.toImage()
                continue
            stored = self._map_edit_states.get(key)
            if stored is not None:
                images[key] = QImage(stored)
                continue
            pixmap = self.pixmap_cache.load(key)
            if not pixmap.isNull():
                images[key] = pixmap.toImage()
        return images

    def apply_mapset_paint_strokes(
        self,
        strokes: list[tuple[tuple[float, float], tuple[float, float]]],
        color: QColor,
        size: int,
        opacity: float,
    ) -> bool:
        """Apply one brush gesture to every map in the current MapSet."""
        if self.current_mapset is None or not strokes:
            return False
        bgr_color = (color.blue(), color.green(), color.red())
        processed: dict[str, QImage] = {}
        for _map_key, map_path in self.current_mapset.maps:
            source = self._load_editable_map_image(map_path)
            if source is None:
                continue
            result = apply_paint_strokes(source, strokes, bgr_color, size, opacity)
            processed[str(map_path.resolve())] = bgr_to_qpixmap(result).toImage()
        return self._commit_mapset_images(processed, "Brush applied to MapSet")

    def apply_mapset_healing_strokes(
        self,
        strokes: list[HealingStroke],
        size: int,
        opacity: float,
    ) -> bool:
        """Start a worker that applies one healing gesture to every MapSet map."""
        if self.current_mapset is None or not strokes:
            return False
        if self._healing_task_id in self._active_task_ids:
            self.set_status("Healing Brush is already running")
            return False
        target_mapset = self.current_mapset
        target_folder = str(target_mapset.folder.resolve())
        history_before = self._take_mapset_history_before()
        images: dict[str, np.ndarray] = {}
        for _map_key, map_path in target_mapset.maps:
            source = self._load_editable_map_image(map_path)
            if source is None:
                continue
            images[str(map_path.resolve())] = source
        if not images:
            self._pending_mapset_history_before = None
            self.set_status("Healing Brush failed: no MapSet images could be loaded")
            return False

        self._healing_restore_images = history_before

        task_id = self._request_worker(
            "healing",
            {
                "images": images,
                "strokes": list(strokes),
                "size": size,
                "opacity": opacity,
            },
        )
        self._healing_task_id = task_id
        self.set_status(f"Applying Healing Brush to {len(images)} MapSet maps...")

        def apply_result(results: dict[str, np.ndarray]) -> None:
            current_folder = str(self.current_mapset.folder.resolve()) if self.current_mapset is not None else None
            if current_folder != target_folder:
                self.set_status("Healing Brush result discarded because the target MapSet changed")
                return
            processed = {
                key: bgr_to_qpixmap(result).toImage()
                for key, result in results.items()
            }
            self._push_mapset_history_entry(history_before, processed)
            self._map_edit_states.update(processed)
            current_key = str(self.current_image_path.resolve()) if self.current_image_path is not None else None
            if current_key in processed:
                view_state = self.canvas.view_state()
                self.canvas.set_map_image(processed[current_key], modified=True)
                self.canvas.apply_view_state(*view_state)
                self._update_image_property_panel(self.current_image_path, self.canvas.pixmap)
            self.set_status(f"Healing Brush applied to {len(processed)} MapSet maps")

        self._task_handlers[task_id] = apply_result
        return True

    def _restore_healing_preview_after_task(self) -> None:
        """Restore the visible preview when background healing does not commit."""
        before = self._healing_restore_images
        if before is None or self.current_image_path is None:
            return
        current_key = str(self.current_image_path.resolve())
        image = before.get(current_key)
        if image is None:
            return
        view_state = self.canvas.view_state()
        self.canvas.set_map_image(QImage(image), modified=current_key in self._map_edit_states)
        self.canvas.apply_view_state(*view_state)
        self._update_image_property_panel(self.current_image_path, self.canvas.pixmap)

    def apply_mapset_selection_fill(self, color: QColor, opacity: float = 1.0) -> bool:
        if self.current_mapset is None or not self.canvas.has_selection() or self.canvas.pixmap.isNull():
            return False
        mask = qimage_to_bgr(self.canvas.selection_mask())
        if mask is None:
            return False
        mask = mask[:, :, 0] if mask.ndim == 3 else mask
        self.begin_mapset_edit_history()
        bgr_color = (color.blue(), color.green(), color.red())
        processed: dict[str, QImage] = {}
        for _map_key, map_path in self.current_mapset.maps:
            source = self._load_editable_map_image(map_path)
            if source is None:
                continue
            result = apply_selection_fill(source, mask, bgr_color, opacity)
            processed[str(map_path.resolve())] = bgr_to_qpixmap(result).toImage()
        return self._commit_mapset_images(processed, "Fill applied to MapSet")

    def apply_mapset_selection_delete(self) -> bool:
        if self.current_mapset is None or not self.canvas.has_selection() or self.canvas.pixmap.isNull():
            return False
        mask = qimage_to_bgr(self.canvas.selection_mask())
        if mask is None:
            return False
        mask = mask[:, :, 0] if mask.ndim == 3 else mask
        self.begin_mapset_edit_history()
        processed: dict[str, QImage] = {}
        for _map_key, map_path in self.current_mapset.maps:
            source = self._load_editable_map_image(map_path)
            if source is None:
                continue
            result = apply_selection_delete(source, mask)
            processed[str(map_path.resolve())] = bgr_to_qpixmap(result).toImage()
        return self._commit_mapset_images(processed, "Selection deleted from MapSet")

    def _commit_mapset_images(self, processed: dict[str, QImage], message: str) -> bool:
        if not processed:
            self._pending_mapset_history_before = None
            return False
        self._push_mapset_history_entry(self._take_mapset_history_before(), processed)
        self._map_edit_states.update(processed)
        current_key = str(self.current_image_path.resolve()) if self.current_image_path is not None else None
        if current_key in processed:
            view_state = self.canvas.view_state()
            self.canvas.set_map_image(processed[current_key], modified=True)
            self.canvas.apply_view_state(*view_state)
            self._update_image_property_panel(self.current_image_path, self.canvas.pixmap)
        self.set_status(message)
        return True

    def _on_patch_dropped(self, clip_id: str, image_position) -> None:
        """Start placement from one thumbnail dropped onto the current target image."""
        self.place_clipboard_patch(clip_id, image_position.x(), image_position.y())

    def place_clipboard_patch(
        self,
        clip_id: str | None = None,
        center_x: float | None = None,
        center_y: float | None = None,
    ) -> bool:
        """Load a stored clip into PatchTool at a target-image position."""
        if self._manual_poisson_task_id in self._active_task_ids:
            self.set_status("Wait for the current Poisson operation to finish")
            return False
        clip_id = clip_id or self.listMasks.selected_clip_id()
        clip = self.patch_clipboard.get(clip_id) if clip_id else None
        if clip is None:
            self.set_status("Select or drag a patch from Patch Clipboard")
            return False
        if self.canvas.pixmap.isNull():
            self.set_status("Open a target image first")
            return False
        if center_x is None:
            center_x = self.canvas.pixmap.width() / 2.0
        if center_y is None:
            center_y = self.canvas.pixmap.height() / 2.0
        map_key = self._current_map_key()
        if map_key is None:
            self.set_status("Cannot determine the current target map key")
            return False
        target_keys = {key for key, _path in self.current_mapset.maps} if self.current_mapset is not None else set()
        missing = sorted(target_keys.difference(clip.map_keys))
        if missing:
            self.set_status(f"Clipboard MapSet patch is missing map keys: {', '.join(missing)}")
            return False
        if not self.tool_controller.load_patch_clip(clip, center_x, center_y, map_key):
            self.set_status("Failed to load clipboard patch")
            return False
        self.ui_setup.activate_tool(ToolMode.PATCH)
        self.set_status("Patch placed: left-drag to move, right-drag to rotate")
        return True

    def start_manual_poisson(self, mode: int | str | None, mode_name: str = "Normal") -> bool:
        """Compose the current manual patch on a worker and commit it if still current."""
        if self._manual_poisson_task_id in self._active_task_ids:
            self.set_status("Manual Poisson is already running")
            return False
        if not self.tool_controller.has_patch_preview():
            self.set_status("Copy a selection first")
            return False
        target_mapset = self.current_mapset
        if target_mapset is None:
            self.set_status("Open a target MapSet first")
            return False
        try:
            target_images = self._mapset_image_snapshots(target_mapset)
            composition_inputs = self.tool_controller.patch_mapset_composition_inputs(target_images)
            history_before = self._mapset_edit_snapshot(target_mapset)
        except (OSError, ValueError, RuntimeError) as exc:
            self.set_status(f"Poisson failed: {exc}")
            return False

        target_folder = str(target_mapset.folder.resolve())

        task_id = self._request_worker(
            "manual_poisson",
            {"composition_inputs": composition_inputs, "mode": mode},
        )
        self._manual_poisson_task_id = task_id
        self.ui_setup.set_manual_poisson_running(True)
        self.set_status(f"Applying Poisson ({mode_name})...")

        def apply_result(results):
            current_folder = str(self.current_mapset.folder.resolve()) if self.current_mapset is not None else None
            if current_folder != target_folder:
                self.set_status("Poisson result discarded because the target MapSet changed")
                return
            current_key = self._current_map_key()
            processed: dict[str, QImage] = {}
            for map_key, result in results.items():
                map_path = target_mapset.map_paths[map_key].resolve()
                processed[str(map_path)] = bgr_to_qpixmap(result).toImage()
            self._push_mapset_history_entry(history_before, processed)
            self._map_edit_states.update(processed)
            if current_key in results:
                current_path = target_mapset.map_paths[current_key].resolve()
                current_image = self._map_edit_states.get(str(current_path))
                if current_image is not None:
                    view_state = self.canvas.view_state()
                    self.canvas.set_map_image(current_image, modified=True)
                    self.canvas.apply_view_state(*view_state)
                    self._update_image_property_panel(self.current_image_path, self.canvas.pixmap)
            self.tool_controller.complete_current_tool(ToolMode.MOVE)
            self._save_current_map_edit()
            self.set_status(f"Poisson applied to {len(results)} MapSet maps ({mode_name})")

        self._task_handlers[task_id] = apply_result
        return True

    def save_current_as_new_mapset(self) -> bool:
        """Save a complete edited MapSet copy without mutating the source folder."""
        if self.project_root_folder is None or self.current_mapset is None:
            QMessageBox.warning(self, "Save MapSet", "Open a folder-backed MapSet first.")
            return False
        if self._mapset_save_task_id in self._active_task_ids:
            self.set_status("A MapSet save is already running")
            return False
        if self._save_all_task_id in self._active_task_ids:
            self.set_status("Wait for Save All to finish")
            return False
        if self._mapset_update_task_id in self._active_task_ids:
            self.set_status("Wait for the current MapSet save to finish")
            return False

        base_name = f"{self.current_mapset.name}_poisson"
        default_name = base_name
        serial = 2
        while (self.project_root_folder / default_name).exists():
            default_name = f"{base_name}_{serial}"
            serial += 1
        name, accepted = QInputDialog.getText(
            self,
            "Save as New MapSet",
            "New MapSet name:",
            text=default_name,
        )
        if not accepted or not name.strip():
            return False

        edited_maps: list[tuple[str, np.ndarray]] = []
        current_path = self.current_image_path.resolve() if self.current_image_path is not None else None
        for map_key, map_path in self.current_mapset.maps:
            resolved = map_path.resolve()
            if current_path is not None and resolved == current_path:
                edited_maps.append((map_key, qimage_to_bgr(self.canvas.pixmap)))
                continue
            stored = self._map_edit_states.get(str(resolved))
            if stored is not None:
                edited_maps.append((map_key, qimage_to_bgr(stored)))

        label_lines = self.canvas.yolo_lines()
        label_text = "\n".join(label_lines) + ("\n" if label_lines else "")
        source_mapset = self.current_mapset
        request = MapSetSaveRequest(
            destination_root=self.project_root_folder,
            mapset_name=name,
            maps=source_mapset.maps,
            edited_maps=tuple(edited_maps),
            label_text=label_text,
        )

        task_id = self._request_worker("save_mapset_copy", {"request": request})
        self._mapset_save_task_id = task_id
        self.buttonSavePoissonMapSet.setEnabled(False)
        self.set_status(f"Saving new MapSet: {name}")

        def apply_saved(saved):
            created = MapSet(
                folder=saved.folder,
                maps=saved.maps,
                label_path=saved.label_path,
                roi_contours=source_mapset.roi_contours,
            )
            self.map_sets = sorted(
                [*self.map_sets, created], key=lambda item: str(item.folder).casefold()
            )
            if self.project is not None:
                self.project.mapsets = self.map_sets
            self._apply_discovered_map_sets(self.map_sets)
            # Label edits were captured in the new MapSet; do not write them back
            # to the source folder while switching to the newly created copy.
            self._labels_modified = False
            for _map_key, source_path in source_mapset.maps:
                self._map_edit_states.pop(str(source_path.resolve()), None)
            self.canvas.mark_clean()
            self._clear_mapset_history()
            self.open_mapset(created)
            if self.project_path is not None:
                self._write_project_manifest(self.project_path, quiet=True)
            self.set_status(f"Saved new MapSet: {created.name}")

        self._task_handlers[task_id] = apply_saved
        return True

    def select_all(self) -> None:
        if self.canvas.pixmap.isNull():
            return
        path = QPainterPath()
        path.addRect(QRectF(self.canvas.pixmap.rect()))
        self.canvas.set_selection(path)

    def delete_selection(self) -> None:
        if not self.canvas.has_selection() or self.canvas.pixmap.isNull():
            return
        if not self.apply_mapset_selection_delete():
            self.canvas._push_undo()
            pixmap = QPixmap(self.canvas.pixmap)
            painter = QPainter(pixmap)
            painter.fillPath(self.canvas.selection_path, QColor("black"))
            painter.end()
            self.canvas.replace_pixmap(pixmap, record_history=False)

    def delete_active_selection(self) -> None:
        """Delete a selected annotation first, otherwise delete selected pixels."""
        if self.canvas.selected_annotation_index >= 0:
            self.remove_annotation(self.canvas.selected_annotation_index)
        else:
            self.delete_selection()

    def auto_roi_selection(self) -> bool:
        """Select an Auto ROI contour on the current canvas without saving it."""
        image = self._current_canvas_image()
        if image is None:
            QMessageBox.warning(self, "Auto ROI", "Open a map before selecting Auto ROI.")
            return False

        contours = roi_contour(image, mode="auto", image_shape=image.shape[:2])
        if not contours:
            QMessageBox.warning(self, "Auto ROI", "Auto ROI contour was not found on the current map.")
            return False

        self._set_canvas_roi_selection(contours)
        self.set_status("Auto ROI selected on current map")
        return True

    def auto_roi_all_mapsets(self) -> bool:
        """Store Auto ROI contours for every loaded MapSet using the current map key."""
        if self.project is None or not self.map_sets:
            QMessageBox.warning(self, "Auto ROI", "Open a dataset folder first.")
            return False

        current_key = self._current_map_key()
        if not current_key:
            QMessageBox.warning(self, "Auto ROI", "Open a map before applying Auto ROI.")
            return False

        created = 0
        failed = 0
        last_current_contours = tuple()
        for map_set in list(self.map_sets):
            image_path = map_set.map_paths.get(current_key)
            if image_path is None:
                failed += 1
                continue

            image = read_image(image_path)
            if image is None:
                failed += 1
                continue

            contours = roi_contour(image, mode="auto", image_shape=image.shape[:2])
            if not contours:
                failed += 1
                get_logger().warning("Auto ROI missing for MapSet: %s", map_set.name)
                continue

            self._update_mapset_roi_contours(map_set, ROI_CONTOUR_KEY, contours)
            if self.current_mapset is not None and self.current_mapset.folder == map_set.folder:
                last_current_contours = contours
            created += 1

        if last_current_contours:
            self._set_canvas_roi_selection(last_current_contours)
        if self.project_path is not None and created:
            self._write_project_manifest(self.project_path, quiet=True)

        self._refresh_augmentation_summary_if_visible()
        self._append_log(f"Auto ROI All MapSets: map={current_key}, created={created}, skipped={failed}")
        self.set_status(f"Auto ROI applied to {created} MapSets, skipped {failed}")
        return created > 0

    def _current_canvas_image(self) -> np.ndarray | None:
        """Return the current canvas image as a BGR array for ROI detection."""
        if self.canvas.pixmap.isNull():
            return None
        image = qimage_to_bgr(self.canvas.pixmap.toImage())
        if image is None or image.size == 0:
            return None
        return image

    def _set_canvas_roi_selection(self, contours) -> None:
        contour = contours[0] if contours else tuple()
        if len(contour) < 3:
            return
        path = QPainterPath()
        first_x, first_y = contour[0]
        path.moveTo(first_x, first_y)
        for point_x, point_y in contour[1:]:
            path.lineTo(point_x, point_y)
        path.closeSubpath()
        self.canvas.set_selection(path)
        self.ui_setup.activate_tool(ToolMode.RECT)

    def export_selection_mask(self) -> None:
        if not self.canvas.has_selection() or self.canvas.pixmap.isNull():
            self.set_status("Select an area before exporting a mask")
            return
        path, _filter = QFileDialog.getSaveFileName(self, "Export Selection Mask", "mask.png", "PNG (*.png)")
        if not path:
            return
        image = QImage(self.canvas.pixmap.size(), QImage.Format.Format_Grayscale8)
        image.fill(0)
        painter = QPainter(image)
        painter.fillPath(self.canvas.selection_path, QColor("white"))
        painter.end()
        if not image.save(path, "PNG"):
            QMessageBox.critical(self, "Export Mask", f"Cannot save mask:\n{path}")

    def start_preprocessing_dialog(self) -> None:
        """Open batch preprocessing options for the current MapSet or all MapSets."""
        if self.canvas.pixmap.isNull():
            QMessageBox.warning(self, "Batch Preprocessing", "Open an image or MapSet first.")
            return
        dialog = BatchPreprocessDialog(
            self.canvas.pixmap.width(),
            self.canvas.pixmap.height(),
            total_mapsets=len(self.map_sets),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        options = dialog.options()
        if not self._preprocess_options_have_work(options):
            self.set_status("No preprocessing option selected")
            return
        try:
            if dialog.target_scope() == "all_mapsets":
                count = self._apply_preprocessing_to_all_mapsets(options)
                self.set_status(f"Batch preprocessing applied to {count} map image(s)")
            elif self.current_mapset is not None:
                count = self._apply_preprocessing_to_current_mapset(options)
                self.set_status(f"Batch preprocessing applied to {count} current MapSet image(s)")
            else:
                self._apply_preprocessing_to_current_image(options)
                self.set_status("Preprocessing applied to current image")
        except Exception as exc:
            QMessageBox.critical(self, "Batch Preprocessing", str(exc))


    def show_resize_dialog(self) -> None:
        """Open resize settings for the current image only."""
        if self.canvas.pixmap.isNull():
            QMessageBox.warning(self, "Resize", "Open an image first.")
            return
        dialog = ResizeDialog(self.canvas.pixmap.width(), self.canvas.pixmap.height(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        options = dialog.options()
        if options.width == self.canvas.pixmap.width() and options.height == self.canvas.pixmap.height():
            self.set_status("Resize skipped: target size equals current size")
            return
        self.apply_transform_options(options)

    def show_rotate_dialog(self) -> None:
        """Open rotation settings and preview changes on the canvas."""
        if self.canvas.pixmap.isNull():
            QMessageBox.warning(self, "Rotate", "Open an image first.")
            return
        self.reset_transform_preview()
        dialog = RotateDialog(self)
        dialog.value_changed.connect(self.update_transform_preview)
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            self.apply_transform_options(dialog.options())
        else:
            self.reset_transform_preview()

    def show_brightness_contrast_dialog(self) -> None:
        """Open brightness and contrast settings and preview changes on the canvas."""
        if self.canvas.pixmap.isNull():
            QMessageBox.warning(self, "Brightness / Contrast", "Open an image first.")
            return
        self.reset_transform_preview()
        dialog = BrightnessContrastDialog(self)
        dialog.value_changed.connect(self.update_transform_preview)
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            self.apply_transform_options(dialog.options())
        else:
            self.reset_transform_preview()

    def apply_fixed_transform(self, kind: str) -> None:
        """Apply one fixed menu transform to the current image immediately."""
        if self.canvas.pixmap.isNull():
            self.set_status("Open an image first")
            return
        if kind == "rotate_180":
            options = PreprocessOptions(rotation_degrees=180.0)
        elif kind == "rotate_90_cw":
            options = PreprocessOptions(rotation_degrees=-90.0)
        elif kind == "rotate_90_ccw":
            options = PreprocessOptions(rotation_degrees=90.0)
        elif kind == "flip_horizontal":
            options = PreprocessOptions(flip_horizontal=True)
        elif kind == "flip_vertical":
            options = PreprocessOptions(flip_vertical=True)
        else:
            return
        self.apply_transform_options(options)

    def update_transform_preview(self, options) -> None:
        """Show a temporary canvas preview for non-resize transform options."""
        if self.canvas.pixmap.isNull():
            return
        preview_options = replace(options, resize_enabled=False)
        if not self._preprocess_options_have_work(preview_options):
            self.canvas.clear_preview_image()
            return
        image = qimage_to_bgr(self.canvas.pixmap)
        result, matrix = self.context.preprocess_api.apply_options(image, preview_options)
        annotations = self._preview_annotations_from_matrix(matrix, result.shape[1], result.shape[0])
        self.canvas.set_preview_image(bgr_to_qpixmap(result), annotations)

    def apply_transform_options(self, options) -> None:
        """Commit transform options to the current MapSet when available."""
        if self.canvas.pixmap.isNull():
            return
        self.canvas.clear_preview_image()
        if not self._preprocess_options_have_work(options):
            self.set_status("No transform option selected")
            return
        if self.current_mapset is not None:
            count = self._apply_preprocessing_to_current_mapset(options)
            status = f"Transform applied to {count} current MapSet image(s)"
        else:
            self._apply_preprocessing_to_current_image(options)
            status = "Transform applied to current image"
        self._labels_modified = True
        self._on_annotations_changed()
        self._refresh_transform_properties()
        self.set_status(status)

    def reset_transform_preview(self) -> None:
        """Cancel temporary transform preview and restore property values."""
        self.canvas.clear_preview_image()
        self._refresh_transform_properties()

    @staticmethod
    def _preprocess_options_have_work(options) -> bool:
        return (
            options.resize_enabled
            or options.flip_horizontal
            or options.flip_vertical
            or abs(options.rotation_degrees) > 1e-6
            or options.brightness_shift != 0
            or getattr(options, "contrast_shift", 0) != 0
        )

    def _apply_preprocessing_to_current_image(self, options) -> None:
        image = qimage_to_bgr(self.canvas.pixmap)
        result, matrix = self.context.preprocess_api.apply_options(image, options)
        self._apply_annotation_affine(matrix, result.shape[1], result.shape[0])
        self.canvas.replace_pixmap(bgr_to_qpixmap(result))
        self.canvas.clear_selection()
        self.canvas.fit_to_window()

    def _apply_preprocessing_to_current_mapset(self, options) -> int:
        self._save_current_map_edit()
        history_before = self._mapset_edit_snapshot(self.current_mapset)
        processed: dict[str, QImage] = {}
        matrix = None
        size = None
        for _map_key, path in self.current_mapset.maps:
            source = self._load_editable_map_image(path)
            if source is None:
                continue
            result, item_matrix = self.context.preprocess_api.apply_options(source, options)
            processed[str(path.resolve())] = bgr_to_qpixmap(result).toImage()
            if matrix is None:
                matrix = item_matrix
                size = (result.shape[1], result.shape[0])
        if not processed or matrix is None or size is None:
            raise ValueError("No MapSet image could be preprocessed.")

        self._push_mapset_history_entry(history_before, processed)
        self._map_edit_states.update(processed)
        current_key = str(self.current_image_path.resolve()) if self.current_image_path is not None else None
        if current_key in processed:
            view_state = self.canvas.view_state()
            self.canvas.set_map_image(processed[current_key], modified=True)
            self.canvas.apply_view_state(*view_state)
            self._update_image_property_panel(self.current_image_path, self.canvas.pixmap)
        self._apply_annotation_affine(matrix, size[0], size[1])
        self.canvas.clear_selection()
        self._labels_modified = True
        self._on_annotations_changed()
        return len(processed)


    def _apply_preprocessing_to_all_mapsets(self, options) -> int:
        """Apply preprocessing to every loaded MapSet image in memory."""
        if not self.map_sets:
            raise ValueError("Open a dataset folder first.")
        self._save_current_map_edit()
        history_before = self._mapset_edit_snapshot(self.current_mapset) if self.current_mapset is not None else None
        count = 0
        active_matrix = None
        active_size = None
        active_processed: dict[str, QImage] = {}
        for map_set in self.map_sets:
            for _map_key, path in map_set.maps:
                source = self._load_editable_map_image(path)
                if source is None:
                    continue
                result, matrix = self.context.preprocess_api.apply_options(source, options)
                image = bgr_to_qpixmap(result).toImage()
                self._map_edit_states[str(path.resolve())] = image
                count += 1
                if map_set is self.current_mapset:
                    active_matrix = matrix
                    active_size = (result.shape[1], result.shape[0])
                    active_processed[str(path.resolve())] = image
        if count == 0:
            raise ValueError("No MapSet image could be preprocessed.")
        self._push_mapset_history_entry(history_before, active_processed)
        current_key = str(self.current_image_path.resolve()) if self.current_image_path is not None else None
        if current_key in active_processed:
            view_state = self.canvas.view_state()
            self.canvas.set_map_image(active_processed[current_key], modified=True)
            self.canvas.apply_view_state(*view_state)
            self._update_image_property_panel(self.current_image_path, self.canvas.pixmap)
        if active_matrix is not None and active_size is not None:
            self._apply_annotation_affine(active_matrix, active_size[0], active_size[1])
            self._labels_modified = True
            self._on_annotations_changed()
        self.canvas.clear_selection()
        return count

    def _load_editable_map_image(self, path: Path) -> np.ndarray | None:
        stored = self._map_edit_states.get(str(path.resolve()))
        if stored is not None:
            return qimage_to_bgr(stored)
        return read_image(path)


    def _preview_annotations_from_matrix(self, matrix: np.ndarray, width: int, height: int) -> list[CanvasAnnotation]:
        """Return transformed annotations for temporary canvas preview."""
        annotations = []
        for annotation in self.canvas.annotations:
            box = self._transform_rect(annotation.bounds, matrix, width, height)
            if box is None:
                continue
            annotations.append(CanvasAnnotation(annotation.class_id, box, annotation.class_name))
        return annotations

    def _apply_annotation_affine(self, matrix: np.ndarray, width: int, height: int) -> None:
        annotations = []
        for annotation in self.canvas.annotations:
            box = self._transform_rect(annotation.bounds, matrix, width, height)
            if box is None:
                continue
            annotations.append(CanvasAnnotation(annotation.class_id, box, annotation.class_name))
        self.canvas.annotations = annotations
        self.canvas.selected_annotation_index = -1
        self.canvas.update()

    @staticmethod
    def _transform_rect(rect: QRectF, matrix: np.ndarray, width: int, height: int) -> QRectF | None:
        points = np.array(
            [
                [rect.left(), rect.top(), 1.0],
                [rect.right(), rect.top(), 1.0],
                [rect.right(), rect.bottom(), 1.0],
                [rect.left(), rect.bottom(), 1.0],
            ],
            dtype=np.float32,
        ).T
        transformed = matrix @ points
        x1 = float(np.clip(transformed[0].min(), 0.0, float(width)))
        y1 = float(np.clip(transformed[1].min(), 0.0, float(height)))
        x2 = float(np.clip(transformed[0].max(), 0.0, float(width)))
        y2 = float(np.clip(transformed[1].max(), 0.0, float(height)))
        if x2 <= x1 or y2 <= y1:
            return None
        return QRectF(x1, y1, x2 - x1, y2 - y1)

    def set_current_selection_as_placement_mask(self) -> None:
        """Store the active selection contour for AutoAugment ROI placement."""
        if self.current_mapset is None or self.current_image_path is None or not self.canvas.has_selection():
            self.set_status("No selection available for ROI contour")
            return
        contours = self._selection_contours_from_canvas()
        if not contours:
            QMessageBox.warning(self, "ROI Contour", "The current selection cannot be converted to a contour.")
            return
        self.current_mapset = self._update_mapset_roi_contours(self.current_mapset, ROI_CONTOUR_KEY, contours)
        self._refresh_augmentation_summary_if_visible()
        self.set_status(f"Stored ROI contour for {self.current_mapset.name}")

    def _refresh_augmentation_summary_if_visible(self) -> None:
        page = getattr(self, "augmentation_page", None)
        if page is not None and hasattr(page, "refresh_project_data"):
            try:
                page.refresh_project_data()
            except Exception:
                pass

    def clear_current_placement_mask(self) -> None:
        """Remove the current map ROI contour from the active MapSet state."""
        if self.current_mapset is None:
            return
        self.current_mapset = self._update_mapset_roi_contours(self.current_mapset, ROI_CONTOUR_KEY, tuple())
        self._refresh_augmentation_summary_if_visible()
        self.set_status(f"Cleared ROI contour for {self.current_mapset.name}")

    def _current_map_key(self) -> str | None:
        index = self.map_switch_tabs.currentIndex() if hasattr(self, "map_switch_tabs") else -1
        data = self.map_switch_tabs.tabData(index) if index >= 0 else None
        if data:
            return str(data[0])
        if self.current_mapset is None or self.current_image_path is None:
            return None
        current = self.current_image_path.resolve()
        for key, path in self.current_mapset.maps:
            if path.resolve() == current:
                return key
        return None

    def _selection_contours_from_canvas(self) -> tuple[tuple[tuple[float, float], ...], ...]:
        polygon = self.canvas.selection_path.toFillPolygon()
        points = [(float(point.x()), float(point.y())) for point in polygon]
        if len(points) < 3:
            bounds = self.canvas.selection_bounds().intersected(QRectF(self.canvas.pixmap.rect()))
            if bounds.isEmpty():
                return tuple()
            points = [
                (float(bounds.left()), float(bounds.top())),
                (float(bounds.right()), float(bounds.top())),
                (float(bounds.right()), float(bounds.bottom())),
                (float(bounds.left()), float(bounds.bottom())),
            ]
        return roi_contour(
            (tuple(points),),
            mode="selection",
            image_shape=(self.canvas.pixmap.height(), self.canvas.pixmap.width()),
        )

    def _update_mapset_roi_contours(self, map_set: MapSet, map_key: str, contours) -> MapSet:
        contour_map = dict(getattr(map_set, "roi_contours", ()) or ())
        normalized = roi_contour(contours, mode="selection")
        if normalized:
            contour_map[map_key] = normalized
        else:
            contour_map.pop(map_key, None)

        updated = replace(map_set, roi_contours=tuple(sorted(contour_map.items(), key=lambda item: item[0])))
        for index, item in enumerate(self.map_sets):
            if item.folder == map_set.folder:
                self.map_sets[index] = updated
                break
        if self.project is not None:
            for index, item in enumerate(self.project.mapsets):
                if item.folder == map_set.folder:
                    self.project.mapsets[index] = updated
                    break
        if self.current_mapset is not None and self.current_mapset.folder == map_set.folder:
            self.current_mapset = updated
        self._replace_project_tree_mapset(updated)
        self._update_mapset_property_panel(updated)
        return updated

    def _refresh_current_project_tree_item(self) -> None:
        if self.current_mapset is not None:
            self._replace_project_tree_mapset(self.current_mapset)

    def _replace_project_tree_mapset(self, updated: MapSet) -> None:
        tree = getattr(self, "treeProject", None)
        if not isinstance(tree, QTreeWidget):
            return
        stack = [tree.topLevelItem(index) for index in range(tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item is None:
                continue
            value = item.data(0, self.MAPSET_ROLE)
            if isinstance(value, MapSet) and value.folder == updated.folder:
                self._replace_project_tree_item(item, updated)
                return
            stack.extend(item.child(index) for index in range(item.childCount()))

    def _replace_project_tree_item(self, item: QTreeWidgetItem, updated: MapSet) -> None:
        tree = getattr(self, "treeProject", None)
        if not isinstance(tree, QTreeWidget):
            return

        selected_item = tree.currentItem()
        selected_path = self._project_tree_item_path(selected_item)
        selected_in_mapset = self._project_tree_item_belongs_to_mapset(selected_item, updated)
        replacement = self._create_mapset_item(updated)
        replacement.setExpanded(item.isExpanded())

        parent = item.parent()
        if parent is not None:
            index = parent.indexOfChild(item)
            parent.takeChild(index)
            parent.insertChild(index, replacement)
        else:
            index = tree.indexOfTopLevelItem(item)
            tree.takeTopLevelItem(index)
            tree.insertTopLevelItem(index, replacement)

        if selected_in_mapset:
            tree.setCurrentItem(
                self._find_project_tree_item_by_path(replacement, selected_path) or replacement
            )
        tree.resizeColumnToContents(0)

    def _project_tree_item_path(self, item: QTreeWidgetItem | None) -> str | None:
        if item is None:
            return None
        path = item.data(0, self.PATH_ROLE)
        return str(path) if path else None

    def _project_tree_item_belongs_to_mapset(
        self,
        item: QTreeWidgetItem | None,
        map_set: MapSet,
    ) -> bool:
        current = item
        while current is not None:
            value = current.data(0, self.MAPSET_ROLE)
            if isinstance(value, MapSet) and value.folder == map_set.folder:
                return True
            current = current.parent()
        return False

    def _find_project_tree_item_by_path(
        self,
        root: QTreeWidgetItem,
        path: str | None,
    ) -> QTreeWidgetItem | None:
        if path is None:
            return None
        if self._project_tree_item_path(root) == path:
            return root
        for index in range(root.childCount()):
            found = self._find_project_tree_item_by_path(root.child(index), path)
            if found is not None:
                return found
        return None

    def _mapset_roi_contours_payload(self, map_set: MapSet) -> dict:
        return {
            key: [
                [[float(x), float(y)] for x, y in contour]
                for contour in contours
            ]
            for key, contours in getattr(map_set, "roi_contours", ())
        }

    def _apply_project_mapsets_to_discovery(self, map_sets: list[MapSet], payload: dict) -> list[MapSet]:
        """Restore saved MapSets and map-key subsets from the project manifest."""
        saved: dict[str, set[str]] = {}
        for item in payload.get("mapsets", []):
            if not isinstance(item, dict):
                continue
            folder = item.get("folder")
            maps = item.get("maps")
            if not folder:
                continue
            if isinstance(maps, dict):
                keys = {str(key) for key in maps}
            elif isinstance(maps, list):
                keys = {str(entry[0]) for entry in maps if isinstance(entry, (list, tuple)) and entry}
            else:
                keys = set()
            saved[str(Path(folder).resolve())] = keys

        if not saved:
            return map_sets

        restored = []
        for map_set in map_sets:
            keys = saved.get(str(map_set.folder.resolve()))
            if keys is None:
                continue
            if keys:
                maps = tuple((key, path) for key, path in map_set.maps if key in keys)
                if maps:
                    restored.append(replace(map_set, maps=maps))
            else:
                restored.append(map_set)
        return restored

    def _apply_project_roi_contours_to_mapsets(self, map_sets: list[MapSet], payload: dict) -> list[MapSet]:
        saved = {}
        for item in payload.get("mapsets", []):
            if not isinstance(item, dict):
                continue
            folder = item.get("folder")
            if not folder:
                continue
            saved[str(Path(folder).resolve())] = item.get("roi_contours", {}) or {}
        restored = []
        for map_set in map_sets:
            contours_payload = saved.get(str(map_set.folder.resolve()), {})
            valid_keys = set(map_set.map_paths) | {ROI_CONTOUR_KEY}
            entries = []
            for key, contours in contours_payload.items():
                if key not in valid_keys:
                    continue
                parsed_contours = []
                for contour in contours or []:
                    points = []
                    for point in contour or []:
                        if isinstance(point, (list, tuple)) and len(point) >= 2:
                            points.append((float(point[0]), float(point[1])))
                    if len(points) >= 3:
                        parsed_contours.append(tuple(points))
                if parsed_contours:
                    entries.append((key, tuple(parsed_contours)))
            restored.append(replace(map_set, roi_contours=tuple(sorted(entries, key=lambda item: item[0]))))
        return restored

    def _ensure_missing_roi_contours(self, target_map_key: str) -> int:
        if self.project is None:
            return 0
        created = 0
        failed = 0
        for map_set in list(self.map_sets):
            if map_set.roi_contour:
                continue
            image_path = map_set.map_paths.get(target_map_key) or map_set.reference_path
            image = read_image(image_path)
            if image is None:
                failed += 1
                continue
            contours = roi_contour(image, mode="auto", image_shape=image.shape[:2])
            if not contours:
                failed += 1
                get_logger().warning("Auto ROI missing for MapSet: %s", map_set.name)
                continue
            self._update_mapset_roi_contours(map_set, ROI_CONTOUR_KEY, contours)
            created += 1
        if created and self.project_path is not None:
            self._write_project_manifest(self.project_path, quiet=True)
        if created or failed:
            self._append_log(f"Auto ROI prepared: created={created}, skipped={failed}")
        return created

    def export_selected_defect(self) -> None:
        if self.current_mapset is None or not self.canvas.has_selection():
            self.set_status("Open a MapSet and select an area first")
            return
        defect_name, accepted = QInputDialog.getText(self, "Export Defect", "Defect name:")
        defect_name = safe_defect_name(defect_name) if accepted else ""
        if not defect_name:
            return
        map_paths = tuple((key, str(path)) for key, path in self.current_mapset.maps)
        selection = QPainterPath(self.canvas.selection_path)
        bounds = selection.boundingRect().toAlignedRect()
        output_root = (self.project_root_folder or Path.cwd()) / "exports" / "defects"

        task_id = self._request_worker(
            "export_defect",
            {
                "map_paths": map_paths,
                "output_root": output_root,
                "defect_name": defect_name,
                "selection": selection,
                "bounds": QRect(bounds),
            },
        )
        self._task_handlers[task_id] = lambda result: QMessageBox.information(
            self, "Export Defect", f"Saved to:\n{result}"
        )

    def _on_task_succeeded(self, task_id: str, result) -> None:
        handler = self._task_handlers.pop(task_id, None)
        if handler is not None:
            handler(result)

    def _on_task_failed(self, task_id: str, message: str, traceback_text: str) -> None:
        self._task_handlers.pop(task_id, None)
        get_logger().error("Background task failed: %s\n%s", message, traceback_text)
        append_crash_report(f"Background task failed: {message}", traceback_text)
        self._append_log(f"Task failed: {message}")
        if task_id == self._auto_augment_task_id and hasattr(self, "augmentation_page"):
            self.augmentation_page.fail_autoaugment_progress(message)
        if task_id == self._manual_poisson_task_id:
            self.set_status(f"Poisson failed: {message}")
        if task_id == self._healing_task_id:
            self._restore_healing_preview_after_task()
            self.set_status(f"Healing Brush failed: {message}")
        if task_id == self._mapset_save_task_id:
            self.set_status(f"MapSet save failed: {message}")
        if task_id == self._mapset_update_task_id:
            self.set_status(f"Current MapSet save failed: {message}")
        if task_id == self._save_all_task_id:
            self.set_status(f"Save All failed: {message}")
        QMessageBox.critical(self, "Background Task Failed", message)

    def _on_task_cancelled(self, task_id: str) -> None:
        """Handle cooperative cancellation from a background task."""
        self._task_handlers.pop(task_id, None)
        if task_id == self._auto_augment_task_id:
            self._append_log("AutoAugment cancelled")
            self.set_status("AutoAugment cancelled")
            if hasattr(self, "augmentation_page"):
                self.augmentation_page.cancel_autoaugment_progress()
        if task_id == self._healing_task_id:
            self._restore_healing_preview_after_task()
            self.set_status("Healing Brush cancelled")
        if task_id == self._save_all_task_id:
            self.set_status("Save All cancelled")

    def _on_task_finished(self, task_id: str) -> None:
        """Release shared task state after Qt confirms task shutdown."""
        self._active_task_ids.discard(task_id)
        get_logger().info("Task finished: %s", task_id)
        if task_id == self._auto_augment_task_id:
            self._auto_augment_task_id = None
            if hasattr(self, "augmentation_page"):
                self.augmentation_page.set_autoaugment_running(False)
        if task_id == self._manual_poisson_task_id:
            self._manual_poisson_task_id = None
            self.ui_setup.set_manual_poisson_running(False)
        if task_id == self._healing_task_id:
            self._healing_task_id = None
            self._healing_restore_images = None
        if task_id == self._mapset_save_task_id:
            self._mapset_save_task_id = None
            if hasattr(self, "buttonSavePoissonMapSet"):
                self.buttonSavePoissonMapSet.setEnabled(True)
        if task_id == self._mapset_update_task_id:
            self._mapset_update_task_id = None
        if task_id == self._save_all_task_id:
            self._save_all_task_id = None


    def _refresh_transform_properties(self) -> None:
        """Refresh current-image transform metadata in the Properties dock."""
        panel = getattr(self, "transform_properties", None)
        if panel is None or self.canvas.pixmap.isNull():
            return
        mapset_name = self.current_mapset.name if self.current_mapset is not None else "-"
        map_name = "-"
        if getattr(self, "map_switch_tabs", None) is not None and self.map_switch_tabs.isVisible():
            map_name = self.map_switch_tabs.tabText(self.map_switch_tabs.currentIndex())
        elif self.current_image_path is not None:
            map_name = self.current_image_path.stem
        state = "Unsaved" if self.canvas.is_modified or self._labels_modified else "Saved"
        panel.set_image_info(
            mapset_name,
            map_name,
            self.canvas.pixmap.width(),
            self.canvas.pixmap.height(),
            len(self.canvas.annotations),
            state,
        )

    def _update_image_property_panel(self, path: Path, pixmap: QPixmap) -> None:
        if hasattr(self, "label_info_file_value"):
            self.label_info_file_value.setText(path.name)
        if hasattr(self, "label_info_size_value"):
            self.label_info_size_value.setText(f"{pixmap.width()} x {pixmap.height()}")
        if hasattr(self, "label_info_zoom_value"):
            self.label_info_zoom_value.setText(f"{self.canvas.zoom * 100:.0f}%")
        if hasattr(self, "label_info_modified_value"):
            self.label_info_modified_value.setText("No")
        self._refresh_transform_properties()
        if hasattr(self, "label_property_title"):
            self.label_property_title.setText(path.name)
        if hasattr(self, "label_property_subtitle"):
            self.label_property_subtitle.setText(str(path.parent))
        self._refresh_transform_properties()

    def _update_mapset_property_panel(self, map_set: MapSet) -> None:
        if hasattr(self, "label_property_title"):
            self.label_property_title.setText(map_set.name)
        if hasattr(self, "label_property_subtitle"):
            self.label_property_subtitle.setText(
                f"{len(map_set.maps)} map(s), {self._mapset_label_count(map_set)} label(s)"
            )
        if hasattr(self, "label_info_file_value"):
            self.label_info_file_value.setText(map_set.name)
        if hasattr(self, "label_info_modified_value"):
            self.label_info_modified_value.setText("No")
        self._refresh_transform_properties()

    def _icon(self, icon_name: str) -> QIcon:
        base = Path(__file__).resolve().parents[1]
        for path in (base / "assets" / "icons" / icon_name, base / "assets" / icon_name):
            if path.exists():
                source = QIcon(str(path)).pixmap(20, 20)
                if source.isNull():
                    return QIcon(str(path))
                themed = QPixmap(source.size())
                themed.fill(Qt.GlobalColor.transparent)
                painter = QPainter(themed)
                painter.drawPixmap(0, 0, source)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                painter.fillRect(themed.rect(), QColor(theme_colors(getattr(self, "current_theme", "dark"))["icon"]))
                painter.end()
                return QIcon(themed)
        return QIcon()

    def _set_tree_item_icon(self, item: QTreeWidgetItem, icon_name: str) -> None:
        item.setData(0, self.ICON_ROLE, icon_name)
        item.setIcon(0, self._icon(icon_name))

    def _refresh_project_tree_icons(self) -> None:
        tree = getattr(self, "treeProject", None)
        if not isinstance(tree, QTreeWidget):
            return

        def refresh(item: QTreeWidgetItem) -> None:
            icon_name = item.data(0, self.ICON_ROLE)
            if icon_name:
                item.setIcon(0, self._icon(str(icon_name)))
            for index in range(item.childCount()):
                refresh(item.child(index))

        for index in range(tree.topLevelItemCount()):
            refresh(tree.topLevelItem(index))

    def export_yolo_dataset(self) -> None:
        from ui.exportdialog import ExportDialog

        if not self._save_current_yolo_labels_if_needed():
            return
        dialog = ExportDialog(self.context.export_api, self)
        dialog.exec()

    def start_yolo_export(self, options) -> None:
        """Run YOLO export on an owned worker with cooperative cancellation."""
        if self.project is None:
            QMessageBox.warning(self, "Export YOLO Dataset", "Open a dataset folder first.")
            return
        if not self._save_current_yolo_labels_if_needed():
            return

        task_id = self._request_worker(
            "yolo_export",
            {"mapsets": self.project.mapsets, "options": options},
        )
        self._task_handlers[task_id] = lambda result: QMessageBox.information(
            self,
            "Export Complete",
            f"Exported images: {result.get('images', 0)}\n"
            f"Exported labels: {result.get('labels', 0)}",
        )

    def start_augmentation_preview(self, options) -> None:
        if self.project is None:
            QMessageBox.warning(self, "Auto Augmentation", "Open a dataset folder first.")
            return
        defect_paths = self.context.augmentation_api.discover_defect_paths(options.defect_root)
        target_paths = [item.reference_path for item in self.project.mapsets]
        if not defect_paths or not target_paths:
            QMessageBox.warning(self, "Auto Augmentation", "No defect patches or target MapSets were found.")
            return
        pairs = [
            (defect_paths[index % len(defect_paths)], target_paths[index % len(target_paths)])
            for index in range(options.preview_count)
        ]

        task_id = self._request_worker(
            "augmentation_preview",
            {"pairs": pairs, "options": options},
        )

        def show(previews):
            if previews:
                self.augmentation_page.set_preview_image(bgr_to_qpixmap(previews[0].result_image))

        self._task_handlers[task_id] = show

    def is_auto_augmentation_running(self) -> bool:
        """Return whether the app still owns the AutoAugment worker."""
        return self._auto_augment_task_id in self._active_task_ids

    def cancel_auto_augmentation(self) -> None:
        """Request cancellation for the active AutoAugment worker."""
        task_id = self._auto_augment_task_id
        if task_id is None or task_id not in self._active_task_ids:
            return
        self.task_cancel_requested.emit(task_id)
        self._append_log("AutoAugment cancellation requested")
        self.set_status("AutoAugment cancellation requested")
        if hasattr(self, "augmentation_page"):
            self.augmentation_page.show_autoaugment_cancelling()

    def start_auto_augmentation(self, options) -> None:
        """Run selected-map AutoAugment in a background worker."""
        if self.project is None:
            QMessageBox.warning(self, "Auto Augmentation", "Open a dataset folder first.")
            return
        if self.is_auto_augmentation_running():
            self.augmentation_page.set_autoaugment_running(True)
            QMessageBox.information(self, "Auto Augmentation", "AutoAugment is already running.")
            return
        self._refresh_augmentation_summary_if_visible()
        self._append_log("0% AutoAugment queued")
        self.augmentation_page.begin_autoaugment_progress(options.output_root)

        task_id = self._request_worker(
            "auto_augment",
            {"project": self.project, "options": options},
        )
        get_logger().info("Task started: AutoAugment %s", task_id)
        self._auto_augment_task_id = task_id
        self.augmentation_page.set_autoaugment_running(True)

        def show(result):
            self._append_log("100% AutoAugment complete")
            if hasattr(self, "augmentation_page"):
                self.augmentation_page.refresh_project_data()
                self.augmentation_page.complete_autoaugment_progress(result)
            self.set_status(
                f"AutoAugment complete: {result.get('images', 0)} images, "
                f"{result.get('annotations', 0)} annotations"
            )

        self._task_handlers[task_id] = show

    def start_orientation_augmentation(self, options) -> None:
        if self.project is None:
            QMessageBox.warning(self, "Orientation Augmentation", "Open a dataset folder first.")
            return

        task_id = self._request_worker(
            "orientation_augment",
            {"mapsets": self.project.mapsets, "options": options},
        )
        self._task_handlers[task_id] = lambda result: QMessageBox.information(
            self,
            "Orientation Augmentation",
            f"Generated samples: {result.get('samples', 0)}\n{result.get('output_root', '')}",
        )

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self,
            "Confirm Exit",
            "Do you want to exit Dataset Editor?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.set_status("Waiting for background tasks to stop...")
            self._shutdown_succeeded = False
            self.shutdown_requested.emit(30000)
            if self._shutdown_succeeded:
                event.accept()
            else:
                QMessageBox.critical(
                    self,
                    "Tasks Still Running",
                    "Dataset Editor could not stop every background task. "
                    "The window will remain open to avoid destroying a running thread.",
                )
                event.ignore()
        else:
            event.ignore()
