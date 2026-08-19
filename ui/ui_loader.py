from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile, QObject, Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QDialog, QDockWidget, QMainWindow, QToolBar, QVBoxLayout


def load_ui(path: str | Path, base_instance) -> None:
	if isinstance(base_instance, QMainWindow):
		_load_main_window_ui(path, base_instance)
		return
	if isinstance(base_instance, QDialog):
		_load_dialog_ui(path, base_instance)
		return
	ui_file = QFile(str(path))
	if not ui_file.open(QFile.OpenModeFlag.ReadOnly):
		raise OSError(f"Failed to open UI file: {path}")
	try:
		loader = QUiLoader(base_instance)
		loaded_widget = loader.load(ui_file)
		if loaded_widget is None:
			raise RuntimeError(f"Failed to load UI file: {path}")
		base_instance.loaded_widget = loaded_widget
		_bind_named_objects(base_instance, loaded_widget)
	finally:
		ui_file.close()


def _load_main_window_ui(path: str | Path, base_instance: QMainWindow) -> None:
	ui_file = QFile(str(path))
	if not ui_file.open(QFile.OpenModeFlag.ReadOnly):
		raise OSError(f"Failed to open UI file: {path}")
	try:
		loader = QUiLoader(base_instance)
		loaded_window = loader.load(ui_file)
		if loaded_window is None:
			raise RuntimeError(f"Failed to load UI file: {path}")
	finally:
		ui_file.close()

	actions = tuple(loaded_window.findChildren(QAction))
	action_groups = tuple(loaded_window.findChildren(QActionGroup))

	base_instance.loaded_window = loaded_window
	base_instance.setObjectName(loaded_window.objectName())
	base_instance.setStyleSheet(loaded_window.styleSheet())
	base_instance.setWindowTitle(loaded_window.windowTitle())
	base_instance.resize(loaded_window.size())

	central_widget = loaded_window.takeCentralWidget()
	if central_widget is not None:
		base_instance.setCentralWidget(central_widget)
	if loaded_window.menuBar() is not None:
		base_instance.setMenuBar(loaded_window.menuBar())
	if loaded_window.statusBar() is not None:
		base_instance.setStatusBar(loaded_window.statusBar())
	for tool_bar in loaded_window.findChildren(QToolBar):
		base_instance.addToolBar(tool_bar)
	for dock_widget in loaded_window.findChildren(QDockWidget):
		base_instance.addDockWidget(loaded_window.dockWidgetArea(dock_widget), dock_widget)
	_bind_named_objects(base_instance, base_instance)
	for action in actions:
		if action.objectName():
			setattr(base_instance, action.objectName(), action)
	for group in action_groups:
		if group.objectName():
			setattr(base_instance, group.objectName(), group)
	base_instance._ui_loader_actions = actions
	base_instance._ui_loader_action_groups = action_groups


def _load_dialog_ui(path: str | Path, base_instance: QDialog) -> None:
	ui_file = QFile(str(path))
	if not ui_file.open(QFile.OpenModeFlag.ReadOnly):
		raise OSError(f"Failed to open UI file: {path}")
	try:
		loader = QUiLoader(base_instance)
		loaded_dialog = loader.load(ui_file)
		if loaded_dialog is None:
			raise RuntimeError(f"Failed to load UI file: {path}")
	finally:
		ui_file.close()

	base_instance.loaded_dialog = loaded_dialog
	base_instance.setObjectName(loaded_dialog.objectName())
	base_instance.setStyleSheet(loaded_dialog.styleSheet())
	base_instance.setWindowTitle(loaded_dialog.windowTitle())
	base_instance.resize(loaded_dialog.size())
	base_instance.setMinimumSize(loaded_dialog.minimumSize())

	loaded_dialog.setParent(base_instance)
	loaded_dialog.setWindowFlags(Qt.WindowType.Widget)
	layout = QVBoxLayout(base_instance)
	layout.setContentsMargins(0, 0, 0, 0)
	layout.setSpacing(0)
	layout.addWidget(loaded_dialog)
	_bind_named_objects(base_instance, loaded_dialog)


def _bind_named_objects(base_instance, *roots) -> None:
	seen = set()
	for root in roots:
		if root is None:
			continue
		for obj in root.findChildren(QObject):
			if id(obj) in seen:
				continue
			seen.add(id(obj))
			name = obj.objectName()
			if name:
				setattr(base_instance, name, obj)
