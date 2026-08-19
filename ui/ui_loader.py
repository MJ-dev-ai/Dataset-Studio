from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtGui import QAction
from PySide6.QtUiTools import QUiLoader


class _UiLoader(QUiLoader):
	def __init__(self, base_instance):
		super().__init__(base_instance)
		self.base_instance = base_instance

	def createWidget(self, class_name, parent=None, name=""):
		widget = self.base_instance if parent is None else super().createWidget(class_name, parent, name)
		if name:
			widget.setObjectName(name)
			setattr(self.base_instance, name, widget)
		return widget


def load_ui(path: str | Path, base_instance) -> None:
	ui_file = QFile(str(path))
	if not ui_file.open(QFile.OpenModeFlag.ReadOnly):
		raise OSError(f"Failed to open UI file: {path}")
	try:
		loader = _UiLoader(base_instance)
		if loader.load(ui_file, base_instance) is None:
			raise RuntimeError(f"Failed to load UI file: {path}")
		for action in base_instance.findChildren(QAction):
			if action.objectName():
				setattr(base_instance, action.objectName(), action)
	finally:
		ui_file.close()
