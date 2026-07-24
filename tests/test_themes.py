import pytest
import re

from ui.themes import theme_colors, theme_stylesheet


def test_both_themes_define_text_and_selection_contrast():
    for name in ("dark", "light"):
        stylesheet = theme_stylesheet(name)
        assert "color:" in stylesheet
        assert "selection-background-color" in stylesheet
    assert theme_colors("dark")["icon"] != theme_colors("light")["icon"]
    assert theme_colors("dark")["canvas"] != theme_colors("light")["canvas"]


def test_theme_switch_changes_colors_not_widget_geometry():
    color_pattern = re.compile(r"#[0-9A-Fa-f]{6}")
    dark_shape = color_pattern.sub("#COLOR", theme_stylesheet("dark")).replace("-light.svg", ".svg")
    light_shape = color_pattern.sub("#COLOR", theme_stylesheet("light"))
    assert dark_shape == light_shape


def test_input_controls_render_direction_arrows():
    stylesheet = theme_stylesheet("light")
    assert "QSpinBox::up-arrow" in stylesheet
    assert "QSpinBox::down-arrow" in stylesheet
    assert "QComboBox::down-arrow" in stylesheet
    assert "chevron-up-accent.svg" in stylesheet


def test_unknown_theme_is_rejected():
    with pytest.raises(ValueError, match="Unknown theme"):
        theme_stylesheet("sepia")
