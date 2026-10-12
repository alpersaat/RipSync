import os
import urllib.parse
from typing import Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QComboBox,
    QSpinBox, QFormLayout
)
from PyQt6.QtCore import pyqtSignal
from core.database import detect_category, get_category_folder, CATEGORY_FOLDER_NAMES
from core.playlist_parser import is_youtube_playlist_url

DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads")

class AddDownloadDialog(QDialog):
    download_confirmed = pyqtSignal(dict)  # Emits data dict
    open_playlist_requested = pyqtSignal(str)  # Emits playlist url

    def __init__(self, initial_url: str = "", initial_filename: str = "",
                 headers: dict = None, initial_quality: str = "max",
                 base_download_dir: str = "", auto_categorize: bool = True, parent=None):
        super().__init__(parent)
        self.initial_url = initial_url
        self.headers = headers or {}
        self.initial_quality = initial_quality or "max"
        self.base_download_dir = base_download_dir or DEFAULT_DOWNLOAD_DIR
        self.auto_categorize = auto_categorize
        self._user_edited_dir = False
        self.start_now = True

        self.setWindowTitle("RipSync - Yeni İndirme Başlat")
        self.resize(520, 260)
        self.setMinimumWidth(480)

        self._init_ui(initial_filename)

    def _init_ui(self, initial_filename: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(18, 18, 18, 18)

        # Playlist notification banner
        self.banner_playlist = QPushButton("📑 Bu bağlantı bir YouTube Çalma Listesi! RipSync Toplu İndiriciyi Aç ➔")
        self.banner_playlist.setStyleSheet("""
            QPushButton {
                background-color: #3d59a1;
                color: #ffffff;
                font-weight: bold;
                padding: 8px 12px;
                border-radius: 6px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #7aa2f7;
                color: #1a1b26;
            }
        """)
        self.banner_playlist.clicked.connect(self._open_playlist_dialog)
        self.banner_playlist.hide()
        layout.addWidget(self.banner_playlist)

        # Watermark-free notification banner for TikTok and Instagram
        self.banner_watermark_free = QLabel("✨ Instagram Reels / TikTok Algılandı: Filigransız (Watermark-Free) İndirme Desteği Aktif!")
        self.banner_watermark_free.setStyleSheet("""
            QLabel {
                background-color: #1a2b3c;
                color: #7dcfff;
                font-weight: bold;
                padding: 8px 12px;
                border-radius: 6px;
                border: 1px solid #3d59a1;
            }
        """)
        self.banner_watermark_free.hide()
        layout.addWidget(self.banner_watermark_free)


        form = QFormLayout()
        form.setSpacing(10)

        # URL Input
        self.edit_url = QLineEdit(self.initial_url)
        self.edit_url.setPlaceholderText("https://ornek.com/dosya.zip")
        self.edit_url.textChanged.connect(self._on_url_changed)
        form.addRow("Bağlantı Adresi (URL):", self.edit_url)

        # Save Directory
        initial_cat = detect_category(initial_filename) if initial_filename else "Others"
        if self.auto_categorize:
            initial_save_dir = get_category_folder(initial_cat, self.base_download_dir)
        else:
            initial_save_dir = self.base_download_dir

        dir_layout = QHBoxLayout()
        self.edit_dir = QLineEdit(initial_save_dir)
        btn_browse = QPushButton("Gözat...")
        btn_browse.setObjectName("btn_secondary")
        btn_browse.clicked.connect(self._browse_dir)
        dir_layout.addWidget(self.edit_dir)
        dir_layout.addWidget(btn_browse)
        form.addRow("Kayıt Klasörü:", dir_layout)

        # Filename Input
        self.edit_filename = QLineEdit(initial_filename)
        self.edit_filename.textChanged.connect(self._on_filename_changed)
        form.addRow("Dosya Adı:", self.edit_filename)

        # Category
        self.combo_category = QComboBox()
        self.combo_category.addItems(["Otomatik", "Video", "Müzik", "Belgeler", "Sıkıştırılmış", "Programlar", "Others"])
        self.combo_category.currentIndexChanged.connect(self._on_category_changed)
        form.addRow("Kategori:", self.combo_category)

        # Quality selector (for Video / Audio / Subtitle)
        self.combo_quality = QComboBox()
        self.combo_quality.addItem("🚀 En Yüksek Kalite (Maksimum - 4K / 1080p)", "max")
        self.combo_quality.addItem("🌟 1080p (Full HD MP4)", "1080p")
        self.combo_quality.addItem("✨ 720p (HD MP4)", "720p")
        self.combo_quality.addItem("📺 480p (Standart MP4)", "480p")
        self.combo_quality.addItem("🎵 Sadece Ses / Müzik (MP3)", "audio")
        self.combo_quality.addItem("📄 Altyazı (.srt İndir)", "subtitle")

        idx_q = self.combo_quality.findData(self.initial_quality)
        if idx_q >= 0:
            self.combo_quality.setCurrentIndex(idx_q)

        self.combo_quality.currentIndexChanged.connect(self._on_quality_changed)
        form.addRow("Video / Medya Kalitesi:", self.combo_quality)

        # Connections (Threads)
        self.spin_connections = QSpinBox()
        self.spin_connections.setRange(1, 32)
        self.spin_connections.setValue(8)
        form.addRow("Bağlantı Sayısı (Parça):", self.spin_connections)

        layout.addLayout(form)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_download_now = QPushButton("Şimdi İndir")
        self.btn_download_now.clicked.connect(lambda: self._submit(start_now=True))
        btn_layout.addWidget(self.btn_download_now)

        self.btn_queue = QPushButton("Daha Sonra İndir")
        self.btn_queue.setObjectName("btn_secondary")
        self.btn_queue.clicked.connect(lambda: self._submit(start_now=False))
        btn_layout.addWidget(self.btn_queue)

        btn_cancel = QPushButton("İptal")
        btn_cancel.setObjectName("btn_secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

        if self.initial_url and not initial_filename:
            self._on_url_changed(self.initial_url)

    def _update_dir_by_category(self, category: Optional[str] = None):
        if self._user_edited_dir or not self.auto_categorize:
            return
        cat = category or self.combo_category.currentText()
        if cat == "Otomatik":
            cat = detect_category(self.edit_filename.text().strip())
        target_dir = get_category_folder(cat, self.base_download_dir)
        self.edit_dir.setText(target_dir)

    def _on_filename_changed(self, text: str):
        if not text:
            return
        cat = detect_category(text.strip())
        if self.combo_category.currentText() == "Otomatik" or self.combo_category.currentIndex() == 0:
            self._update_dir_by_category(cat)

    def _on_category_changed(self):
        cat = self.combo_category.currentText()
        self._update_dir_by_category(cat)

    def _on_url_changed(self, url: str):
        if not url:
            self.banner_playlist.hide()
            self.banner_watermark_free.hide()
            return

        u_lower = url.strip().lower()

        # Check if URL is a YouTube playlist
        if is_youtube_playlist_url(url.strip()):
            self.banner_playlist.show()
        else:
            self.banner_playlist.hide()

        # Check if URL is TikTok or Instagram
        is_tiktok = any(d in u_lower for d in ("tiktok.com", "tiktokv.com", "vt.tiktok.com", "vm.tiktok.com"))
        is_ig = any(d in u_lower for d in ("instagram.com", "instagr.am"))

        if is_tiktok or is_ig:
            platform_name = "TikTok" if is_tiktok else "Instagram Reels"
            self.banner_watermark_free.setText(f"✨ {platform_name} Algılandı: Filigransız (Watermark-Free) Video İndirme Aktif!")
            self.banner_watermark_free.show()
            # Auto-set Category to Video
            idx_v = self.combo_category.findText("Video")
            if idx_v >= 0:
                self.combo_category.setCurrentIndex(idx_v)
            if not self.edit_filename.text() or self.edit_filename.text() in ("download", "video"):
                default_prefix = "TikTok_Video.mp4" if is_tiktok else "Instagram_Reels.mp4"
                self.edit_filename.setText(default_prefix)
        else:
            self.banner_watermark_free.hide()

        parsed = urllib.parse.urlparse(url.strip())
        path_name = os.path.basename(parsed.path)
        if path_name and not (is_tiktok or is_ig):
            clean_name = urllib.parse.unquote(path_name).split("?")[0]
            if not self.edit_filename.text() or self.edit_filename.text() == "download":
                self.edit_filename.setText(clean_name)
                cat = detect_category(clean_name)
                idx = self.combo_category.findText(cat)
                if idx >= 0:
                    self.combo_category.setCurrentIndex(idx)
                else:
                    self._update_dir_by_category(cat)


    def _open_playlist_dialog(self):
        url = self.edit_url.text().strip()
        self.open_playlist_requested.emit(url)
        self.reject()

    def _on_quality_changed(self):
        q = self.combo_quality.currentData()
        name = self.edit_filename.text().strip()
        base = os.path.splitext(name)[0] if name else "download"
        if q == "audio":
            self.combo_category.setCurrentText("Müzik")
            if name.endswith(".mp4") or name.endswith(".mkv") or name.endswith(".webm") or name.endswith(".srt"):
                self.edit_filename.setText(f"{base}.mp3")
        elif q == "subtitle":
            self.combo_category.setCurrentText("Belgeler")
            if name.endswith(".mp4") or name.endswith(".mkv") or name.endswith(".webm") or name.endswith(".mp3"):
                self.edit_filename.setText(f"{base}.srt")
        else:
            if name.endswith(".mp3") or name.endswith(".srt"):
                self.edit_filename.setText(f"{base}.mp4")

    def _browse_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "Kayıt Klasörü Seç", self.edit_dir.text())
        if chosen:
            self._user_edited_dir = True
            self.edit_dir.setText(chosen)

    def _submit(self, start_now: bool):
        url = self.edit_url.text().strip()
        if not url:
            return

        cat_choice = self.combo_category.currentText()
        if cat_choice == "Otomatik":
            cat_choice = detect_category(self.edit_filename.text().strip())

        data = {
            "url": url,
            "save_dir": self.edit_dir.text().strip(),
            "filename": self.edit_filename.text().strip(),
            "category": cat_choice,
            "connections": self.spin_connections.value(),
            "quality": self.combo_quality.currentData() or "max",
            "start_now": start_now,
            "headers": self.headers
        }
        self.download_confirmed.emit(data)
        self.accept()
