import os
import subprocess
from typing import Dict, Any, Optional, List
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeWidget, QTreeWidgetItem, QTableWidget,
    QTableWidgetItem, QHeaderView, QToolBar, QPushButton,
    QLabel, QProgressBar, QMenu, QMessageBox, QStatusBar,
    QApplication, QSystemTrayIcon, QSlider, QCheckBox, QComboBox, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QShortcut

from ui.styles import DARK_THEME, format_size, format_progress_size, format_speed, format_eta
from ui.add_download_dialog import AddDownloadDialog
from ui.progress_dialog import ProgressDialog
from ui.settings_dialog import SettingsDialog
from ui.power_countdown_dialog import PowerCountdownDialog
from ui.scheduler_dialog import SchedulerDialog
from ui.playlist_dialog import PlaylistDownloadDialog
from ui.tray_icon import create_default_icon, TrayIcon
from ui.clipboard_monitor import ClipboardMonitor
from ui.clipboard_popup import ClipboardNotificationPopup
from core.database import Database
from core.queue_manager import QueueManager
from core.power_manager import PowerCountdownManager
from core.scheduler import DownloadScheduler
from core.playlist_parser import is_youtube_playlist_url

class MainWindow(QMainWindow):
    # Cross-thread UI signal
    sig_bridge_download = pyqtSignal(dict)
    sig_progress_update = pyqtSignal(str, int, int, float, int)
    sig_segments_update = pyqtSignal(str, list)
    sig_status_update = pyqtSignal(str, str, str)
    sig_task_added = pyqtSignal(dict)
    sig_queue_empty = pyqtSignal()
    sig_countdown_tick = pyqtSignal(int, str)
    sig_countdown_executed = pyqtSignal(str)
    sig_scheduler_tick = pyqtSignal(dict)
    sig_scheduler_started = pyqtSignal()
    sig_scheduler_stopped = pyqtSignal(str)

    def __init__(self, db: Database, queue_mgr: QueueManager):
        super().__init__()
        self.db = db
        self.queue_mgr = queue_mgr

        self.setWindowTitle("RipSync - Internet Download Manager")
        self.setWindowIcon(create_default_icon())
        self.resize(1000, 620)
        self.setStyleSheet(DARK_THEME)

        self.current_category = "All"
        self.active_dialogs: Dict[str, ProgressDialog] = {}

        # Power Countdown Manager
        self.power_mgr = PowerCountdownManager(countdown_seconds=30)
        self.power_dialog: Optional[PowerCountdownDialog] = None
        self.current_queue_action = self.db.get_setting("on_queue_complete_action", "none")

        # Scheduler (Night downloading & queue schedule)
        sched_settings = self.db.get_scheduler_settings()
        self.scheduler = DownloadScheduler(**sched_settings)
        self.queue_mgr.attach_scheduler(self.scheduler)

        self._init_ui()
        self._init_signals()
        self._load_downloads_to_table()

        # Clipboard Notification Popup & Monitor
        self.clip_popup = ClipboardNotificationPopup()
        self.clip_popup.download_requested.connect(self._handle_clipboard_download)

        self.clip_monitor = ClipboardMonitor(self)
        clip_enabled = bool(self.db.get_setting("clipboard_enabled", True))
        self.clip_monitor.set_enabled(clip_enabled)
        self.clip_monitor.link_detected.connect(self._on_clipboard_link_detected)

        # Tray Icon
        self.tray = TrayIcon(current_queue_action=self.current_queue_action, parent=self)
        self.tray.show_window_requested.connect(self._toggle_window)
        self.tray.start_all_requested.connect(self._on_start_all)
        self.tray.pause_all_requested.connect(self._on_pause_all)
        self.tray.speed_limit_requested.connect(self._on_tray_speed_limit_requested)
        self.tray.queue_action_changed.connect(self._on_queue_action_changed_from_tray)
        self.tray.scheduler_requested.connect(self._show_scheduler_dialog)
        self.tray.scheduler_toggle_requested.connect(self._toggle_scheduler_from_tray)
        self.tray.playlist_requested.connect(lambda: self._show_playlist_dialog())
        self.tray.quit_requested.connect(self._quit_application)
        self.tray.show()

        # Start Scheduler background loop
        self.scheduler.start()

    def _init_ui(self):
        # Toolbar
        toolbar = QToolBar("Ana Araç Çubuğu")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.act_add = QAction("➕ URL Ekle", self)
        self.act_add.triggered.connect(self._show_add_dialog)
        toolbar.addAction(self.act_add)

        self.act_playlist = QAction("📑 Oynatma Listesi İndir", self)
        self.act_playlist.setToolTip("YouTube Çalma Listesindeki Videoları Toplu Tara ve İndir")
        self.act_playlist.triggered.connect(lambda: self._show_playlist_dialog())
        toolbar.addAction(self.act_playlist)

        toolbar.addSeparator()

        self.act_start = QAction("▶ Başlat", self)
        self.act_start.triggered.connect(self._start_selected)
        toolbar.addAction(self.act_start)

        self.act_pause = QAction("⏸ Duraklat", self)
        self.act_pause.triggered.connect(self._pause_selected)
        toolbar.addAction(self.act_pause)

        self.act_stop = QAction("⏹ İptal", self)
        self.act_stop.triggered.connect(self._cancel_selected)
        toolbar.addAction(self.act_stop)

        self.act_delete = QAction("🗑 Sil", self)
        self.act_delete.triggered.connect(self._delete_selected)
        toolbar.addAction(self.act_delete)

        toolbar.addSeparator()

        self.act_open_file = QAction("📂 Dosyayı Aç", self)
        self.act_open_file.triggered.connect(self._open_selected_file)
        toolbar.addAction(self.act_open_file)

        self.act_open_folder = QAction("📁 Klasörde Göster", self)
        self.act_open_folder.triggered.connect(self._open_selected_folder)
        toolbar.addAction(self.act_open_folder)

        toolbar.addSeparator()

        self.act_start_queue = QAction("⚡ Kuyruğu Başlat", self)
        self.act_start_queue.triggered.connect(self._on_start_all)
        toolbar.addAction(self.act_start_queue)

        self.act_pause_all = QAction("⏸ Tümünü Durdur", self)
        self.act_pause_all.triggered.connect(self._on_pause_all)
        toolbar.addAction(self.act_pause_all)

        toolbar.addSeparator()

        self.act_scheduler = QAction("⏱ Zamanlayıcı", self)
        self.act_scheduler.setToolTip("Gece İndirmesi ve Kuyruk Planlama Penceresini Aç")
        self.act_scheduler.triggered.connect(self._show_scheduler_dialog)
        toolbar.addAction(self.act_scheduler)

        toolbar.addSeparator()

        self.act_settings = QAction("⚙ Ayarlar", self)
        self.act_settings.triggered.connect(self._show_settings_dialog)
        toolbar.addAction(self.act_settings)

        self.act_extension = QAction("🌐 Eklenti", self)
        self.act_extension.setToolTip("Chrome / Edge Tarayıcı Eklentisi Kurulum Kılavuzu")
        self.act_extension.triggered.connect(self._show_extension_guide)
        toolbar.addAction(self.act_extension)

        toolbar.addSeparator()

        # Concurrency Widget (Sequential Queue Limit)
        tb_conc_widget = QWidget()
        tb_conc_layout = QHBoxLayout(tb_conc_widget)
        tb_conc_layout.setContentsMargins(6, 0, 6, 0)
        tb_conc_layout.setSpacing(6)

        lbl_conc = QLabel("⚡ Sıralı:")
        lbl_conc.setStyleSheet("font-weight: bold; color: #7aa2f7;")
        lbl_conc.setToolTip("Aynı anda indirilecek maksimum dosya sayısı (Sıralı İndirme Limiti)")
        tb_conc_layout.addWidget(lbl_conc)

        self.spin_tb_concurrent = QSpinBox()
        self.spin_tb_concurrent.setRange(1, 10)
        self.spin_tb_concurrent.setValue(self.queue_mgr.max_concurrent)
        self.spin_tb_concurrent.setSuffix(" Dosya")
        self.spin_tb_concurrent.setFixedWidth(85)
        self.spin_tb_concurrent.setToolTip("Aynı anda inecek dosya sayısı (biri bitince sıradaki başlar)")
        self.spin_tb_concurrent.valueChanged.connect(self._on_toolbar_concurrent_changed)
        tb_conc_layout.addWidget(self.spin_tb_concurrent)

        toolbar.addWidget(tb_conc_widget)

        toolbar.addSeparator()

        # Scheduler Quick Control Widget on Toolbar
        tb_sched_widget = QWidget()
        tb_sched_layout = QHBoxLayout(tb_sched_widget)
        tb_sched_layout.setContentsMargins(6, 0, 6, 0)
        tb_sched_layout.setSpacing(6)

        self.chk_tb_scheduler = QCheckBox("⏱ Zamanlayıcı:")
        self.chk_tb_scheduler.setStyleSheet("font-weight: bold; color: #7aa2f7;")
        self.chk_tb_scheduler.setToolTip("Gece indirmesi zamanlayıcısını Aç / Kapat")
        self.chk_tb_scheduler.toggled.connect(self._on_toolbar_scheduler_toggled)
        tb_sched_layout.addWidget(self.chk_tb_scheduler)

        self.lbl_tb_sched_time = QLabel("02:00 - 07:00")
        self.lbl_tb_sched_time.setStyleSheet("color: #c0caf5; font-size: 11px;")
        tb_sched_layout.addWidget(self.lbl_tb_sched_time)

        self.lbl_tb_sched_badge = QLabel("Kapalı")
        self.lbl_tb_sched_badge.setStyleSheet("font-weight: bold; color: #7982a9; min-width: 60px;")
        tb_sched_layout.addWidget(self.lbl_tb_sched_badge)

        btn_sched_cfg = QPushButton("⚙")
        btn_sched_cfg.setObjectName("btn_secondary")
        btn_sched_cfg.setFixedSize(24, 24)
        btn_sched_cfg.setToolTip("Zamanlayıcı ve Kuyruk Planlama Ayarlarını Aç")
        btn_sched_cfg.clicked.connect(self._show_scheduler_dialog)
        tb_sched_layout.addWidget(btn_sched_cfg)

        toolbar.addWidget(tb_sched_widget)

        toolbar.addSeparator()

        # Global Speed Limiter Widget on Toolbar (IDM Quick Limiter)
        tb_limiter_widget = QWidget()
        tb_limiter_layout = QHBoxLayout(tb_limiter_widget)
        tb_limiter_layout.setContentsMargins(6, 0, 6, 0)
        tb_limiter_layout.setSpacing(8)

        self.chk_tb_speed_limit = QCheckBox("⚡ Hız Limiti:")
        self.chk_tb_speed_limit.setStyleSheet("font-weight: bold; color: #7aa2f7;")
        self.chk_tb_speed_limit.setToolTip("Hız Sınırlayıcıyı tek tıkla Aç / Kapat (Tam Hız)")
        self.chk_tb_speed_limit.toggled.connect(self._on_toolbar_limit_toggled)
        tb_limiter_layout.addWidget(self.chk_tb_speed_limit)

        self.slider_tb_limit = QSlider(Qt.Orientation.Horizontal)
        self.slider_tb_limit.setRange(256, 50 * 1024)  # 256 KB/s - 50 MB/s
        self.slider_tb_limit.setSingleStep(256)
        self.slider_tb_limit.setPageStep(1024)
        self.slider_tb_limit.setFixedWidth(130)
        self.slider_tb_limit.setToolTip("İndirme hız limitini kaydırarak ayarlayın")
        self.slider_tb_limit.setEnabled(False)
        self.slider_tb_limit.valueChanged.connect(self._on_toolbar_slider_changed)
        tb_limiter_layout.addWidget(self.slider_tb_limit)

        self.combo_tb_limit = QComboBox()
        self.combo_tb_limit.addItem("512 KB/s", 512)
        self.combo_tb_limit.addItem("1 MB/s", 1024)
        self.combo_tb_limit.addItem("2 MB/s", 2048)
        self.combo_tb_limit.addItem("5 MB/s", 5120)
        self.combo_tb_limit.addItem("10 MB/s", 10240)
        self.combo_tb_limit.addItem("25 MB/s", 25600)
        self.combo_tb_limit.addItem("50 MB/s", 51200)
        self.combo_tb_limit.setFixedWidth(100)
        self.combo_tb_limit.setToolTip("Hazır hız limiti seçin")
        self.combo_tb_limit.setEnabled(False)
        self.combo_tb_limit.currentIndexChanged.connect(self._on_toolbar_combo_changed)
        tb_limiter_layout.addWidget(self.combo_tb_limit)

        self.lbl_tb_limit_val = QLabel("Tam Hız")
        self.lbl_tb_limit_val.setStyleSheet("font-weight: bold; color: #9ece6a; min-width: 75px;")
        tb_limiter_layout.addWidget(self.lbl_tb_limit_val)

        toolbar.addWidget(tb_limiter_widget)

        toolbar.addSeparator()

        # Queue Completion Power Action Widget on Toolbar
        tb_queue_widget = QWidget()
        tb_queue_layout = QHBoxLayout(tb_queue_widget)
        tb_queue_layout.setContentsMargins(6, 0, 6, 0)
        tb_queue_layout.setSpacing(6)

        lbl_qa = QLabel("🏁 Kuyruk Bitince:")
        lbl_qa.setStyleSheet("font-weight: bold; color: #7aa2f7;")
        tb_queue_layout.addWidget(lbl_qa)

        self.combo_tb_queue_action = QComboBox()
        self.combo_tb_queue_action.addItem("❌ Eylem Yok", "none")
        self.combo_tb_queue_action.addItem("🛑 Bilgisayarı Kapat", "shutdown")
        self.combo_tb_queue_action.addItem("🌙 Uyku Moduna Al", "sleep")
        self.combo_tb_queue_action.setFixedWidth(155)
        self.combo_tb_queue_action.setToolTip("Kuyruktaki tüm indirmeler bittiğinde yapılacak sistem eylemi")
        idx_qa = self.combo_tb_queue_action.findData(self.current_queue_action)
        if idx_qa >= 0:
            self.combo_tb_queue_action.setCurrentIndex(idx_qa)
        self.combo_tb_queue_action.currentIndexChanged.connect(self._on_toolbar_queue_action_changed)
        tb_queue_layout.addWidget(self.combo_tb_queue_action)

        toolbar.addWidget(tb_queue_widget)

        # Central Widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # Left: Categories Tree
        self.tree_categories = QTreeWidget()
        self.tree_categories.setHeaderHidden(True)
        self.tree_categories.setFixedWidth(200)

        root_all = QTreeWidgetItem(["📥 Tüm İndirmeler"])
        root_all.setData(0, Qt.ItemDataRole.UserRole, "All")
        self.tree_categories.addTopLevelItem(root_all)

        cats = [
            ("⏳ Devam Edenler", "Downloading"),
            ("✔ Tamamlananlar", "Completed"),
            ("⏸ Duraklatılanlar", "Paused"),
            ("❌ Hatalar", "Error"),
            ("🎬 Videolar", "Video"),
            ("🎵 Müzik", "Music"),
            ("📄 Belgeler", "Documents"),
            ("📦 Sıkıştırılmış", "Compressed"),
            ("💻 Programlar", "Programs"),
            ("📁 Diğer", "Others")
        ]
        for name, key in cats:
            item = QTreeWidgetItem([name])
            item.setData(0, Qt.ItemDataRole.UserRole, key)
            root_all.addChild(item)

        root_all.setExpanded(True)
        self.tree_categories.currentItemChanged.connect(self._on_category_changed)
        splitter.addWidget(self.tree_categories)

        # Right: Downloads Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Dosya Adı", "Boyut", "İlerleme", "Hız", "Kalan Süre", "Durum", "Eklenme Tarihi"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 150)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 160)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_table_context_menu)
        self.table.cellDoubleClicked.connect(self._on_row_double_click)

        # Keyboard shortcuts for table
        self.shortcut_delete = QShortcut(QKeySequence.StandardKey.Delete, self.table)
        self.shortcut_delete.activated.connect(self._delete_selected)

        splitter.addWidget(self.table)
        splitter.setSizes([200, 800])

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.lbl_ext_status = QLabel("🟢 Tarayıcı Köprüsü: Aktif (Port 28710)")
        self.lbl_ext_status.setStyleSheet("color: #9ece6a; font-weight: bold; margin-left: 10px;")
        self.status_bar.addWidget(self.lbl_ext_status)

        self.lbl_speed_stat = QLabel("Toplam Hız: 0 KB/s")
        self.lbl_speed_stat.setStyleSheet("color: #7aa2f7; font-weight: bold; margin-left: 20px;")
        self.status_bar.addWidget(self.lbl_speed_stat)

        self.lbl_limiter_stat = QLabel("⚡ Hız Sınırı: Kapalı (Tam Hız)")
        self.lbl_limiter_stat.setStyleSheet("color: #9ece6a; font-weight: bold; margin-left: 20px;")
        self.status_bar.addWidget(self.lbl_limiter_stat)

        self.lbl_scheduler_stat = QLabel("⏱ Zamanlayıcı: Kapalı")
        self.lbl_scheduler_stat.setStyleSheet("color: #7982a9; font-weight: bold; margin-left: 20px;")
        self.status_bar.addWidget(self.lbl_scheduler_stat)

        # Load initial speed limit state into toolbar controls
        self._init_speed_limiter_controls()

        # Initial sync for scheduler controls
        st = self.scheduler.get_status()
        self._sync_scheduler_toolbar_ui(st)

    def _init_signals(self):
        # Connect queue manager thread-safe callbacks to PyQt signals
        self.queue_mgr.on_task_progress = lambda did, d, t, s, e: self.sig_progress_update.emit(did, d, t, s, e)
        self.queue_mgr.on_task_segments = lambda did, segs: self.sig_segments_update.emit(did, segs)
        self.queue_mgr.on_task_status = lambda did, st, err: self.sig_status_update.emit(did, st, err)
        self.queue_mgr.on_task_added = lambda rec: self.sig_task_added.emit(rec)
        self.queue_mgr.on_queue_empty = lambda: self.sig_queue_empty.emit()

        # Connect power countdown callbacks
        self.power_mgr.on_tick = lambda remaining, action: self.sig_countdown_tick.emit(remaining, action)
        self.power_mgr.on_executed = lambda action: self.sig_countdown_executed.emit(action)

        # Connect scheduler callbacks
        self.scheduler.on_tick = lambda info: self.sig_scheduler_tick.emit(info)
        self.scheduler.on_schedule_start = lambda: self.sig_scheduler_started.emit()
        self.scheduler.on_schedule_stop = lambda act: self.sig_scheduler_stopped.emit(act)
        self.queue_mgr.on_scheduler_power_action = lambda act: self._handle_scheduler_power_action(act)

        self.sig_progress_update.connect(self._handle_progress_update)
        self.sig_segments_update.connect(self._handle_segments_update)
        self.sig_status_update.connect(self._handle_status_update)
        self.sig_task_added.connect(self._handle_task_added)
        self.sig_bridge_download.connect(self._handle_bridge_download)
        self.sig_queue_empty.connect(self._handle_queue_empty)
        self.sig_countdown_tick.connect(self._handle_countdown_tick)
        self.sig_countdown_executed.connect(self._handle_countdown_executed)
        self.sig_scheduler_tick.connect(self._handle_scheduler_tick)
        self.sig_scheduler_started.connect(self._handle_scheduler_started)
        self.sig_scheduler_stopped.connect(self._handle_scheduler_stopped)

    def _load_downloads_to_table(self):
        self.table.setRowCount(0)
        downloads = self.db.get_all_downloads()
        for dl in downloads:
            self._add_or_update_table_row(dl)

    def _find_row_by_id(self, download_id: str) -> int:
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == download_id:
                return r
        return -1

    def _add_or_update_table_row(self, dl: Dict[str, Any]):
        download_id = dl["id"]
        row = self._find_row_by_id(download_id)
        if row == -1:
            row = self.table.rowCount()
            self.table.insertRow(row)

        item_name = QTableWidgetItem(dl.get("filename", "download"))
        item_name.setData(Qt.ItemDataRole.UserRole, download_id)
        self.table.setItem(row, 0, item_name)

        tot = dl.get("total_size", -1)
        done = dl.get("downloaded_size", 0)
        status = dl.get("status", "Queued")
        if status == "Completed" and tot > 0:
            self.table.setItem(row, 1, QTableWidgetItem(format_size(tot)))
        elif status == "Completed" and done > 0:
            self.table.setItem(row, 1, QTableWidgetItem(format_size(done)))
        elif status in ("Downloading", "Paused", "Probing"):
            self.table.setItem(row, 1, QTableWidgetItem(format_progress_size(done, tot)))
        elif tot > 0:
            self.table.setItem(row, 1, QTableWidgetItem(format_size(tot)))
        else:
            self.table.setItem(row, 1, QTableWidgetItem("Bilinmiyor"))

        # Progress bar widget
        prog = QProgressBar()
        prog.setRange(0, 100)
        pct = int((done / tot) * 100) if tot > 0 else (100 if status == "Completed" else 0)
        prog.setValue(min(100, max(0, pct)))
        self.table.setCellWidget(row, 2, prog)

        speed = dl.get("speed", 0)
        self.table.setItem(row, 3, QTableWidgetItem(format_speed(speed) if speed > 0 else "--"))

        eta = dl.get("eta", 0)
        self.table.setItem(row, 4, QTableWidgetItem(format_eta(eta) if eta > 0 else "--"))

        self.table.setItem(row, 5, QTableWidgetItem(status))

        date_add = dl.get("date_added", "")
        self.table.setItem(row, 6, QTableWidgetItem(date_add))

    def _handle_progress_update(self, download_id: str, downloaded: int, total: int, speed: float, eta: int):
        row = self._find_row_by_id(download_id)
        if row >= 0:
            self.table.item(row, 1).setText(format_progress_size(downloaded, total))
            if total > 0:
                pct = int((downloaded / total) * 100)
                prog = self.table.cellWidget(row, 2)
                if isinstance(prog, QProgressBar):
                    prog.setValue(min(100, pct))
            self.table.item(row, 3).setText(format_speed(speed))
            self.table.item(row, 4).setText(format_eta(eta))

        # Forward to open progress dialog if visible
        if download_id in self.active_dialogs:
            self.active_dialogs[download_id].update_progress(downloaded, total, speed, eta)

        # Update total speed in status bar
        active_speeds = [d.speed_limiter.get_limit() or sum(s.current_speed for s in d.segments)
                         for d in self.queue_mgr.active_downloaders.values()]
        tot_speed = sum(sum(s.current_speed for s in d.segments) for d in self.queue_mgr.active_downloaders.values())
        self.lbl_speed_stat.setText(f"Toplam Hız: {format_speed(tot_speed)}")

    def _handle_segments_update(self, download_id: str, segments: list):
        if download_id in self.active_dialogs:
            dl_obj = self.queue_mgr.get_downloader(download_id)
            tot = dl_obj.total_size if dl_obj else -1
            self.active_dialogs[download_id].update_segments(segments, tot)

    def _handle_status_update(self, download_id: str, status: str, err: str):
        row = self._find_row_by_id(download_id)
        if row >= 0:
            self.table.item(row, 5).setText(status)
            rec = self.db.get_download(download_id)
            if rec:
                if rec.get("filename"):
                    self.table.item(row, 0).setText(rec["filename"])
                t_size = rec.get("total_size", -1)
                d_size = rec.get("downloaded_size", 0)
                if status == "Completed":
                    final_size = t_size if t_size > 0 else d_size
                    self.table.item(row, 1).setText(format_size(final_size))
                elif status in ("Downloading", "Paused", "Probing"):
                    self.table.item(row, 1).setText(format_progress_size(d_size, t_size))
                elif t_size > 0:
                    self.table.item(row, 1).setText(format_size(t_size))

            if status == "Completed":
                prog = self.table.cellWidget(row, 2)
                if isinstance(prog, QProgressBar):
                    prog.setValue(100)
                self.table.item(row, 3).setText("--")
                self.table.item(row, 4).setText("0 sn")
                if rec:
                    toast_en = bool(self.db.get_setting("toast_notifications", True))
                    if toast_en:
                        is_vid = rec.get("category") == "Video"
                        self.tray.notify_completed(
                            filename=rec["filename"],
                            save_path=rec.get("save_path", ""),
                            is_video=is_vid
                        )

        if download_id in self.active_dialogs:
            self.active_dialogs[download_id].update_status(status, err)

    def _handle_task_added(self, rec: Dict[str, Any]):
        self._add_or_update_table_row(rec)

    def _handle_bridge_download(self, data: dict):
        """Called when Chrome extension sends a download request."""
        url = data.get("url", "")
        filename = data.get("filename", "")
        headers = {}
        if data.get("referer"):
            headers["Referer"] = data["referer"]
        if data.get("cookies"):
            headers["Cookie"] = data["cookies"]
        if data.get("userAgent"):
            headers["User-Agent"] = data["userAgent"]

        # Show Add Download Dialog prefilled
        quality = data.get("quality", "max")
        default_dir = self.db.get_setting("default_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
        auto_cat = bool(self.db.get_setting("auto_categorize", True))

        self.activateWindow()
        self.raise_()
        dlg = AddDownloadDialog(
            initial_url=url,
            initial_filename=filename,
            headers=headers,
            initial_quality=quality,
            base_download_dir=default_dir,
            auto_categorize=auto_cat,
            parent=self
        )
        dlg.download_confirmed.connect(self._on_download_confirmed)
        dlg.exec()

    def _on_clipboard_link_detected(self, url: str, info: dict):
        """Called when ClipboardMonitor detects a downloadable or video URL."""
        # Show sleek toast notification popup
        self.clip_popup.show_for_url(url, info)

    def _handle_clipboard_download(self, url: str, start_immediately: bool, info: dict = None):
        """Called from ClipboardNotificationPopup when user clicks download or customize."""
        info = info or {}
        candidate_filename = info.get("filename", "")
        is_playlist = info.get("is_playlist", False) or is_youtube_playlist_url(url)

        if is_playlist:
            # Open Playlist Download Dialog directly so user can review and pick videos
            self.activateWindow()
            self.raise_()
            self._show_playlist_dialog(initial_url=url)
            return

        if start_immediately:
            # Add directly to queue with user's default settings
            default_dir = self.db.get_setting("default_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
            conns = int(self.db.get_setting("connections", 8))
            pref_quality = self.db.get_setting("preferred_quality", "max")

            did = self.queue_mgr.add_download(
                url=url,
                save_dir=default_dir,
                filename=candidate_filename,
                connections=conns,
                quality=pref_quality,
                headers={},
                start_now=True
            )
            # Show progress window for download
            self._open_progress_dialog(did)
            # Also notify tray
            self.tray.showMessage(
                "İndirme Başlatıldı",
                f"Bağlantı indirme kuyruğuna alındı:\n{url[:60]}...",
                QSystemTrayIcon.MessageIcon.Information,
                2500
            )
        else:
            # Bring main window or dialog to front
            self.activateWindow()
            self.raise_()
            self._show_add_dialog(initial_url=url, initial_filename=candidate_filename)

    def _show_add_dialog(self, initial_url: str = "", initial_filename: str = ""):
        default_dir = self.db.get_setting("default_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
        auto_cat = bool(self.db.get_setting("auto_categorize", True))
        dlg = AddDownloadDialog(
            initial_url=initial_url,
            initial_filename=initial_filename,
            base_download_dir=default_dir,
            auto_categorize=auto_cat,
            parent=self
        )
        dlg.download_confirmed.connect(self._on_download_confirmed)
        dlg.open_playlist_requested.connect(lambda p_url: self._show_playlist_dialog(initial_url=p_url))
        dlg.exec()

    def _show_playlist_dialog(self, initial_url: str = ""):
        default_dir = self.db.get_setting("default_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
        pref_quality = self.db.get_setting("preferred_quality", "max")
        dlg = PlaylistDownloadDialog(
            initial_url=initial_url,
            base_download_dir=default_dir,
            initial_quality=pref_quality,
            parent=self
        )
        dlg.batch_download_confirmed.connect(self._on_batch_playlist_download)
        dlg.exec()

    def _on_batch_playlist_download(self, items: list, start_now: bool):
        """
        Adds all selected playlist videos to the queue.
        If start_now is True, sequential queue automatically starts up to max_concurrent items,
        queuing the rest sequentially so they download one after another cleanly.
        """
        if not items:
            return

        added_ids = []
        first_id = None

        for item in items:
            did = self.queue_mgr.add_download(
                url=item["url"],
                save_dir=item["save_dir"],
                filename=item["filename"],
                connections=item.get("connections", 8),
                quality=item.get("quality", "max"),
                headers=item.get("headers"),
                start_now=start_now
            )
            added_ids.append(did)
            if not first_id:
                first_id = did

        total_added = len(added_ids)
        if start_now:
            msg = f"{total_added} video indirme kuyruğuna alındı ve sırayla indirilmeye başlandı."
            self.statusBar().showMessage(msg, 5000)
            self.tray.showMessage("Çalma Listesi İndiriliyor", msg, QSystemTrayIcon.MessageIcon.Information, 3500)
            if first_id:
                self._open_progress_dialog(first_id)
        else:
            msg = f"{total_added} video indirme kuyruğuna eklendi (Daha sonra indirilmek üzere)."
            self.statusBar().showMessage(msg, 5000)
            self.tray.showMessage("Kuyruğa Eklendi", msg, QSystemTrayIcon.MessageIcon.Information, 3000)

    def _on_download_confirmed(self, data: dict):
        did = self.queue_mgr.add_download(
            url=data["url"],
            save_dir=data["save_dir"],
            filename=data["filename"],
            connections=data["connections"],
            quality=data.get("quality", "max"),
            headers=data.get("headers"),
            start_now=data["start_now"]
        )
        if data["start_now"]:
            self._open_progress_dialog(did)

    def _open_progress_dialog(self, download_id: str):
        if download_id in self.active_dialogs:
            self.active_dialogs[download_id].show()
            self.active_dialogs[download_id].raise_()
            return

        rec = self.db.get_download(download_id)
        if not rec:
            return

        # Determine current active limit for this downloader
        active_dl = self.queue_mgr.get_downloader(download_id)
        current_limit = active_dl.speed_limiter.get_limit() if active_dl else self.queue_mgr.global_speed_limit_bps

        dlg = ProgressDialog(download_id, rec["filename"], rec["save_path"], initial_speed_limit=current_limit, parent=self)
        dlg.pause_requested.connect(self.queue_mgr.pause_download)
        dlg.resume_requested.connect(self.queue_mgr.resume_download)
        dlg.cancel_requested.connect(self.queue_mgr.cancel_download)
        dlg.speed_limit_changed.connect(self._handle_single_task_speed_limit)

        self.active_dialogs[download_id] = dlg
        dlg.show()

    def _on_row_double_click(self, row: int, col: int):
        item = self.table.item(row, 0)
        if not item:
            return
        download_id = item.data(Qt.ItemDataRole.UserRole)
        rec = self.db.get_download(download_id)
        if not rec:
            return

        if rec["status"] == "Completed":
            # Open file
            self._open_selected_file()
        else:
            self._open_progress_dialog(download_id)

    def _get_selected_download_id(self) -> Optional[str]:
        ids = self._get_selected_download_ids()
        return ids[0] if ids else None

    def _get_selected_download_ids(self) -> List[str]:
        """Returns list of unique download IDs currently selected in the table."""
        selected_ids = []
        for item in self.table.selectedItems():
            if item.column() == 0:
                did = item.data(Qt.ItemDataRole.UserRole)
                if did and did not in selected_ids:
                    selected_ids.append(did)
        return selected_ids

    def _start_selected(self):
        dids = self._get_selected_download_ids()
        for did in dids:
            self.queue_mgr.resume_download(did)
        if len(dids) == 1:
            self._open_progress_dialog(dids[0])

    def _pause_selected(self):
        dids = self._get_selected_download_ids()
        for did in dids:
            self.queue_mgr.pause_download(did)

    def _cancel_selected(self):
        dids = self._get_selected_download_ids()
        for did in dids:
            self.queue_mgr.cancel_download(did)

    def _delete_selected(self):
        dids = self._get_selected_download_ids()
        if not dids:
            return
        count = len(dids)
        if count == 1:
            msg = "Bu indirmeyi listeden silmek istediğinize emin misiniz?"
            title = "İndirmeyi Sil"
        else:
            msg = f"Seçilen {count} adet indirmeyi listeden kaldırmak istediğinize emin misiniz?"
            title = "Toplu Silme (Listeden Kaldır)"

        reply = QMessageBox.question(
            self,
            title,
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            for did in dids:
                self.queue_mgr.delete_download(did, delete_file=False)
            self._load_downloads_to_table()

    def _delete_selected_with_files(self):
        dids = self._get_selected_download_ids()
        if not dids:
            return
        count = len(dids)
        if count == 1:
            msg = "Bu indirmeyi ve indirilmiş dosyasını kalıcı olarak diskten silmek istiyor musunuz?"
            title = "Dosyayı ve İndirmeyi Sil"
        else:
            msg = f"Seçilen {count} adet indirmeyi ve dosyalarını kalıcı olarak diskten silmek istiyor musunuz?"
            title = "Toplu Dosya Silme"

        reply = QMessageBox.question(
            self,
            title,
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            for did in dids:
                self.queue_mgr.delete_download(did, delete_file=True)
            self._load_downloads_to_table()

    def _open_selected_file(self):
        did = self._get_selected_download_id()
        if not did:
            return
        rec = self.db.get_download(did)
        if rec and os.path.exists(rec["save_path"]):
            os.startfile(rec["save_path"])
        else:
            QMessageBox.warning(self, "Uyarı", "Dosya henüz indirilmedi veya bulunamadı.")

    def _open_selected_folder(self):
        did = self._get_selected_download_id()
        if not did:
            return
        rec = self.db.get_download(did)
        if rec:
            folder = os.path.dirname(rec["save_path"])
            if os.path.exists(folder):
                subprocess.Popen(f'explorer /select,"{os.path.abspath(rec["save_path"])}"')
            else:
                QMessageBox.warning(self, "Uyarı", "Klasör bulunamadı.")

    def _on_start_all(self):
        self.queue_mgr.start_queue()

    def _on_pause_all(self):
        self.queue_mgr.pause_queue()

    def _init_speed_limiter_controls(self):
        """Sync toolbar speed limiter controls with stored DB settings."""
        speed_en = bool(self.db.get_setting("speed_limit_enabled", False))
        speed_kb = int(self.db.get_setting("speed_limit_kb", 5120))  # Default 5 MB/s

        self.chk_tb_speed_limit.blockSignals(True)
        self.slider_tb_limit.blockSignals(True)
        self.combo_tb_limit.blockSignals(True)

        self.slider_tb_limit.setValue(speed_kb)
        self.chk_tb_speed_limit.setChecked(speed_en)
        self.slider_tb_limit.setEnabled(speed_en)
        self.combo_tb_limit.setEnabled(speed_en)

        # Set combo index if matches
        idx = self.combo_tb_limit.findData(speed_kb)
        if idx >= 0:
            self.combo_tb_limit.setCurrentIndex(idx)

        self.chk_tb_speed_limit.blockSignals(False)
        self.slider_tb_limit.blockSignals(False)
        self.combo_tb_limit.blockSignals(False)

        self._update_toolbar_limit_ui(speed_en, speed_kb)

    def _update_toolbar_limit_ui(self, enabled: bool, kb_val: int):
        if enabled:
            if kb_val >= 1024:
                mb = kb_val / 1024.0
                txt = f"{int(mb)} MB/s" if mb == int(mb) else f"{mb:.1f} MB/s"
            else:
                txt = f"{kb_val} KB/s"
            self.lbl_tb_limit_val.setText(txt)
            self.lbl_tb_limit_val.setStyleSheet("font-weight: bold; color: #ff9e64; min-width: 75px;")
            self.lbl_limiter_stat.setText(f"⚡ Hız Sınırı: Aktif ({txt})")
            self.lbl_limiter_stat.setStyleSheet("color: #ff9e64; font-weight: bold; margin-left: 20px;")
        else:
            self.lbl_tb_limit_val.setText("Tam Hız")
            self.lbl_tb_limit_val.setStyleSheet("font-weight: bold; color: #9ece6a; min-width: 75px;")
            self.lbl_limiter_stat.setText("⚡ Hız Sınırı: Kapalı (Tam Hız)")
            self.lbl_limiter_stat.setStyleSheet("color: #9ece6a; font-weight: bold; margin-left: 20px;")

    def _on_toolbar_limit_toggled(self, enabled: bool):
        self.slider_tb_limit.setEnabled(enabled)
        self.combo_tb_limit.setEnabled(enabled)
        kb_val = self.slider_tb_limit.value()

        self.db.set_setting("speed_limit_enabled", enabled)
        self.db.set_setting("speed_limit_kb", kb_val)

        if enabled:
            self.queue_mgr.set_global_speed_limit(kb_val * 1024)
        else:
            self.queue_mgr.set_global_speed_limit(0)

        self._update_toolbar_limit_ui(enabled, kb_val)

    def _on_toolbar_slider_changed(self, value: int):
        self.combo_tb_limit.blockSignals(True)
        idx = self.combo_tb_limit.findData(value)
        if idx >= 0:
            self.combo_tb_limit.setCurrentIndex(idx)
        else:
            self.combo_tb_limit.setCurrentIndex(-1)
        self.combo_tb_limit.blockSignals(False)

        self.db.set_setting("speed_limit_kb", value)
        if self.chk_tb_speed_limit.isChecked():
            self.queue_mgr.set_global_speed_limit(value * 1024)
            self._update_toolbar_limit_ui(True, value)

    def _on_toolbar_combo_changed(self, index: int):
        val = self.combo_tb_limit.currentData()
        if val is not None:
            self.slider_tb_limit.setValue(val)

    def _on_tray_speed_limit_requested(self, kb_val: int):
        """Called from tray icon menu to change global speed limit."""
        if kb_val <= 0:
            self.chk_tb_speed_limit.setChecked(False)
            self.tray.showMessage(
                "Hız Sınırlayıcı",
                "Tam Hıza Geçildi (Sınırsız).",
                QSystemTrayIcon.MessageIcon.Information if hasattr(QSystemTrayIcon, "MessageIcon") else 1,
                2000
            )
        else:
            self.slider_tb_limit.setValue(kb_val)
            self.chk_tb_speed_limit.setChecked(True)
            txt = f"{kb_val / 1024:.1f} MB/s" if kb_val >= 1024 else f"{kb_val} KB/s"
            self.tray.showMessage(
                "Hız Sınırlayıcı",
                f"Hız {txt} ile sınırlandı.",
                QSystemTrayIcon.MessageIcon.Information if hasattr(QSystemTrayIcon, "MessageIcon") else 1,
                2000
            )

    def _handle_single_task_speed_limit(self, download_id: str, bps: int):
        """Applied when user tweaks speed limiter slider inside a specific download's ProgressDialog."""
        self.queue_mgr.set_download_speed_limit(download_id, bps)

    def _set_single_download_speed_limit(self, download_id: str, kb_val: int):
        """Set speed limit directly from context menu (0 means unlimited / full speed)."""
        bps = kb_val * 1024
        self.queue_mgr.set_download_speed_limit(download_id, bps)
        if download_id in self.active_dialogs:
            dlg = self.active_dialogs[download_id]
            if bps > 0:
                dlg.chk_limit.setChecked(True)
                dlg.slider_limit.setValue(kb_val)
            else:
                dlg.chk_limit.setChecked(False)

    def _show_settings_dialog(self):
        dlg = SettingsDialog(self.db, self)
        if dlg.exec():
            # Apply modified settings
            max_c = self.db.get_setting("max_concurrent", 3)
            self.queue_mgr.set_max_concurrent(int(max_c))
            speed_en = self.db.get_setting("speed_limit_enabled", False)
            if speed_en:
                kb = self.db.get_setting("speed_limit_kb", 1024)
                self.queue_mgr.set_global_speed_limit(int(kb) * 1024)
            else:
                self.queue_mgr.set_global_speed_limit(0)

            # Keep toolbar UI in sync with settings dialog
            self._init_speed_limiter_controls()

            # Keep queue action in sync
            self.current_queue_action = self.db.get_setting("on_queue_complete_action", "none")
            idx_qa = self.combo_tb_queue_action.findData(self.current_queue_action)
            if idx_qa >= 0:
                self.combo_tb_queue_action.blockSignals(True)
                self.combo_tb_queue_action.setCurrentIndex(idx_qa)
                self.combo_tb_queue_action.blockSignals(False)
            self.tray.update_queue_action_ui(self.current_queue_action)

            clip_en = self.db.get_setting("clipboard_enabled", True)
            self.clip_monitor.set_enabled(bool(clip_en))

    def _show_extension_guide(self):
        port = int(self.db.get_setting("extension_port", 28710))
        from ui.extension_guide_dialog import ExtensionGuideDialog
        dlg = ExtensionGuideDialog(self, bridge_port=port)
        dlg.exec()

    def _show_table_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        did = self.table.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        rec = self.db.get_download(did)
        if not rec:
            return

        selected_ids = self._get_selected_download_ids()
        # If right clicked on an unselected row, select it
        if did not in selected_ids:
            selected_ids = [did]

        menu = QMenu(self)
        status = rec["status"]
        count = len(selected_ids)

        if count > 1:
            # Multi-selection context actions
            menu.addAction(f"📌 {count} İndirme Seçildi").setEnabled(False)
            menu.addSeparator()

            act_start_bulk = menu.addAction(f"▶ Seçilenleri Başlat ({count})")
            act_start_bulk.triggered.connect(self._start_selected)

            act_pause_bulk = menu.addAction(f"⏸ Seçilenleri Duraklat ({count})")
            act_pause_bulk.triggered.connect(self._pause_selected)

            act_stop_bulk = menu.addAction(f"⏹ Seçilenleri İptal Et ({count})")
            act_stop_bulk.triggered.connect(self._cancel_selected)

            menu.addSeparator()
            act_del_bulk = menu.addAction(f"🗑 Seçilenleri Listeden Kaldır ({count})")
            act_del_bulk.triggered.connect(self._delete_selected)

            act_del_files_bulk = menu.addAction(f"💥 Seçilenleri ve Dosyalarını Tamamen Sil ({count})")
            act_del_files_bulk.triggered.connect(self._delete_selected_with_files)

            menu.exec(self.table.viewport().mapToGlobal(pos))
            return

        if status in ("Downloading", "Probing"):
            act = menu.addAction("⏸ Duraklat")
            act.triggered.connect(lambda: self.queue_mgr.pause_download(did))
        else:
            act = menu.addAction("▶ Başlat / Devam Et")
            act.triggered.connect(lambda: self.queue_mgr.resume_download(did))

        act_prog = menu.addAction("📊 İlerleme Detayı (IDM Segment Penceresi)")
        act_prog.triggered.connect(lambda: self._open_progress_dialog(did))

        # Queue reordering options if Queued
        if status == "Queued":
            menu_queue = menu.addMenu("📋 Kuyruk Sırası (Öncelik)")
            act_up = menu_queue.addAction("⬆ Kuyrukta Yukarı Taşı")
            act_up.triggered.connect(lambda: self._move_download_order(did, "up"))
            act_down = menu_queue.addAction("⬇ Kuyrukta Aşağı Taşı")
            act_down.triggered.connect(lambda: self._move_download_order(did, "down"))
            act_top = menu_queue.addAction("⚡ Kuyruğun Başına Al")
            act_top.triggered.connect(lambda: self._move_download_order(did, "top"))

        # Speed Limiter Submenu for selected item (IDM style single-click limit)
        menu_limiter = menu.addMenu("⚡ Hız Sınırı (Speed Limiter)")
        act_unlimit = menu_limiter.addAction("🚀 Tam Hız (Sınırsız)")
        act_unlimit.triggered.connect(lambda: self._set_single_download_speed_limit(did, 0))

        menu_limiter.addSeparator()
        for label, kb_val in [
            ("512 KB/s", 512),
            ("1 MB/s", 1024),
            ("2 MB/s", 2048),
            ("5 MB/s (Önerilen)", 5120),
            ("10 MB/s", 10240),
            ("25 MB/s", 25600),
            ("50 MB/s", 51200),
        ]:
            act_preset = menu_limiter.addAction(f"⏱ {label}")
            act_preset.triggered.connect(lambda checked, k=kb_val: self._set_single_download_speed_limit(did, k))

        menu.addSeparator()

        if status == "Completed":
            act_open = menu.addAction("📂 Dosyayı Aç")
            act_open.triggered.connect(self._open_selected_file)

        act_folder = menu.addAction("📁 Klasörde Göster")
        act_folder.triggered.connect(self._open_selected_folder)

        menu.addSeparator()

        act_del = menu.addAction("🗑 Listeden Kaldır")
        act_del.triggered.connect(self._delete_selected)

        act_del_all = menu.addAction("💥 Dosya ile Birlikte Tamamen Sil")
        act_del_all.triggered.connect(self._delete_selected_with_files)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _delete_with_file(self, download_id: Optional[str] = None):
        if download_id:
            reply = QMessageBox.question(
                self,
                "Dosyayı Sil",
                "Dosyayı ve indirilen kaydı kalıcı olarak diskten silmek istiyor musunuz?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.queue_mgr.delete_download(download_id, delete_file=True)
                self._load_downloads_to_table()
        else:
            self._delete_selected_with_files()

    def _on_category_changed(self, current: QTreeWidgetItem, previous: QTreeWidgetItem):
        if not current:
            return
        key = current.data(0, Qt.ItemDataRole.UserRole)
        self.current_category = key

        # Filter downloads
        if key in ("Downloading", "Completed", "Paused", "Error"):
            downloads = self.db.get_all_downloads(status=key)
        elif key == "All":
            downloads = self.db.get_all_downloads()
        else:
            downloads = self.db.get_all_downloads(category=key)

        self.table.setRowCount(0)
        for dl in downloads:
            self._add_or_update_table_row(dl)

    def _on_toolbar_queue_action_changed(self, index: int):
        act = self.combo_tb_queue_action.currentData() or "none"
        self.current_queue_action = act
        self.db.set_setting("on_queue_complete_action", act)
        self.tray.update_queue_action_ui(act)

    def _on_queue_action_changed_from_tray(self, action: str):
        self.current_queue_action = action
        self.db.set_setting("on_queue_complete_action", action)
        idx = self.combo_tb_queue_action.findData(action)
        if idx >= 0:
            self.combo_tb_queue_action.blockSignals(True)
            self.combo_tb_queue_action.setCurrentIndex(idx)
            self.combo_tb_queue_action.blockSignals(False)

        desc = "Bilgisayarı Kapat" if action == "shutdown" else ("Uyku Moduna Al" if action == "sleep" else "Eylem Yok")
        self.tray.showMessage(
            "Kuyruk Bittiğinde",
            f"Kuyruk bitiş eylemi: {desc}",
            QSystemTrayIcon.MessageIcon.Information if hasattr(QSystemTrayIcon, "MessageIcon") else 1,
            2000
        )

    def _handle_queue_empty(self):
        """Called when all active downloads finish and no items remain queued."""
        action = self.current_queue_action
        if action not in ("shutdown", "sleep"):
            return

        if self.power_mgr.is_active():
            return

        # Show countdown dialog
        self.power_dialog = PowerCountdownDialog(action=action, total_seconds=30, parent=self)
        self.power_dialog.cancelled.connect(self._cancel_power_countdown)
        self.power_dialog.accepted.connect(self._execute_power_immediately)

        self.power_mgr.start_countdown(action, seconds=30)
        self.power_dialog.show()
        self.power_dialog.raise_()
        self.power_dialog.activateWindow()

    def _handle_countdown_tick(self, remaining: int, action: str):
        if self.power_dialog and self.power_dialog.isVisible():
            self.power_dialog.update_countdown(remaining)

    def _handle_countdown_executed(self, action: str):
        if self.power_dialog:
            self.power_dialog.close()
            self.power_dialog = None

    def _cancel_power_countdown(self):
        self.power_mgr.cancel()
        if self.power_dialog:
            self.power_dialog.close()
            self.power_dialog = None
        self.tray.showMessage(
            "Güç Yönetimi",
            "Otomatik kapatma / uyku işlemi kullanıcı tarafından iptal edildi.",
            QSystemTrayIcon.MessageIcon.Information if hasattr(QSystemTrayIcon, "MessageIcon") else 1,
            3000
        )

    def _execute_power_immediately(self):
        act = self.current_queue_action
        self.power_mgr.cancel()
        if self.power_dialog:
            self.power_dialog.close()
            self.power_dialog = None
        from core.power_manager import execute_shutdown, execute_sleep
        if act == "shutdown":
            execute_shutdown(timeout_seconds=0)
        elif act == "sleep":
            execute_sleep()

    def _move_download_order(self, download_id: str, direction: str):
        if direction == "top":
            self.queue_mgr.move_queue_to_top(download_id)
        else:
            self.queue_mgr.reorder_queue(download_id, direction)
        self._load_downloads_to_table()

    def _show_scheduler_dialog(self):
        dlg = SchedulerDialog(self.db, self.queue_mgr, self.scheduler, parent=self)
        dlg.queue_started.connect(self._on_start_all)
        dlg.queue_paused.connect(self._on_pause_all)
        if dlg.exec():
            # Sync toolbar concurrent spinbox
            self.spin_tb_concurrent.blockSignals(True)
            self.spin_tb_concurrent.setValue(self.queue_mgr.max_concurrent)
            self.spin_tb_concurrent.blockSignals(False)

            # Sync scheduler UI status
            st = self.scheduler.get_status()
            self._sync_scheduler_toolbar_ui(st)

    def _on_toolbar_concurrent_changed(self, val: int):
        self.queue_mgr.set_max_concurrent(val)

    def _on_toolbar_scheduler_toggled(self, checked: bool):
        self.scheduler.update_config(enabled=checked)
        self.db.save_scheduler_settings({"enabled": checked})
        st = self.scheduler.get_status()
        self._sync_scheduler_toolbar_ui(st)
        self.tray.update_scheduler_ui(checked, st.get("state_text", ""))

    def _toggle_scheduler_from_tray(self, enabled: bool):
        self.chk_tb_scheduler.setChecked(enabled)

    def _handle_scheduler_tick(self, info: dict):
        self._sync_scheduler_toolbar_ui(info)
        # Update status bar
        if not info["enabled"]:
            self.lbl_scheduler_stat.setText("⏱ Zamanlayıcı: Kapalı")
            self.lbl_scheduler_stat.setStyleSheet("color: #7982a9; font-weight: bold; margin-left: 20px;")
        elif info["is_in_window"]:
            txt = f"⏱ Zamanlayıcı: {info['state_text']} (Kalan: {info['time_remaining_str']})"
            self.lbl_scheduler_stat.setText(txt)
            self.lbl_scheduler_stat.setStyleSheet("color: #9ece6a; font-weight: bold; margin-left: 20px;")
        else:
            txt = f"⏱ Zamanlayıcı: {info['state_text']} (Kalan: {info['time_remaining_str']})"
            self.lbl_scheduler_stat.setText(txt)
            self.lbl_scheduler_stat.setStyleSheet("color: #e0af68; font-weight: bold; margin-left: 20px;")

        self.tray.update_scheduler_ui(info["enabled"], info.get("state_text", ""))

    def _sync_scheduler_toolbar_ui(self, info: dict):
        en = info.get("enabled", False)
        self.chk_tb_scheduler.blockSignals(True)
        self.chk_tb_scheduler.setChecked(en)
        self.chk_tb_scheduler.blockSignals(False)

        start_s = info.get("start_time_str", "02:00")
        stop_s = info.get("stop_time_str", "07:00")
        self.lbl_tb_sched_time.setText(f"{start_s} - {stop_s}")

        if not en:
            self.lbl_tb_sched_badge.setText("Kapalı")
            self.lbl_tb_sched_badge.setStyleSheet("font-weight: bold; color: #7982a9; min-width: 60px;")
        elif info.get("is_in_window"):
            self.lbl_tb_sched_badge.setText("İndiriliyor")
            self.lbl_tb_sched_badge.setStyleSheet("font-weight: bold; color: #9ece6a; min-width: 60px;")
        else:
            self.lbl_tb_sched_badge.setText("Beklemede")
            self.lbl_tb_sched_badge.setStyleSheet("font-weight: bold; color: #e0af68; min-width: 60px;")

    def _handle_scheduler_started(self):
        self.tray.showMessage(
            "⏱ Zamanlayıcı Başlatıldı",
            f"Gece indirme saati geldi ({self.scheduler.start_time_str}). İndirme kuyruğu başlatıldı.",
            QSystemTrayIcon.MessageIcon.Information if hasattr(QSystemTrayIcon, "MessageIcon") else 1,
            4000
        )

    def _handle_scheduler_stopped(self, action: str):
        self.tray.showMessage(
            "⏱ Zamanlayıcı Durduruldu",
            f"Planlanan bitiş saatine ulaşıldı ({self.scheduler.stop_time_str}). İndirmeler duraklatıldı.",
            QSystemTrayIcon.MessageIcon.Information if hasattr(QSystemTrayIcon, "MessageIcon") else 1,
            4000
        )
        if action in ("shutdown", "sleep"):
            self._handle_scheduler_power_action(action)

    def _handle_scheduler_power_action(self, action: str):
        if self.power_mgr.is_active():
            return
        self.power_dialog = PowerCountdownDialog(action=action, total_seconds=30, parent=self)
        self.power_dialog.cancelled.connect(self._cancel_power_countdown)
        self.power_dialog.accepted.connect(self._execute_power_immediately)
        self.power_mgr.start_countdown(action, seconds=30)
        self.power_dialog.show()
        self.power_dialog.raise_()
        self.power_dialog.activateWindow()

    def _toggle_window(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.activateWindow()

    def _quit_application(self):
        """Cleanly quits the application from tray menu."""
        self.scheduler.stop()
        self.power_mgr.cancel()
        self.tray.hide()
        QApplication.instance().quit()

    def closeEvent(self, event):
        # Check setting: minimize to tray or quit
        close_to_tray = bool(self.db.get_setting("close_to_tray", True))
        if close_to_tray:
            # Minimize to tray instead of quitting
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "RipSync Arka Planda",
                "Uygulama sistem tepsisinde (Tray) çalışmaya devam ediyor.",
                QSystemTrayIcon.MessageIcon.Information if hasattr(QSystemTrayIcon, "MessageIcon") else 1,
                2000
            )
        else:
            self.scheduler.stop()
            self.power_mgr.cancel()
            self.tray.hide()
            event.accept()
