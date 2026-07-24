from pathlib import Path


def test_save_all_action_is_in_file_menu_and_connected():
    ui_setup = Path("ui/uisetup.py").read_text(encoding="utf-8")
    mainwindow = Path("ui/mainwindow.py").read_text(encoding="utf-8")

    assert "action_save_all" in ui_setup
    assert "Save All" in ui_setup
    assert "self.window.save_all" in ui_setup
    assert "def save_all" in mainwindow
