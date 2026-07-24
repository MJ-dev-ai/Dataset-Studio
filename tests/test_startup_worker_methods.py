from pathlib import Path


def test_mainwindow_has_worker_progress_methods_and_valid_stack_page():
	text = Path("ui/mainwindow.py").read_text(encoding="utf-8")
	assert "def _setup_log_console" in text
	assert "def _on_task_progress" in text
	assert "task_progress.connect(self._on_task_progress)" in text
	assert "stack.setCurrentWidget(self.editor_page)" in text
	assert "stack.setCurrentWidget(self.canvas)" not in text
