import os
import threading
import httpx
from typing import Dict, Any, List, Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QComboBox, QFileDialog, QProgressBar, QMessageBox,
    QSpinBox, QSplitter, QWidget, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon

from core.database import detect_category, get_category_folder
from core.playlist_parser import is_youtube_playlist_url, normalize_playlist_url, fetch_playlist_metadata

DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads")

class PlaylistScanThread(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            data = fetch_playlist_metadata(self.url)
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))

class ThumbnailLoaderThread(QThread):
    loaded = pyqtSignal(int, bytes)  # row_idx, image_bytes

    def __init__(self, items: List[tuple]):  # List of (row_idx, thumb_url)
        super().__init__()
        self.items = items
        self._is_running = True

    def run(self):
        for row_idx, url in self.items:
            if not self._is_running:
                break
            if not url:
                continue
            try:
                resp = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4.0, follow_redirects=True)
                if self._is_running and resp.status_code == 200:
                    self.loaded.emit(row_idx, resp.content)
            except Exception:
                continue

    def stop(self):
        self._is_running = False

class PlaylistDownloadDialog(QDialog):
    """
    Dialog to scan, preview, filter, and batch download YouTube Playlists.
    Allows user to select specific videos, choose quality/format (Video or MP3 Audio),
    and add all chosen items to the download queue with 1-click.
    """
    # Emits list of download specs: [{"url": ..., "filename": ..., "quality": ..., "save_dir": ..., "category": ...}, ...]
    batch_download_confirmed = pyqtSignal(list, bool)  # items, start_now

    def __init__(self, initial_url: str = "", base_download_dir: str = "",
                 initial_quality: str = "max", parent=None):
        super().__init__(parent)
        self.initial_url = initial_url
        self.base_download_dir = base_download_dir or DEFAULT_DOWNLOAD_DIR
        self.initial_quality = initial_quality or "max"

        self.playlist_data: Optional[Dict[str, Any]] = None
        self.scan_thread: Optional[PlaylistScanThread] = None
        self.thumb_thread: Optional[ThumbnailLoaderThread] = None

        self.setWindowTitle("RipSync - YouTube Oynatma Listesi İndirici")
        self.resize(920, 640)
        self.setMinimumSize(780, 520)

        self._init_ui()

        if self.initial_url:
            self.edit_url.setText(self.initial_url)
            self._start_scan()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(18, 18, 18, 18)

        # 1. URL Bar & Scan Button
        url_box = QHBoxLayout()
        lbl_url = QLabel("Çalma Listesi Bağlantısı:")
        lbl_url.setStyleSheet("font-weight: bold; color: #7aa2f7;")
        self.edit_url = QLineEdit()
        self.edit_url.setPlaceholderText("https://www.youtube.com/playlist?list=...")
        self.edit_url.returnPressed.connect(self._start_scan)

        self.btn_scan = QPushButton("🔍 Listeyi Tara")
        self.btn_scan.setFixedWidth(130)
        self.btn_scan.clicked.connect(self._start_scan)

        url_box.addWidget(lbl_url)
        url_box.addWidget(self.edit_url, 1)
        url_box.addWidget(self.btn_scan)
        main_layout.addLayout(url_box)

        # Progress / Status Bar while scanning
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # indeterminate animation
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        # 2. Playlist Info Header & Statistics Card
        self.info_card = QFrame()
        self.info_card.setStyleSheet("""
            QFrame {
                background-color: #24283b;
                border: 1px solid #414868;
                border-radius: 8px;
                padding: 6px 12px;
            }
        """)
        info_layout = QHBoxLayout(self.info_card)
        info_layout.setContentsMargins(10, 8, 10, 8)

        self.lbl_playlist_title = QLabel("Henüz bir çalma listesi taranmadı.")
        self.lbl_playlist_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #c0caf5;")
        self.lbl_playlist_title.setWordWrap(True)

        self.lbl_stats = QLabel("Toplam: 0 Video | Seçilen: 0 Video")
        self.lbl_stats.setStyleSheet("font-weight: bold; color: #9ece6a; font-size: 12px;")
        self.lbl_stats.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        info_layout.addWidget(self.lbl_playlist_title, 1)
        info_layout.addWidget(self.lbl_stats)
        main_layout.addWidget(self.info_card)

        # 3. Selection toolbar (Select All, Deselect All, Invert, Search Filter)
        sel_bar = QHBoxLayout()
        sel_bar.setSpacing(8)

        self.btn_select_all = QPushButton("✔ Tümünü Seç")
        self.btn_select_all.setObjectName("btn_secondary")
        self.btn_select_all.clicked.connect(self._select_all)
        sel_bar.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("✖ Tümünü Kaldır")
        self.btn_deselect_all.setObjectName("btn_secondary")
        self.btn_deselect_all.clicked.connect(self._deselect_all)
        sel_bar.addWidget(self.btn_deselect_all)

        self.btn_invert_sel = QPushButton("🔄 Seçimi Tersine Çevir")
        self.btn_invert_sel.setObjectName("btn_secondary")
        self.btn_invert_sel.clicked.connect(self._invert_selection)
        sel_bar.addWidget(self.btn_invert_sel)

        sel_bar.addSpacing(16)

        lbl_filter = QLabel("Filtrele:")
        lbl_filter.setStyleSheet("color: #7aa2f7;")
        sel_bar.addWidget(lbl_filter)

        self.edit_filter = QLineEdit()
        self.edit_filter.setPlaceholderText("Başlığa göre ara...")
        self.edit_filter.textChanged.connect(self._apply_filter)
        sel_bar.addWidget(self.edit_filter, 1)

        main_layout.addLayout(sel_bar)

        # 4. Videos Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Seç", "Kapak", "#", "Video Başlığı", "Süre"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setIconSize(self.table.iconSize())

        # Header columns sizing
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 50)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 80)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 50)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 90)

        main_layout.addWidget(self.table, 1)

        # 5. Download Options Bar (Quality, Save Dir, Connections)
        opts_box = QHBoxLayout()
        opts_box.setSpacing(12)

        lbl_q = QLabel("İndirme Kalitesi / Format:")
        lbl_q.setStyleSheet("font-weight: bold; color: #7aa2f7;")
        opts_box.addWidget(lbl_q)

        self.combo_quality = QComboBox()
        self.combo_quality.addItem("🚀 En Yüksek Kalite (Maksimum MP4)", "max")
        self.combo_quality.addItem("🌟 1080p (Full HD MP4)", "1080p")
        self.combo_quality.addItem("✨ 720p (HD MP4)", "720p")
        self.combo_quality.addItem("📺 480p (Standart MP4)", "480p")
        self.combo_quality.addItem("🎵 Sadece Ses / Müzik (MP3)", "audio")
        self.combo_quality.addItem("📄 Altyazı (.srt İndir)", "subtitle")
        idx_q = self.combo_quality.findData(self.initial_quality)
        if idx_q >= 0:
            self.combo_quality.setCurrentIndex(idx_q)
        self.combo_quality.currentIndexChanged.connect(self._on_quality_changed)
        opts_box.addWidget(self.combo_quality)

        opts_box.addSpacing(10)

        lbl_dir = QLabel("Kayıt Klasörü:")
        lbl_dir.setStyleSheet("font-weight: bold; color: #7aa2f7;")
        opts_box.addWidget(lbl_dir)

        # Target folder inside Downloads/Videolar or Downloads/Müzik
        init_cat = "Music" if self.initial_quality == "audio" else "Video"
        init_dir = get_category_folder(init_cat, self.base_download_dir)
        self.edit_dir = QLineEdit(init_dir)
        opts_box.addWidget(self.edit_dir, 1)

        btn_browse = QPushButton("Gözat...")
        btn_browse.setObjectName("btn_secondary")
        btn_browse.clicked.connect(self._browse_dir)
        opts_box.addWidget(btn_browse)

        main_layout.addLayout(opts_box)

        # Numbering prefix option
        prefix_box = QHBoxLayout()
        self.chk_prefix_index = QCheckBox("Dosya adının başına sıra numarası ekle (Örn: '01 - Video Başlığı.mp4')")
        self.chk_prefix_index.setChecked(True)
        self.chk_prefix_index.setStyleSheet("color: #a9b1d6; font-weight: bold;")
        prefix_box.addWidget(self.chk_prefix_index)
        prefix_box.addStretch()
        main_layout.addLayout(prefix_box)

        # 6. Bottom Action Buttons (Tek Tıkla Sırayla İndir / Kuyruğa Ekle / İptal)
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)

        self.btn_download_now = QPushButton("🚀 Seçilenleri Hemen Sırayla İndir")
        self.btn_download_now.setStyleSheet("""
            QPushButton {
                background-color: #7aa2f7;
                color: #1a1b26;
                font-weight: bold;
                font-size: 13px;
                padding: 10px 22px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #89b4fa;
            }
        """)
        self.btn_download_now.clicked.connect(lambda: self._submit(start_now=True))
        self.btn_download_now.setEnabled(False)
        btn_box.addWidget(self.btn_download_now)

        self.btn_add_queue = QPushButton("📥 Kuyruğa Ekle (Daha Sonra)")
        self.btn_add_queue.setObjectName("btn_secondary")
        self.btn_add_queue.clicked.connect(lambda: self._submit(start_now=False))
        self.btn_add_queue.setEnabled(False)
        btn_box.addWidget(self.btn_add_queue)

        btn_box.addStretch()

        btn_cancel = QPushButton("Kapat")
        btn_cancel.setObjectName("btn_secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        main_layout.addLayout(btn_box)

    def _start_scan(self):
        url = self.edit_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Hata", "Lütfen geçerli bir YouTube çalma listesi bağlantısı girin.")
            return

        if not is_youtube_playlist_url(url):
            ret = QMessageBox.question(
                self,
                "Bağlantı Uyarısı",
                "Bu bağlantı standart bir YouTube çalma listesi gibi görünmüyor.\nYine de taranmasını denemek istiyor musunuz?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if ret != QMessageBox.StandardButton.Yes:
                return

        self.btn_scan.setEnabled(False)
        self.btn_download_now.setEnabled(False)
        self.btn_add_queue.setEnabled(False)
        self.progress_bar.show()
        self.lbl_playlist_title.setText("Çalma listesi taranıyor, lütfen bekleyin...")
        self.lbl_stats.setText("Taranıyor...")
        self.table.setRowCount(0)

        if self.thumb_thread:
            self.thumb_thread.stop()
            self.thumb_thread.wait()

        self.scan_thread = PlaylistScanThread(url)
        self.scan_thread.finished.connect(self._on_scan_success)
        self.scan_thread.error.connect(self._on_scan_error)
        self.scan_thread.start()

    def _on_scan_success(self, data: dict):
        self.progress_bar.hide()
        self.btn_scan.setEnabled(True)
        self.playlist_data = data

        title = data.get("title", "YouTube Çalma Listesi")
        count = data.get("count", 0)
        uploader = data.get("uploader", "")

        sub_info = f" ({uploader})" if uploader else ""
        self.lbl_playlist_title.setText(f"📑 {title}{sub_info}")
        self.lbl_stats.setText(f"Toplam: {count} Video | Seçilen: {count} Video")

        entries = data.get("entries", [])
        self.table.setRowCount(len(entries))

        thumb_tasks = []

        for row, item in enumerate(entries):
            # Checkbox item
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Checked)
            chk_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, chk_item)

            # Thumbnail placeholder
            thumb_item = QTableWidgetItem("🎬")
            thumb_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, thumb_item)

            # Index
            idx_item = QTableWidgetItem(f"{item.get('index', row + 1):02d}")
            idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            idx_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(row, 2, idx_item)

            # Title
            title_item = QTableWidgetItem(item.get("title", ""))
            title_item.setToolTip(f"{item.get('title')}\nURL: {item.get('url')}")
            title_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(row, 3, title_item)

            # Duration
            dur_item = QTableWidgetItem(item.get("duration_str", "--:--"))
            dur_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            dur_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(row, 4, dur_item)

            # Row height
            self.table.setRowHeight(row, 44)

            # Queue thumbnail download
            if item.get("thumbnail"):
                thumb_tasks.append((row, item["thumbnail"]))

        self.table.itemChanged.connect(self._on_table_item_changed)
        self._update_selection_stats()

        self.btn_download_now.setEnabled(count > 0)
        self.btn_add_queue.setEnabled(count > 0)

        # Start loading thumbnails in background
        if thumb_tasks:
            self.thumb_thread = ThumbnailLoaderThread(thumb_tasks)
            self.thumb_thread.loaded.connect(self._on_thumbnail_loaded)
            self.thumb_thread.start()

    def _on_thumbnail_loaded(self, row: int, data: bytes):
        try:
            pix = QPixmap()
            if pix.loadFromData(data):
                scaled = pix.scaled(64, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                item = self.table.item(row, 1)
                if item:
                    item.setText("")
                    item.setIcon(QIcon(scaled))
        except Exception:
            pass

    def _on_scan_error(self, err_msg: str):
        self.progress_bar.hide()
        self.btn_scan.setEnabled(True)
        self.lbl_playlist_title.setText("Çalma listesi taranırken hata oluştu.")
        self.lbl_stats.setText("Hata")
        QMessageBox.critical(self, "Tarama Hatası", f"Çalma listesi bilgileri alınamadı:\n\n{err_msg}")

    def _on_table_item_changed(self, item: QTableWidgetItem):
        if item.column() == 0:
            self._update_selection_stats()

    def _update_selection_stats(self):
        total = self.table.rowCount()
        selected = 0
        for r in range(total):
            chk = self.table.item(r, 0)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                selected += 1

        self.lbl_stats.setText(f"Toplam: {total} Video | Seçilen: {selected} Video")
        self.btn_download_now.setEnabled(selected > 0)
        self.btn_add_queue.setEnabled(selected > 0)

    def _select_all(self):
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            if not self.table.isRowHidden(r):
                chk = self.table.item(r, 0)
                if chk:
                    chk.setCheckState(Qt.CheckState.Checked)
        self.table.blockSignals(False)
        self._update_selection_stats()

    def _deselect_all(self):
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            if not self.table.isRowHidden(r):
                chk = self.table.item(r, 0)
                if chk:
                    chk.setCheckState(Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self._update_selection_stats()

    def _invert_selection(self):
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            if not self.table.isRowHidden(r):
                chk = self.table.item(r, 0)
                if chk:
                    new_st = Qt.CheckState.Unchecked if chk.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
                    chk.setCheckState(new_st)
        self.table.blockSignals(False)
        self._update_selection_stats()

    def _apply_filter(self, query: str):
        q = query.strip().lower()
        for r in range(self.table.rowCount()):
            title_item = self.table.item(r, 3)
            if not q:
                self.table.setRowHidden(r, False)
            else:
                title = title_item.text().lower() if title_item else ""
                self.table.setRowHidden(r, q not in title)

    def _on_quality_changed(self):
        q = self.combo_quality.currentData()
        cat = "Music" if q == "audio" else ("Documents" if q == "subtitle" else "Video")
        self.edit_dir.setText(get_category_folder(cat, self.base_download_dir))

    def _browse_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "Kayıt Klasörü Seç", self.edit_dir.text())
        if chosen:
            self.edit_dir.setText(chosen)

    def _submit(self, start_now: bool):
        if not self.playlist_data:
            return

        selected_items = []
        entries = self.playlist_data.get("entries", [])
        quality = self.combo_quality.currentData() or "max"
        save_dir = self.edit_dir.text().strip()
        add_prefix = self.chk_prefix_index.isChecked()

        ext = "mp3" if quality == "audio" else ("srt" if quality == "subtitle" else "mp4")
        cat = "Music" if quality == "audio" else ("Documents" if quality == "subtitle" else "Video")

        for r in range(self.table.rowCount()):
            chk = self.table.item(r, 0)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                if r < len(entries):
                    item = entries[r]
                    idx = item.get("index", r + 1)
                    raw_title = item.get("title", f"Video_{idx}")

                    if add_prefix:
                        clean_fn = f"{idx:02d} - {raw_title}.{ext}"
                    else:
                        clean_fn = f"{raw_title}.{ext}"

                    selected_items.append({
                        "url": item.get("url"),
                        "filename": clean_fn,
                        "save_dir": save_dir,
                        "category": cat,
                        "quality": quality,
                        "connections": 8,
                        "headers": {}
                    })

        if not selected_items:
            QMessageBox.information(self, "Bilgi", "İndirmek için en az bir video seçmelisiniz.")
            return

        self.batch_download_confirmed.emit(selected_items, start_now)
        self.accept()

    def closeEvent(self, event):
        if self.thumb_thread:
            self.thumb_thread.stop()
            self.thumb_thread.wait()
        super().closeEvent(event)
