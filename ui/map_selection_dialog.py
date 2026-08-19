"""Dialog for selecting which detected map keys are loaded into a project.

Author: TNS AI
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
	QCheckBox,
	QDialog,
	QDialogButtonBox,
	QHBoxLayout,
	QLabel,
	QPushButton,
	QScrollArea,
	QVBoxLayout,
	QWidget,
)


class MapSelectionDialog(QDialog):
	"""Let the user choose detected map keys before loading MapSets."""

	def __init__(self, map_counts: dict[str, int], parent=None):
		super().__init__(parent)
		self.setWindowTitle("Select Maps to Load")
		self.resize(420, 520)
		self._checks: dict[str, QCheckBox] = {}
		layout = QVBoxLayout(self)

		description = QLabel("Select the maps to load from the detected MapSets.", self)
		description.setWordWrap(True)
		layout.addWidget(description)

		scroll = QScrollArea(self)
		scroll.setWidgetResizable(True)
		content = QWidget(scroll)
		content_layout = QVBoxLayout(content)
		for map_key, count in sorted(map_counts.items(), key=lambda item: item[0].casefold()):
			check = QCheckBox(f"{map_key}  ({count})", content)
			check.setChecked(True)
			check.setProperty("map_key", map_key)
			self._checks[map_key] = check
			content_layout.addWidget(check)
		content_layout.addStretch(1)
		scroll.setWidget(content)
		layout.addWidget(scroll, 1)

		button_row = QHBoxLayout()
		select_all = QPushButton("Select All", self)
		clear_all = QPushButton("Clear All", self)
		select_all.clicked.connect(lambda: self._set_all_checked(True))
		clear_all.clicked.connect(lambda: self._set_all_checked(False))
		button_row.addWidget(select_all)
		button_row.addWidget(clear_all)
		button_row.addStretch(1)
		layout.addLayout(button_row)

		buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
		buttons.accepted.connect(self.accept)
		buttons.rejected.connect(self.reject)
		layout.addWidget(buttons)

	def selected_map_keys(self) -> set[str]:
		"""Return checked map keys."""
		return {
			map_key
			for map_key, check in self._checks.items()
			if check.checkState() == Qt.CheckState.Checked
		}

	def accept(self) -> None:
		"""Accept only when at least one map key is selected."""
		if not self.selected_map_keys():
			return
		super().accept()

	def _set_all_checked(self, checked: bool) -> None:
		for check in self._checks.values():
			check.setChecked(checked)
