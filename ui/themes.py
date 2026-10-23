from __future__ import annotations

from pathlib import Path
import logging

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QDialogButtonBox, QPushButton


THEME_NAMES = ("dark", "light")
_ICON_ROOT = Path(__file__).resolve().parents[1] / "assets" / "icons"
_STYLE_ASSETS = {
    "arrow_up": (_ICON_ROOT / "chevron-up-accent.svg").as_posix(),
    "arrow_down": (_ICON_ROOT / "chevron-down-accent.svg").as_posix(),
}


def configure_application_font(app) -> None:
    """Register bundled UI weights once per application, before creating widgets."""
    if app.property("editorFontsLoaded"):
        return
    font_root = _ICON_ROOT.parent / "fonts"
    for weight in ("Regular", "Medium", "SemiBold"):
        path = font_root / f"Pretendard-{weight}.otf"
        if QFontDatabase.addApplicationFont(str(path)) < 0:
            logging.getLogger(__name__).warning("UI font could not be loaded: %s", path)
    font = QFont()
    font.setFamilies(["Pretendard", "Malgun Gothic", "Segoe UI", "sans-serif"])
    font.setPixelSize(13)
    font.setWeight(QFont.Weight.Normal)
    app.setFont(font)
    app.setProperty("editorFontsLoaded", True)


def theme_colors(theme: str) -> dict[str, str]:
    """Return colors only; widget geometry lives in the shared style template."""
    if theme not in THEME_NAMES:
        raise ValueError(f"Unknown theme: {theme}")
    if theme == "light":
        return {
            "window": "#E4E5E7", "panel": "#F4F4F5", "panel_alt": "#EAEAEC",
            "input": "#FFFFFF", "text": "#24262A", "muted": "#62666D",
            "border": "#C5C7CB", "separator": "#D6D7DA", "hover": "#E0E2E5",
            "selected": "#DCE8F5", "selected_text": "#173E6C",
            "disabled": "#898D94", "disabled_bg": "#ECECEE",
            "canvas": "#CACCCF", "icon": "#41454B",
            "primary_top": "#3979B9", "primary_bottom": "#2868A9",
            "primary_hover_top": "#4384C5", "primary_hover_bottom": "#3378BB",
            "primary_pressed_top": "#245E99", "primary_pressed_bottom": "#20558A",
            "primary_text": "#FFFFFF", "scroll_handle": "#B4B7BD",
            "danger": "#B43535", "danger_bg": "#F9E7E7",
            "success": "#16803D", "success_border": "#22A06B",
        }
    return {
        "window": "#202123", "panel": "#2B2C2F", "panel_alt": "#333438",
        "input": "#222326", "text": "#E4E5E7", "muted": "#ADB0B7",
        "border": "#4A4C52", "separator": "#3C3E43", "hover": "#3E4046",
        "selected": "#304C69", "selected_text": "#EDF5FF",
        "disabled": "#797D85", "disabled_bg": "#303135",
        "canvas": "#191A1C", "icon": "#D5D7DC",
        "primary_top": "#72A9DC", "primary_bottom": "#326FA9",
        "primary_hover_top": "#83B7E8", "primary_hover_bottom": "#3D7FBB",
        "primary_pressed_top": "#2A6094", "primary_pressed_bottom": "#245786",
        "primary_text": "#FFFFFF", "scroll_handle": "#5B5E65",
        "danger": "#EF9B9B", "danger_bg": "#4C3336",
        "success": "#39A96B", "success_border": "#22A06B",
    }


_STYLE_TEMPLATE = """
QWidget {{
    background-color: {panel};
    color: {text};
    font-family: "Pretendard", "Malgun Gothic", "Segoe UI", sans-serif;
    font-size: 13px;
    font-weight: 400;
}}
QMainWindow {{
    background-color: {window};
    color: {text};
}}
QDialog, QMessageBox, QInputDialog {{ background-color: {panel}; color: {text}; }}
QDialogButtonBox {{ background-color: transparent; }}
QStackedWidget, QScrollArea, QAbstractScrollArea, QMdiArea {{
    background-color: {panel};
    color: {text};
    border: none;
}}
QWidget#dockToolsContents, QWidget#dockOptionsContents,
QWidget#dockProjectContents, QWidget#dockPropertiesContents,
QWidget#dockLogsContents {{ background-color: {panel}; }}

QDockWidget {{ color: {text}; border: none; }}
QDockWidget::title {{
    background-color: {panel_alt};
    color: {text};
    border-bottom: 1px solid {separator};
    padding: 7px 10px;
    font-weight: 600;
}}
QWidget#dockPanelHeader {{ background-color: {panel_alt}; border-bottom: 1px solid {separator}; }}
QLabel[uiRole="panelTitle"] {{ font-weight: 600; }}

QGroupBox {{
    background-color: {panel};
    border: 1px solid {separator};
    border-radius: 3px;
    margin-top: 18px;
    padding: 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 5px;
    color: {text};
    font-size: 13px;
    font-weight: 600;
    background-color: transparent;
}}
QGroupBox#annotationPanel QPushButton {{ padding: 5px 6px; }}
QFrame {{ border-color: {separator}; }}
QLabel {{ color: {text}; background-color: transparent; }}
QLabel:disabled {{ color: {disabled}; }}
QFrame#resultMetric {{ background-color: {panel_alt}; border: 1px solid {separator}; border-radius: 6px; }}
QLabel#metricNumber {{ font-size: 24px; font-weight: 600; }}

QPushButton {{
    min-height: 18px;
    background: {panel_alt};
    border: 1px solid {border};
    border-radius: 3px;
    padding: 5px 12px;
    color: {text};
    font-weight: 500;
}}
QPushButton:hover {{
    background: {hover};
    border-color: {muted};
}}
QPushButton:pressed {{
    background: {selected};
    border-color: {primary_top};
}}
QPushButton:focus, QToolButton:focus {{ border: 1px solid {primary_top}; }}
QPushButton:disabled {{
    background: {disabled_bg};
    color: {disabled};
    border: 1px solid {separator};
}}
QPushButton[uiRole="primary"], QToolButton[uiRole="primary"] {{
    background: {primary_bottom}; color: {primary_text}; border: 1px solid {primary_bottom};
    font-weight: 600;
}}
QPushButton[uiRole="primary"]:hover, QToolButton[uiRole="primary"]:hover {{ background: {primary_hover_bottom}; }}
QPushButton[uiRole="primary"]:pressed, QToolButton[uiRole="primary"]:pressed {{ background: {primary_pressed_bottom}; }}
QPushButton[uiRole="primary"]:focus, QToolButton[uiRole="primary"]:focus {{ border-color: {primary_top}; }}
QPushButton[uiRole="primary"]:disabled, QToolButton[uiRole="primary"]:disabled {{
    background: {disabled_bg}; color: {disabled}; border-color: {separator};
}}
QPushButton[uiRole="danger"] {{ color: {danger}; }}
QPushButton[uiRole="danger"]:hover {{ background: {danger_bg}; border-color: {danger}; }}
QPushButton[uiRole="danger"]:disabled {{ color: {disabled}; border-color: {separator}; }}
QLabel[uiRole="hint"] {{ color: {muted}; font-size: 12px; }}
QLabel#documentSummary {{ background: {panel_alt}; color: {muted}; font-size: 12px; padding: 7px 12px; border-bottom: 1px solid {separator}; }}
QLabel[uiRole="toolTitle"] {{ font-weight: 600; padding-right: 10px; }}
QMainWindow::separator {{ background: {window}; width: 3px; height: 3px; }}
QMainWindow::separator:hover {{ background: {primary_bottom}; }}
QWidget#dockOptionsContents, QWidget#pageOptionsNavigate, QWidget#pageOptionsSelect,
QWidget#pageOptionsBrush, QWidget#pageOptionsPaste {{ background-color: {panel_alt}; }}
QToolButton#optionsApplyPoisson {{ background-color: {primary_bottom}; color: {primary_text}; }}
QToolButton#optionsApplyPoisson:disabled {{ background-color: {disabled_bg}; color: {disabled}; }}

QToolButton {{
    background-color: transparent;
    color: {text};
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 4px;
}}
QToolButton:hover {{ background-color: {hover}; border-color: {border}; }}
QToolButton:pressed, QToolButton:checked {{
    background-color: {selected};
    color: {selected_text};
    border-color: {primary_bottom};
}}
QToolButton:disabled {{ color: {disabled}; background-color: transparent; border-color: transparent; }}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {input};
    color: {text};
    border: 1px solid {border};
    border-radius: 3px;
    padding: 5px 6px;
    selection-background-color: {primary_bottom};
    selection-color: {primary_text};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {primary_top}; }}
QSpinBox, QDoubleSpinBox {{ font-weight: 500; }}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    background-color: {disabled_bg}; color: {disabled}; border-color: {separator};
}}
QSpinBox, QDoubleSpinBox {{ padding-right: 25px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    background-color: {panel_alt};
    border: none;
    border-left: 1px solid {border};
    border-bottom: 1px solid {separator};
    border-top-right-radius: 4px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    background-color: {panel_alt};
    border: none;
    border-left: 1px solid {border};
    border-bottom-right-radius: 4px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background-color: {hover}; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("{arrow_up}"); width: 9px; height: 9px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("{arrow_down}"); width: 9px; height: 9px;
}}

QComboBox {{ padding-right: 27px; }}
QComboBox:hover {{ border-color: {muted}; }}
QComboBox:focus {{ border-color: {primary_top}; }}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border: none;
    border-left: 1px solid {border};
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
    background-color: {panel_alt};
}}
QComboBox::drop-down:hover {{ background-color: {hover}; }}
QComboBox::down-arrow {{ image: url("{arrow_down}"); width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{
    background-color: {panel}; color: {text}; border: 1px solid {border};
    border-radius: 4px; padding: 2px; outline: none;
}}
QComboBox QAbstractItemView::item {{ padding: 7px 10px; border-radius: 3px; }}
QComboBox QAbstractItemView::item:selected {{ background-color: {selected}; color: {selected_text}; }}

QCheckBox, QRadioButton {{ color: {text}; background: transparent; spacing: 7px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px; background-color: {input}; border: 1px solid {border};
}}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {primary_top}; }}
QCheckBox::indicator:checked {{ background-color: {primary_bottom}; border-color: {primary_bottom}; image: url("{checkmark}"); }}
QRadioButton::indicator:checked {{
    border: 4px solid {primary_bottom}; background-color: {input};
}}
QCheckBox:disabled, QRadioButton:disabled {{ color: {disabled}; }}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ background-color: {disabled_bg}; border-color: {border}; }}

QMenuBar, QMenu, QToolBar {{ background-color: {panel}; color: {text}; border: none; }}
QMenuBar {{ border-bottom: 1px solid {separator}; }}
QMenuBar::item {{ padding: 6px 10px; background: transparent; border-radius: 2px; }}
QMenuBar::item:selected {{ background-color: {hover}; color: {text}; }}
QMenu {{ border: 1px solid {border}; border-radius: 3px; padding: 4px; }}
QMenu::item {{ padding: 7px 28px 7px 24px; border-radius: 2px; }}
QMenu::item:selected {{ background-color: {selected}; color: {selected_text}; }}
QMenu::item:disabled {{ color: {disabled}; }}
QMenu::separator {{ height: 1px; background: {separator}; margin: 5px 8px; }}

QTreeView, QListView, QTableView {{
    background-color: {input}; color: {text}; border: 1px solid {separator}; border-radius: 3px;
    alternate-background-color: {panel_alt}; outline: none; padding: 3px;
}}
QTreeView::item, QListView::item {{ min-height: 22px; padding: 3px 5px; border-radius: 2px; }}
QTreeView::item:hover, QListView::item:hover {{ background-color: {hover}; }}
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {{
    background-color: {selected}; color: {selected_text};
}}
QHeaderView::section {{
    background-color: {panel_alt}; color: {muted}; border: none;
    border-bottom: 1px solid {separator}; padding: 6px 8px; font-weight: 600;
}}

QTabWidget::pane {{ background-color: {panel}; border: 1px solid {separator}; border-radius: 0; }}
QTabBar {{ background-color: {panel_alt}; }}
QTabBar::tab {{
    background-color: transparent; color: {muted}; border: none;
    border-bottom: 2px solid transparent; padding: 7px 12px;
}}
QTabBar::tab:hover {{ color: {text}; background-color: {hover}; }}
QTabBar::tab:selected {{ background-color: {panel}; color: {text}; border-bottom-color: {primary_top}; font-weight: 600; }}
QTabBar::tab:disabled {{ color: {disabled}; }}

QScrollBar:vertical, QScrollBar:horizontal {{
    border: none; background: {window}; width: 8px; height: 8px; border-radius: 4px;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {scroll_handle}; min-height: 30px; min-width: 30px; border-radius: 4px;
}}
QScrollBar::handle:hover {{ background: {muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: none; background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QProgressBar {{
    background-color: {input}; color: {text}; border: 1px solid {border};
    border-radius: 4px; text-align: center; min-height: 16px;
}}
QProgressBar::chunk {{ background-color: {primary_bottom}; border-radius: 3px; }}
QStatusBar {{ background-color: {panel}; color: {muted}; border-top: 1px solid {separator}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel, QStatusBar QToolButton {{ color: {muted}; font-size: 12px; }}
QSlider::groove:horizontal {{ height: 4px; background: {separator}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {primary_bottom}; }}
QSlider::handle:horizontal {{ width: 12px; margin: -5px 0; background: {primary_bottom}; border: 2px solid {panel}; border-radius: 7px; }}
QSlider::handle:horizontal:hover, QSlider::handle:horizontal:focus {{ background: {primary_hover_bottom}; }}
QSlider::sub-page:horizontal:disabled, QSlider::handle:horizontal:disabled {{ background: {scroll_handle}; }}
QToolTip {{
    background-color: {panel}; color: {text}; border: 1px solid {border};
    border-radius: 4px; padding: 5px 7px;
}}

/* AutoAugment owns layout in Designer; visual behavior remains theme-owned here. */
QDialog#autoaugment_dialog QFrame#info_frame,
QDialog#autoaugment_dialog QFrame#preview_frame,
QDialog#autoaugment_dialog QFrame#progress_frame,
QDialog#autoaugment_dialog QGroupBox {{
    background-color: {panel};
    border: 1px solid {separator};
    border-radius: 3px;
}}
QDialog#autoaugment_dialog QGroupBox {{
    margin-top: 18px;
    padding: 14px 12px 10px 12px;
}}
QDialog#autoaugment_dialog QGroupBox::title {{
    background-color: {panel};
    font-size: 13px;
    font-weight: 600;
}}
QDialog#autoaugment_dialog QFrame#results_frame {{
    background-color: {panel};
    border: 1px solid {separator};
    border-radius: 3px;
}}
QDialog#autoaugment_dialog QLabel#results_title_label,
QDialog#autoaugment_dialog QLabel#distribution_title_label {{
    color: {success};
    font-weight: 600;
}}
QDialog#autoaugment_dialog QLabel#preview_image_label {{
    background-color: {panel_alt};
    border: 1px solid {separator};
    border-radius: 3px;
    color: {muted};
}}
QDialog#autoaugment_dialog QLabel[autoaugmentRole="samplePreview"] {{
    background-color: {panel_alt};
    border: 1px solid {separator};
    border-radius: 3px;
    color: {muted};
}}
QDialog#autoaugment_dialog QPushButton[autoaugmentRole="outlineButton"] {{
    background: {panel}; color: {text}; border: 1px solid {border};
}}
QDialog#autoaugment_dialog QPushButton[autoaugmentRole="cancelButton"] {{
    background: {panel_alt}; color: {muted}; border: 1px solid {separator};
}}
QDialog#autoaugment_dialog QPushButton[autoaugmentRole="primaryButton"] {{
    background: {primary_bottom}; color: {primary_text};
    border: 1px solid {primary_bottom}; font-weight: 600;
}}
QDialog#autoaugment_dialog QPushButton[autoaugmentRole="primaryButton"]:hover {{
    background: {primary_hover_bottom}; border-color: {primary_hover_bottom};
}}
QDialog#autoaugment_dialog QPushButton:disabled {{ background: {disabled_bg}; color: {disabled}; border: 1px solid {separator}; }}
QDialog#autoaugment_dialog QPushButton[autoaugmentRole="primaryButton"]:disabled {{ background: {disabled_bg}; color: {disabled}; border-color: {separator}; }}
QDialog#autoaugment_dialog QSlider::groove:horizontal {{
    height: 5px; background: {separator}; border-radius: 2px;
}}
QDialog#autoaugment_dialog QSlider::sub-page:horizontal {{
    background: {primary_bottom}; border-radius: 2px;
}}
QDialog#autoaugment_dialog QSlider::handle:horizontal {{
    background: {primary_bottom}; border: 3px solid {panel};
    width: 14px; height: 14px; margin: -6px 0; border-radius: 7px;
}}
QDialog#autoaugment_dialog QSlider::sub-page:horizontal:disabled,
QDialog#autoaugment_dialog QSlider::handle:horizontal:disabled {{ background: {scroll_handle}; }}
QDialog#autoaugment_dialog QFrame#results_frame QProgressBar::chunk {{
    background-color: {success_border};
}}

QTreeWidget#treeProject {{ background: {panel}; border: 0; outline: 0; }}
QTreeWidget#treeProject::item {{ height: 24px; padding: 1px 3px; }}
QTreeWidget#treeProject::branch {{ background: transparent; }}
QTreeWidget#treeProject::branch:closed:has-children {{ image: url("{tree_right}"); }}
QTreeWidget#treeProject::branch:open:has-children {{ image: url("{tree_down}"); }}
"""


def theme_stylesheet(theme: str) -> str:
    """Render the shared widget design with only theme color substitutions."""
    suffix = "-light" if theme == "dark" else ""
    tree_assets = {
        "tree_right": (_ICON_ROOT / f"chevron-right{suffix}.svg").as_posix(),
        "tree_down": (_ICON_ROOT / f"chevron-down{suffix}.svg").as_posix(),
    }
    return _STYLE_TEMPLATE.format(**theme_colors(theme), **_STYLE_ASSETS, **tree_assets, checkmark=(_ICON_ROOT / "check-white.svg").as_posix())


def configure_dialog(dialog, width: int = 480, accept_text: str = "적용") -> None:
    """Give editor dialogs consistent spacing and explicit primary/secondary actions."""
    dialog.setMinimumWidth(width)
    dialog.setSizeGripEnabled(True)
    dialog.layout().setContentsMargins(16, 16, 16, 16)
    dialog.layout().setSpacing(12)
    for button in dialog.findChildren(QPushButton):
        button.setAutoDefault(False)
    for box in dialog.findChildren(QDialogButtonBox):
        for standard, text in ((QDialogButtonBox.StandardButton.Cancel, "취소"), (QDialogButtonBox.StandardButton.Close, "닫기"), (QDialogButtonBox.StandardButton.Ok, accept_text), (QDialogButtonBox.StandardButton.Apply, accept_text)):
            button = box.button(standard)
            if button is not None:
                button.setText(text)
                if standard in (QDialogButtonBox.StandardButton.Ok, QDialogButtonBox.StandardButton.Apply):
                    button.setProperty("uiRole", "primary")
                    button.setDefault(True)
    for button in dialog.findChildren(QPushButton):
        button.style().unpolish(button)
        button.style().polish(button)
