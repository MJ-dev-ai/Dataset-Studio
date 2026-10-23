"""Dialog for selecting detected map keys before loading."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
from ui.themes import configure_dialog


class MapSetSelectionDialog(QDialog):
	"""Let the user choose which detected map keys should be loaded."""

	def __init__(self, map_counts: dict[str, int], parent=None):
		super().__init__(parent)
		self.setWindowTitle("불러올 맵 선택")
		self.resize(360, 420)
		self._checks: dict[str, QCheckBox] = {}

		layout = QVBoxLayout(self)
		description = QLabel("불러올 맵 종류를 선택하세요. 괄호 안은 발견된 이미지 수입니다.", self)
		description.setWordWrap(True)
		layout.addWidget(description)

		scroll = QScrollArea(self)
		scroll.setWidgetResizable(True)
		content = QWidget(scroll)
		content_layout = QVBoxLayout(content)

		for map_key, count in sorted(map_counts.items(), key=lambda item: item[0].casefold()):
			check = QCheckBox(f"{map_key}  ({count})", content)
			check.setChecked(True)
			self._checks[map_key] = check
			content_layout.addWidget(check)

		content_layout.addStretch(1)
		scroll.setWidget(content)
		layout.addWidget(scroll, 1)

		quick_layout = QHBoxLayout()
		select_all = QPushButton("전체 선택", self)
		clear_all = QPushButton("전체 해제", self)
		select_all.clicked.connect(lambda: self._set_all_checked(True))
		clear_all.clicked.connect(lambda: self._set_all_checked(False))
		quick_layout.addWidget(select_all)
		quick_layout.addWidget(clear_all)
		quick_layout.addStretch(1)
		layout.addLayout(quick_layout)

		buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
		buttons.accepted.connect(self.accept)
		buttons.rejected.connect(self.reject)
		layout.addWidget(buttons)
		self.buttons = buttons
		self.selection_hint = QLabel(self)
		layout.insertWidget(layout.count() - 1, self.selection_hint)
		for check in self._checks.values():
			check.toggled.connect(self._update_selection_state)
		self._update_selection_state()
		configure_dialog(self, 440, "불러오기")

	def _update_selection_state(self) -> None:
		"""Keep confirmation disabled and explain why when no map is selected."""
		count = len(self.selected_map_keys())
		self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(count > 0)
		self.selection_hint.setText(f"{count}개 맵 종류 선택" if count else "하나 이상의 맵을 선택하세요.")

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
