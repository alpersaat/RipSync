"""Yeni İndirme Başlat diyaloğu.

Kullanıcı odaklı düzen:
  * Medya önizlemesi (kapak, gerçek başlık, süre, tahmini boyut) — dosya adı
    artık sayfa başlığından değil, gerçek medya bilgisinden gelir.
  * Uzun onay kutuları tam genişlikte (metin kesilmez).
  * Parça sayısı / öncelik / kuyruk gibi teknik alanlar "Gelişmiş seçenekler"
    bölümünde katlanmış durur.
  * Kalite listesi kaynağa uyarlanır (altyazı yoksa seçenek pasif olur).
"""

import os
import re
import urllib.parse
from typing import Any, List, Optional

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from core.categories import CATEGORY_FOLDER_NAMES, detect_category, get_category_folder
from core.playlist_parser import is_youtube_playlist_url
from core.paths import get_disk_free_space
from ui.language import label_pair
from ui.styles import format_size, T

DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads")

# Kategori: görünen ad -> çekirdekteki iç ad (klasör seçimi iç adla yapılır)
CATEGORY_ITEMS: List[tuple] = [
    ("Otomatik", "Otomatik"),
    ("Video", "Video"),
    ("Müzik", "Music"),
    ("Belgeler", "Documents"),
    ("Arşivler", "Compressed"),
    ("Programlar", "Programs"),
    ("Diğer", "Others"),
]

# Akış/sayfa başlıklarından gelen anlamsız dosya adları
_GENERIC_NAME_WORDS = {
    "anasayfa", "home", "akış", "akis", "feed", "explore", "keşfet", "kesfet",
    "bildirimler", "notifications", "profil", "profile", "video", "videos",
    "download", "indir", "x", "twitter", "tiktok", "instagram", "youtube",
    "untitled", "media",
}
_GENERIC_NAME_PREFIXES = (
    "x video", "twitter video", "tiktok video", "instagram video",
    "instagram reels", "video",
)

_VIDEO_PAGE_HINTS = (
    "youtube.com", "youtu.be", "x.com", "twitter.com", "tiktok.com",
    "instagram.com", "vimeo.com", "dailymotion.com", "twitch.tv",
    "facebook.com", "fb.watch", "bilibili.com",
)
_DIRECT_FILE_RE = re.compile(
    r"\.(zip|rar|7z|tar|gz|bz2|exe|msi|iso|apk|pdf|docx?|xlsx?|pptx?|txt|csv|srt)($|\?|/)",
    re.IGNORECASE,
)

_QUALITY_MAX_HEIGHT = {"1080p": 1080, "720p": 720, "480p": 480}

# Arka planda çalışan önizleme iş parçacıkları; pencere kapansa da nesne
# çöp toplanmasın diye burada tutulur (Qt: "destroyed while running" olmasın).
_LIVE_THREADS: List[QThread] = []


def _sanitize_name_part(text: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._-")
    return cleaned[:80].strip()


def is_generic_media_name(name: str) -> bool:
    """Ad, sayfa başlığından gelen anlamsız bir isim mi? ("Anasayfa _ X" vb.)"""
    base = os.path.splitext((name or "").strip())[0]
    low = re.sub(r"[\s._\-|/]+", " ", base).strip().lower()
    low = re.sub(r"\s*(x|twitter|tiktok|instagram|youtube)$", "", low).strip()
    if not low:
        return True
    if low in _GENERIC_NAME_WORDS:
        return True
    return any(low == p or low.startswith(p + " ") for p in _GENERIC_NAME_PREFIXES)


def is_media_page_url(url: str) -> bool:
    """URL bir video/medya sayfası mı (doğrudan dosya indirmesi değil)?"""
    u = (url or "").strip().lower()
    if not u.startswith(("http://", "https://")):
        return False
    if _DIRECT_FILE_RE.search(urllib.parse.urlparse(u).path):
        return False
    return any(hint in u for hint in _VIDEO_PAGE_HINTS)


def _format_duration(seconds: Any) -> str:
    try:
        total = int(float(seconds or 0))
    except (TypeError, ValueError):
        return ""
    if total <= 0:
        return ""
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _best_format(formats: List[dict], predicate, height_target: int = 0) -> Optional[dict]:
    candidates = [f for f in formats if predicate(f)]
    if not candidates:
        return None
    fitted = [f for f in candidates if 0 < (f.get("height") or 0) <= height_target] if height_target else []
    if fitted:
        candidates = fitted
    with_size = [f for f in candidates if (f.get("filesize") or 0) > 0]
    return max(with_size or candidates, key=lambda f: f.get("height") or 0)


def estimate_media_size(info: Optional[dict], quality: str) -> int:
    """Seçilen kalite için yaklaşık toplam boyut (bayt); bilinmiyorsa 0."""
    formats = (info or {}).get("formats") or []
    if not formats or quality == "subtitle":
        return 0
    if quality == "audio":
        fmt = _best_format(formats, lambda f: f.get("has_audio"))
    else:
        fmt = _best_format(formats, lambda f: f.get("has_video"), _QUALITY_MAX_HEIGHT.get(quality, 0))
    if not fmt:
        return 0
    size = fmt.get("filesize") or 0
    if quality != "audio" and not fmt.get("has_audio"):
        audio_fmt = _best_format(formats, lambda f: f.get("has_audio") and not f.get("has_video"))
        if audio_fmt:
            size += audio_fmt.get("filesize") or 0
    return size


def max_available_height(info: Optional[dict]) -> int:
    heights = [f.get("height") or 0 for f in (info or {}).get("formats") or [] if f.get("has_video")]
    return max(heights) if heights else 0


class MediaInfoThread(QThread):
    """Medya bilgisini (başlık, süre, kapak, formatlar) arka planda çeker."""

    loaded = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        info = None
        try:
            from core.media_sniffer import MediaSniffer
            info = MediaSniffer.extract_info(self.url)
        except Exception:
            info = None
        if self._stop:
            return
        if not info:
            self.failed.emit("Bu bağlantının bilgileri alınamadı; indirme başarısız olabilir.")
            return

        thumb_url = info.get("thumbnail") or ""
        if thumb_url:
            try:
                import httpx
                resp = httpx.get(
                    thumb_url, headers={"User-Agent": "Mozilla/5.0"},
                    timeout=5.0, follow_redirects=True,
                )
                if resp.status_code == 200 and 0 < len(resp.content) < 4 * 1024 * 1024:
                    info["_thumb_bytes"] = resp.content
            except Exception:
                pass

        if not self._stop:
            self.loaded.emit(info)


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
        self._user_edited_filename = False
        self._updating_filename = False
        self._metadata_user_touched = False
        self._syncing_metadata = False
        self._media_info: Optional[dict] = None
        self._probed_url = ""
        self._info_thread: Optional[MediaInfoThread] = None
        self._closing = False
        self.start_now = True

        self.setWindowTitle("RipSync - Yeni İndirme Başlat")
        self.setMinimumWidth(620)

        self._init_ui(initial_filename)

    # ------------------------------------------------------------------ UI ---
    def _init_ui(self, initial_filename: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 16, 18, 16)

        # Playlist notification banner
        self.banner_playlist = QPushButton("📑 Bu bağlantı bir YouTube Çalma Listesi! RipSync Toplu İndiriciyi Aç ➔")
        self.banner_playlist.setStyleSheet(f"""
            QPushButton {{
                background-color: {T['accent_primary']};
                color: {T['text_on_accent']};
                font-weight: bold;
                padding: 8px 12px;
                border-radius: 6px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: {T['accent']};
                color: {T['bg_main']};
            }}
        """)
        self.banner_playlist.clicked.connect(self._open_playlist_dialog)
        self.banner_playlist.hide()
        layout.addWidget(self.banner_playlist)

        # Watermark-free notification banner for TikTok and Instagram
        self.banner_watermark_free = QLabel("✨ Instagram Reels / TikTok Algılandı: Filigransız (Watermark-Free) İndirme Desteği Aktif!")
        self.banner_watermark_free.setWordWrap(True)
        self.banner_watermark_free.setStyleSheet(f"""
            QLabel {{
                background-color: {T['info_bg']};
                color: {T['color_cyan']};
                font-weight: bold;
                padding: 8px 12px;
                border-radius: 6px;
                border: 1px solid {T['accent_primary']};
            }}
        """)
        self.banner_watermark_free.hide()
        layout.addWidget(self.banner_watermark_free)

        # Oturum gerektiren siteler için uyarı (X/Twitter vb.)
        self.banner_login_needed = QLabel(
            "ℹ️ X (Twitter) videoları için tarayıcı oturumu gerekebilir. İndirme başarısız olursa "
            "videoyu tarayıcıda açıp tekrar deneyin."
        )
        self.banner_login_needed.setWordWrap(True)
        self.banner_login_needed.setStyleSheet(f"""
            QLabel {{
                background-color: {T['warning_bg']};
                color: {T['color_orange']};
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 6px;
                border: 1px solid {T['color_orange']};
            }}
        """)
        self.banner_login_needed.hide()
        layout.addWidget(self.banner_login_needed)

        # Site rule banner
        self.banner_site_rule = QLabel("🌐 Site Kuralı: Bu web sitesi özel klasörünüze kaydedilecek.")
        self.banner_site_rule.setWordWrap(True)
        self.banner_site_rule.setStyleSheet(f"""
            QLabel {{
                background-color: {T['bg_panel']};
                color: {T['color_purple']};
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 6px;
                border: 1px solid {T['accent']};
            }}
        """)
        self.banner_site_rule.hide()
        layout.addWidget(self.banner_site_rule)

        # File conflict warning banner
        self.banner_conflict = QLabel("⚠️ Bu isimde bir dosya klasörde zaten var! RipSync ayarlarınıza göre otomatik adlandırılacak.")
        self.banner_conflict.setWordWrap(True)
        self.banner_conflict.setStyleSheet(f"""
            QLabel {{
                background-color: {T['warning_bg']};
                color: {T['color_orange']};
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 6px;
                border: 1px solid {T['color_orange']};
            }}
        """)
        self.banner_conflict.hide()
        layout.addWidget(self.banner_conflict)

        layout.addWidget(self._build_preview_card())

        # ---- Kaydırılabilir form gövdesi ------------------------------------
        self.form_scroll = QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        form_host = QWidget()
        host_layout = QVBoxLayout(form_host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        self._form = form

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
        dir_layout.setSpacing(8)
        self.edit_dir = QLineEdit(initial_save_dir)
        btn_browse = QPushButton("Gözat...")
        btn_browse.setObjectName("btn_secondary")
        btn_browse.clicked.connect(self._browse_dir)
        dir_layout.addWidget(self.edit_dir)
        dir_layout.addWidget(btn_browse)
        form.addRow("Kayıt Klasörü:", dir_layout)

        # Klasörün nasıl belirlendiğini açıkça söyle (kategori mi, özel klasör mü)
        self.lbl_dir_note = QLabel("")
        self.lbl_dir_note.setWordWrap(True)
        self.lbl_dir_note.setStyleSheet(f"color: {T['text_secondary']}; font-size: 11px;")
        form.addRow(self.lbl_dir_note)

        # Filename Input
        self.edit_filename = QLineEdit(initial_filename)
        self.edit_filename.setPlaceholderText("dosya_adi.mp4")
        self.edit_filename.textChanged.connect(self._on_filename_changed)
        form.addRow("Dosya Adı:", self.edit_filename)

        # Category
        self.combo_category = QComboBox()
        for label, internal in CATEGORY_ITEMS:
            self.combo_category.addItem(label, internal)
        self.combo_category.setToolTip(
            "Kategori, dosyanın kaydedileceği alt klasörü belirler "
            "(Video ➔ Videolar, Müzik ➔ Müzik ...).\n"
            "Kayıt klasörünü elle değiştirirseniz kategori yok sayılır."
        )
        self.combo_category.currentIndexChanged.connect(self._on_category_changed)
        form.addRow("Kategori (klasörü belirler):", self.combo_category)

        # Quality selector (for Video / Audio / Subtitle)
        self.combo_quality = QComboBox()
        self.combo_quality.addItem("🏆 En Yüksek Kalite (4K / 1080p ne varsa)", "max")
        self.combo_quality.addItem("🎬 1080p (Full HD MP4)", "1080p")
        self.combo_quality.addItem("🎬 720p (HD MP4)", "720p")
        self.combo_quality.addItem("🎬 480p (Standart MP4)", "480p")
        self.combo_quality.addItem("🎵 Sadece Ses / Müzik (MP3)", "audio")
        self.combo_quality.addItem("📄 Altyazı (.srt)", "subtitle")

        idx_q = self.combo_quality.findData(self.initial_quality)
        if idx_q >= 0:
            self.combo_quality.setCurrentIndex(idx_q)

        self.combo_quality.currentIndexChanged.connect(self._on_quality_changed)
        form.addRow("Video / Medya Kalitesi:", self.combo_quality)

        # Kaliteyle ilgili bilgi/uyarı satırı (kaynak yetmiyorsa, altyazı yoksa)
        self.lbl_quality_note = QLabel("")
        self.lbl_quality_note.setWordWrap(True)
        self.lbl_quality_note.setStyleSheet(f"color: {T['color_orange']}; font-size: 11px;")
        self.lbl_quality_note.hide()
        form.addRow(self.lbl_quality_note)

        # Etiketler
        self.edit_tags = QLineEdit()
        self.edit_tags.setPlaceholderText("Örn: İş, Ders, Arşiv (Virgülle ayırın)")
        form.addRow("🏷️ Etiketler (Opsiyonel):", self.edit_tags)

        # ---- Medya ekleri: tam genişlikte satır (etiketler kesilmez) --------
        extras_host = QWidget()
        extras_layout = QHBoxLayout(extras_host)
        extras_layout.setContentsMargins(0, 0, 0, 0)
        extras_layout.setSpacing(16)
        self.chk_download_subtitles = QCheckBox("📝 Altyazıyı da indir (.srt)")
        self.chk_download_subtitles.setToolTip("Video ile birlikte altyazı dosyasını da kaydeder")
        self.chk_download_thumbnail = QCheckBox("🖼️ Kapak resmini indir")
        self.chk_download_thumbnail.setToolTip("Video/şarkı kapak resmini (thumbnail) kaydeder")
        self.chk_embed_metadata = QCheckBox("🎵 MP3 etiket & kapak göm")
        self.chk_embed_metadata.setChecked(False)
        self.chk_embed_metadata.setEnabled(False)
        self.chk_embed_metadata.setToolTip(
            "Yalnızca 'Sadece Ses / Müzik (MP3)' seçildiğinde geçerlidir: "
            "şarkıcı, parça adı ve albüm kapağını dosyaya gömer."
        )
        self.chk_embed_metadata.toggled.connect(self._on_metadata_toggled)
        extras_layout.addWidget(self.chk_download_subtitles)
        extras_layout.addWidget(self.chk_download_thumbnail)
        extras_layout.addWidget(self.chk_embed_metadata)
        extras_layout.addStretch(1)
        form.addRow(QLabel("🎞️ Medya ekleri:"))
        form.addRow(extras_host)

        # ---- Gelişmiş seçenekler (katlanmış) --------------------------------
        self.btn_advanced = QToolButton()
        self.btn_advanced.setCheckable(True)
        self.btn_advanced.setArrowType(Qt.ArrowType.RightArrow)
        self.btn_advanced.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_advanced.setText("Gelişmiş seçenekler")
        self.btn_advanced.setAutoRaise(True)
        self.btn_advanced.setStyleSheet(
            f"QToolButton {{ color: {T['text_muted']}; font-weight: bold; border: none; padding: 2px 0; }}"
        )
        self.btn_advanced.toggled.connect(self._toggle_advanced)

        self.adv_container = QWidget()
        adv_form = QFormLayout(self.adv_container)
        adv_form.setContentsMargins(0, 0, 0, 0)
        adv_form.setSpacing(10)
        adv_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        adv_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._adv_form = adv_form

        self.spin_connections = QSpinBox()
        self.spin_connections.setRange(1, 32)
        self.spin_connections.setValue(8)
        self.spin_connections.setToolTip(
            "Dosya kaç parçaya bölünüp aynı anda indirilsin.\n"
            "8 çoğu bağlantı için iyi bir dengedir; yüksek değer bazı sitelerde engellenebilir."
        )
        self.spin_connections.valueChanged.connect(self._update_advanced_summary)
        adv_form.addRow(
            label_pair("Aynı anda inen parça sayısı:", "Bağlantı Sayısı (Parça):"),
            self.spin_connections,
        )

        self.combo_priority = QComboBox()
        self.combo_priority.addItem("⚖️ Normal Öncelik (Dengeli Paylaşım)", "normal")
        self.combo_priority.addItem("🚀 Yüksek Öncelik (Yüksek Hız Payı)", "high")
        self.combo_priority.addItem("🐢 Düşük Öncelik (Arka Plan)", "low")
        self.combo_priority.currentIndexChanged.connect(self._update_advanced_summary)
        adv_form.addRow("Bant Genişliği Önceliği:", self.combo_priority)

        self.combo_queue = QComboBox()
        if self.db:
            queues = self.db.get_all_queues()
            for q in queues:
                self.combo_queue.addItem(f"🗂️ {q['name']}", q["id"])
        else:
            self.combo_queue.addItem("🗂️ Ana Kuyruk", "default")
        self.combo_queue.currentIndexChanged.connect(self._update_advanced_summary)
        adv_form.addRow("İndirme Kuyruğu:", self.combo_queue)

        self.adv_container.hide()
        self.adv_container.setVisible(False)

        # ---- Tamamlanınca yapılacaklar: tam genişlikte onay kutuları --------
        self.chk_auto_open = QCheckBox("🏁 İndirme bitince dosyayı aç")
        self.chk_auto_open.setStyleSheet(f"color: {T['accent']}; font-weight: bold;")
        self.chk_auto_open.setToolTip("İndirme bittiğinde dosyayı Windows'ta varsayılan uygulamayla açar")
        form.addRow(self.chk_auto_open)

        self.chk_auto_extract = QCheckBox("📦 İndirme bitince arşivi ayıkla (.zip, .tar vb.)")
        self.chk_auto_extract.setStyleSheet(f"color: {T['success']}; font-weight: bold;")
        self.chk_auto_extract.setToolTip("Arşiv dosyası tamamlandığında otomatik olarak aynı klasöre çıkarır")
        form.addRow(self.chk_auto_extract)

        host_layout.addLayout(form)
        host_layout.addWidget(self.btn_advanced)
        host_layout.addWidget(self.adv_container)
        host_layout.addStretch(1)
        self.form_scroll.setWidget(form_host)
        layout.addWidget(self.form_scroll, 1)
        self._fit_scroll_height()

        # ---- Düğmeler: birincil eylem en sağda (Windows alışkanlığı) --------
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.addStretch(1)

        self.btn_queue = QPushButton("➕ Kuyruğa Ekle")
        self.btn_queue.setObjectName("btn_secondary")
        self.btn_queue.setToolTip("İndirmeyi listeye ekler, hemen başlatmaz")
        self.btn_queue.clicked.connect(lambda: self._submit(start_now=False))
        btn_layout.addWidget(self.btn_queue)

        btn_cancel = QPushButton("✕ İptal")
        btn_cancel.setObjectName("btn_secondary")
        btn_cancel.setToolTip("Hiçbir şey kaydetmeden kapatır (Esc)")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        self.btn_download_now = QPushButton("⬇️ Şimdi İndir")
        self.btn_download_now.setDefault(True)
        self.btn_download_now.clicked.connect(lambda: self._submit(start_now=True))
        btn_layout.addWidget(self.btn_download_now)

        layout.addLayout(btn_layout)

        self._update_advanced_summary()
        self._update_dir_note(initial_cat if self.auto_categorize else None)
        self._sync_metadata_option(self.combo_quality.currentData())

        # URL'e bağlı algılama her durumda çalışsın (dosya adı önceden dolu
        # geldiğinde -eklenti akışı- banner/site kuralı atlanmasın).
        if self.initial_url:
            self._on_url_changed(self.initial_url)

    def _fit_scroll_height(self):
        """Form kaydırma alanı: içerik sığdığı kadar yer kaplasın, ekranı taşmasın.

        QScrollArea'nın kendi sizeHint'i güvenilmez (içerikten küçük çıkıyor),
        bu yüzden yükseklik içerik ipucundan hesaplanır.
        """
        host = self.form_scroll.widget()
        if host is None:
            return
        host.adjustSize()
        content_h = host.sizeHint().height()
        screen = QApplication.primaryScreen()
        if screen is not None:
            limit = screen.availableGeometry().height() - 240
        else:
            limit = 720
        self.form_scroll.setFixedHeight(max(240, min(content_h + 8, max(320, limit))))
        self._align_advanced_labels()

    def _align_advanced_labels(self):
        """Gelişmiş alan etiketleri ana formun etiket sütunuyla aynı hizaya gelsin."""
        widths: List[int] = []
        try:
            for row in range(self._form.rowCount()):
                item = self._form.itemAt(row, QFormLayout.ItemRole.LabelRole)
                widget = item.widget() if item is not None else None
                if widget is not None:
                    widths.append(widget.width())
        except Exception:
            return
        width = max(widths) if widths else 0
        if width <= 0:
            return
        for field in (self.spin_connections, self.combo_priority, self.combo_queue):
            label = self._adv_form.labelForField(field)
            if label is not None:
                label.setMinimumWidth(width)

    def _build_preview_card(self) -> QWidget:
        self.preview_card = QWidget()
        self.preview_card.setStyleSheet(
            f"QWidget#previewCard {{ background-color: {T['bg_card']}; "
            f"border: 1px solid {T['border_panel']}; border-radius: 8px; }}"
        )
        self.preview_card.setObjectName("previewCard")

        card_layout = QHBoxLayout(self.preview_card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(12)

        self.lbl_thumb = QLabel("🎬")
        self.lbl_thumb.setFixedSize(160, 90)
        self.lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_thumb.setStyleSheet(
            f"QLabel {{ background-color: {T['bg_panel']}; border-radius: 6px; "
            f"color: {T['text_secondary']}; font-size: 26px; }}"
        )
        card_layout.addWidget(self.lbl_thumb)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        self.lbl_media_title = QLabel("Bağlantı inceleniyor...")
        self.lbl_media_title.setWordWrap(True)
        self.lbl_media_title.setStyleSheet(
            f"QLabel {{ color: {T['text_primary']}; font-weight: bold; border: none; }}"
        )
        self.lbl_media_meta = QLabel("")
        self.lbl_media_meta.setWordWrap(True)
        self.lbl_media_meta.setStyleSheet(f"QLabel {{ color: {T['text_muted']}; border: none; }}")
        text_layout.addWidget(self.lbl_media_title)
        text_layout.addWidget(self.lbl_media_meta)
        text_layout.addStretch(1)
        card_layout.addLayout(text_layout, 1)

        self.preview_card.hide()
        return self.preview_card

    # ------------------------------------------------------------- Yaşam döngüsü
    def showEvent(self, event):
        super().showEvent(event)
        self._probe_media_info()
        # Yerleşim oturduktan sonra form yüksekliğini içeriğe göre ayarla
        QTimer.singleShot(0, self._fit_scroll_height)

    def reject(self):
        self._shutdown_thread()
        super().reject()

    def closeEvent(self, event):
        self._shutdown_thread()
        super().closeEvent(event)

    def _shutdown_thread(self):
        self._closing = True
        if self._info_thread is not None:
            self._info_thread.stop()

    # ------------------------------------------------------------ Önizleme işi
    def _probe_media_info(self):
        url = self.edit_url.text().strip()
        if self._closing or not url or url == self._probed_url:
            return
        if not is_media_page_url(url):
            return
        if self._info_thread is not None and self._info_thread.isRunning():
            return

        self._probed_url = url
        self.lbl_media_title.setText("Bağlantı inceleniyor...")
        self.lbl_media_meta.setText("Başlık, süre ve boyut çekiliyor.")
        self.preview_card.show()

        thread = MediaInfoThread(url)
        self._info_thread = thread
        _LIVE_THREADS.append(thread)
        thread.loaded.connect(self._on_media_info)
        thread.failed.connect(self._on_media_info_failed)
        thread.finished.connect(lambda: self._forget_thread(thread))
        thread.start()

    @staticmethod
    def _forget_thread(thread: QThread):
        try:
            _LIVE_THREADS.remove(thread)
        except ValueError:
            pass

    def _on_media_info(self, info: dict):
        if self._closing:
            return
        self._media_info = info or {}

        title = _sanitize_name_part(self._media_info.get("title") or "")
        if title:
            self.lbl_media_title.setText(title)
            # Kullanıcı adı elle değiştirmediyse ve mevcut ad anlamsızsa
            # gerçek medya başlığını kullan.
            if not self._user_edited_filename and is_generic_media_name(self.edit_filename.text()):
                self._set_filename(f"{title}{self._current_ext()}")

        thumb_bytes = self._media_info.get("_thumb_bytes")
        if thumb_bytes:
            pixmap = QPixmap()
            if pixmap.loadFromData(thumb_bytes):
                self.lbl_thumb.setPixmap(
                    pixmap.scaled(
                        self.lbl_thumb.size(),
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )

        self._apply_quality_availability()
        self._update_preview_meta()

    def _on_media_info_failed(self, message: str):
        """Bilgi alınamadıysa kullanıcıyı erken uyar (sessiz başarısızlık olmasın)."""
        if self._closing or self._media_info is not None:
            return
        self.lbl_media_title.setText("Bağlantı çözümlenemedi")
        self.lbl_media_title.setStyleSheet(
            f"QLabel {{ color: {T['color_orange']}; font-weight: bold; border: none; }}"
        )
        self.lbl_media_meta.setText(message)
        self.preview_card.show()
        self._fit_scroll_height()

    def _update_preview_meta(self):
        if self._media_info is None:
            return
        if not is_media_page_url(self.edit_url.text().strip()):
            return
        quality = self.combo_quality.currentData() or "max"
        parts: List[str] = []
        duration = _format_duration(self._media_info.get("duration"))
        if duration:
            parts.append(f"⏱ {duration}")
        height = max_available_height(self._media_info)
        if height:
            parts.append(f"🎞 en fazla {height}p")
        size = estimate_media_size(self._media_info, quality)
        if size > 0:
            parts.append(f"~{format_size(size)}")
        elif quality not in ("subtitle", "audio"):
            parts.append("boyut bilgisi yok")
        self.lbl_media_meta.setText(" · ".join(parts) if parts else "")

    def _apply_quality_availability(self):
        """Kaynağa göre kalite listesini uyarla: olmayan kalite/altyazı seçilmesin."""
        info = self._media_info or {}
        notes: List[str] = []

        if info.get("subtitles") is False:
            idx_sub = self.combo_quality.findData("subtitle")
            if idx_sub >= 0:
                item = self.combo_quality.model().item(idx_sub)
                if item is not None:
                    item.setEnabled(False)
                    item.setText("📄 Altyazı (bu bağlantıda yok)")
                if self.combo_quality.currentData() == "subtitle":
                    self.combo_quality.setCurrentIndex(self.combo_quality.findData("max"))
                    notes.append("Bu bağlantıda altyazı bulunamadığı için kalite 'En Yüksek' olarak ayarlandı.")

        target = _QUALITY_MAX_HEIGHT.get(self.combo_quality.currentData() or "", 0)
        max_h = max_available_height(info)
        if target and max_h and target > max_h:
            fallback = "1080p" if max_h >= 1080 else ("720p" if max_h >= 720 else ("480p" if max_h >= 480 else "max"))
            self.combo_quality.setCurrentIndex(self.combo_quality.findData(fallback))
            notes.append(f"Bu videonun en yüksek çözünürlüğü {max_h}p; kalite buna düşürüldü.")

        if notes:
            self.lbl_quality_note.setText(" ".join(notes))
            self.lbl_quality_note.show()
        else:
            self.lbl_quality_note.hide()

    # -------------------------------------------------------------- Yardımcılar
    def _current_ext(self) -> str:
        quality = self.combo_quality.currentData() or "max"
        if quality == "audio":
            return ".mp3"
        if quality == "subtitle":
            return ".srt"
        return ".mp4"

    def _set_filename(self, text: str, user_edited: bool = False):
        self._updating_filename = True
        try:
            self.edit_filename.setText(text)
        finally:
            self._updating_filename = False
        if user_edited:
            self._user_edited_filename = True

    def _set_category(self, internal: str):
        idx = self.combo_category.findData(internal)
        if idx >= 0:
            self.combo_category.setCurrentIndex(idx)

    def _category_internal(self) -> str:
        return self.combo_category.currentData() or "Others"

    def _toggle_advanced(self, checked: bool):
        self.btn_advanced.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        )
        self.adv_container.setVisible(checked)
        self._fit_scroll_height()
        self._update_advanced_summary()

    def _update_advanced_summary(self):
        if not hasattr(self, "btn_advanced"):
            return
        queue_name = (self.combo_queue.currentText() or "").replace("🗂️ ", "").strip()
        priority = (self.combo_priority.currentText() or "").split(" (")[0]
        priority = re.sub(r"^[^\w]+", "", priority)
        summary = (
            f"Gelişmiş seçenekler — {self.spin_connections.value()} parça · "
            f"{priority} · {queue_name}"
        )
        self.btn_advanced.setText(summary)

    def _update_dir_note(self, category: Optional[str] = None):
        if not hasattr(self, "lbl_dir_note"):
            return
        if not self.auto_categorize:
            self.lbl_dir_note.setText("Otomatik kategori kapalı: dosya doğrudan bu klasöre kaydedilir.")
            return
        if self._user_edited_dir:
            self.lbl_dir_note.setText(
                "Özel klasör seçildi: kategori klasörü kullanılmayacak."
            )
            return
        cat = category or self._category_internal()
        if cat == "Otomatik":
            cat = detect_category(self.edit_filename.text().strip())
        sub = CATEGORY_FOLDER_NAMES.get(cat) or ""
        self.lbl_dir_note.setText(
            f"Kategori klasörü kullanılıyor ({sub})." if sub else "Kategori klasörü yok: dosya bu klasöre kaydedilir."
        )

    def _update_dir_by_category(self, category: Optional[str] = None):
        if self._user_edited_dir or not self.auto_categorize:
            self._update_dir_note(category)
            return
        cat = category or self._category_internal()
        if cat == "Otomatik":
            cat = detect_category(self.edit_filename.text().strip())
        self.edit_dir.setText(get_category_folder(cat, self.base_download_dir))
        self._update_dir_note(cat)
        self._check_file_conflict()

    def _on_filename_changed(self, text: str):
        if not self._updating_filename:
            self._user_edited_filename = True
        if not text:
            self._check_file_conflict()
            return
        cat = detect_category(text.strip())
        if self._category_internal() == "Otomatik":
            self._update_dir_by_category(cat)
        self._update_dir_note(cat)
        self._check_file_conflict()

    def _on_category_changed(self):
        self._update_dir_by_category(self._category_internal())

    def _on_metadata_toggled(self, checked: bool):
        if not self._syncing_metadata:
            self._metadata_user_touched = True

    def _sync_metadata_option(self, quality: str):
        """MP3 etiket seçeneği yalnızca ses indirmesinde anlamlıdır."""
        is_audio = quality == "audio"
        self._syncing_metadata = True
        try:
            self.chk_embed_metadata.setEnabled(is_audio)
            if is_audio:
                if not self._metadata_user_touched:
                    self.chk_embed_metadata.setChecked(True)
            else:
                self.chk_embed_metadata.setChecked(False)
        finally:
            self._syncing_metadata = False

    def _on_url_changed(self, url: str):
        url = (url or "").strip()
        if not url:
            self.banner_playlist.hide()
            self.banner_watermark_free.hide()
            self.banner_login_needed.hide()
            return

        u_lower = url.lower()

        # Check if URL is a YouTube playlist
        if is_youtube_playlist_url(url):
            self.banner_playlist.show()
        else:
            self.banner_playlist.hide()

        # Check if URL is TikTok, Instagram or Twitter/X
        is_tiktok = any(d in u_lower for d in ("tiktok.com", "tiktokv.com", "vt.tiktok.com", "vm.tiktok.com"))
        is_ig = any(d in u_lower for d in ("instagram.com", "instagr.am"))
        is_twitter = any(d in u_lower for d in ("twitter.com", "x.com")) and ("/status/" in u_lower or "/i/status/" in u_lower)

        if is_twitter:
            self.banner_login_needed.show()
        else:
            self.banner_login_needed.hide()

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
            self._set_category("Video")
            if not self.edit_filename.text().strip() or is_generic_media_name(self.edit_filename.text()):
                if is_tiktok:
                    default_prefix = "TikTok_Video.mp4"
                elif is_ig:
                    default_prefix = "Instagram_Reels.mp4"
                else:
                    status_match = re.search(r"/status/(\d+)", url)
                    default_prefix = f"X video {status_match.group(1)}.mp4" if status_match else "Twitter_Video.mp4"
                self._set_filename(default_prefix)
                self._update_dir_by_category("Video")
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
                    self._update_dir_note()
            else:
                self.banner_site_rule.hide()
        else:
            self.banner_site_rule.hide()

        parsed = urllib.parse.urlparse(url)
        path_name = os.path.basename(parsed.path)
        if path_name and not (is_tiktok or is_ig or is_twitter):
            clean_name = urllib.parse.unquote(path_name).split("?")[0]
            if not self.edit_filename.text().strip() or is_generic_media_name(self.edit_filename.text()):
                self._set_filename(clean_name)
                cat = detect_category(clean_name)
                self._set_category(cat if self.combo_category.findData(cat) >= 0 else "Others")
                self._update_dir_by_category(cat)

        # Medya sayfasıysa önizlemeyi tazele (pencere açıksa)
        if is_media_page_url(url):
            if url != self._probed_url:
                self._probed_url = ""
                if self.isVisible():
                    self._probe_media_info()

    def _open_playlist_dialog(self):
        url = self.edit_url.text().strip()
        self.open_playlist_requested.emit(url)
        self.reject()

    def _on_quality_changed(self):
        q = self.combo_quality.currentData()
        self._sync_metadata_option(q)
        name = self.edit_filename.text().strip()
        base = os.path.splitext(name)[0] if name else "download"
        if q == "audio":
            self._set_category("Music")
            if name.lower().endswith((".mp4", ".mkv", ".webm", ".srt")):
                self._set_filename(f"{base}.mp3")
        elif q == "subtitle":
            self._set_category("Documents")
            if name.lower().endswith((".mp4", ".mkv", ".webm", ".mp3")):
                self._set_filename(f"{base}.srt")
        else:
            if name.lower().endswith((".mp3", ".srt")):
                self._set_filename(f"{base}.mp4")
            # Kaliteyle birlikte kategori de geri gelsin (MP3 -> Müzik olmuşsa
            # video kalitesine dönünce tekrar Video olsun).
            if self._category_internal() in ("Music", "Documents"):
                detected = detect_category(self.edit_filename.text().strip())
                if self.combo_category.findData(detected) >= 0:
                    self._set_category(detected)
        self._update_dir_note()
        self._update_preview_meta()

    def _browse_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "Kayıt Klasörü Seç", self.edit_dir.text())
        if chosen:
            self._user_edited_dir = True
            self.edit_dir.setText(chosen)
            self._update_dir_note()
            self._check_file_conflict()

    def _check_file_conflict(self):
        fname = self.edit_filename.text().strip()
        fdir = self.edit_dir.text().strip()
        if fname and fdir and os.path.exists(os.path.join(fdir, fname)):
            conflict_action = self.db.get_conflict_setting() if self.db else "auto_rename"
            if conflict_action == "overwrite":
                self.banner_conflict.setText("⚠️ Dikkat: Bu isimde bir dosya klasörde zaten var! Çakışma ayarınız 'Üzerine Yaz' olduğu için mevcut dosya silinecektir.")
                self.banner_conflict.setStyleSheet(f"""
                    QLabel {{
                        background-color: {T['danger_bg']};
                        color: {T['danger']};
                        font-weight: bold;
                        padding: 6px 12px;
                        border-radius: 6px;
                        border: 1px solid {T['danger']};
                    }}
                """)
            elif conflict_action == "skip":
                self.banner_conflict.setText("⏭️ Bu isimde bir dosya klasörde zaten var! Çakışma ayarınız 'İndirmeyi Atla' olarak ayarlanmış.")
                self.banner_conflict.setStyleSheet(f"""
                    QLabel {{
                        background-color: {T['warning_bg']};
                        color: {T['color_orange']};
                        font-weight: bold;
                        padding: 6px 12px;
                        border-radius: 6px;
                        border: 1px solid {T['color_orange']};
                    }}
                """)
            else:
                self.banner_conflict.setText("🔄 Bu isimde bir dosya klasörde zaten var! RipSync ayarlarınıza göre otomatik adlandırılacak.")
                self.banner_conflict.setStyleSheet(f"""
                    QLabel {{
                        background-color: {T['info_bg']};
                        color: {T['color_cyan']};
                        font-weight: bold;
                        padding: 6px 12px;
                        border-radius: 6px;
                        border: 1px solid {T['accent_primary']};
                    }}
                """)
            self.banner_conflict.show()
        else:
            self.banner_conflict.hide()

    def _submit(self, start_now: bool):
        url = self.edit_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Bağlantı gerekli", "Lütfen indirilecek bağlantı adresini girin.")
            self.edit_url.setFocus()
            return

        target_dir = self.edit_dir.text().strip()
        fname_final = self.edit_filename.text().strip()
        if not fname_final:
            QMessageBox.warning(self, "Dosya adı gerekli", "Lütfen kaydedilecek dosya adını girin.")
            self.edit_filename.setFocus()
            return

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
                self._set_filename(new_name, user_edited=True)
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

        cat_choice = self._category_internal()
        if cat_choice == "Otomatik":
            cat_choice = detect_category(self.edit_filename.text().strip())

        req_headers = dict(self.headers)
        req_headers["download_subtitles"] = self.chk_download_subtitles.isChecked()
        req_headers["download_thumbnail"] = self.chk_download_thumbnail.isChecked()
        req_headers["embed_metadata"] = self.chk_embed_metadata.isChecked() and self.chk_embed_metadata.isEnabled()

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
        self._shutdown_thread()
        self.download_confirmed.emit(data)
        self.accept()
