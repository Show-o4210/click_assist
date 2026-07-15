"""共享深色主题色板与 QSS。"""

from __future__ import annotations

BG = "#14161c"
PANEL = "#1e222b"
PANEL2 = "#252a35"
FG = "#e8eaed"
MUTED = "#8b93a7"
BLUE = "#4c8dff"
GREEN = "#3ddc97"
YELLOW = "#ffd166"
ORANGE = "#ff9f43"
RED = "#ff5d6c"
AXIS = "#3a4150"
LINE = "#2a3140"
INPUT_BG = "#0d0f14"
BORDER = "#343b4a"
SELECT = "#2d4a7a"

APP_QSS = f"""
QWidget {{
    background-color: {BG};
    color: {FG};
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 12px;
}}
QMainWindow, QDialog {{
    background-color: {BG};
}}
QLabel {{
    background: transparent;
    color: {FG};
}}
QLabel[role="muted"] {{
    color: {MUTED};
}}
QLabel[role="status"] {{
    font-weight: 700;
    font-size: 13px;
}}
QLabel[role="countdown"] {{
    color: {YELLOW};
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 16px;
    font-weight: 700;
}}
QLabel[role="meta"] {{
    color: {MUTED};
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 11px;
}}
QLabel[role="info"] {{
    color: {GREEN};
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 11px;
    font-weight: 700;
}}
QFrame#panel {{
    background-color: {PANEL};
    border: none;
}}
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {INPUT_BG};
    color: {FG};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 3px 6px;
    min-height: 22px;
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox QAbstractItemView {{
    background-color: {PANEL};
    color: {FG};
    selection-background-color: {SELECT};
    border: 1px solid {BORDER};
}}
QCheckBox {{
    spacing: 6px;
    color: {FG};
    background: transparent;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {BORDER};
    border-radius: 3px;
    background: {INPUT_BG};
}}
QCheckBox::indicator:checked {{
    background: {BLUE};
    border-color: {BLUE};
}}
QPushButton {{
    background-color: {PANEL2};
    color: {FG};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 5px 12px;
    min-height: 24px;
}}
QPushButton:hover {{
    background-color: #2e3545;
    border-color: {BLUE};
}}
QPushButton:pressed {{
    background-color: #1a1f2a;
}}
QPushButton:disabled {{
    color: {MUTED};
    background-color: #1a1d24;
}}
QPushButton[accent="green"] {{
    background-color: {GREEN};
    color: #111;
    border: none;
    font-weight: 700;
}}
QPushButton[accent="green"]:hover {{
    background-color: #55e8a8;
}}
QPushButton[accent="red"] {{
    background-color: {RED};
    color: #111;
    border: none;
    font-weight: 700;
}}
QPushButton[accent="red"]:hover {{
    background-color: #ff7a86;
}}
QPushButton[accent="blue"] {{
    background-color: {BLUE};
    color: #111;
    border: none;
    font-weight: 700;
}}
QPushButton[accent="blue"]:hover {{
    background-color: #6aa0ff;
}}
QPushButton[accent="yellow"] {{
    background-color: {YELLOW};
    color: #111;
    border: none;
    font-weight: 700;
}}
QPushButton[accent="yellow"]:hover {{
    background-color: #ffe08a;
}}
QPushButton[accent="orange"] {{
    background-color: {ORANGE};
    color: #111;
    border: none;
    font-weight: 700;
}}
QSlider::groove:horizontal {{
    height: 6px;
    background: {INPUT_BG};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    width: 14px;
    margin: -5px 0;
    background: {BLUE};
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {BLUE};
    border-radius: 3px;
}}
QListWidget, QTableWidget, QTreeWidget {{
    background-color: {PANEL};
    color: {FG};
    border: 1px solid {BORDER};
    border-radius: 4px;
    outline: none;
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 11px;
}}
QListWidget::item:selected, QTableWidget::item:selected {{
    background-color: {SELECT};
    color: {FG};
}}
QHeaderView::section {{
    background-color: {PANEL2};
    color: {MUTED};
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    padding: 4px 6px;
    font-weight: 600;
}}
QTableWidget {{
    gridline-color: {BORDER};
}}
QScrollBar:vertical {{
    background: {BG};
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {BG};
    height: 10px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {MUTED};
}}
QToolTip {{
    background-color: {PANEL};
    color: {FG};
    border: 1px solid {BORDER};
    padding: 4px;
}}
QStatusBar {{
    background: {PANEL};
    color: {MUTED};
}}
QSplitter::handle {{
    background: {BORDER};
}}
QTextEdit, QPlainTextEdit {{
    background-color: {PANEL};
    color: {FG};
    border: 1px solid {BORDER};
    border-radius: 4px;
    font-family: Consolas, "Cascadia Mono", monospace;
}}
"""
