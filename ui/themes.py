from __future__ import annotations

from pathlib import Path


THEME_NAMES = ("dark", "light")
_ICON_ROOT = Path(__file__).resolve().parents[1] / "assets" / "icons"
_STYLE_ASSETS = {
    "arrow_up": (_ICON_ROOT / "chevron-up-accent.svg").as_posix(),
    "arrow_down": (_ICON_ROOT / "chevron-down-accent.svg").as_posix(),
}


def theme_colors(theme: str) -> dict[str, str]:
    """Return colors only; widget geometry lives in the shared style template."""
    if theme not in THEME_NAMES:
        raise ValueError(f"Unknown theme: {theme}")
    if theme == "light":
        return {
            "window": "#F3F4F6", "panel": "#FFFFFF", "panel_alt": "#F9FAFB",
            "input": "#FFFFFF", "text": "#1F2937", "muted": "#64748B",
            "border": "#D1D5DB", "separator": "#E5E7EB", "hover": "#EFF6FF",
            "selected": "#DBEAFE", "selected_text": "#1E3A8A",
            "disabled": "#9CA3AF", "disabled_bg": "#F3F4F6",
            "canvas": "#E5E7EB", "icon": "#334155",
            "primary_top": "#3B82F6", "primary_bottom": "#2563EB",
            "primary_hover_top": "#60A5FA", "primary_hover_bottom": "#3B82F6",
            "primary_pressed_top": "#2563EB", "primary_pressed_bottom": "#1D4ED8",
            "primary_text": "#FFFFFF", "scroll_handle": "#CBD5E1",
            "success": "#16803D", "success_border": "#22A06B",
        }
    return {
        "window": "#181A1F", "panel": "#23262D", "panel_alt": "#2B2F37",
        "input": "#1D2026", "text": "#F3F4F6", "muted": "#AAB2BF",
        "border": "#414753", "separator": "#343A45", "hover": "#2D3E5A",
        "selected": "#274C77", "selected_text": "#FFFFFF",
        "disabled": "#747D8B", "disabled_bg": "#272A31",
        "canvas": "#111318", "icon": "#F3F4F6",
        "primary_top": "#4B8DF8", "primary_bottom": "#2563EB",
        "primary_hover_top": "#60A5FA", "primary_hover_bottom": "#3B82F6",
        "primary_pressed_top": "#2563EB", "primary_pressed_bottom": "#1D4ED8",
        "primary_text": "#FFFFFF", "scroll_handle": "#4B5563",
        "success": "#39A96B", "success_border": "#22A06B",
    }


_STYLE_TEMPLATE = """
QWidget {{
    background-color: {window};
    color: {text};
    font-family: "Inter", "Noto Sans KR", "Malgun Gothic", "Segoe UI", sans-serif;
    font-size: 11px;
}}
QMainWindow, QDialog, QMessageBox, QInputDialog {{
    background-color: {window};
    color: {text};
}}
QDialog > QWidget {{ background-color: {window}; }}
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
    padding: 7px 9px;
}}

QGroupBox {{
    background-color: {panel};
    border: none;
    border-radius: 12px;
    margin-top: 10px;
    padding: 15px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 5px;
    color: {text};
    font-size: 12px;
    font-weight: 700;
    background-color: transparent;
}}
QFrame {{ border-color: {separator}; }}
QLabel {{ color: {text}; background-color: transparent; }}
QLabel:disabled {{ color: {disabled}; }}

QPushButton {{
    min-height: 18px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {primary_top}, stop:1 {primary_bottom});
    border: none;
    border-radius: 4px;
    padding: 6px 12px;
    color: {primary_text};
    font-weight: 500;
}}
QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {primary_hover_top}, stop:1 {primary_hover_bottom});
    font-weight: 600;
}}
QPushButton:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {primary_pressed_top}, stop:1 {primary_pressed_bottom});
}}
QPushButton:disabled {{
    background: {disabled_bg};
    color: {disabled};
    border: 1px solid {separator};
}}

QToolButton {{
    background-color: transparent;
    color: {text};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px;
}}
QToolButton:hover {{ background-color: {hover}; border-color: {border}; }}
QToolButton:pressed, QToolButton:checked {{
    background-color: {selected};
    color: {selected_text};
    border-color: {primary_bottom};
}}
QToolButton:disabled {{ color: {disabled}; background-color: transparent; }}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {input};
    color: {text};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 6px;
    selection-background-color: {primary_bottom};
    selection-color: {primary_text};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {primary_top}; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
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
QComboBox:hover {{ border-color: {primary_top}; }}
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
QCheckBox::indicator:checked {{ background-color: {primary_bottom}; border-color: {primary_bottom}; }}
QRadioButton::indicator:checked {{
    border: 4px solid {primary_bottom}; background-color: {input};
}}
QCheckBox:disabled, QRadioButton:disabled {{ color: {disabled}; }}

QMenuBar, QMenu, QToolBar {{ background-color: {panel}; color: {text}; border: none; }}
QMenuBar::item {{ padding: 6px 10px; background: transparent; border-radius: 4px; }}
QMenuBar::item:selected {{ background-color: {hover}; color: {text}; }}
QMenu {{ border: 1px solid {border}; border-radius: 6px; padding: 5px; }}
QMenu::item {{ padding: 7px 28px 7px 24px; border-radius: 4px; }}
QMenu::item:selected {{ background-color: {selected}; color: {selected_text}; }}
QMenu::item:disabled {{ color: {disabled}; }}
QMenu::separator {{ height: 1px; background: {separator}; margin: 5px 8px; }}

QTreeView, QListView, QTableView {{
    background-color: {panel}; color: {text}; border: none; border-radius: 8px;
    alternate-background-color: {panel_alt}; outline: none; padding: 3px;
}}
QTreeView::item, QListView::item {{ min-height: 22px; padding: 3px 5px; border-radius: 4px; }}
QTreeView::item:hover, QListView::item:hover {{ background-color: {hover}; }}
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {{
    background-color: {selected}; color: {selected_text};
}}
QHeaderView::section {{
    background-color: {panel_alt}; color: {muted}; border: none;
    border-bottom: 1px solid {separator}; padding: 6px 8px; font-weight: 600;
}}

QTabWidget::pane {{ background-color: {panel}; border: 1px solid {separator}; border-radius: 8px; }}
QTabBar::tab {{
    background-color: transparent; color: {muted}; border: none;
    border-bottom: 2px solid transparent; padding: 8px 12px;
}}
QTabBar::tab:hover {{ color: {text}; background-color: {hover}; }}
QTabBar::tab:selected {{ color: {primary_top}; border-bottom-color: {primary_top}; font-weight: 600; }}

QScrollBar:vertical, QScrollBar:horizontal {{
    border: none; background: {window}; width: 8px; height: 8px; border-radius: 4px;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {scroll_handle}; min-height: 30px; min-width: 30px; border-radius: 4px;
}}
QScrollBar::handle:hover {{ background: {primary_top}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: none; background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QProgressBar {{
    background-color: {input}; color: {text}; border: 1px solid {border};
    border-radius: 4px; text-align: center; min-height: 16px;
}}
QProgressBar::chunk {{ background-color: {primary_bottom}; border-radius: 3px; }}
QStatusBar {{ background-color: {panel}; color: {muted}; border-top: 1px solid {separator}; }}
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
    border-radius: 10px;
}}
QDialog#autoaugment_dialog QGroupBox {{
    margin-top: 10px;
    padding: 14px 12px 10px 12px;
}}
QDialog#autoaugment_dialog QGroupBox::title {{
    background-color: {panel};
    font-size: 12px;
    font-weight: 600;
}}
QDialog#autoaugment_dialog QFrame#results_frame {{
    background-color: {panel};
    border: 1px dashed {success_border};
    border-radius: 10px;
}}
QDialog#autoaugment_dialog QLabel#results_title_label,
QDialog#autoaugment_dialog QLabel#distribution_title_label {{
    color: {success};
    font-weight: 700;
}}
QDialog#autoaugment_dialog QLabel#preview_image_label {{
    background-color: {panel_alt};
    border: 1px solid {separator};
    border-radius: 8px;
    color: {muted};
}}
QDialog#autoaugment_dialog QLabel[autoaugmentRole="samplePreview"] {{
    background-color: {panel_alt};
    border: 1px solid {separator};
    border-radius: 5px;
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
    border: 1px solid {primary_bottom}; font-weight: 700;
}}
QDialog#autoaugment_dialog QPushButton[autoaugmentRole="primaryButton"]:hover {{
    background: {primary_hover_bottom}; border-color: {primary_hover_bottom};
}}
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
QDialog#autoaugment_dialog QFrame#results_frame QProgressBar::chunk {{
    background-color: {success_border};
}}

QTreeWidget#treeProject {{ border: 0; outline: 0; }}
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
    return _STYLE_TEMPLATE.format(**theme_colors(theme), **_STYLE_ASSETS, **tree_assets)
