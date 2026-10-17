"""İkon seti: emoji yerine tutarlı SVG ikonlar.

resources/icons altındaki şablon dosyalarda {color} yer tutucusu bulunur;
tema token'ına göre boyanır ve QIcon olarak döndürülür.
"""
import os
from PyQt6.QtCore import QByteArray, Qt, QSize
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

TEMPLATES: dict = {}  # name -> svg metninin önbelleği

_TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resources", "icons",
)


def _template(name: str) -> str:
    svg = TEMPLATES.get(name)
    if svg is not None:
        return svg
    path = os.path.join(_TEMPLATE_DIR, f"{name}.svg")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            svg = f.read()
    else:
        # Varsayılan dolgu ikonu
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">'
            '<rect x="4" y="4" width="16" height="16" rx="4" fill="{color}"/>'
            "</svg>"
        )
    TEMPLATES[name] = svg
    return svg


def colored_svg(name: str, color: str) -> str:
    """İkonun tema rengiyle boyanmış SVG metnini döndürür."""
    return _template(name).replace("{color}", color)


def get_icon(name: str, color: str | None = None, size: int = 24) -> QIcon:
    """SVG ikonu tema token rengine göre boyayıp QIcon döndürür."""
    from ui.styles import T
    color = color or T["accent"]
    renderer = QSvgRenderer(QByteArray(colored_svg(name, color).encode("utf-8")))
    pixmap = QPixmap(int(size * 2), int(size * 2))  # retina netliği
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p)
    p.end()
    return QIcon(pixmap)


def apply_theme_icons() -> dict:
    """Temadan üretilen QIcon'ları döndürür (ana pencereye bağlama için hazır set)."""
    from ui.styles import T
    return {
        "plus": get_icon("plus", T["accent"]),
        "play": get_icon("play", T["success"]),
        "pause": get_icon("pause", T["warning"]),
        "trash": get_icon("trash", T["danger"]),
        "settings": get_icon("settings", T["text_secondary"]),
        "more": get_icon("more", T["text_secondary"]),
        "folder-open": get_icon("folder-open", T["info"]),
        "folder": get_icon("folder", T["text_secondary"]),
        "sheet": get_icon("sheet", T["info"]),
        "clock": get_icon("clock", T["text_secondary"]),
        "search": get_icon("search", T["accent"]),
        "list": get_icon("list", T["accent"]),
        "chart": get_icon("chart", T["accent"]),
        "globe": get_icon("globe", T["info"]),
        "broom": get_icon("broom", T["warning"]),
        "boom": get_icon("boom", T["danger"]),
        "stop": get_icon("stop", T["danger"]),
    }


# Geçerli ikon boyutu
ICON_SIZE = QSize(20, 20)
