from pathlib import Path


def test_save_labels_action_is_in_file_menu_and_connected():
	text = Path("ui/uisetup.py").read_text(encoding="utf-8")
	assert "action_save_labels" in text
	assert "Save Labels" in text
	assert "self.window.save_current_yolo_labels" in text
