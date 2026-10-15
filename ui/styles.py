from typing import Any, Dict

ACCENT_COLORS = {
    "blue": {
        "name": "Elektrik Mavisi",
        "primary": "#3d59a1",
        "hover": "#4e75c7",
        "active": "#2d4277",
        "accent": "#7aa2f7",
        "accent_light": "#9ab8fc"
    },
    "emerald": {
        "name": "Zümrüt Yeşili",
        "primary": "#059669",
        "hover": "#10b981",
        "active": "#047857",
        "accent": "#34d399",
        "accent_light": "#6ee7b7"
    },
    "purple": {
        "name": "Ametist Moru",
        "primary": "#7c3aed",
        "hover": "#8b5cf6",
        "active": "#6d28d9",
        "accent": "#a78bfa",
        "accent_light": "#c4b5fd"
    },
    "amber": {
        "name": "Amber Turuncu",
        "primary": "#d97706",
        "hover": "#f59e0b",
        "active": "#b45309",
        "accent": "#fbbf24",
        "accent_light": "#fde68a"
    }
}


def get_theme_stylesheet(theme: str = "dark", accent: str = "blue") -> str:
    """Generates complete modern Qt stylesheet for RipSync based on theme and accent color."""
    t = theme.lower() if theme else "dark"
    acc = accent.lower() if accent in ACCENT_COLORS else "blue"
    ac = ACCENT_COLORS[acc]

    if t == "light":
        bg_main = "#f4f5f8"
        bg_panel = "#ffffff"
        bg_card = "#f9fafb"
        bg_hover = "#f3f4f6"
        border = "#d1d5db"
        border_panel = "#e5e7eb"
        text_primary = "#111827"
        text_muted = "#4b5563"
        selection = "#dbeafe"
        slider_groove = "#e5e7eb"
        header_bg = "#f3f4f6"
        disabled_bg = "#f3f4f6"
        disabled_text = "#9ca3af"
        scrollbar_bg = "#f4f5f8"
        scrollbar_handle = "#d1d5db"
        menu_bg = "#ffffff"
        menu_border = "#e5e7eb"
    else:
        # Default Dark
        bg_main = "#1a1b26"
        bg_panel = "#1f2335"
        bg_card = "#24283b"
        bg_hover = "#292e42"
        border = "#414868"
        border_panel = "#292e42"
        text_primary = "#c0caf5"
        text_muted = "#a9b1d6"
        selection = "#34446e"
        slider_groove = "#1f2335"
        header_bg = "#24283b"
        disabled_bg = "#2a2e3f"
        disabled_text = "#565f89"
        scrollbar_bg = "#1a1b26"
        scrollbar_handle = "#414868"
        menu_bg = "#24283b"
        menu_border = "#414868"

    return f"""
QMainWindow, QDialog {{
    background-color: {bg_main};
    color: {text_primary};
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    font-size: 13px;
}}

QWidget {{
    color: {text_primary};
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}}

/* ToolBar */
QToolBar {{
    background-color: {bg_card};
    border-bottom: 1px solid {border};
    spacing: 8px;
    padding: 6px;
}}

QToolButton {{
    background-color: transparent;
    color: {text_primary};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 500;
}}

QToolButton:hover {{
    background-color: {bg_hover};
    border: 1px solid {border};
}}

QToolButton:pressed {{
    background-color: {border};
}}

/* TreeWidget (Categories Sidebar) */
QTreeWidget {{
    background-color: {bg_panel};
    border: 1px solid {border_panel};
    border-radius: 8px;
    padding: 6px;
    outline: none;
}}

QTreeWidget::item {{
    padding: 8px 10px;
    border-radius: 6px;
    color: {text_muted};
}}

QTreeWidget::item:hover {{
    background-color: {bg_hover};
    color: {text_primary};
}}

QTreeWidget::item:selected {{
    background-color: {ac["primary"]};
    color: #ffffff;
    font-weight: bold;
}}

/* TableWidget (Downloads List) */
QTableWidget {{
    background-color: {bg_panel};
    border: 1px solid {border_panel};
    border-radius: 8px;
    gridline-color: {border_panel};
    selection-background-color: {selection};
    selection-color: {text_primary};
    outline: none;
}}

QHeaderView::section {{
    background-color: {header_bg};
    color: {ac["accent"]};
    font-weight: bold;
    padding: 8px;
    border: none;
    border-right: 1px solid {border_panel};
    border-bottom: 2px solid {ac["primary"]};
}}

QTableWidget::item {{
    padding: 6px;
    border-bottom: 1px solid {border_panel};
}}

QTableWidget::item:selected {{
    background-color: {selection};
    color: {text_primary};
}}

/* Buttons */
QPushButton {{
    background-color: {ac["primary"]};
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}}

QPushButton:hover {{
    background-color: {ac["hover"]};
}}

QPushButton:pressed {{
    background-color: {ac["active"]};
}}

QPushButton:disabled {{
    background-color: {disabled_bg};
    color: {disabled_text};
}}

QPushButton#btn_secondary {{
    background-color: {bg_card};
    color: {text_primary};
    border: 1px solid {border};
}}

QPushButton#btn_secondary:hover {{
    background-color: {bg_hover};
}}

/* Input Fields */
QLineEdit, QSpinBox, QComboBox {{
    background-color: {bg_card};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 7px 10px;
    color: {text_primary};
    selection-background-color: {ac["primary"]};
}}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {ac["accent"]};
}}

QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}

/* Slider (Speed Limiter) */
QSlider::groove:horizontal {{
    border: 1px solid {border};
    height: 6px;
    background: {slider_groove};
    border-radius: 3px;
}}

QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ac["primary"]}, stop:1 {ac["accent"]});
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background: {ac["accent"]};
    border: 2px solid #ffffff;
    width: 16px;
    margin-top: -6px;
    margin-bottom: -6px;
    border-radius: 8px;
}}

QSlider::handle:horizontal:hover {{
    background: {ac["accent_light"]};
}}

QSlider::handle:horizontal:pressed {{
    background: {ac["active"]};
}}

QSlider::groove:horizontal:disabled {{
    background: {bg_card};
    border: 1px solid {border_panel};
}}

QSlider::sub-page:horizontal:disabled {{
    background: {border};
}}

QSlider::handle:horizontal:disabled {{
    background: {disabled_text};
    border: 2px solid {border_panel};
}}

/* Progress Bar */
QProgressBar {{
    background-color: {bg_card};
    border: 1px solid {border};
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    font-size: 11px;
    font-weight: bold;
}}

QProgressBar::chunk {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ac["primary"]}, stop:1 {ac["accent"]});
    border-radius: 5px;
}}

/* Status Bar */
QStatusBar {{
    background-color: {bg_panel};
    border-top: 1px solid {border_panel};
    color: {ac["accent"]};
    font-size: 12px;
}}

/* Splitter */
QSplitter::handle {{
    background-color: {bg_card};
}}

/* ScrollBars */
QScrollBar:vertical {{
    background: {scrollbar_bg};
    width: 10px;
    margin: 0px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical {{
    background: {scrollbar_handle};
    min-height: 20px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical:hover {{
    background: {border};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QMenu {{
    background-color: {menu_bg};
    border: 1px solid {menu_border};
    border-radius: 6px;
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 20px;
    border-radius: 4px;
    color: {text_primary};
}}

QMenu::item:selected {{
    background-color: {ac["primary"]};
    color: #ffffff;
}}
"""

DARK_THEME = get_theme_stylesheet("dark", "blue")


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
