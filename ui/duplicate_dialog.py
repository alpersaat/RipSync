import os
from typing import Dict, Any, Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QFormLayout, QCheckBox
)
from PyQt6.QtCore import Qt
from ui.styles import format_size, T
from core.paths import show_in_explorer


class DuplicateDownloadDialog(QDialog):
    """
    Dialog shown when an added URL or target file already exists in download history or on disk.
    Offers:
    - Open existing file (if present on disk)
    - Re-download (start fresh)
    - Cancel
    """
    ACTION_CANCEL = "cancel"
    ACTION_RE_DOWNLOAD = "re_download"
    ACTION_OPEN_EXISTING = "open_existing"

    def __init__(self, existing_record: Dict[str, Any], current_url: str = "", parent=None):
        super().__init__(parent)
        self.record = existing_record
        self.current_url = current_url
        self.action = self.ACTION_CANCEL

        self.setWindowTitle("🛡️ Yinelenen İndirme Uyarısı")
        self.resize(520, 290)
        self.setMinimumWidth(460)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(18, 18, 18, 18)

        # Header warning banner
        lbl_banner = QLabel("⚠️ Bu dosya veya bağlantı daha önce indirilmiş ya da listenizde mevcut!")
        lbl_banner.setStyleSheet(f"""
            QLabel {{
                background-color: {T['warning_bg']};
                color: {T['color_orange']};
                font-weight: bold;
                font-size: 13px;
                padding: 10px 14px;
                border-radius: 6px;
                border: 1px solid {T['color_orange']};
            }}
        """)
        layout.addWidget(lbl_banner)

        # Details box
        grp = QGroupBox("Mevcut İndirme Bilgisi")
        form = QFormLayout(grp)
        form.setSpacing(8)

        fname = self.record.get("filename") or "Bilinmeyen Dosya"
        status = self.record.get("status") or "Bilinmiyor"
        save_path = self.record.get("save_path") or ""
        total_size = self.record.get("total_size", -1)
        date_added = self.record.get("date_added") or ""
        date_completed = self.record.get("date_completed") or ""

        status_tr_map = {
            "Completed": "✅ Tamamlandı",
            "Downloading": "⏳ İndiriliyor",
            "Queued": "📋 Kuyrukta Bekliyor",
            "Paused": "⏸️ Duraklatıldı",
            "Error": "❌ Hata"
        }
        status_text = status_tr_map.get(status, status)

        form.addRow("Dosya Adı:", QLabel(f"<b>{fname}</b>"))
        form.addRow("Durum:", QLabel(status_text))

        if total_size and total_size > 0:
            form.addRow("Boyut:", QLabel(format_size(total_size)))

        date_disp = date_completed if (status == "Completed" and date_completed) else date_added
        if date_disp:
            form.addRow("Tarih:", QLabel(date_disp))

        file_exists = bool(save_path and os.path.exists(save_path))
        disk_status = "✅ Diskte Mevcut" if file_exists else "⚠️ Diskte Bulunamadı (Silinmiş/Taşınmış)"
        lbl_disk = QLabel(disk_status)
        lbl_disk.setStyleSheet(f"color: {T['success']};" if file_exists else f"color: {T['danger']};")
        form.addRow("Kayıt Konumu:", lbl_disk)

        layout.addWidget(grp)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        # Open existing button (enabled if file exists)
        self.btn_open = QPushButton("📂 Dosyayı / Klasörü Aç")
        self.btn_open.setObjectName("btn_secondary")
        self.btn_open.setEnabled(file_exists)
        self.btn_open.clicked.connect(self._on_open_existing)
        btn_layout.addWidget(self.btn_open)

        btn_layout.addStretch()

        self.btn_redownload = QPushButton("🔄 Yeniden İndir")
        self.btn_redownload.setStyleSheet(f"background-color: {T['accent']}; color: {T['bg_main']}; font-weight: bold; padding: 6px 14px;")
        self.btn_redownload.clicked.connect(self._on_redownload)
        btn_layout.addWidget(self.btn_redownload)

        self.btn_cancel = QPushButton("İptal")
        self.btn_cancel.setObjectName("btn_secondary")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def _on_open_existing(self):
        save_path = self.record.get("save_path", "")
        if save_path and os.path.exists(save_path):
            show_in_explorer(save_path)
        self.action = self.ACTION_OPEN_EXISTING
        self.accept()

    def _on_redownload(self):
        self.action = self.ACTION_RE_DOWNLOAD
        self.accept()

    def get_action(self) -> str:
        return self.action

