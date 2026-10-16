import os
import urllib.parse
from typing import Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QComboBox,
    QSpinBox, QFormLayout, QCheckBox, QMessageBox
)
from PyQt6.QtCore import pyqtSignal
from core.database import detect_category, get_category_folder, CATEGORY_FOLDER_NAMES
from core.playlist_parser import is_youtube_playlist_url
from core.paths import get_disk_free_space
from ui.styles import format_size

DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads")

class AddDownloadDialog(QDialog):
    download_confirmed = pyqtSignal(dict)  # Emits data dict
    open_playlist_requested = pyqtSignal(str)  # Emits playlist url

    def __init__(self, initial_url: str = "", initial_filename: str = "",
                 headers: dict = None, initial_quality: str = "max",
                 base_download_dir: str = "", auto_categorize: bool = True,
                 site_rules=None, db=None, parent=None):
        super().__init__(parent)
        self.initial_url = initial_url
        self.headers = headers or {}
        self.initial_quality = initial_quality or "max"
        self.base_download_dir = base_download_dir or DEFAULT_DOWNLOAD_DIR
        self.auto_categorize = auto_categorize
        self.site_rules = site_rules
        self.db = db
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

        # Site rule banner
        self.banner_site_rule = QLabel("🌐 Site Kuralı: Bu web sitesi özel klasörünüze kaydedilecek.")
        self.banner_site_rule.setStyleSheet("""
            QLabel {
                background-color: #1f2335;
                color: #bb9af7;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 6px;
                border: 1px solid #7aa2f7;
            }
        """)
        self.banner_site_rule.hide()
        layout.addWidget(self.banner_site_rule)

        # File conflict warning banner
        self.banner_conflict = QLabel("⚠️ Bu isimde bir dosya klasörde zaten var! RipSync ayarlarınıza göre otomatik adlandırılacak.")
        self.banner_conflict.setStyleSheet("""
            QLabel {
                background-color: #2b221a;
                color: #ff9e64;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 6px;
                border: 1px solid #ff9e64;
            }
        """)
        self.banner_conflict.hide()
        layout.addWidget(self.banner_conflict)

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

        # Tags Input
        self.edit_tags = QLineEdit()
        self.edit_tags.setPlaceholderText("Örn: İş, Ders, Arşiv (Virgülle ayırın)")
        form.addRow("🏷️ Etiketler (Opsiyonel):", self.edit_tags)

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

        # Media options (Subtitles, Thumbnail, MP3 Metadata)
        media_opts_layout = QHBoxLayout()
        self.chk_download_subtitles = QCheckBox("📝 Altyazı (.srt)")
        self.chk_download_subtitles.setToolTip("Video ile birlikte altyazı dosyasını da kaydeder")
        self.chk_download_thumbnail = QCheckBox("🖼️ Kapak Resmi")
        self.chk_download_thumbnail.setToolTip("Video/şarkı kapak resmini (thumbnail) kaydeder")
        self.chk_embed_metadata = QCheckBox("🎵 MP3 Etiket & Kapak Göm")
        self.chk_embed_metadata.setChecked(True)
        self.chk_embed_metadata.setToolTip("MP3 dosyasına şarkıcı, parça adı ve albüm kapağını gömer")

        media_opts_layout.addWidget(self.chk_download_subtitles)
        media_opts_layout.addWidget(self.chk_download_thumbnail)
        media_opts_layout.addWidget(self.chk_embed_metadata)
        form.addRow("Medya Ekstraları:", media_opts_layout)

        # Connections (Threads)
        self.spin_connections = QSpinBox()
        self.spin_connections.setRange(1, 32)
        self.spin_connections.setValue(8)
        form.addRow("Bağlantı Sayısı (Parça):", self.spin_connections)

        # Priority (Bandwidth weighting)
        self.combo_priority = QComboBox()
        self.combo_priority.addItem("⚖️ Normal Öncelik (Dengeli Paylaşım)", "normal")
        self.combo_priority.addItem("🚀 Yüksek Öncelik (Yüksek Hız Payı)", "high")
        self.combo_priority.addItem("🐢 Düşük Öncelik (Arka Plan)", "low")
        form.addRow("Bant Genişliği Önceliği:", self.combo_priority)

        # Queue selector
        self.combo_queue = QComboBox()
        if self.db:
            queues = self.db.get_all_queues()
            for q in queues:
                self.combo_queue.addItem(f"🗂️ {q['name']}", q["id"])
        else:
            self.combo_queue.addItem("🗂️ Ana Kuyruk", "default")
        form.addRow("İndirme Kuyruğu:", self.combo_queue)

        # Auto-open on completion
        self.chk_auto_open = QCheckBox("🏁 İndirme tamamlandığında dosyayı otomatik aç")
        self.chk_auto_open.setStyleSheet("color: #7aa2f7; font-weight: bold;")
        self.chk_auto_open.setToolTip("İndirme bittiğinde Windows'ta dosyayı otomatik olarak çalıştırır / açar")
        form.addRow("", self.chk_auto_open)

        self.chk_auto_extract = QCheckBox("📦 Bittiğinde arşivi otomatik klasöre çıkart (.zip, .tar vb.)")
        self.chk_auto_extract.setStyleSheet("color: #9ece6a; font-weight: bold;")
        self.chk_auto_extract.setToolTip("Arşiv dosyası tamamlandığında otomatik olarak aynı klasöre açar")
        form.addRow("", self.chk_auto_extract)

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
        self._check_file_conflict()

    def _on_filename_changed(self, text: str):
        if not text:
            self._check_file_conflict()
            return
        cat = detect_category(text.strip())
        if self.combo_category.currentText() == "Otomatik" or self.combo_category.currentIndex() == 0:
            self._update_dir_by_category(cat)
        self._check_file_conflict()

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

        # Check if URL is TikTok, Instagram or Twitter/X
        is_tiktok = any(d in u_lower for d in ("tiktok.com", "tiktokv.com", "vt.tiktok.com", "vm.tiktok.com"))
        is_ig = any(d in u_lower for d in ("instagram.com", "instagr.am"))
        is_twitter = any(d in u_lower for d in ("twitter.com", "x.com")) and ("/status/" in u_lower or "/i/status/" in u_lower)

        if is_tiktok or is_ig or is_twitter:
            if is_tiktok:
                platform_name = "TikTok Filigransız Video"
            elif is_ig:
                platform_name = "Instagram Reels Filigransız Video"
            else:
                platform_name = "X (Twitter) HD Video"

            self.banner_watermark_free.setText(f"✨ {platform_name} Algılandı: Doğrudan Video İndirme Aktif!")
            self.banner_watermark_free.show()
            # Auto-set Category to Video
            idx_v = self.combo_category.findText("Video")
            if idx_v >= 0:
                self.combo_category.setCurrentIndex(idx_v)
            if not self.edit_filename.text() or self.edit_filename.text() in ("download", "video"):
                if is_tiktok:
                    default_prefix = "TikTok_Video.mp4"
                elif is_ig:
                    default_prefix = "Instagram_Reels.mp4"
                else:
                    default_prefix = "Twitter_Video.mp4"
                self.edit_filename.setText(default_prefix)
        else:
            self.banner_watermark_free.hide()

        # Check site rules
        if self.site_rules:
            matched_folder = self.site_rules.match_rule(url)
            if matched_folder:
                self.banner_site_rule.setText(f"🌐 Site Kuralı: '{matched_folder}' klasörüne yönlendirildi.")
                self.banner_site_rule.show()
                if not self._user_edited_dir:
                    self.edit_dir.setText(matched_folder)
            else:
                self.banner_site_rule.hide()
        else:
            self.banner_site_rule.hide()

        parsed = urllib.parse.urlparse(url.strip())
        path_name = os.path.basename(parsed.path)
        if path_name and not (is_tiktok or is_ig or is_twitter):
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
            self._check_file_conflict()

    def _check_file_conflict(self):
        fname = self.edit_filename.text().strip()
        fdir = self.edit_dir.text().strip()
        if fname and fdir and os.path.exists(os.path.join(fdir, fname)):
            conflict_action = self.db.get_conflict_setting() if self.db else "auto_rename"
            if conflict_action == "overwrite":
                self.banner_conflict.setText("⚠️ Dikkat: Bu isimde bir dosya klasörde zaten var! Çakışma ayarınız 'Üzerine Yaz' olduğu için mevcut dosya silinecektir.")
                self.banner_conflict.setStyleSheet("""
                    QLabel {
                        background-color: #3b1f1f;
                        color: #f7768e;
                        font-weight: bold;
                        padding: 6px 12px;
                        border-radius: 6px;
                        border: 1px solid #f7768e;
                    }
                """)
            elif conflict_action == "skip":
                self.banner_conflict.setText("⏭️ Bu isimde bir dosya klasörde zaten var! Çakışma ayarınız 'İndirmeyi Atla' olarak ayarlanmış.")
                self.banner_conflict.setStyleSheet("""
                    QLabel {
                        background-color: #2b221a;
                        color: #ff9e64;
                        font-weight: bold;
                        padding: 6px 12px;
                        border-radius: 6px;
                        border: 1px solid #ff9e64;
                    }
                """)
            else:
                self.banner_conflict.setText("🔄 Bu isimde bir dosya klasörde zaten var! RipSync ayarlarınıza göre otomatik adlandırılacak.")
                self.banner_conflict.setStyleSheet("""
                    QLabel {
                        background-color: #1a2b3c;
                        color: #7dcfff;
                        font-weight: bold;
                        padding: 6px 12px;
                        border-radius: 6px;
                        border: 1px solid #3d59a1;
                    }
                """)
            self.banner_conflict.show()
        else:
            self.banner_conflict.hide()

    def _submit(self, start_now: bool):
        url = self.edit_url.text().strip()
        if not url:
            return

        target_dir = self.edit_dir.text().strip()
        fname_final = self.edit_filename.text().strip()

        # Duplicate download check
        if self.db and self.db.get_duplicate_warning_setting():
            check_path = os.path.join(target_dir, fname_final) if fname_final else None
            dup = self.db.find_duplicate_download(url=url, filename=fname_final, save_path=check_path)
            if dup:
                from ui.duplicate_dialog import DuplicateDownloadDialog
                dlg = DuplicateDownloadDialog(dup, current_url=url, parent=self)
                dlg.exec()
                action = dlg.get_action()
                if action == DuplicateDownloadDialog.ACTION_CANCEL:
                    return
                elif action == DuplicateDownloadDialog.ACTION_OPEN_EXISTING:
                    self.reject()
                    return

        # Overwrite file conflict confirmation check
        conflict_action = self.db.get_conflict_setting() if self.db else "auto_rename"
        target_path = os.path.join(target_dir, fname_final) if (target_dir and fname_final) else ""
        if conflict_action == "overwrite" and target_path and os.path.exists(target_path):
            from ui.overwrite_dialog import OverwriteConfirmDialog
            ow_dlg = OverwriteConfirmDialog(target_dir, fname_final, parent=self)
            ow_dlg.exec()
            chosen_action = ow_dlg.get_action()
            if chosen_action == OverwriteConfirmDialog.ACTION_CANCEL:
                return
            elif chosen_action == OverwriteConfirmDialog.ACTION_AUTO_RENAME:
                new_name = ow_dlg.get_resolved_filename()
                self.edit_filename.setText(new_name)
                fname_final = new_name

        # Check disk free space
        free_space = get_disk_free_space(target_dir)
        if free_space >= 0 and free_space < 50 * 1024 * 1024:  # Less than 50 MB
            reply = QMessageBox.warning(
                self,
                "⚠️ Yetersiz Disk Alanı Uyarısı",
                f"Hedef sürücüde çok az boş alan kaldı ({format_size(free_space)}).\n"
                "İndirme diskin dolması nedeniyle yarım kalabilir.\nYine de devam etmek istiyor musunuz?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        cat_choice = self.combo_category.currentText()
        if cat_choice == "Otomatik":
            cat_choice = detect_category(self.edit_filename.text().strip())

        req_headers = dict(self.headers)
        req_headers["download_subtitles"] = self.chk_download_subtitles.isChecked()
        req_headers["download_thumbnail"] = self.chk_download_thumbnail.isChecked()
        req_headers["embed_metadata"] = self.chk_embed_metadata.isChecked()

        data = {
            "url": url,
            "save_dir": target_dir,
            "filename": self.edit_filename.text().strip(),
            "category": cat_choice,
            "connections": self.spin_connections.value(),
            "quality": self.combo_quality.currentData() or "max",
            "priority": self.combo_priority.currentData() or "normal",
            "tags": self.edit_tags.text().strip(),
            "queue_id": self.combo_queue.currentData() or "default",
            "start_now": start_now,
            "auto_open": self.chk_auto_open.isChecked(),
            "auto_extract": self.chk_auto_extract.isChecked(),
            "headers": req_headers
        }
        self.download_confirmed.emit(data)
        self.accept()
