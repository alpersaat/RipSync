from typing import Any, Dict, Optional

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


def theme_tokens(theme: str = "dark", accent: str = "blue") -> Dict[str, str]:
    """Tek kaynak renk token sözlüğü.

    Tüm UI katmanı gömülü renk yerine buradaki anahtarları kullanır:
    ara yüz, diyaloglar, çizim bileşenleri (paintEvent) hep aynı sözlükten beslenir.
    """
    t = theme.lower() if theme else "dark"
    acc = accent.lower() if accent in ACCENT_COLORS else "blue"
    ac = ACCENT_COLORS[acc]

    if t == "light":
        tokens = {
            "bg_main": "#f4f5f8",
            "bg_panel": "#ffffff",
            "bg_card": "#f9fafb",
            "bg_hover": "#eef0f4",
            "border": "#d1d5db",
            "border_panel": "#e5e7eb",
            "text_primary": "#111827",
            "text_muted": "#4b5563",
            "text_secondary": "#6b7280",
            "selection": "#dbeafe",
            "header_bg": "#f3f4f6",
            "disabled_bg": "#f3f4f6",
            "disabled_text": "#9ca3af",
            "scrollbar_bg": "#f4f5f8",
            "scrollbar_handle": "#c3c8d4",
            "menu_bg": "#ffffff",
            "menu_border": "#e5e7eb",
            "code_bg": "#e8ecf3",
            # Durum renkleri (açık temada koyu, okunur tonlar)
            "success": "#15803d",
            "warning": "#b45309",
            "danger": "#dc2626",
            "info": "#0369a1",
            # Durum rozet arka planları
            "success_bg": "#dcfce7",
            "warning_bg": "#fef3c7",
            "danger_bg": "#fee2e2",
            "info_bg": "#e0f2fe",
            # Genişletilmiş palet (grafik/rozet/öznitelik renkleri)
            "color_blue": "#2563eb",
            "color_cyan": "#0891b2",
            "color_teal": "#0d9488",
            "color_sky": "#0284c7",
            "color_orange": "#ea580c",
            "color_red": "#dc2626",
            "color_yellow": "#d97706",
            "color_purple": "#7c3aed",
            "color_green_light": "#65a30d",
            "color_slate": "#64748b",
            "text_on_accent": "#ffffff",
            "accent_dark": "#1e293b",
        }
    else:
        tokens = {
            "bg_main": "#1a1b26",
            "bg_panel": "#1f2335",
            "bg_card": "#24283b",
            "bg_hover": "#292e42",
            "border": "#414868",
            "border_panel": "#292e42",
            "text_primary": "#c0caf5",
            "text_muted": "#a9b1d6",
            "text_secondary": "#7982a9",
            "selection": "#34446e",
            "header_bg": "#24283b",
            "disabled_bg": "#2a2e3f",
            "disabled_text": "#565f89",
            "scrollbar_bg": "#1a1b26",
            "scrollbar_handle": "#414868",
            "menu_bg": "#24283b",
            "menu_border": "#414868",
            "code_bg": "#15161e",
            # Durum renkleri
            "success": "#9ece6a",
            "warning": "#e0af68",
            "danger": "#f7768e",
            "info": "#7dcfff",
            # Durum rozet arka planları
            "success_bg": "#1e3a2e",
            "warning_bg": "#2b221a",
            "danger_bg": "#3b1f1f",
            "info_bg": "#1a2b3c",
            # Genişletilmiş palet
            "color_blue": "#89b4fa",
            "color_cyan": "#7dcfff",
            "color_teal": "#73daca",
            "color_sky": "#2ac3de",
            "color_orange": "#ff9e64",
            "color_red": "#f7768e",
            "color_yellow": "#e0af68",
            "color_purple": "#bb9af7",
            "color_green_light": "#b9f27c",
            "color_slate": "#7982a9",
            "text_on_accent": "#ffffff",
            "accent_dark": "#10131f",
        }

    # Vurgu (accent) token'ları — seçilen vurgu rengine göre
    tokens["accent_primary"] = ac["primary"]
    tokens["accent_hover"] = ac["hover"]
    tokens["accent_active"] = ac["active"]
    tokens["accent"] = ac["accent"]
    tokens["accent_light"] = ac["accent_light"]
    return tokens


# ---- Modül düzeyinde "canlı" token durumu ------------------------------------
# T = get_tokens() her modülün BİR KEZ aldığı ortak sözlüktür.
# Tema değişince refresh_tokens() bu sözlüğü YERİNDE günceller;
# yeni değerlendirilen tüm stil ifadeleri yeni temaya geçer.
_TOKENS: Dict[str, str] = theme_tokens("dark", "blue")
_APP_DB: Optional[Any] = None  # Ana pencere kaydeder: styles.set_database(self.db)


def set_database(db: Any) -> None:
    """Ana pencere, ayar okuması için uygulama veritabanı örneğini kaydeder."""
    global _APP_DB
    _APP_DB = db


def get_tokens() -> Dict[str, str]:
    """Mevcut tema token sözlüğünü (ortak, yerinde güncellenen) döndürür."""
    return _TOKENS


def resolve_system_theme() -> str:
    """'system' teması için OS tercihini çözer: 'dark' veya 'light'.

    Windows: HKCU\\...\\Themes\\Personalize\\AppsUseLightTheme (0 = koyu).
    Diğer platformlar Qt paletinden tahmin eder.
    """
    try:
        import sys as _sys
        if _sys.platform == "win32":
            import winreg
            k = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            val, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
            winreg.CloseKey(k)
            return "light" if int(val) == 1 else "dark"
    except Exception:
        pass
    try:
        from PyQt6.QtWidgets import QApplication  # noqa
        app = QApplication.instance()
        if app is not None:
            pal = app.palette()
            return "light" if pal.window().color().lightness() > 128 else "dark"
    except Exception:
        pass
    return "dark"


def refresh_tokens(theme: Optional[str] = None, accent: Optional[str] = None) -> dict:
    """Token sözlüğünü yerinde günceller.

    theme/accent verilmezse kayıtlı ayarlardan okunur.
    Ana pencere tema değişikliklerinde çağırır; böylece tüm UI modülleri
    yeni temaya geçer.
    """
    if _APP_DB is not None:
        cfg = _APP_DB.get_theme_settings()
    else:
        cfg = {}
    new_theme = theme if theme else cfg.get("theme", "dark")
    new_accent = accent if accent else cfg.get("accent", "blue")
    if new_theme == "system":
        new_theme = resolve_system_theme()
    if new_theme not in ("dark", "light"):
        new_theme = "dark"
    tokens = theme_tokens(new_theme, new_accent)
    _TOKENS.clear()
    _TOKENS.update(tokens)
    return _TOKENS


T = get_tokens()  # Kısa ad: from ui.styles import T → ortak sözlük


def get_app_stylesheet() -> str:
    """Kayıtlı tema ayarlarından ('system' dahil) tüm uygulamanın stil sayfasını üretir."""
    cfg = _APP_DB.get_theme_settings() if _APP_DB is not None else {"theme": "dark", "accent": "blue"}
    theme_key = cfg.get("theme", "dark")
    accent = cfg.get("accent", "blue")
    resolved = resolve_system_theme() if theme_key == "system" else (theme_key or "dark")
    return get_theme_stylesheet(resolved, accent)


def get_theme_stylesheet(theme: str = "dark", accent: str = "blue") -> str:
    """Generates complete modern Qt stylesheet for RipSync based on theme and accent color."""
    tokens = theme_tokens(theme, accent)
    return generate_stylesheet_from_tokens(tokens)


def generate_stylesheet_from_tokens(t: Dict[str, str]) -> str:
    ac_primary = t["accent_primary"]
    ac_hover = t["accent_hover"]
    ac_active = t["accent_active"]
    ac_accent = t["accent"]
    ac_light = t["accent_light"]
    bg_main = t["bg_main"]
    bg_panel = t["bg_panel"]
    bg_card = t["bg_card"]
    bg_hover = t["bg_hover"]
    border = t["border"]
    border_panel = t["border_panel"]
    text_primary = t["text_primary"]
    text_muted = t["text_muted"]
    selection = t["selection"]
    header_bg = t["header_bg"]
    disabled_bg = t["disabled_bg"]
    disabled_text = t["disabled_text"]
    slider_groove = t["bg_panel"]
    scrollbar_bg = t["scrollbar_bg"]
    scrollbar_handle = t["scrollbar_handle"]
    menu_bg = t["menu_bg"]
    menu_border = t["menu_border"]

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
    background-color: {ac_primary};
    color: {t["text_on_accent"]};
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
    color: {ac_accent};
    font-weight: bold;
    padding: 8px;
    border: none;
    border-right: 1px solid {border_panel};
    border-bottom: 2px solid {ac_primary};
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
    background-color: {ac_primary};
    color: {t["text_on_accent"]};
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}}

QPushButton:hover {{
    background-color: {ac_hover};
}}

QPushButton:pressed {{
    background-color: {ac_active};
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
    selection-background-color: {ac_primary};
}}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {ac_accent};
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
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ac_primary}, stop:1 {ac_accent});
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background: {ac_accent};
    border: 2px solid {t["text_on_accent"]};
    width: 16px;
    margin-top: -6px;
    margin-bottom: -6px;
    border-radius: 8px;
}}

QSlider::handle:horizontal:hover {{
    background: {ac_light};
}}

QSlider::handle:horizontal:pressed {{
    background: {ac_active};
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
    color: {t["text_on_accent"]};
    font-size: 11px;
    font-weight: bold;
}}

QProgressBar::chunk {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ac_primary}, stop:1 {ac_accent});
    border-radius: 5px;
}}

/* Status Bar */
QStatusBar {{
    background-color: {bg_panel};
    border-top: 1px solid {border_panel};
    color: {ac_accent};
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
    background-color: {ac_primary};
    color: {t["text_on_accent"]};
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
