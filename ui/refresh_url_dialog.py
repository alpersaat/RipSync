import os
import json
from typing import Dict, Any, Optional
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFormLayout, QGroupBox, QMessageBox, QFrame
)
from ui.styles import format_progress_size
from core.stream_downloader import is_stream_url


class RefreshUrlDialog(QDialog):
    """
    Dialog allowing users to refresh or update an expired download URL
    or manually supply a direct media stream URL when social platform scrapers break.
    """
    url_refreshed = pyqtSignal(str, str, dict)  # (download_id, new_url, new_headers)

    def __init__(self, download_record: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.record = download_record
        self.download_id = download_record.get("id", "")
        self.old_url = download_record.get("url", "")
        self.is_social = is_stream_url(self.old_url)
        self.is_error = download_record.get("status") == "Error"

        title = "RipSync - Manuel Link Gir / Bağlantıyı Yenile" if self.is_social or self.is_error else "RipSync - Bağlantı Adresini Yenile (Refresh URL)"
        self.setWindowTitle(title)
        self.resize(580, 420)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        # Social / Media Guidance Banner
        if self.is_social or self.is_error:
            banner_box = QFrame()
            banner_box.setStyleSheet("""
                QFrame {
                    background-color: #1f2335;
                    border: 1px solid #ff9e64;
                    border-radius: 8px;
                    padding: 8px;
                }
            """)
            b_layout = QVBoxLayout(banner_box)
            b_layout.setSpacing(6)

            lbl_b_title = QLabel("💡 Sosyal Medya İndirme Yardımı / Manuel Link Girişi")
            lbl_b_title.setStyleSheet("font-weight: bold; color: #ff9e64; font-size: 13px;")
            b_layout.addWidget(lbl_b_title)

            lbl_b_desc = QLabel(
                "YouTube, TikTok, Instagram veya X gibi platformlar sayfa yapısını değiştirdiğinde veya bot güvenliği uyguladığında otomatik çözümleme başarısız olabilir.\n"
                "• Videoyu tarayıcınızda açıp sağ tıklayarak 'Video adresini kopyala' deyin veya F12 Network sekmesinden doğrudan .mp4 bağlantısını bulun.\n"
                "• Yeni bağlantıyı aşağıdaki alana yapıştırıp 'Adresi Güncelle ve Devam Et' seçeneğini kullanın."
            )
            lbl_b_desc.setWordWrap(True)
            lbl_b_desc.setStyleSheet("color: #c0caf5; font-size: 11px; line-height: 140%;")
            b_layout.addWidget(lbl_b_desc)

            btn_open_browser = QPushButton("🌐 Videoyu Tarayıcıda Aç")
            btn_open_browser.setObjectName("btn_secondary")
            btn_open_browser.setStyleSheet("padding: 4px 10px; font-size: 11px; font-weight: bold;")
            btn_open_browser.clicked.connect(self._open_in_browser)
            b_layout.addWidget(btn_open_browser, alignment=Qt.AlignmentFlag.AlignLeft)

            layout.addWidget(banner_box)

        # Info Header Box
        grp_info = QGroupBox("İndirme Bilgileri & Durum")
        f_info = QFormLayout(grp_info)

        lbl_file = QLabel(self.record.get("filename", "Bilinmiyor"))
        lbl_file.setStyleSheet("font-weight: bold; color: #7aa2f7;")
        f_info.addRow("Dosya Adı:", lbl_file)

        # Current error if available
        err_msg = self.record.get("error_message")
        if err_msg:
            lbl_err = QLabel(err_msg)
            lbl_err.setWordWrap(True)
            lbl_err.setStyleSheet("color: #f7768e; font-size: 11px; font-weight: bold;")
            f_info.addRow("Karşılaşılan Sorun:", lbl_err)

        done = self.record.get("downloaded_size", 0)
        tot = self.record.get("total_size", -1)
        lbl_progress = QLabel(format_progress_size(done, tot))
        lbl_progress.setStyleSheet("color: #9ece6a; font-weight: bold;")
        f_info.addRow("Mevcut İlerleme:", lbl_progress)

        txt_old_url = self.old_url if len(self.old_url) <= 65 else self.old_url[:62] + "..."
        lbl_old = QLabel(txt_old_url)
        lbl_old.setToolTip(self.old_url)
        lbl_old.setStyleSheet("color: #565f89; font-size: 11px;")
        f_info.addRow("Eski / Mevcut URL:", lbl_old)

        layout.addWidget(grp_info)

        # New URL Box
        grp_input = QGroupBox("Yeni / Manuel İndirme Bağlantısı")
        f_input = QFormLayout(grp_input)

        url_layout = QHBoxLayout()
        self.edit_new_url = QLineEdit()
        self.edit_new_url.setPlaceholderText("Doğrudan video akış linkini (.mp4) veya yeni bağlantıyı buraya yapıştırın...")
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

        lbl_hint = QLabel("💡 Not: RipSync mevcut indirilmiş parçaları koruyacak ve yeni link üzerinden indirmeyi devam ettirecektir.")
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

    def _open_in_browser(self):
        if self.old_url and (self.old_url.startswith("http://") or self.old_url.startswith("https://")):
            QDesktopServices.openUrl(QUrl(self.old_url))

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
