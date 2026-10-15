import os
import json
from typing import Dict, Any, Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFormLayout, QGroupBox, QMessageBox
)
from ui.styles import format_progress_size


class RefreshUrlDialog(QDialog):
    """
    Dialog allowing users to refresh or update an expired download URL
    (e.g. for Google Drive, Mega, CDN temporary tokens) without losing already-downloaded bytes.
    """
    url_refreshed = pyqtSignal(str, str, dict)  # (download_id, new_url, new_headers)

    def __init__(self, download_record: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.record = download_record
        self.download_id = download_record.get("id", "")
        self.setWindowTitle("RipSync - Bağlantı Adresini Yenile (Refresh URL)")
        self.resize(540, 360)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(18, 18, 18, 18)

        # Info Header Box
        grp_info = QGroupBox("İndirme Durumu & Bilgileri")
        f_info = QFormLayout(grp_info)

        lbl_file = QLabel(self.record.get("filename", "Bilinmiyor"))
        lbl_file.setStyleSheet("font-weight: bold; color: #7aa2f7;")
        f_info.addRow("Dosya Adı:", lbl_file)

        done = self.record.get("downloaded_size", 0)
        tot = self.record.get("total_size", -1)
        lbl_progress = QLabel(format_progress_size(done, tot))
        lbl_progress.setStyleSheet("color: #9ece6a; font-weight: bold;")
        f_info.addRow("Mevcut İlerleme:", lbl_progress)

        old_url = self.record.get("url", "")
        txt_old_url = old_url if len(old_url) <= 65 else old_url[:62] + "..."
        lbl_old = QLabel(txt_old_url)
        lbl_old.setToolTip(old_url)
        lbl_old.setStyleSheet("color: #565f89; font-size: 11px;")
        f_info.addRow("Eski (Süresi Dolan) URL:", lbl_old)

        layout.addWidget(grp_info)

        # New URL Box
        grp_input = QGroupBox("Yeni İndirme Bağlantısı")
        f_input = QFormLayout(grp_input)

        url_layout = QHBoxLayout()
        self.edit_new_url = QLineEdit()
        self.edit_new_url.setPlaceholderText("Tarayıcıdan kopyalanan yeni bağlantıyı yapıştırın...")
        btn_paste = QPushButton("📋 Yapıştır")
        btn_paste.setObjectName("btn_secondary")
        btn_paste.clicked.connect(self._paste_clipboard)
        url_layout.addWidget(self.edit_new_url)
        url_layout.addWidget(btn_paste)
        f_input.addRow("Yeni URL:", url_layout)

        self.edit_referer = QLineEdit()
        self.edit_referer.setPlaceholderText("İsteğe bağlı Referer adresi...")
        # Check existing headers
        old_headers = {}
        if self.record.get("headers_json"):
            try:
                old_headers = json.loads(self.record["headers_json"])
            except Exception:
                pass
        if "Referer" in old_headers:
            self.edit_referer.setText(old_headers["Referer"])
        f_input.addRow("Yeni Referer (İsteğe Bağlı):", self.edit_referer)

        layout.addWidget(grp_input)

        lbl_hint = QLabel("💡 Not: RipSync mevcut indirilmiş parçaları koruyacak ve yeni link üzerinden kaldığı byte'tan indirmeye devam edecektir.")
        lbl_hint.setWordWrap(True)
        lbl_hint.setStyleSheet("color: #7aa2f7; font-size: 11px;")
        layout.addWidget(lbl_hint)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("İptal")
        btn_cancel.setObjectName("btn_secondary")
        btn_cancel.clicked.connect(self.reject)

        btn_confirm = QPushButton("🔄 Adresi Güncelle ve Devam Et")
        btn_confirm.clicked.connect(self._on_confirm)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_confirm)
        layout.addLayout(btn_layout)

    def _paste_clipboard(self):
        from PyQt6.QtWidgets import QApplication
        clip = QApplication.clipboard().text().strip()
        if clip:
            self.edit_new_url.setText(clip)

    def _on_confirm(self):
        new_url = self.edit_new_url.text().strip()
        if not new_url or not (new_url.startswith("http://") or new_url.startswith("https://")):
            QMessageBox.warning(self, "Uyarı", "Lütfen geçerli bir http:// veya https:// bağlantı adresi giriniz.")
            return

        headers = {}
        if self.record.get("headers_json"):
            try:
                headers = json.loads(self.record["headers_json"])
            except Exception:
                pass

        ref = self.edit_referer.text().strip()
        if ref:
            headers["Referer"] = ref

        self.url_refreshed.emit(self.download_id, new_url, headers)
        self.accept()

