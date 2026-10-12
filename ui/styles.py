from typing import Any

DARK_THEME = """
QMainWindow, QDialog {
    background-color: #1a1b26;
    color: #c0caf5;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    font-size: 13px;
}

QWidget {
    color: #c0caf5;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

/* ToolBar */
QToolBar {
    background-color: #24283b;
    border-bottom: 1px solid #414868;
    spacing: 8px;
    padding: 6px;
}

QToolButton {
    background-color: transparent;
    color: #c0caf5;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 500;
}

QToolButton:hover {
    background-color: #2f354f;
    border: 1px solid #565f89;
}

QToolButton:pressed {
    background-color: #414868;
}

/* TreeWidget (Categories Sidebar) */
QTreeWidget {
    background-color: #1f2335;
    border: 1px solid #292e42;
    border-radius: 8px;
    padding: 6px;
    outline: none;
}

QTreeWidget::item {
    padding: 8px 10px;
    border-radius: 6px;
    color: #a9b1d6;
}

QTreeWidget::item:hover {
    background-color: #292e42;
    color: #c0caf5;
}

QTreeWidget::item:selected {
    background-color: #3d59a1;
    color: #ffffff;
    font-weight: bold;
}

/* TableWidget (Downloads List) */
QTableWidget {
    background-color: #1f2335;
    border: 1px solid #292e42;
    border-radius: 8px;
    gridline-color: #292e42;
    selection-background-color: #2e3c64;
    selection-color: #ffffff;
    outline: none;
}

QHeaderView::section {
    background-color: #24283b;
    color: #7aa2f7;
    font-weight: bold;
    padding: 8px;
    border: none;
    border-right: 1px solid #292e42;
    border-bottom: 2px solid #3d59a1;
}

QTableWidget::item {
    padding: 6px;
    border-bottom: 1px solid #24283b;
}

QTableWidget::item:selected {
    background-color: #34446e;
}

/* Buttons */
QPushButton {
    background-color: #3d59a1;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #4e75c7;
}

QPushButton:pressed {
    background-color: #2d4277;
}

QPushButton:disabled {
    background-color: #2a2e3f;
    color: #565f89;
}

QPushButton#btn_secondary {
    background-color: #292e42;
    color: #c0caf5;
    border: 1px solid #414868;
}

QPushButton#btn_secondary:hover {
    background-color: #3b4261;
}

/* Input Fields */
QLineEdit, QSpinBox, QComboBox {
    background-color: #24283b;
    border: 1px solid #414868;
    border-radius: 6px;
    padding: 7px 10px;
    color: #c0caf5;
    selection-background-color: #3d59a1;
}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #7aa2f7;
}

QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}

/* Slider (Speed Limiter) */
QSlider::groove:horizontal {
    border: 1px solid #414868;
    height: 6px;
    background: #1f2335;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3d59a1, stop:1 #7aa2f7);
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #7aa2f7;
    border: 2px solid #ffffff;
    width: 16px;
    margin-top: -6px;
    margin-bottom: -6px;
    border-radius: 8px;
}

QSlider::handle:horizontal:hover {
    background: #bb9af7;
    transform: scale(1.1);
}

QSlider::handle:horizontal:pressed {
    background: #2ac3de;
}

QSlider::groove:horizontal:disabled {
    background: #24283b;
    border: 1px solid #292e42;
}

QSlider::sub-page:horizontal:disabled {
    background: #414868;
}

QSlider::handle:horizontal:disabled {
    background: #565f89;
    border: 2px solid #292e42;
}

/* Progress Bar */
QProgressBar {
    background-color: #24283b;
    border: 1px solid #414868;
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    font-size: 11px;
    font-weight: bold;
}

QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3d59a1, stop:1 #7aa2f7);
    border-radius: 5px;
}

/* Status Bar */
QStatusBar {
    background-color: #1f2335;
    border-top: 1px solid #292e42;
    color: #7aa2f7;
    font-size: 12px;
}

/* Splitter */
QSplitter::handle {
    background-color: #24283b;
}

/* ScrollBars */
QScrollBar:vertical {
    background: #1a1b26;
    width: 10px;
    margin: 0px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background: #414868;
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #565f89;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QMenu {
    background-color: #24283b;
    border: 1px solid #414868;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 6px 20px;
    border-radius: 4px;
    color: #c0caf5;
}

QMenu::item:selected {
    background-color: #3d59a1;
    color: #ffffff;
}
"""

def format_size(bytes_count: Any) -> str:
    if bytes_count is None:
        return "Bilinmiyor"
    try:
        val = float(bytes_count)
    except (ValueError, TypeError):
        return "Bilinmiyor"
    if val < 0:
        return "Bilinmiyor"
    if val < 1024:
        return f"{int(val)} B"
    elif val < 1024 * 1024:
        return f"{val / 1024:.2f} KB"
    elif val < 1024 * 1024 * 1024:
        return f"{val / (1024 * 1024):.2f} MB"
    else:
        return f"{val / (1024 * 1024 * 1024):.2f} GB"

def format_progress_size(downloaded_bytes: Any, total_bytes: Any) -> str:
    """
    Format downloaded and total bytes clearly:
    - If total is known (> 0): e.g. '12.45 MB / 45.00 MB'
    - If total is unknown or estimating: e.g. '12.45 MB / Bilinmiyor'
    """
    dl_str = format_size(downloaded_bytes)
    if total_bytes is not None and total_bytes > 0:
        tot_str = format_size(total_bytes)
        return f"{dl_str} / {tot_str}"
    return f"{dl_str} / Bilinmiyor"

def format_speed(bytes_per_sec: float) -> str:
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.0f} B/s"
    elif bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.1f} KB/s"
    else:
        return f"{bytes_per_sec / (1024 * 1024):.2f} MB/s"

def format_eta(seconds: int) -> str:
    if seconds <= 0:
        return "--"
    if seconds < 60:
        return f"{seconds} sn"
    elif seconds < 3600:
        m = seconds // 60
        s = seconds % 60
        return f"{m} dk {s} sn"
    else:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h} sa {m} dk"
