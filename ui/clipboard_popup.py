import os
import urllib.parse
from typing import Optional
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QPoint, QEasingCurve, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QApplication, QGraphicsDropShadowEffect
)
from PyQt6.QtGui import QColor, QFont, QCursor
from ui.styles import T  # noqa: F401  (tema tokenlari)

class ClipboardNotificationPopup(QWidget):
    """
    Sleek, modern floating toast notification that slides in at the bottom-right
    of the primary desktop screen whenever a downloadable link or video link
    is copied to the clipboard.
    """
    download_requested = pyqtSignal(str, bool, dict)  # url, start_immediately, info
    dismissed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_url = ""
        self.current_info = {}
        self._auto_close_timer = QTimer(self)
        self._auto_close_timer.setInterval(8000)  # 8 seconds before auto-dismiss
        self._auto_close_timer.setSingleShot(True)
        self._auto_close_timer.timeout.connect(self.hide_animated)

        self.anim = None
        self._init_window_flags()
        self._init_ui()

    def _init_window_flags(self):
        # Frameless, Always on Top, Tool window (does not steal focus or show in taskbar)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedSize(360, 130)

    def _init_ui(self):
        # Container widget for styling and drop shadow
        self.container = QWidget(self)
        self.container.setGeometry(10, 10, 340, 110)
        self.container.setObjectName("container")
        self.container.setStyleSheet(f"""
            QWidget#container {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {T['bg_panel']}, stop:1 {T['bg_main']});
                border: 1px solid {T['accent_primary']};
                border-radius: 12px;
            }}
        """)

        # Drop shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 4)
        self.container.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        # Header bar: Icon + Title + Close Button
        header = QHBoxLayout()
        header.setSpacing(8)

        self.lbl_icon = QLabel("⚡")
        self.lbl_icon.setStyleSheet(f"font-size: 16px; color: {T['accent']};")

        self.lbl_title = QLabel("İndirme Bağlantısı Algılandı")
        self.lbl_title.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {T['accent']};")

        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(22, 22)
        self.btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_close.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {T['disabled_text']};
                font-size: 13px;
                font-weight: bold;
                border-radius: 11px;
            }}
            QPushButton:hover {{
                background-color: {T['danger']};
                color: {T['text_on_accent']};
            }}
        """)
        self.btn_close.clicked.connect(self.hide_animated)

        header.addWidget(self.lbl_icon)
        header.addWidget(self.lbl_title, 1)
        header.addWidget(self.btn_close)
        layout.addLayout(header)

        # Subtitle / Domain & File info
        self.lbl_info = QLabel("Link indirilsin mi?")
        self.lbl_info.setStyleSheet(f"color: {T['text_primary']}; font-size: 11px;")
        self.lbl_info.setWordWrap(True)
        layout.addWidget(self.lbl_info)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_quick_download = QPushButton("⚡ Hemen İndir")
        self.btn_quick_download.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_quick_download.setStyleSheet(f"""
            QPushButton {{
                background-color: {T['accent']};
                color: {T['bg_main']};
                font-weight: bold;
                font-size: 11px;
                padding: 6px 10px;
                border: none;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {T['color_blue']};
            }}
            QPushButton:pressed {{
                background-color: {T['accent_primary']};
                color: {T['text_on_accent']};
            }}
        """)
        self.btn_quick_download.clicked.connect(self._on_quick_download)

        self.btn_open_dialog = QPushButton("Ayarlarla İndir...")
        self.btn_open_dialog.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_open_dialog.setStyleSheet(f"""
            QPushButton {{
                background-color: {T['bg_card']};
                color: {T['text_primary']};
                font-size: 11px;
                padding: 6px 10px;
                border: 1px solid {T['border']};
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {T['bg_hover']};
                border-color: {T['accent']};
                color: {T['text_on_accent']};
            }}
        """)
        self.btn_open_dialog.clicked.connect(self._on_open_dialog)

        self.btn_ignore = QPushButton("Yoksay")
        self.btn_ignore.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_ignore.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {T['text_secondary']};
                font-size: 11px;
                padding: 6px 8px;
                border: none;
            }}
            QPushButton:hover {{
                color: {T['danger']};
            }}
        """)
        self.btn_ignore.clicked.connect(self.hide_animated)

        btn_layout.addWidget(self.btn_quick_download)
        btn_layout.addWidget(self.btn_open_dialog)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_ignore)

        layout.addLayout(btn_layout)

    def show_for_url(self, url: str, source_info: dict):
        self.current_url = url
        self.current_info = source_info or {}
        service_name = source_info.get("service", "Bağlantı")
        icon = source_info.get("icon", "⚡")
        is_video = source_info.get("is_video", False)

        self.lbl_icon.setText(icon)
        self.lbl_title.setText(f"{service_name} Bağlantısı Kopyalandı")

        # Format URL / file preview
        parsed = urllib.parse.urlparse(url)
        path_name = os.path.basename(parsed.path) or parsed.netloc
        if len(path_name) > 35:
            path_name = path_name[:32] + "..."

        is_playlist = source_info.get("is_playlist", False)
        is_watermark_free = source_info.get("watermark_free", False)

        if is_playlist:
            self.lbl_info.setText(f"<b>{service_name}</b> algılandı! Videolar taranıp seçilerek indirilsin mi?")
            self.btn_quick_download.setText("📑 Listeyi Tara ve İndir")
        elif is_watermark_free:
            self.lbl_info.setText(f"<b>{service_name}</b> filigransız (watermark-free) video olarak indirilsin mi?")
            self.btn_quick_download.setText("✨ Filigransız İndir")
        elif is_video:
            self.lbl_info.setText(f"<b>{service_name}</b> videosu tek tıkla kuyruğa eklensin mi?")
            self.btn_quick_download.setText("⚡ Hemen İndir")
        else:
            self.lbl_info.setText(f"Dosya: <b>{path_name}</b> indirilsin mi?")
            self.btn_quick_download.setText("⚡ Hemen İndir")


        if self.anim:
            self.anim.stop()
        self.anim = QPropertyAnimation(self, b"pos")
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            target_x = geo.x() + geo.width() - self.width() - 16
            target_y = geo.y() + geo.height() - self.height() - 16
            start_y = geo.y() + geo.height() + 20

            self.move(target_x, start_y)
            self.show()

            # Smooth slide-up animation
            self.anim.setDuration(350)
            self.anim.setStartValue(QPoint(target_x, start_y))
            self.anim.setEndValue(QPoint(target_x, target_y))
            self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.anim.start()
        else:
            self.show()

        # Restart auto-close timer
        self._auto_close_timer.start()

    def hide_animated(self):
        self._auto_close_timer.stop()
        if self.anim:
            self.anim.stop()
        screen = QApplication.primaryScreen()
        if screen and self.isVisible():
            geo = screen.availableGeometry()
            target_x = self.x()
            target_y = geo.y() + geo.height() + 20

            self.anim = QPropertyAnimation(self, b"pos")
            self.anim.setDuration(250)
            self.anim.setStartValue(self.pos())
            self.anim.setEndValue(QPoint(target_x, target_y))
            self.anim.setEasingCurve(QEasingCurve.Type.InCubic)
            self.anim.finished.connect(self._finish_hide)
            self.anim.start()
        else:
            self.hide()
            self.dismissed.emit()

    def _finish_hide(self):
        if self.anim:
            try:
                self.anim.finished.disconnect(self._finish_hide)
            except Exception:
                pass
        self.hide()
        self.dismissed.emit()

    def _on_quick_download(self):
        self._auto_close_timer.stop()
        url = self.current_url
        info = self.current_info
        self.hide()
        self.download_requested.emit(url, True, info)

    def _on_open_dialog(self):
        self._auto_close_timer.stop()
        url = self.current_url
        info = self.current_info
        self.hide()
        self.download_requested.emit(url, False, info)

    # Pause timer if mouse is hovering over popup
    def enterEvent(self, event):
        self._auto_close_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._auto_close_timer.start()
        super().leaveEvent(event)
