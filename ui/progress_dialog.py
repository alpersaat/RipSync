import os
from typing import List, Dict, Any, Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QWidget, QFrame, QGridLayout,
    QSlider, QCheckBox, QComboBox, QGroupBox, QMessageBox
)
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QLinearGradient, QFont
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from ui.styles import format_size, format_speed, format_eta, T
from core.downloader import MultiThreadDownloader

class SegmentVisualizerWidget(QWidget):
    """
    IDM-style real-time segment progress visualizer.
    Draws each download thread's downloaded byte range along a single continuous bar.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.segments: List[Dict[str, Any]] = []
        self.total_size: int = -1
        self.setMinimumHeight(32)

    def update_segments(self, segments: List[Dict[str, Any]], total_size: int):
        self.segments = segments
        self.total_size = total_size
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()

        # Background track
        bg_color = QColor(T['bg_panel'])
        border_color = QColor(T['border'])
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1))
        painter.drawRoundedRect(0, 0, width - 1, height - 1, 6, 6)

        if self.total_size <= 0 or not self.segments:
            # Draw indeterminate or waiting
            painter.setPen(QColor(T['disabled_text']))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Bağlantı kuruluyor...")
            return

        # Palette of colors for distinct segments (IDM multi-thread visual feel)
        colors = [
            QColor(T['accent']), QColor(T['color_sky']), QColor(T['color_cyan']),
            QColor(T['success']), QColor(T['color_purple']), QColor(T['color_orange']),
            QColor(T['color_teal']), QColor(T['color_teal'])
        ]

        # Draw each segment's downloaded range
        for seg in self.segments:
            idx = seg.get("index", 0)
            start = seg.get("start", 0)
            curr = seg.get("current", 0)
            end = seg.get("end", 0)
            if end <= start:
                continue

            color = colors[idx % len(colors)]

            x_start = int((start / self.total_size) * width)
            x_curr = int((curr / self.total_size) * width)
            x_end = int((end / self.total_size) * width)

            w_downloaded = max(1, x_curr - x_start)

            # Draw downloaded portion
            grad = QLinearGradient(x_start, 0, x_start + w_downloaded, 0)
            grad.setColorAt(0, color.darker(110))
            grad.setColorAt(1, color.lighter(110))
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(x_start, 2, w_downloaded, height - 4)

            # Draw remaining partition boundary
            painter.setPen(QPen(QColor(T['border']), 1, Qt.PenStyle.DashLine))
            painter.drawLine(x_end, 2, x_end, height - 2)

            # Draw active head marker
            if seg.get("status") == "downloading" and x_curr < x_end:
                painter.setPen(QPen(QColor(T['text_on_accent']), 2))
                painter.drawLine(x_curr, 2, x_curr, height - 2)

        # Draw active connections count watermark
        active_conns = len([s for s in self.segments if s.get("status") == "downloading"])
        painter.setPen(QColor(255, 255, 255, 180))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.drawText(width - 65, height - 6, f"{len(self.segments)} Parça")

class ProgressDialog(QDialog):
    pause_requested = pyqtSignal(str)
    resume_requested = pyqtSignal(str)
    cancel_requested = pyqtSignal([str], [str, bool])
    refresh_url_requested = pyqtSignal(str)  # download_id
    speed_limit_changed = pyqtSignal(str, int)  # download_id, bytes_per_sec (0 for unlimited)
    auto_open_changed = pyqtSignal(str, bool)    # download_id, auto_open flag

    def __init__(self, download_id: str, filename: str, save_path: str, initial_speed_limit: int = 0, initial_auto_open: bool = False, parent=None):
        super().__init__(parent)
        self.download_id = download_id
        self.filename = filename
        self.save_path = save_path
        self.is_paused = False
        self.current_speed_limit_bps = initial_speed_limit
        self.initial_auto_open = initial_auto_open

        self.setWindowTitle(f"İndiriliyor: {filename}")
        self.resize(580, 420)
        self.setMinimumWidth(520)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        # File info section
        self.lbl_filename = QLabel(self.filename)
        self.lbl_filename.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {T['accent']};")
        layout.addWidget(self.lbl_filename)

        # Grid for metrics
        grid_frame = QFrame()
        grid_frame.setStyleSheet(f"background-color: {T['bg_panel']}; border-radius: 8px; padding: 6px;")
        grid = QGridLayout(grid_frame)
        grid.setVerticalSpacing(8)
        grid.setHorizontalSpacing(16)

        lbl_status_title = QLabel("Durum:")
        lbl_status_title.setStyleSheet(f"color: {T['text_secondary']}; font-weight: bold;")
        self.lbl_status = QLabel("Başlatılıyor...")
        grid.addWidget(lbl_status_title, 0, 0)
        grid.addWidget(self.lbl_status, 0, 1)

        lbl_size_title = QLabel("Dosya Boyutu:")
        lbl_size_title.setStyleSheet(f"color: {T['text_secondary']}; font-weight: bold;")
        self.lbl_size = QLabel("Hesaplanıyor...")
        grid.addWidget(lbl_size_title, 1, 0)
        grid.addWidget(self.lbl_size, 1, 1)

        lbl_speed_title = QLabel("İndirme Hızı:")
        lbl_speed_title.setStyleSheet(f"color: {T['text_secondary']}; font-weight: bold;")
        self.lbl_speed = QLabel("0 KB/s")
        grid.addWidget(lbl_speed_title, 0, 2)
        grid.addWidget(self.lbl_speed, 0, 3)

        lbl_eta_title = QLabel("Kalan Süre:")
        lbl_eta_title.setStyleSheet(f"color: {T['text_secondary']}; font-weight: bold;")
        self.lbl_eta = QLabel("--")
        grid.addWidget(lbl_eta_title, 1, 2)
        grid.addWidget(self.lbl_eta, 1, 3)

        layout.addWidget(grid_frame)

        # Main progress bar
        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        self.prog_bar.setFixedHeight(22)
        layout.addWidget(self.prog_bar)

        # Segment Visualizer
        lbl_segment_title = QLabel("Bağlantı Parçaları (Segment Streams):")
        lbl_segment_title.setStyleSheet(f"font-size: 11px; color: {T['text_secondary']}; font-weight: bold;")
        layout.addWidget(lbl_segment_title)

        self.segment_visualizer = SegmentVisualizerWidget()
        layout.addWidget(self.segment_visualizer)

        # Speed Limiter Control Panel (IDM Style)
        limiter_frame = QFrame()
        limiter_frame.setStyleSheet(f"background-color: {T['bg_panel']}; border: 1px solid {T['bg_hover']}; border-radius: 8px; padding: 6px;")
        limiter_layout = QVBoxLayout(limiter_frame)
        limiter_layout.setContentsMargins(10, 8, 10, 8)
        limiter_layout.setSpacing(6)

        limiter_header = QHBoxLayout()
        self.chk_limit = QCheckBox("⚡ Hız Sınırlayıcıyı Etkinleştir (Speed Limiter)")
        self.chk_limit.setStyleSheet(f"font-weight: bold; color: {T['accent']};")
        self.chk_limit.toggled.connect(self._on_speed_limit_toggled)
        limiter_header.addWidget(self.chk_limit)

        limiter_header.addStretch()

        self.lbl_limit_val = QLabel("Sınırsız (Tam Hız)")
        self.lbl_limit_val.setStyleSheet(f"font-weight: bold; color: {T['success']}; font-size: 12px;")
        limiter_header.addWidget(self.lbl_limit_val)

        limiter_layout.addLayout(limiter_header)

        slider_row = QHBoxLayout()
        self.slider_limit = QSlider(Qt.Orientation.Horizontal)
        self.slider_limit.setRange(256, 50 * 1024)  # 256 KB/s to 50 MB/s
        self.slider_limit.setSingleStep(256)
        self.slider_limit.setPageStep(1024)
        self.slider_limit.setValue(5 * 1024)  # Default 5 MB/s
        self.slider_limit.setEnabled(False)
        self.slider_limit.valueChanged.connect(self._on_slider_value_changed)
        slider_row.addWidget(self.slider_limit)

        self.combo_presets = QComboBox()
        self.combo_presets.addItem("Hazır Limitler...", None)
        self.combo_presets.addItem("512 KB/s", 512)
        self.combo_presets.addItem("1 MB/s", 1024)
        self.combo_presets.addItem("2 MB/s", 2048)
        self.combo_presets.addItem("5 MB/s (Önerilen)", 5120)
        self.combo_presets.addItem("10 MB/s", 10240)
        self.combo_presets.addItem("25 MB/s", 25600)
        self.combo_presets.addItem("50 MB/s", 51200)
        self.combo_presets.setEnabled(False)
        self.combo_presets.currentIndexChanged.connect(self._on_preset_selected)
        slider_row.addWidget(self.combo_presets)

        limiter_layout.addLayout(slider_row)
        layout.addWidget(limiter_frame)

        # Initialize limiter state from initial_speed_limit
        if self.current_speed_limit_bps > 0:
            self.chk_limit.setChecked(True)
            kb = max(256, self.current_speed_limit_bps // 1024)
            self.slider_limit.setValue(kb)
            self.slider_limit.setEnabled(True)
            self.combo_presets.setEnabled(True)
            self._update_limit_label(kb)
        else:
            self.chk_limit.setChecked(False)
        # Auto-open checkbox
        self.chk_auto_open = QCheckBox("🏁 İndirme tamamlandığında dosyayı otomatik aç")
        self.chk_auto_open.setStyleSheet(f"color: {T['accent']}; font-weight: bold; margin-top: 4px;")
        self.chk_auto_open.setChecked(self.initial_auto_open)
        self.chk_auto_open.toggled.connect(lambda checked: self.auto_open_changed.emit(self.download_id, checked))
        layout.addWidget(self.chk_auto_open)

        # Buttons
        btn_layout = QHBoxLayout()

        self.btn_manual_link = QPushButton("🔗 Manuel Link Gir / Yenile")
        self.btn_manual_link.setStyleSheet(f"""
            QPushButton {{
                background-color: {T['color_orange']};
                color: {T['bg_main']};
                font-weight: bold;
                padding: 6px 14px;
                border-radius: 6px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {T['warning']};
            }}
        """)
        self.btn_manual_link.setToolTip("İndirme hata verdiğinde yeni veya doğrudan video bağlantısını girmenizi sağlar")
        self.btn_manual_link.clicked.connect(lambda: self.refresh_url_requested.emit(self.download_id))
        self.btn_manual_link.hide()
        btn_layout.addWidget(self.btn_manual_link)

        btn_layout.addStretch()

        self.btn_pause = QPushButton("Duraklat")
        self.btn_pause.clicked.connect(self._toggle_pause)
        btn_layout.addWidget(self.btn_pause)

        self.btn_cancel = QPushButton("İptal")
        self.btn_cancel.setObjectName("btn_secondary")
        self.btn_cancel.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_close = QPushButton("Kapat")
        self.btn_close.setObjectName("btn_secondary")
        self.btn_close.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

    def _on_speed_limit_toggled(self, enabled: bool):
        self.slider_limit.setEnabled(enabled)
        self.combo_presets.setEnabled(enabled)
        if enabled:
            kb = self.slider_limit.value()
            self._update_limit_label(kb)
            self.current_speed_limit_bps = kb * 1024
            self.speed_limit_changed.emit(self.download_id, self.current_speed_limit_bps)
        else:
            self.lbl_limit_val.setText("Sınırsız (Tam Hız)")
            self.lbl_limit_val.setStyleSheet(f"font-weight: bold; color: {T['success']}; font-size: 12px;")
            self.current_speed_limit_bps = 0
            self.speed_limit_changed.emit(self.download_id, 0)

    def _on_slider_value_changed(self, value: int):
        if self.chk_limit.isChecked():
            self._update_limit_label(value)
            self.current_speed_limit_bps = value * 1024
            self.speed_limit_changed.emit(self.download_id, self.current_speed_limit_bps)

    def _on_preset_selected(self, index: int):
        val = self.combo_presets.currentData()
        if val is not None:
            self.slider_limit.setValue(val)

    def _update_limit_label(self, kb_val: int):
        if kb_val >= 1024:
            mb_val = kb_val / 1024.0
            if mb_val == int(mb_val):
                text = f"Maksimum: {int(mb_val)} MB/s"
            else:
                text = f"Maksimum: {mb_val:.1f} MB/s"
        else:
            text = f"Maksimum: {kb_val} KB/s"
        self.lbl_limit_val.setText(text)
        self.lbl_limit_val.setStyleSheet(f"font-weight: bold; color: {T['color_orange']}; font-size: 12px;")

    def _toggle_pause(self):
        if self.is_paused:
            self.is_paused = False
            self.btn_pause.setText("Duraklat")
            self.resume_requested.emit(self.download_id)
        else:
            self.is_paused = True
            self.btn_pause.setText("Devam Et")
            self.pause_requested.emit(self.download_id)

    def _on_cancel(self):
        if self.lbl_status.text() == "Completed" or self.prog_bar.value() == 100:
            self.close()
            return

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("İndirmeyi İptal Et - RipSync")
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setText("<h3>İndirmeyi iptal etmek yerine duraklatmak ister misiniz?</h3>")
        msg_box.setInformativeText(
            "Duraklatırsanız indirilen kısımlar diskte korunur ve dilediğiniz zaman kaldığı yerden devam edebilirsiniz.\n\n"
            "İptal ederseniz indirme süreci sonlandırılacaktır."
        )

        btn_pause = msg_box.addButton("⏸️ Duraklat (Önerilen)", QMessageBox.ButtonRole.AcceptRole)
        btn_cancel_keep = msg_box.addButton("⏹️ İptal Et (Dosyayı Koru)", QMessageBox.ButtonRole.ActionRole)
        btn_cancel_delete = msg_box.addButton("🗑️ İptal Et ve Dosyayı Sil", QMessageBox.ButtonRole.DestructiveRole)
        btn_dismiss = msg_box.addButton("Vazgeç", QMessageBox.ButtonRole.RejectRole)

        try:
            msg_box.setDefaultButton(btn_pause)
        except Exception:
            pass
        msg_box.exec()

        clicked = msg_box.clickedButton()
        if clicked == btn_pause:
            self.is_paused = True
            self.btn_pause.setText("Devam Et")
            self.pause_requested.emit(self.download_id)
            self.close()
        elif clicked == btn_cancel_keep:
            try:
                self.cancel_requested[str, bool].emit(self.download_id, False)
            except Exception:
                self.cancel_requested.emit(self.download_id)
            self.close()
        elif clicked == btn_cancel_delete:
            try:
                self.cancel_requested[str, bool].emit(self.download_id, True)
            except Exception:
                self.cancel_requested.emit(self.download_id)
            self.close()

    def update_progress(self, downloaded: int, total: int, speed: float, eta: int):
        if total > 0:
            pct = int((downloaded / total) * 100)
            self.prog_bar.setValue(min(100, pct))
            self.lbl_size.setText(f"{format_size(downloaded)} / {format_size(total)} (%{pct})")
        else:
            self.prog_bar.setValue(0)
            self.lbl_size.setText(f"{format_size(downloaded)} / Bilinmiyor")

        self.lbl_speed.setText(format_speed(speed))
        self.lbl_eta.setText(format_eta(eta))

    def update_segments(self, segments: List[Dict[str, Any]], total_size: int):
        self.segment_visualizer.update_segments(segments, total_size)

    def update_status(self, status: str, err: str = ""):
        self.lbl_status.setText(status if not err else f"Hata: {err}")
        if status == "Completed":
            self.lbl_status.setStyleSheet(f"color: {T['success']}; font-weight: bold;")
            self.btn_pause.setEnabled(False)
            self.prog_bar.setValue(100)
            self.lbl_speed.setText("Tamamlandı")
            self.lbl_eta.setText("0 sn")
            self.btn_manual_link.hide()
        elif status == "Paused":
            self.lbl_status.setStyleSheet(f"color: {T['warning']}; font-weight: bold;")
            self.btn_pause.setText("Devam Et")
            self.is_paused = True
            self.btn_manual_link.hide()
        elif status == "Downloading":
            self.lbl_status.setStyleSheet(f"color: {T['accent']}; font-weight: bold;")
            self.btn_pause.setText("Duraklat")
            self.is_paused = False
            self.btn_manual_link.hide()
        elif status == "Error":
            self.lbl_status.setStyleSheet(f"color: {T['danger']}; font-weight: bold;")
            self.lbl_status.setWordWrap(True)
            if err:
                self.lbl_status.setToolTip(err)
            self.btn_manual_link.show()
        else:
            self.btn_manual_link.hide()
