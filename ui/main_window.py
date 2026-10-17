import os
import subprocess
from typing import Dict, Any, Optional, List
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeWidget, QTreeWidgetItem, QTableWidget,
    QTableWidgetItem, QHeaderView, QToolBar, QPushButton,
    QLabel, QProgressBar, QMenu, QMessageBox, QStatusBar,
    QApplication, QSystemTrayIcon, QSlider, QCheckBox, QComboBox, QSpinBox,
    QLineEdit, QFileDialog, QInputDialog, QToolButton, QSizePolicy, QDialog,
    QStackedWidget, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QUrl, QMimeData
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QShortcut, QDrag, QDragEnterEvent, QDropEvent

from datetime import datetime
from ui.styles import DARK_THEME, get_theme_stylesheet, format_size, format_progress_size, format_speed, format_eta, T
from ui.add_download_dialog import AddDownloadDialog
from ui.progress_dialog import ProgressDialog
from ui.settings_dialog import SettingsDialog
from ui.power_countdown_dialog import PowerCountdownDialog
from ui.scheduler_dialog import SchedulerDialog
from ui.playlist_dialog import PlaylistDownloadDialog
from ui.batch_add_dialog import BatchAddDialog, extract_valid_urls
from ui.checksum_dialog import ChecksumDialog
from ui.properties_dialog import DownloadPropertiesDialog
from ui.statistics_dialog import StatisticsDialog
from ui.refresh_url_dialog import RefreshUrlDialog
from ui.bandwidth_graph import BandwidthGraphWidget
from ui.tray_icon import create_default_icon, TrayIcon
from ui.clipboard_monitor import ClipboardMonitor
from ui.clipboard_popup import ClipboardNotificationPopup
from ui.duplicate_dialog import DuplicateDownloadDialog
from ui.delete_dialog import DeleteConfirmDialog
from core.database import Database
from core.queue_manager import QueueManager
from core.power_manager import (
    PowerCountdownManager, set_global_power_manager,
    is_user_active, get_idle_duration_seconds
)
from core.scheduler import DownloadScheduler
from core.playlist_parser import is_youtube_playlist_url
from core.paths import show_in_explorer, get_disk_total_and_free, get_disk_free_space
from core.notifier import (
    play_completion_sound, play_error_sound, play_warning_sound,
    notify_power_countdown, notify_power_suspended, open_browser_power_alert
)
from core.extractor import is_archive_file, extract_archive_async
from core.logger import get_logger

logger = get_logger("ui.main_window")
from core.stream_downloader import is_stream_url
from core.site_rules import SiteRulesManager
from core.metered_connection import MeteredConnectionMonitor, is_metered_connection


class NumericTableWidgetItem(QTableWidgetItem):
    """QTableWidgetItem with numerical comparison support for size, progress, speed, and ETA."""
    def __lt__(self, other):
        if isinstance(other, QTableWidgetItem):
            val1 = self.data(Qt.ItemDataRole.UserRole)
            val2 = other.data(Qt.ItemDataRole.UserRole)
            if val1 is not None and val2 is not None:
                if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
                    return val1 < val2
        return super().__lt__(other)


class DownloadsTableWidget(QTableWidget):
    """Custom table widget supporting drag & drop outward (dragging completed files to Explorer/apps)
    and hover quick actions (pause/open/reveal) at row level."""

    HOVER_ACTIONS = ("toggle", "open", "folder")

    def __init__(self, parent_window=None, parent=None):
        super().__init__(parent)
        self.parent_window = parent_window
        self.setDragEnabled(True)
        self.setMouseTracking(True)
        self._hover_row = -1
        self._hover_bar: QFrame = None
        self._hover_buttons: dict = {}

    # ---- Satır üstü hızlı eylemler ------------------------------------------
    def _ensure_hover_bar(self):
        if self._hover_bar is None:
            bar = QFrame(self.viewport())
            bar.setObjectName("row_hover_bar")
            bar.setStyleSheet(
                f"QFrame#row_hover_bar {{ background-color: {T['bg_card']};"
                f" border: 1px solid {T['border']}; border-radius: 6px; }}"
                "QPushButton { background: transparent; border: none; padding: 2px 5px; font-size: 13px; }"
                f"QPushButton:hover {{ background-color: {T['bg_hover']}; border-radius: 4px; }}"
            )
            lay = QHBoxLayout(bar)
            lay.setContentsMargins(2, 0, 2, 0)
            lay.setSpacing(1)
            self._btn_toggle = QPushButton("⏯")
            self._btn_toggle.setToolTip("Duraklat / Devam Ettir")
            self._btn_open = QPushButton("📂")
            self._btn_open.setToolTip("Dosyayı Aç")
            self._btn_folder = QPushButton("📁")
            self._btn_folder.setToolTip("Klasörde Göster")
            for btn, act in (
                (self._btn_toggle, self._act_toggle),
                (self._btn_open, self._act_open),
                (self._btn_folder, self._act_folder),
            ):
                btn.setFixedSize(26, 22)
                btn.clicked.connect(act)
                lay.addWidget(btn)
            self._hover_bar = bar
            bar.hide()

    def _row_download(self, row):
        if self.parent_window is None or row < 0:
            return None
        item = self.item(row, 0)
        if not item:
            return None
        did = item.data(Qt.ItemDataRole.UserRole)
        try:
            return self.parent_window.queue_mgr.get_download(did), did
        except Exception:
            return None, None

    def _act_toggle(self):
        rec, did = self._row_download(self._hover_row)
        if not rec or not did:
            return
        qm = self.parent_window.queue_mgr
        status = rec.get("status")
        if status == "Downloading":
            qm.pause_download(did)
        elif status in ("Paused", "Queued", "Error"):
            qm.resume_download(did) if hasattr(qm, "resume_download") else qm.start_download(did)
        else:
            qm.start_download(did)

    def _act_open(self):
        rec, did = self._row_download(self._row_download_row_or_latest())
        if not rec:
            return
        spath = rec.get("save_path") or ""
        if os.path.exists(spath):
            try:
                os.startfile(spath)  # noqa: S606 (platform: Windows)
            except Exception:
                pass

    def _row_download_row_or_latest(self):
        # Butona basıldığında fare satırı değişmiş olabilir; en son görünen satırı kullan.
        return self._hover_row

    def _act_folder(self):
        rec, did = self._row_download(self._hover_row)
        if not rec:
            return
        spath = rec.get("save_path") or ""
        try:
            from core.paths import show_in_explorer
            show_in_explorer(spath if os.path.exists(spath) else os.path.dirname(spath) or spath)
        except Exception:
            pass

    def _update_hover_bar(self, row: int):
        self._ensure_hover_bar()
        rec, did = self._row_download(row)
        if rec is None and did is None:
            self._hover_bar.hide()
            self._hover_row = -1
            return
        self._hover_row = row
        # Toggle düğmesinin duruma uygun simgesi
        status = rec.get("status")
        if status == "Downloading":
            self._btn_toggle.setText("⏸")
            self._btn_toggle.setToolTip("Duraklat")
        elif status in ("Paused", "Queued", "Error", "Retrying"):
            self._btn_toggle.setText("▶")
            self._btn_toggle.setToolTip("Devam Ettir")
        else:
            self._btn_toggle.setText("▶")
            self._btn_toggle.setToolTip("Başlat")
        # Tamamlanan indirmede aç klasik; diğerlerinde gizle
        completed = status == "Completed" and os.path.exists(rec.get("save_path") or "")
        self._btn_open.setVisible(completed)
        self._btn_folder.setVisible(completed or status in ("Completed", "Cancelled"))
        # Konum: satırın sağ üstü
        row_y = self.rowViewportPosition(row)
        col_w = max(0, self.columnWidth(self.columnCount() - 1))
        w = self._hover_bar.sizeHint().width()
        h = max(26, self.rowHeight(row) + 2)
        vw = self.viewport().width()
        x = vw - w - 12
        self._hover_bar.setGeometry(max(0, x), max(0, row_y + (self.rowHeight(row) - h) // 2), w, h)
        self._hover_bar.raise_()
        self._hover_bar.show()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        row = self.rowAt(pos.y())
        if row >= 0 and (self._hover_bar is None or row != self._hover_row
                         or not self._hover_bar.geometry().contains(self._hover_bar.mapFromGlobal(event.globalPosition().toPoint()))):
            self._update_hover_bar(row)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hover_bar is not None:
            self._hover_bar.hide()
        self._hover_row = -1
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if self._hover_bar is not None and self._hover_bar.isVisible():
            vp_pos = self._hover_bar.mapFromGlobal(event.globalPosition().toPoint())
            if not self._hover_bar.geometry().contains(vp_pos):
                self._hover_bar.hide()
        super().mousePressEvent(event)

    def startDrag(self, supportedActions):
        selected_rows = set(item.row() for item in self.selectedItems())
        urls = []
        if self.parent_window:
            for r in selected_rows:
                item = self.item(r, 0)
                if item:
                    did = item.data(Qt.ItemDataRole.UserRole)
                    rec = self.parent_window.queue_mgr.get_download(did)
                    if rec and rec.get("status") == "Completed":
                        spath = rec.get("save_path")
                        if spath and os.path.exists(spath):
                            urls.append(QUrl.fromLocalFile(os.path.abspath(spath)))
        if urls:
            drag = QDrag(self)
            mime = QMimeData()
            mime.setUrls(urls)
            ids = self._selected_download_ids()
            if ids:
                mime.setData("application/x-ripsync-download-ids", "\n".join(ids).encode("utf-8"))
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.CopyAction)
        else:
            ids = self._selected_download_ids()
            if ids:
                drag = QDrag(self)
                mime = QMimeData()
                mime.setData("application/x-ripsync-download-ids", "\n".join(ids).encode("utf-8"))
                drag.setMimeData(mime)
                drag.exec(Qt.DropAction.MoveAction)
            else:
                super().startDrag(supportedActions)

    def _selected_download_ids(self) -> list:
        ids = []
        for r in set(item.row() for item in self.selectedItems()):
            item = self.item(r, 0)
            if item:
                did = item.data(Qt.ItemDataRole.UserRole)
                if did and str(did) not in ("__ADD_QUEUE__",):
                    ids.append(str(did))
        return ids


class CategoriesTreeWidget(QTreeWidget):
    """Sol panel ağacı: tablo satırlarını kuyruğa sürükleyip bırakmayı destekler."""

    MIME_IDS = "application/x-ripsync-download-ids"

    def __init__(self, parent_window=None, parent=None):
        super().__init__(parent)
        self.parent_window = parent_window
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(self.MIME_IDS):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(self.MIME_IDS):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _queue_id_at(self, event):
        item = self.itemAt(event.position().toPoint())
        if item is None:
            return None
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, str):
            if data.startswith("queue:"):
                return data.split(":", 1)[1]
            if self.root_queues_item is not None and item == self.root_queues_item:
                return "default"
        return None

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(self.MIME_IDS) or self.parent_window is None:
            event.ignore()
            return
        try:
            ids = bytes(event.mimeData().data(self.MIME_IDS)).decode("utf-8").splitlines()
            ids = [x for x in (s.strip() for s in ids) if x]
        except Exception:
            ids = []
        qid = self._queue_id_at(event)
        if ids and qid:
            event.acceptProposedAction()
            self.parent_window._move_downloads_to_queue(ids, qid)
        else:
            event.ignore()


class MainWindow(QMainWindow):
    # Cross-thread UI signal
    sig_bridge_download = pyqtSignal(dict)
    sig_bridge_status = pyqtSignal(str, int, str)
    sig_progress_update = pyqtSignal(str, int, int, float, int)
    sig_segments_update = pyqtSignal(str, list)
    sig_status_update = pyqtSignal(str, str, str)
    sig_task_added = pyqtSignal(dict)
    sig_queue_empty = pyqtSignal()
    sig_countdown_tick = pyqtSignal(int, str)
    sig_countdown_executed = pyqtSignal(str)
    sig_countdown_suspended = pyqtSignal(str)
    sig_countdown_resumed = pyqtSignal()
    sig_scheduler_tick = pyqtSignal(dict)
    sig_scheduler_started = pyqtSignal()
    sig_scheduler_stopped = pyqtSignal(str)

    def __init__(self, db: Database, queue_mgr: QueueManager):
        super().__init__()
        self.db = db
        self.queue_mgr = queue_mgr
        self.bridge_server = None

        self.setWindowTitle("RipSync - Internet Download Manager")
        self.setWindowIcon(create_default_icon())
        from ui import styles as _styles
        _styles.set_database(db)
        thm_cfg = db.get_theme_settings()
        _styles.refresh_tokens(thm_cfg.get("theme", "dark"), thm_cfg.get("accent", "blue"))
        self.setStyleSheet(_styles.get_app_stylesheet())

        self.current_category = "All"
        self.current_tag: Optional[str] = None
        self.current_queue_id: Optional[str] = None
        self.site_rules_mgr = SiteRulesManager(self.db)
        self.active_dialogs: Dict[str, ProgressDialog] = {}

        # Metered Connection Monitor
        self.metered_monitor = MeteredConnectionMonitor(check_interval_ms=25000, parent=self)
        self.metered_monitor.metered_changed.connect(self._on_metered_status_changed)
        self.queue_mgr.on_metered_blocked = self._on_metered_blocked

        # Power Countdown Manager
        self.power_mgr = PowerCountdownManager(countdown_seconds=30)
        set_global_power_manager(self.power_mgr)
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
        clip_cfg = self.db.get_clipboard_settings()
        self.clip_monitor.configure(
            enabled=bool(clip_cfg.get("enabled", False)),
            only_media=bool(clip_cfg.get("only_media", False)),
            ignore_domains=clip_cfg.get("ignore_domains")
        )
        self.clip_monitor.link_detected.connect(self._on_clipboard_link_detected)

        # Check clipboard first-run privacy prompt
        if not clip_cfg.get("prompted", False):
            QTimer.singleShot(700, self._check_clipboard_first_run_consent)

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

        # Check First-Run / Onboarding Tour & Apply UI Mode
        self.ui_mode = self.db.get_ui_mode()
        self.apply_ui_mode(self.ui_mode)
        QTimer.singleShot(400, self._check_first_run_onboarding)

    def _init_menubar(self):
        menubar = self.menuBar()

        # 📁 Dosya Menüsü
        menu_file = menubar.addMenu("📁 Dosya")
        act_file_add = menu_file.addAction("➕ Yeni URL Ekle...")
        act_file_add.setShortcut(QKeySequence("Ctrl+N"))
        act_file_add.triggered.connect(self._show_add_dialog)

        act_file_batch = menu_file.addAction("📋 Toplu Link Ekle...")
        act_file_batch.setShortcut(QKeySequence("Ctrl+B"))
        act_file_batch.triggered.connect(lambda: self._show_batch_add_dialog())

        act_file_playlist = menu_file.addAction("📑 Oynatma Listesi İndir...")
        act_file_playlist.triggered.connect(lambda: self._show_playlist_dialog())

        menu_file.addSeparator()
        act_clean = menu_file.addAction("🧹 Eksik Dosyaları Temizle")
        act_clean.triggered.connect(self._clean_missing_files)

        menu_file.addSeparator()
        act_exit = menu_file.addAction("❌ Çıkış")
        act_exit.setShortcut(QKeySequence("Alt+F4"))
        act_exit.triggered.connect(self._quit_application)

        # 👁️ Görünüm Menüsü
        menu_view = menubar.addMenu("👁️ Görünüm")
        self.act_view_simple = menu_view.addAction("🟢 Basit Mod (Sade Görünüm)")
        self.act_view_simple.setCheckable(True)
        self.act_view_simple.triggered.connect(lambda: self.apply_ui_mode("simple"))

        self.act_view_advanced = menu_view.addAction("⚡ Gelişmiş Mod (Uzman Araçları)")
        self.act_view_advanced.setCheckable(True)
        self.act_view_advanced.triggered.connect(lambda: self.apply_ui_mode("advanced"))

        menu_view.addSeparator()
        act_focus_search = menu_view.addAction("🔍 Aramaya Odaklan")
        act_focus_search.setShortcut(QKeySequence("Ctrl+F"))
        act_focus_search.triggered.connect(lambda: getattr(self, "edit_search", None) and self.edit_search.setFocus())

        # ⬇️ İndirme Menüsü
        menu_dl = menubar.addMenu("⬇️ İndirme")
        act_start = menu_dl.addAction("▶ Seçilenleri Başlat")
        act_start.triggered.connect(self._start_selected)

        act_pause = menu_dl.addAction("⏸ Seçilenleri Duraklat")
        act_pause.triggered.connect(self._pause_selected)

        act_cancel = menu_dl.addAction("⏹ Seçilenleri İptal Et")
        act_cancel.triggered.connect(self._cancel_selected)

        act_del = menu_dl.addAction("🗑 Seçilenleri Listeden Kaldır")
        act_del.setShortcut(QKeySequence("Delete"))
        act_del.setToolTip("Dosyayı diskte koruyarak yalnızca listeden kaldırır (Varsayılan)")
        act_del.triggered.connect(self._delete_selected)

        act_del_file = menu_dl.addAction("💥 Seçilenleri Dosyasıyla Birlikte Sil")
        act_del_file.setShortcut(QKeySequence("Shift+Delete"))
        act_del_file.setToolTip("İndirme kaydını ve indirilen dosyayı kalıcı olarak diskten siler")
        act_del_file.triggered.connect(self._delete_selected_with_files)

        menu_dl.addSeparator()
        act_start_all = menu_dl.addAction("⚡ Tüm Kuyruğu Başlat")
        act_start_all.triggered.connect(self._on_start_all)

        act_pause_all = menu_dl.addAction("⏸ Tümünü Durdur")
        act_pause_all.triggered.connect(self._on_pause_all)

        # 🛠️ Araçlar Menüsü
        menu_tools = menubar.addMenu("🛠️ Araçlar")
        act_sched = menu_tools.addAction("⏱ Gece Zamanlayıcısı...")
        act_sched.triggered.connect(self._show_scheduler_dialog)

        act_stats = menu_tools.addAction("📊 İstatistikler & Trafik...")
        act_stats.triggered.connect(self._show_statistics_dialog)

        menu_tools.addSeparator()
        act_ext_dir = menu_tools.addAction("📁 Eklenti Klasörünü Seç / Aç")
        act_ext_dir.triggered.connect(self._select_and_open_extension_dir)

        act_ext_copy = menu_tools.addAction("📋 Eklenti Klasör Yolunu Kopyala")
        act_ext_copy.triggered.connect(self._copy_extension_dir_path)

        act_ext = menu_tools.addAction("🌐 Tarayıcı Eklentisi Kılavuzu (Görsel)...")
        act_ext.triggered.connect(self._show_extension_guide)

        menu_tools.addSeparator()
        act_settings = menu_tools.addAction("⚙ Ayarlar...")
        act_settings.setShortcut(QKeySequence("Ctrl+P"))
        act_settings.triggered.connect(self._show_settings_dialog)

        # ❓ Yardım Menüsü
        menu_help = menubar.addMenu("❓ Yardım")
        act_wiz = menu_help.addAction("🧙 Eklenti & Kurulum Sihirbazı...")
        act_wiz.triggered.connect(self._show_setup_wizard)

        act_tour = menu_help.addAction("🚀 Hızlı Başlangıç Rehberli Turu (Onboarding)...")
        act_tour.triggered.connect(self._show_onboarding_dialog)

        act_about = menu_help.addAction("ℹ️ RipSync Hakkında...")
        act_about.triggered.connect(self._show_about_dialog)

    def _init_ui(self):
        # Menu Bar
        self._init_menubar()

        # Toolbar — kalıcı ve sık kullanılanlar:
        # ➕ URL Ekle | ▶/⏸ Başlat-Duraklat | 🗑 Sil | ⚙ Ayarlar | ⋯ Daha fazla
        toolbar = QToolBar("Ana Araç Çubuğu")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.toolbar = toolbar

        self.act_add = QAction("➕ URL Ekle", self)
        self.act_add.triggered.connect(self._show_add_dialog)
        toolbar.addAction(self.act_add)

        toolbar.addSeparator()

        # Başlat / Duraklat tek toggle (seçime göre davranır)
        self.act_toggle_run = QAction("▶ Başlat", self)
        self.act_toggle_run.setToolTip("Seçili indirmeleri başlatır veya duraklatır")
        self.act_toggle_run.triggered.connect(self._on_toggle_run_triggered)
        toolbar.addAction(self.act_toggle_run)

        self.act_delete = QAction("🗑 Sil", self)
        self.act_delete.setToolTip("Listeden Kaldır (Delete)\nVarsayılan: Dosya diskte korunur, listeden silinir.")
        self.act_delete.triggered.connect(self._delete_selected)
        toolbar.addAction(self.act_delete)

        toolbar.addSeparator()

        self.act_settings = QAction("⚙ Ayarlar", self)
        self.act_settings.triggered.connect(self._show_settings_dialog)
        toolbar.addAction(self.act_settings)

        # ---- Daha fazla (⋯): ikincil ve gelişmiş eylemler ----------------
        # Bu eylemler artık araç çubuğunda tek satırda yığılmaz; hem menüde
        # hem kısayollarla erişilebilir kalır (Basit modda hiçbir işlev kaybolmaz).
        self.act_playlist = QAction("📑 Oynatma Listesi İndir", self)
        self.act_playlist.setToolTip("YouTube Çalma Listesindeki Videoları Toplu Tara ve İndir")
        self.act_playlist.triggered.connect(lambda: self._show_playlist_dialog())

        self.act_batch_add = QAction("📋 Toplu Link Ekle", self)
        self.act_batch_add.setToolTip("Birden fazla web bağlantısını tek seferde toplu olarak ekle (Ctrl+B)")
        self.act_batch_add.triggered.connect(lambda: self._show_batch_add_dialog())

        self.act_start_queue = QAction("⚡ Kuyruğu Başlat", self)
        self.act_start_queue.triggered.connect(self._on_start_all)

        self.act_pause_all = QAction("⏸ Tümünü Durdur", self)
        self.act_pause_all.triggered.connect(self._on_pause_all)

        self.act_scheduler = QAction("⏱ Zamanlayıcı", self)
        self.act_scheduler.setToolTip("Gece İndirmesi ve Kuyruk Planlama Penceresini Aç")
        self.act_scheduler.triggered.connect(self._show_scheduler_dialog)

        self.act_statistics = QAction("📊 İstatistikler", self)
        self.act_statistics.setToolTip("İndirme İstatistikleri ve Ağ Trafiği Raporunu Aç")
        self.act_statistics.triggered.connect(self._show_statistics_dialog)

        self.act_clean_missing = QAction("🧹 Eksik Dosyaları Temizle", self)
        self.act_clean_missing.setToolTip("Diskten silinmiş veya taşınmış tamamlanmış indirmeleri listeden ayıkla")
        self.act_clean_missing.triggered.connect(self._clean_missing_files)

        self.act_open_file = QAction("📂 Dosyayı Aç", self)
        self.act_open_file.triggered.connect(self._open_selected_file)

        self.act_open_folder = QAction("📁 Klasörde Göster", self)
        self.act_open_folder.triggered.connect(self._open_selected_folder)

        self.act_extension = QAction("🌐 Eklenti", self)
        self.act_extension.setToolTip("Chrome / Edge Tarayıcı Eklentisi Kurulum Kılavuzu")
        self.act_extension.triggered.connect(self._show_extension_guide)

        self.act_delete_file = QAction("💥 Dosyayla Sil", self)
        self.act_delete_file.setToolTip("Dosyayla Birlikte Sil (Shift+Delete)\nİndirme kaydını ve dosyasını kalıcı olarak siler.")
        self.act_delete_file.triggered.connect(self._delete_selected_with_files)

        self.act_stop = QAction("⏹ Seçilenleri İptal Et", self)
        self.act_stop.triggered.connect(self._cancel_selected)

        self.menu_more = QMenu(self)
        self.menu_more.addAction(self.act_playlist)
        self.menu_more.addAction(self.act_batch_add)
        self.menu_more.addSeparator()
        self.menu_more.addAction(self.act_start_queue)
        self.menu_more.addAction(self.act_pause_all)
        self.menu_more.addSeparator()
        self.menu_more.addAction(self.act_scheduler)
        self.menu_more.addAction(self.act_statistics)
        self.menu_more.addAction(self.act_clean_missing)
        self.menu_more.addSeparator()
        self.menu_more.addAction(self.act_open_file)
        self.menu_more.addAction(self.act_open_folder)
        self.menu_more.addSeparator()
        self.menu_more.addAction(self.act_extension)
        self.menu_more.addAction(self.act_delete_file)
        self.menu_more.addSeparator()
        self.menu_more.addAction(self.act_stop)

        btn_more = QToolButton(self)
        btn_more.setText("⋯ Daha Fazla")
        btn_more.setToolTip("Diğer tüm araçlar")
        btn_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn_more.setMenu(self.menu_more)
        self.btn_more = btn_more
        self.act_more_widget = toolbar.addWidget(btn_more)

        self.adv_toolbar_separators = []

        self.btn_extension = QToolButton(self)
        self.btn_extension.setText("🌐 Eklenti")
        self.btn_extension.setToolTip("Tarayıcı Eklentisi: Klasörü Aç/Seç, Yolu Kopyala, Otomatik Yükle veya Rehber")
        self.btn_extension.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)

        ext_menu = QMenu(self.btn_extension)

        act_open_ext_dir = QAction("📁 Eklenti Klasörünü Seç / Aç", self)
        act_open_ext_dir.setToolTip("Eklenti klasörünü Dosya Gezgini'nde açar ve yolunu panoya kopyalar")
        act_open_ext_dir.triggered.connect(self._select_and_open_extension_dir)
        ext_menu.addAction(act_open_ext_dir)

        act_copy_ext_path = QAction("📋 Eklenti Klasör Yolunu Kopyala", self)
        act_copy_ext_path.setToolTip("Eklenti klasör yolunu panoya kopyalar (Ctrl+V ile yapıştırabilirsiniz)")
        act_copy_ext_path.triggered.connect(self._copy_extension_dir_path)
        ext_menu.addAction(act_copy_ext_path)

        ext_menu.addSeparator()

        act_launch_chrome = QAction("🚀 Chrome ile Aç (Otomatik Yükle)", self)
        act_launch_chrome.triggered.connect(lambda: self._launch_browser_with_ext("chrome"))
        ext_menu.addAction(act_launch_chrome)

        act_launch_edge = QAction("🚀 Edge ile Aç (Otomatik Yükle)", self)
        act_launch_edge.triggered.connect(lambda: self._launch_browser_with_ext("edge"))
        ext_menu.addAction(act_launch_edge)

        ext_menu.addSeparator()

        act_open_ext_guide = QAction("🖼 Görsel Kurulum Rehberi (Adımlı)...", self)
        act_open_ext_guide.triggered.connect(self._show_extension_guide)
        ext_menu.addAction(act_open_ext_guide)

        act_setup_wiz = QAction("🧙 Kurulum Sihirbazı...", self)
        act_setup_wiz.triggered.connect(self._show_setup_wizard)
        ext_menu.addAction(act_setup_wiz)

        self.btn_extension.setMenu(ext_menu)
        self.btn_extension.clicked.connect(self._show_extension_guide)

        toolbar.addSeparator()

        # Toolbar Spacer and Mode Switcher (Basit / Gelişmiş Mod Geçişi)
        tb_spacer = QWidget()
        tb_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(tb_spacer)

        self.btn_mode_toggle = QPushButton("🟢 Basit Mod (Geç: Gelişmiş ❯)")
        self.btn_mode_toggle.setObjectName("btn_mode_toggle")
        self.btn_mode_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mode_toggle.clicked.connect(self._toggle_ui_mode)
        toolbar.addWidget(self.btn_mode_toggle)

        # ---- İkincil şerit: sürekli ayarlar araç çubuğundan çıkarılıp
        # ince bir şeride taşındı (yalnızca Gelişmiş modda görünür).

        # Concurrency Widget (Sequential Queue Limit)
        self.tb_conc_widget = QWidget()
        tb_conc_layout = QHBoxLayout(self.tb_conc_widget)
        tb_conc_layout.setContentsMargins(6, 0, 6, 0)
        tb_conc_layout.setSpacing(6)

        lbl_conc = QLabel("⚡ Sıralı:")
        lbl_conc.setStyleSheet(f"font-weight: bold; color: {T['accent']};")
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

        # Scheduler Quick Control Widget
        self.tb_sched_widget = QWidget()
        tb_sched_layout = QHBoxLayout(self.tb_sched_widget)
        tb_sched_layout.setContentsMargins(6, 0, 6, 0)
        tb_sched_layout.setSpacing(6)

        self.chk_tb_scheduler = QCheckBox("⏱ Zamanlayıcı:")
        self.chk_tb_scheduler.setStyleSheet(f"font-weight: bold; color: {T['accent']};")
        self.chk_tb_scheduler.setToolTip("Gece indirmesi zamanlayıcısını Aç / Kapat")
        self.chk_tb_scheduler.toggled.connect(self._on_toolbar_scheduler_toggled)
        tb_sched_layout.addWidget(self.chk_tb_scheduler)

        self.lbl_tb_sched_time = QLabel("02:00 - 07:00")
        self.lbl_tb_sched_time.setStyleSheet(f"color: {T['text_primary']}; font-size: 11px;")
        tb_sched_layout.addWidget(self.lbl_tb_sched_time)

        self.lbl_tb_sched_badge = QLabel("Kapalı")
        self.lbl_tb_sched_badge.setStyleSheet(f"font-weight: bold; color: {T['text_secondary']}; min-width: 60px;")
        tb_sched_layout.addWidget(self.lbl_tb_sched_badge)

        btn_sched_cfg = QPushButton("⚙")
        btn_sched_cfg.setObjectName("btn_secondary")
        btn_sched_cfg.setFixedSize(24, 24)
        btn_sched_cfg.setToolTip("Zamanlayıcı ve Kuyruk Planlama Ayarlarını Aç")
        btn_sched_cfg.clicked.connect(self._show_scheduler_dialog)
        tb_sched_layout.addWidget(btn_sched_cfg)

        # Global Speed Limiter Widget (IDM Quick Limiter)
        self.tb_limiter_widget = QWidget()
        tb_limiter_layout = QHBoxLayout(self.tb_limiter_widget)
        tb_limiter_layout.setContentsMargins(6, 0, 6, 0)
        tb_limiter_layout.setSpacing(8)

        self.chk_tb_speed_limit = QCheckBox("⚡ Hız Limiti:")
        self.chk_tb_speed_limit.setStyleSheet(f"font-weight: bold; color: {T['accent']};")
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
        self.lbl_tb_limit_val.setStyleSheet(f"font-weight: bold; color: {T['success']}; min-width: 75px;")
        tb_limiter_layout.addWidget(self.lbl_tb_limit_val)

        # Queue Completion Power Action Widget
        self.tb_queue_widget = QWidget()
        tb_queue_layout = QHBoxLayout(self.tb_queue_widget)
        tb_queue_layout.setContentsMargins(6, 0, 6, 0)
        tb_queue_layout.setSpacing(6)

        lbl_qa = QLabel("🏁 Kuyruk Bitince:")
        lbl_qa.setStyleSheet(f"font-weight: bold; color: {T['accent']};")
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

        # İkincil şeridi kur
        self.quick_bar = QWidget()
        quick_layout = QHBoxLayout(self.quick_bar)
        quick_layout.setContentsMargins(8, 2, 8, 2)
        quick_layout.setSpacing(10)
        quick_layout.addWidget(self.tb_conc_widget)
        quick_layout.addWidget(self.tb_sched_widget)
        quick_layout.addWidget(self.tb_limiter_widget)
        quick_layout.addWidget(self.tb_queue_widget)
        quick_bar_spacer = QWidget()
        quick_bar_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        quick_layout.addWidget(quick_bar_spacer)
        self.quick_bar.setProperty("objectName", "quick_settings_bar")
        self._apply_toolbar_icons()



        # Central Widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)

        main_layout.addWidget(self.quick_bar)  # İkincil ayar şeridi (Gelişmiş mod)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # Left: Categories Tree
        self.tree_categories = CategoriesTreeWidget(parent_window=self)
        self.tree_categories.root_queues_item = None
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

        self.root_tags = QTreeWidgetItem(["🏷️ Etiketler"])
        self.root_tags.setData(0, Qt.ItemDataRole.UserRole, "__TAGS_ROOT__")
        self.tree_categories.addTopLevelItem(self.root_tags)
        self.root_tags.setExpanded(True)
        self._refresh_tags_tree()

        self.root_queues = QTreeWidgetItem(["🗂️ Kuyruklar"])
        self.root_queues.setData(0, Qt.ItemDataRole.UserRole, "__QUEUES_ROOT__")
        self.tree_categories.addTopLevelItem(self.root_queues)
        self.tree_categories.root_queues_item = self.root_queues
        self.root_queues.setExpanded(True)
        self._refresh_queues_tree()
        self._restore_tree_state()

        self.tree_categories.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_categories.customContextMenuRequested.connect(self._show_categories_tree_context_menu)

        self.tree_categories.currentItemChanged.connect(self._on_category_changed)
        self.tree_categories.itemExpanded.connect(self._persist_tree_state)
        self.tree_categories.itemCollapsed.connect(self._persist_tree_state)
        splitter.addWidget(self.tree_categories)

        # Right: Container with Live Search & Filter Bar + Downloads Table
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # Search & Filter Bar
        search_filter_bar = QWidget()
        sf_layout = QHBoxLayout(search_filter_bar)
        sf_layout.setContentsMargins(2, 2, 2, 4)
        sf_layout.setSpacing(6)

        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("🔍 Dosya adı veya link ara... (Ctrl+F)")
        self.edit_search.setClearButtonEnabled(True)
        self.edit_search.setStyleSheet(
            f"QLineEdit {{ background-color: {T['bg_panel']}; border: 1px solid {T['border']}; border-radius: 6px; padding: 4px 10px; color: {T['text_primary']}; font-size: 12px; min-height: 22px; }}"
            f"QLineEdit:focus {{ border: 1px solid {T['accent']}; }}"
        )
        self.edit_search.textChanged.connect(self._apply_search_and_filter)
        sf_layout.addWidget(self.edit_search, stretch=1)

        # Quick Status Filter Chips
        self.filter_btn_group = {}
        for chip_id, chip_label in [
            ("all", "Tümü"),
            ("Downloading", "⏳ İnenler"),
            ("Completed", "✔ Tamamlanan"),
            ("Paused", "⏸ Duraklatılan"),
            ("Error", "❌ Hatalı"),
        ]:
            btn = QPushButton(chip_label)
            btn.setCheckable(True)
            btn.setChecked(chip_id == "all")
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {T['bg_card']}; border: 1px solid {T['border']}; border-radius: 5px; padding: 4px 8px; color: {T['text_muted']}; font-size: 11px; font-weight: bold; min-height: 20px; }}"
                f"QPushButton:checked {{ background-color: {T['accent']}; color: {T['bg_main']}; border-color: {T['accent']}; }}"
                f"QPushButton:hover:!checked {{ background-color: {T['bg_hover']}; color: {T['text_primary']}; }}"
            )
            btn.clicked.connect(lambda checked, c=chip_id: self._on_filter_chip_clicked(c))
            self.filter_btn_group[chip_id] = btn
            sf_layout.addWidget(btn)

        # Multi-criteria Filter Combos
        self.combo_size_filter = QComboBox()
        self.combo_size_filter.addItem("📏 Boyut: Tümü", "all")
        self.combo_size_filter.addItem("< 50 MB", "small")
        self.combo_size_filter.addItem("50 - 500 MB", "medium")
        self.combo_size_filter.addItem("500 MB - 2 GB", "large")
        self.combo_size_filter.addItem("> 2 GB", "huge")
        self.combo_size_filter.setFixedWidth(115)
        self.combo_size_filter.currentIndexChanged.connect(self._apply_search_and_filter)
        sf_layout.addWidget(self.combo_size_filter)

        self.combo_date_filter = QComboBox()
        self.combo_date_filter.addItem("📅 Tarih: Tümü", "all")
        self.combo_date_filter.addItem("Bugün", "today")
        self.combo_date_filter.addItem("Dün", "yesterday")
        self.combo_date_filter.addItem("Son 7 Gün", "week")
        self.combo_date_filter.addItem("Daha Eski", "older")
        self.combo_date_filter.setFixedWidth(115)
        self.combo_date_filter.currentIndexChanged.connect(self._apply_search_and_filter)
        sf_layout.addWidget(self.combo_date_filter)

        self.lbl_filter_count = QLabel("0 / 0")
        self.lbl_filter_count.setStyleSheet(f"color: {T['accent']}; font-size: 11px; font-weight: bold; padding: 0 4px;")
        sf_layout.addWidget(self.lbl_filter_count)

        right_layout.addWidget(search_filter_bar)

        # Downloads Table (supports drag-and-drop file export)
        self.table = DownloadsTableWidget(parent_window=self)
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
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._update_run_toggle_state())

        # Smart column sorting
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)

        # Enable Drag & Drop onto MainWindow
        self.setAcceptDrops(True)

        # Keyboard shortcuts for table
        self.shortcut_delete = QShortcut(QKeySequence.StandardKey.Delete, self.table)
        self.shortcut_delete.activated.connect(self._delete_selected)

        self.shortcut_shift_delete = QShortcut(QKeySequence("Shift+Delete"), self.table)
        self.shortcut_shift_delete.activated.connect(self._delete_selected_with_files)

        # Queue reordering shortcuts (Ctrl+Up / Ctrl+Down)
        self.shortcut_up = QShortcut(QKeySequence("Ctrl+Up"), self.table)
        self.shortcut_up.activated.connect(lambda: self._move_selected_queue("up"))

        self.shortcut_down = QShortcut(QKeySequence("Ctrl+Down"), self.table)
        self.shortcut_down.activated.connect(lambda: self._move_selected_queue("down"))

        # Global Search and Batch Shortcuts
        self.shortcut_search = QShortcut(QKeySequence("Ctrl+F"), self)
        self.shortcut_search.activated.connect(self.edit_search.setFocus)

        self.shortcut_esc = QShortcut(QKeySequence("Escape"), self.edit_search)
        self.shortcut_esc.activated.connect(self._clear_search)

        self.shortcut_batch = QShortcut(QKeySequence("Ctrl+B"), self)
        self.shortcut_batch.activated.connect(lambda: self._show_batch_add_dialog())

        # Komut Paleti (Ctrl+K) — eylemleri tek yerden arayıp çalıştır
        self.shortcut_palette = QShortcut(QKeySequence("Ctrl+K"), self)
        self.shortcut_palette.activated.connect(self._show_command_palette)

        # Kısayol Dökümü (F1)
        self.shortcut_help_shortcuts = QShortcut(QKeySequence("F1"), self)
        self.shortcut_help_shortcuts.activated.connect(self._show_shortcuts_dialog)

        from ui.empty_state import EmptyStateWidget
        self.table_stack = QStackedWidget()
        self.table_stack.addWidget(self.table)

        self.empty_state = EmptyStateWidget()
        self.empty_state.add_clicked.connect(self._show_add_dialog)
        self.empty_state.batch_clicked.connect(self._show_batch_add_dialog)
        self.table_stack.addWidget(self.empty_state)

        self.table_stack.setCurrentWidget(self.empty_state)  # boş listede başlat
        self._sync_empty_state()
        right_layout.addWidget(self.table_stack)
        splitter.addWidget(right_panel)
        splitter.setSizes([200, 800])

        # Status Bar — kalıcılar: toplam hız + hız grafiği + kısa uyarı.
        # Diğer durumlar ⚡ açılır durum panelinde toplanır.
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Açılır durum paneli: disk, hız sınırı, zamanlayıcı, köprü durumu.
        self.btn_status_panel = QToolButton()
        self.btn_status_panel.setText("ℹ️ Durum")
        self.btn_status_panel.setToolTip("Disk, hız sınırı, zamanlayıcı ve köprü durumunu gör")
        self.btn_status_panel.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_status_panel = QMenu(self.btn_status_panel)
        self.menu_status_panel.aboutToShow.connect(self._refresh_status_panel)
        self.act_status_disk = self.menu_status_panel.addAction("💾 Disk —")
        self.act_status_limiter = self.menu_status_panel.addAction("⚡ Hız Sınırı —")
        self.act_status_scheduler = self.menu_status_panel.addAction("⏱ Zamanlayıcı —")
        self.menu_status_panel.addSeparator()
        self.act_status_bridge = self.menu_status_panel.addAction("🌐 Tarayıcı Köprüsü —")
        self.act_status_bridge.triggered.connect(self._show_settings_dialog)
        self.btn_status_panel.setMenu(self.menu_status_panel)
        self.status_bar.addWidget(self.btn_status_panel)

        # Referans etiketler: değerleri mevcut güncelleme kodu ile canlı tutulur,
        # doğrudan görünmez; panel açılırken okunur.
        self.lbl_ext_status = QLabel("Tarayıcı Köprüsü: Başlatılıyor...")
        self.lbl_ext_status.hide()

        # Real-time Bandwidth Sparkline Graph (Clickable -> Opens Statistics)
        self.speed_graph = BandwidthGraphWidget(parent=self)
        self.speed_graph.setToolTip("Son 40 sn hız grafiği (Detaylı İstatistikler için tıklayın)")
        self.speed_graph.mousePressEvent = lambda e: self._show_statistics_dialog()
        self.status_bar.addWidget(self.speed_graph)

        self.lbl_speed_stat = QLabel("Toplam Hız: 0 KB/s")
        self.lbl_speed_stat.setStyleSheet(f"color: {T['accent']}; font-weight: bold; margin-left: 10px;")
        self.status_bar.addWidget(self.lbl_speed_stat)

        # Referans etiketler (panelde gösterilir)
        self.lbl_disk_stat = QLabel("💾 Disk: Taranıyor...")
        self.lbl_disk_stat.hide()

        self.lbl_limiter_stat = QLabel("⚡ Hız Sınırı: Kapalı (Tam Hız)")
        self.lbl_limiter_stat.hide()

        self.lbl_scheduler_stat = QLabel("⏱ Zamanlayıcı: Kapalı")
        self.lbl_scheduler_stat.hide()

        # Kota koruması uyarısı: güvenlik uyarısı olarak kalıcı ve görünür.
        self.btn_metered_stat = QPushButton("📶 Tarifeli Bağlantı (Kota Koruması Aktif - Tıkla)")
        self.btn_metered_stat.setStyleSheet(f"""
            QPushButton {{
                background-color: {T['danger']};
                color: {T['text_on_accent']};
                font-weight: bold;
                border-radius: 4px;
                padding: 2px 8px;
                margin-left: 15px;
            }}
            QPushButton:hover {{
                background-color: {T['color_orange']};
            }}
        """)
        self.btn_metered_stat.setToolTip("Tarifeli mobil veri / hotspot bağlantısı algılandı. Tıklayarak kota korumasını geçici olarak devre dışı bırakabilirsiniz.")
        self.btn_metered_stat.clicked.connect(self._on_metered_btn_clicked)
        self.status_bar.addPermanentWidget(self.btn_metered_stat)

        # Timer for smooth speed graph decay and disk space sync
        self.timer_speed_decay = QTimer(self)
        self.timer_speed_decay.setInterval(1000)
        self.timer_speed_decay.timeout.connect(self._on_speed_decay_tick)
        self.timer_speed_decay.start()

        self._update_disk_space_ui()

        # Load initial speed limit state into toolbar controls
        self._init_speed_limiter_controls()

        # Initial sync for scheduler controls
        st = self.scheduler.get_status()
        self._sync_scheduler_toolbar_ui(st)

    def _apply_toolbar_icons(self):
        """Araç çubuğuna tema renkli SVG ikonlarını uygular (tema değişince yeniden çağrılır)."""
        try:
            from ui.icons import apply_theme_icons, ICON_SIZE
        except Exception:
            return
        toolbar = getattr(self, "toolbar", None)
        if toolbar is not None:
            toolbar.setIconSize(ICON_SIZE)
        icons = apply_theme_icons()
        self._icon_pack = icons
        act_add = getattr(self, "act_add", None)
        if act_add is not None:
            act_add.setIcon(icons["plus"])
        act_run = getattr(self, "act_toggle_run", None)
        if act_run is not None:
            act_run.setIcon(icons["play"])
        act_del = getattr(self, "act_delete", None)
        if act_del is not None:
            act_del.setIcon(icons["trash"])
        act_set = getattr(self, "act_settings", None)
        if act_set is not None:
            act_set.setIcon(icons["settings"])
        btn_more = getattr(self, "btn_more", None)
        if btn_more is not None:
            btn_more.setIcon(icons["more"])

    def _refresh_status_panel(self):
        """⚡ Durum panelini açılmadan günceller (disk, limit, zamanlayıcı, köprü)."""
        self.act_status_disk.setText(getattr(self, "lbl_disk_stat", None) and self.lbl_disk_stat.text() or "💾 Disk: Bilinmiyor")
        self.act_status_limiter.setText(getattr(self, "lbl_limiter_stat", None) and self.lbl_limiter_stat.text() or "⚡ Hız Sınırı: —")
        self.act_status_scheduler.setText(getattr(self, "lbl_scheduler_stat", None) and self.lbl_scheduler_stat.text() or "⏱ Zamanlayıcı: —")
        self.act_status_bridge.setText(getattr(self, "lbl_ext_status", None) and self.lbl_ext_status.text() or "🌐 Tarayıcı Köprüsü: —")

    def _row_is_running(self, row: int) -> bool:
        """Satırın sütun-5 durumuna göre True döndürür: 'Downloading'."""
        item = self.table.item(row, 0) if row < self.table.rowCount() else None
        if item is None:
            return False
        st = self.table.item(row, 5)
        if st is not None:
            raw = st.data(Qt.ItemDataRole.UserRole)
            if raw == "Downloading" or (isinstance(raw, str) and "Downloading" in raw):
                return True
        return False

    def _on_toggle_run_triggered(self):
        """▶/⏸ tek toggle: seçili indirmelerden biri çalışıyorsa duraklat, değilse başlat."""
        model = self.table.selectionModel() if hasattr(self, "table") else None
        if model is None:
            self._start_selected()
            return
        rows = sorted(set(idx.row() for idx in model.selectedRows()))
        if any(self._row_is_running(r) for r in rows):
            self._pause_selected()
        else:
            self._start_selected()

    def _update_run_toggle_state(self):
        """Seçime ve koşum durumuna göre ▶/⏸ düğmesinin metnini günceller."""
        act = getattr(self, "act_toggle_run", None)
        if act is None:
            return
        model = self.table.selectionModel() if hasattr(self, "table") else None
        rows = set(idx.row() for idx in model.selectedRows()) if model is not None else set()
        rows = {r for r in rows if 0 <= r < self.table.rowCount()}
        if not rows:
            act.setText("▶ Başlat")
            act.setToolTip("Seçili indirmeleri başlatır")
            icons = getattr(self, "_icon_pack", {})
            if icons:
                act.setIcon(icons["play"])
            return
        icons = getattr(self, "_icon_pack", {})
        if any(self._row_is_running(r) for r in rows):
            act.setText("⏸ Duraklat")
            act.setToolTip("Seçili çalışan indirmeleri duraklatır")
            if icons:
                act.setIcon(icons["pause"])
        else:
            act.setText("▶ Başlat")
            act.setToolTip("Seçili indirmeleri başlatır")
            if icons:
                act.setIcon(icons["play"])

    def _persist_tree_state(self, item=None):
        """Sol panel başlıklarının (Kategori/Etiketler/Kuyruklar) açık-kapalı durumunu kalıcı saklar."""
        try:
            state = self.db.get_setting("sidebar_tree_expanded", {})
            if not isinstance(state, dict):
                state = {}
            key = getattr(self, "root_all", None)
            for name, root in (("all", self.root_all), ("tags", self.root_tags), ("queues", self.root_queues)):
                if root is not None:
                    state[name] = root.isExpanded()
            self.db.set_setting("sidebar_tree_expanded", state)
        except Exception:
            pass

    def _restore_tree_state(self):
        try:
            state = self.db.get_setting("sidebar_tree_expanded", {})
            if not isinstance(state, dict):
                return
            mapping = (("all", self.root_all), ("tags", self.root_tags), ("queues", self.root_queues))
            for name, root in mapping:
                if root is not None and name in state:
                    root.setExpanded(bool(state.get(name)))
        except Exception:
            pass

    def _show_command_palette(self):
        """Ctrl+K komut paletini açar: tüm eylemler aramayla tek yerden."""
        from ui.command_palette import CommandPaletteDialog
        commands = []
        toolbar_actions = [
            ("▶/⏸ Başlat / Duraklat (Seçili)", lambda: self._on_toggle_run_triggered()),
            ("🗑 Sil (Seçili)", self._delete_selected),
            ("➕ URL Ekle", self._show_add_dialog),
            ("⚙ Ayarlar", self._show_settings_dialog),
            ("📑 Oynatma Listesi İndir", lambda: self._show_playlist_dialog()),
            ("📋 Toplu Link Ekle", lambda: self._show_batch_add_dialog()),
            ("⚡ Kuyruğu Başlat", self._on_start_all),
            ("⏸ Tümünü Durdur", self._on_pause_all),
            ("⏱ Zamanlayıcı", self._show_scheduler_dialog),
            ("📊 İstatistikler", self._show_statistics_dialog),
            ("🧹 Eksik Dosyaları Temizle", self._clean_missing_files),
            ("📂 Dosyayı Aç", self._open_selected_file),
            ("📁 Klasörde Göster", self._open_selected_folder),
            ("🌐 Eklenti Kılavuzu", self._show_extension_guide),
            ("💥 Dosyayla Sil", self._delete_selected_with_files),
            ("⏹ Seçilenleri İptal Et", self._cancel_selected),
            ("🧙 Kurulum Sihirbazı", self._show_setup_wizard),
            ("🚀 Onboarding Turu", self._show_onboarding_dialog),
        ]
        for label, cb in toolbar_actions:
            commands.append((label, cb, "Eylemler"))
        # Mod geçişleri + filtre kategorileri
        commands.append(("Arayüz Modu: Basit ⟷ Gelişmiş Geçiş", self._toggle_ui_mode, "Görünüm"))
        for cat_key, cat_label in (("All", "Kategori: Tüm İndirmeler"), ("Completed", "Kategori: Tamamlananlar"),
                                    ("Downloading", "Kategori: Devam Edenler"), ("Video", "Kategori: Videolar"),
                                    ("Music", "Kategori: Müzik")):
            commands.append((cat_label, lambda key=cat_key: self._on_category_changed(None, self._category_item_for(key)), "Görünüm"))
        # Basit mod / arama odak
        commands.append(("Aramaya Odaklan (Ctrl+F)", self.edit_search.setFocus, "Görünüm"))
        dlg = CommandPaletteDialog(self)
        self._apply_palette_dark = True
        dlg.open_with(commands)

    def _category_item_for(self, key: str):
        """Kategori anahtarına uygun ItemsItem döndürür (komut paleti için)."""
        it = self.tree_categories.topLevelItem(0)
        if it is not None and it.data(0, Qt.ItemDataRole.UserRole) == "All":
            for i in range(it.childCount()):
                ch = it.child(i)
                if ch.data(0, Qt.ItemDataRole.UserRole) == key:
                    return ch
        return it

    def _show_shortcuts_dialog(self):
        """F1: mevcut kısayolların okunur dökümü."""
        rows = [
            ("Ctrl+N", "Yeni URL Ekle"),
            ("Ctrl+B", "Toplu Link Ekle"),
            ("Ctrl+F", "Aramaya Odaklan"),
            ("Ctrl+K", "Komut Paleti"),
            ("Ctrl+P", "Ayarlar"),
            ("Delete", "Seçileni Listeden Kaldır"),
            ("Shift+Delete", "Seçileni Dosyasıyla Sil"),
            ("Ctrl+Up / Ctrl+Down", "Kuyruğunda yukarı/aşağı taşı"),
            ("Esc", "Aramayı Temizle"),
            ("F1", "Bu kısayol listesi"),
        ]
        lines = "\n".join([f"<tr><td style='padding:4px 14px 4px 0;'><b>{k}</b></td><td style='padding:4px 0;'>{v}</td></tr>" for k, v in rows])
        QMessageBox.information(
            self,
            "Kısayollar (F1)",
            f"<table>{lines}</table>"
        )

    def _init_signals(self):        # Connect queue manager thread-safe callbacks to PyQt signals
        self.queue_mgr.on_task_progress = lambda did, d, t, s, e: self.sig_progress_update.emit(did, d, t, s, e)
        self.queue_mgr.on_task_segments = lambda did, segs: self.sig_segments_update.emit(did, segs)
        self.queue_mgr.on_task_status = lambda did, st, err: self.sig_status_update.emit(did, st, err)
        self.queue_mgr.on_task_added = lambda rec: self.sig_task_added.emit(rec)
        self.queue_mgr.on_queue_empty = lambda: self.sig_queue_empty.emit()

        # Connect power countdown callbacks
        self.power_mgr.on_tick = lambda remaining, action: self.sig_countdown_tick.emit(remaining, action)
        self.power_mgr.on_confirm_requested = lambda action: self._on_power_confirm_requested(action)
        self.power_mgr.on_suspended = lambda reason: self.sig_countdown_suspended.emit(reason)
        self.power_mgr.on_resumed = lambda: self.sig_countdown_resumed.emit()

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
        self.sig_bridge_status.connect(self._handle_bridge_status)
        self.sig_queue_empty.connect(self._handle_queue_empty)
        self.sig_countdown_tick.connect(self._handle_countdown_tick)
        self.sig_countdown_executed.connect(self._handle_countdown_executed)
        self.sig_countdown_suspended.connect(self._handle_countdown_suspended)
        self.sig_countdown_resumed.connect(self._handle_countdown_resumed)
        self.sig_scheduler_tick.connect(self._handle_scheduler_tick)
        self.sig_scheduler_started.connect(self._handle_scheduler_started)
        self.sig_scheduler_stopped.connect(self._handle_scheduler_stopped)

    def _sync_empty_state(self):
        """Tablo boşken yönlendirme ekranını gösterir; ilk indirmenin eklenmesiyle tabloya döner."""
        stack = getattr(self, "table_stack", None)
        if stack is None:
            return
        empty = self.table.rowCount() == 0
        stack.setCurrentWidget(self.empty_state if empty else self.table)
        if empty and getattr(self, "speed_graph", None) is not None:
            pass

    def _load_downloads_to_table(self):
        self.table.setRowCount(0)
        downloads = self.queue_mgr.get_all_downloads()
        for dl in downloads:
            self._add_or_update_table_row(dl)
        self._apply_search_and_filter()

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

        fname = dl.get("filename", "download")
        tags_raw = dl.get("tags", "").strip() if dl.get("tags") else ""
        display_name = fname
        if tags_raw:
            tag_badges = " ".join([f"[{t.strip()}]" for t in tags_raw.split(",") if t.strip()])
            display_name = f"{fname}  🏷️ {tag_badges}"

        item_name = NumericTableWidgetItem(display_name)
        item_name.setData(Qt.ItemDataRole.UserRole, download_id)
        if tags_raw:
            item_name.setToolTip(f"Dosya: {fname}\nEtiketler: {tags_raw}")
        self.table.setItem(row, 0, item_name)

        tot = dl.get("total_size", -1)
        done = dl.get("downloaded_size", 0)
        status = dl.get("status", "Queued")
        eff_size = tot if tot > 0 else done

        if status == "Completed" and tot > 0:
            txt_size = format_size(tot)
        elif status == "Completed" and done > 0:
            txt_size = format_size(done)
        elif status in ("Downloading", "Paused", "Probing", "Retrying"):
            txt_size = format_progress_size(done, tot)
        elif tot > 0:
            txt_size = format_size(tot)
        else:
            txt_size = "Bilinmiyor"

        item_size = NumericTableWidgetItem(txt_size)
        item_size.setData(Qt.ItemDataRole.UserRole, eff_size)
        self.table.setItem(row, 1, item_size)

        # Progress bar widget
        prog = QProgressBar()
        prog.setRange(0, 100)
        pct = int((done / tot) * 100) if tot > 0 else (100 if status == "Completed" else 0)
        prog.setValue(min(100, max(0, pct)))
        self.table.setCellWidget(row, 2, prog)

        speed = dl.get("speed", 0)
        item_spd = NumericTableWidgetItem(format_speed(speed) if speed > 0 else "--")
        item_spd.setData(Qt.ItemDataRole.UserRole, int(speed))
        self.table.setItem(row, 3, item_spd)

        eta = dl.get("eta", 0)
        item_eta = NumericTableWidgetItem(format_eta(eta) if eta > 0 else "--")
        item_eta.setData(Qt.ItemDataRole.UserRole, int(eta))
        self.table.setItem(row, 4, item_eta)

        prio = (dl.get("priority") or "normal").lower()
        display_status = status
        prio_tooltip = ""
        if prio == "high":
            prio_tooltip = "Bant Genişliği Önceliği: 🚀 Yüksek (%70 Hız Payı)"
            if status in ("Downloading", "Queued", "Probing", "Retrying"):
                display_status = f"🚀 {status}"
        elif prio == "low":
            prio_tooltip = "Bant Genişliği Önceliği: 🐢 Düşük (%10 Hız Payı)"
            if status in ("Downloading", "Queued", "Probing", "Retrying"):
                display_status = f"🐢 {status}"
        else:
            prio_tooltip = "Bant Genişliği Önceliği: ⚖️ Normal"

        if status == "Completed":
            spath = dl.get("save_path", "")
            if spath and not os.path.exists(spath):
                display_status = "⚠️ Dosya Eksik"
                item_name.setToolTip(f"⚠️ Dosya disk üzerinde bulunamadı (silinmiş veya taşınmış):\n{spath}")
                item_name.setText(f"⚠️ {dl.get('filename', 'download')}")

        item_status = NumericTableWidgetItem(display_status)
        item_status.setData(Qt.ItemDataRole.UserRole, status)
        item_status.setToolTip(prio_tooltip)
        self.table.setItem(row, 5, item_status)

        date_add = dl.get("date_added", "")
        item_date = NumericTableWidgetItem(date_add)
        item_date.setData(Qt.ItemDataRole.UserRole, date_add)
        self.table.setItem(row, 6, item_date)
        self._apply_search_and_filter()

    def _handle_progress_update(self, download_id: str, downloaded: int, total: int, speed: float, eta: int):
        row = self._find_row_by_id(download_id)
        if row >= 0:
            col1 = self.table.item(row, 1)
            if col1:
                col1.setText(format_progress_size(downloaded, total))
                col1.setData(Qt.ItemDataRole.UserRole, downloaded)
            if total > 0:
                pct = int((downloaded / total) * 100)
                prog = self.table.cellWidget(row, 2)
                if isinstance(prog, QProgressBar):
                    prog.setValue(min(100, pct))
            col3 = self.table.item(row, 3)
            if col3:
                col3.setText(format_speed(speed))
                col3.setData(Qt.ItemDataRole.UserRole, int(speed))
            col4 = self.table.item(row, 4)
            if col4:
                col4.setText(format_eta(eta))
                col4.setData(Qt.ItemDataRole.UserRole, int(eta))

        # Forward to open progress dialog if visible
        if download_id in self.active_dialogs:
            self.active_dialogs[download_id].update_progress(downloaded, total, speed, eta)

        # Update total speed in status bar and real-time bandwidth graph
        tot_speed = sum(sum(s.current_speed for s in d.segments) for d in self.queue_mgr.active_downloaders.values())
        self.lbl_speed_stat.setText(f"Toplam Hız: {format_speed(tot_speed)}")
        if hasattr(self, "speed_graph"):
            self.speed_graph.add_speed_sample(tot_speed)

    def _handle_segments_update(self, download_id: str, segments: list):
        if download_id in self.active_dialogs:
            dl_obj = self.queue_mgr.get_downloader(download_id)
            tot = dl_obj.total_size if dl_obj else -1
            self.active_dialogs[download_id].update_segments(segments, tot)

    def _handle_status_update(self, download_id: str, status: str, err: str):
        row = self._find_row_by_id(download_id)
        if row >= 0:
            item_st = self.table.item(row, 5)
            if item_st:
                item_st.setText(status)
                item_st.setData(Qt.ItemDataRole.UserRole, status)
            self._update_run_toggle_state()

            rec = self.queue_mgr.get_download(download_id)
            if rec:
                if rec.get("filename"):
                    item_f = self.table.item(row, 0)
                    if item_f:
                        item_f.setText(rec["filename"])
                t_size = rec.get("total_size", -1)
                d_size = rec.get("downloaded_size", 0)
                col1 = self.table.item(row, 1)
                if col1:
                    if status == "Completed":
                        final_size = t_size if t_size > 0 else d_size
                        col1.setText(format_size(final_size))
                        col1.setData(Qt.ItemDataRole.UserRole, final_size)
                    elif status in ("Downloading", "Paused", "Probing"):
                        col1.setText(format_progress_size(d_size, t_size))
                        col1.setData(Qt.ItemDataRole.UserRole, d_size)
                    elif t_size > 0:
                        col1.setText(format_size(t_size))
                        col1.setData(Qt.ItemDataRole.UserRole, t_size)

            if status == "Completed":
                prog = self.table.cellWidget(row, 2)
                if isinstance(prog, QProgressBar):
                    prog.setValue(100)
                col3 = self.table.item(row, 3)
                if col3:
                    col3.setText("--")
                    col3.setData(Qt.ItemDataRole.UserRole, 0)
                col4 = self.table.item(row, 4)
                if col4:
                    col4.setText("0 sn")
                    col4.setData(Qt.ItemDataRole.UserRole, 0)

                # Sound notification on completion
                if bool(self.db.get_setting("sound_notifications", True)):
                    play_completion_sound()

                if rec:
                    toast_en = bool(self.db.get_setting("toast_notifications", True))
                    if toast_en:
                        is_vid = rec.get("category") == "Video"
                        self.tray.notify_completed(
                            filename=rec["filename"],
                            save_path=rec.get("save_path", ""),
                            is_video=is_vid
                        )

                    # Auto-open on completion
                    if rec.get("auto_open"):
                        spath = rec.get("save_path", "")
                        if spath and os.path.exists(spath):
                            try:
                                os.startfile(os.path.abspath(spath))
                            except Exception as e:
                                logger.error(f"Dosya otomatik açılamadı ({spath}): {e}")
                                self.statusBar().showMessage(f"❌ Dosya açılamadı: {rec['filename']} - {e}", 5000)
                                self.tray.notify_warning("Dosya Açılamadı", f"{rec['filename']} açılamadı: {e}")

                    # Auto-extract archives on completion
                    auto_extract_global = bool(self.db.get_setting("auto_extract_archives", False))
                    auto_extract_task = bool(rec.get("auto_extract", 0))
                    if auto_extract_global or auto_extract_task:
                        spath = rec.get("save_path", "")
                        if spath and os.path.exists(spath) and is_archive_file(spath):
                            def _on_extracted(success: bool, msg: str, f_name=rec["filename"]):
                                if success:
                                    self.statusBar().showMessage(f"📦 Arşiv başarıyla çıkartıldı: {f_name}", 5000)
                                    self.tray.showMessage("Arşiv Çıkartıldı", f"{f_name} başarıyla klasöre açıldı.", QSystemTrayIcon.MessageIcon.Information, 3500)
                                else:
                                    print(f"[AutoExtract] Error extracting {f_name}: {msg}")
                            extract_archive_async(spath, callback=_on_extracted)

                # Refresh disk space indicator on completion
                self._update_disk_space_ui()

            elif status == "Error":
                # Sound notification on error
                if bool(self.db.get_setting("sound_notifications", True)):
                    play_error_sound()

            elif status == "CorruptState":
                # Bozuk durum dosyası: kullanıcıya 'yeniden dene' / 'devam et' seçimi sun.
                self._ask_corrupt_state_action(download_id, err)

        if download_id in self.active_dialogs:
            self.active_dialogs[download_id].update_status(status, err)

    def _ask_corrupt_state_action(self, download_id: str, message: str):
        """Bozuk indirme durumu dosyası durumunda kullanıcıya yeniden dene / devam et seçimi sunar."""
        dl = self.queue_mgr.get_downloader(download_id)
        if dl is None:
            return

        rec = self.queue_mgr.get_download(download_id)
        fname = rec.get("filename") if rec else (dl.filename or download_id)

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Bozuk İndirme Durumu - RipSync")
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setText(f"<h3>{fname} için indirme durumu dosyası bozuk.</h3>")
        msg_box.setInformativeText(
            "Yarıda biten dosya diskte korunuyor ve silinmeyecek.\n\n"
            f"Durum: {message or 'Durum dosyası okunamadı veya bozuk.'}\n\n"
            "Nasıl devam etmek istersiniz?"
        )
        btn_retry = msg_box.addButton("🔄 Yeniden Dene (Baştan, Tek Bağlantı)", QMessageBox.ButtonRole.AcceptRole)
        btn_resume = msg_box.addButton("▶️ Devam Et (Dosyadan Kaldığı Yerden, Tek Bağlantı)", QMessageBox.ButtonRole.ActionRole)
        btn_keep = msg_box.addButton("⏹️ İptal Et (Dosyayı Koru)", QMessageBox.ButtonRole.DestructiveRole)
        msg_box.setDefaultButton(btn_resume)

        try:
            msg_box.exec()
        except Exception:
            return

        clicked = msg_box.clickedButton()
        if clicked == btn_retry:
            dl.retry()
        elif clicked == btn_resume:
            dl.resume()
        else:
            # İptal Et (Dosyayı Koru): durumu duraklatılmış/kayıtsız olarak işaretle,
            # indirmeyi sonlandır ve dosyayı diskte bırak.
            dl.pause()

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
            site_rules=self.site_rules_mgr,
            db=self.db,
            parent=self
        )
        dlg.download_confirmed.connect(self._on_download_confirmed)
        dlg.exec()

    def set_bridge_server(self, bridge_server):
        """Attaches bridge server instance and updates UI status."""
        self.bridge_server = bridge_server
        if self.bridge_server:
            if self.bridge_server.is_running:
                st = "running_fallback" if self.bridge_server.conflict_detected else "running"
                self._handle_bridge_status(st, self.bridge_server.actual_port, "")
            elif self.bridge_server.conflict_detected:
                self._handle_bridge_status("conflict", self.bridge_server.port, self.bridge_server.error_message or "")

    def restart_bridge_server(self, new_port: Optional[int] = None) -> bool:
        """Restarts the bridge server, optionally applying a new port."""
        port = int(new_port if new_port is not None else self.db.get_setting("extension_port", 28710))
        token = self.db.get_or_create_bridge_token()
        if self.bridge_server:
            success = self.bridge_server.restart(new_port=port, wait_for_ready=True)
            if success:
                from server.bridge_server import write_extension_config
                write_extension_config(token=token, port=self.bridge_server.actual_port)
            return success
        else:
            from server.bridge_server import BridgeServer, write_extension_config
            self.bridge_server = BridgeServer(
                host="127.0.0.1",
                port=port,
                auth_token=token,
                on_download_request=lambda data: self.sig_bridge_download.emit(data),
                on_media_detected=lambda data: None,
                auto_fallback=True,
                on_status_change=lambda st, p, msg: self.sig_bridge_status.emit(st, p, msg or "")
            )
            success = self.bridge_server.start(wait_for_ready=True)
            if success:
                write_extension_config(token=token, port=self.bridge_server.actual_port)
            return success

    def _handle_bridge_status(self, status: str, port: int, message: str):
        """Updates the status bar indicator and delivers warnings on conflict."""
        if status == "running":
            self.lbl_ext_status.setText(f"🟢 Tarayıcı Köprüsü: Aktif (Port {port})")
            self.lbl_ext_status.setStyleSheet(f"color: {T['success']}; font-weight: bold; margin-left: 10px; cursor: pointer;")
            self.lbl_ext_status.setToolTip(f"Köprü sunucusu 127.0.0.1:{port} adresinde aktif.\nKurulum kılavuzu için tıklayın.")
        elif status == "running_fallback":
            self.lbl_ext_status.setText(f"🟡 Tarayıcı Köprüsü: Aktif (Port {port} - Çakışma Çözüldü)")
            self.lbl_ext_status.setStyleSheet(f"color: {T['warning']}; font-weight: bold; margin-left: 10px; cursor: pointer;")
            self.lbl_ext_status.setToolTip(f"{message}\nTarayıcı eklentisi bu yeni porta otomatik bağlanacaktır.\nDetaylar için tıklayın.")
            if hasattr(self, "tray") and self.tray:
                self.tray.showMessage(
                    "RipSync - Port Çakışması Çözüldü",
                    f"Varsayılan port kullanımda olduğu için köprü sunucusu otomatik olarak {port} portuna geçirildi.",
                    QSystemTrayIcon.MessageIcon.Warning,
                    5000
                )
        elif status == "conflict":
            self.lbl_ext_status.setText(f"🔴 Tarayıcı Köprüsü: Port Çakışması (Port {port})")
            self.lbl_ext_status.setStyleSheet(f"color: {T['danger']}; font-weight: bold; margin-left: 10px; cursor: pointer;")
            self.lbl_ext_status.setToolTip(f"Port {port} başka bir program tarafından kullanılıyor!\nAyarları açıp portu değiştirmek için tıklayın.")
            if hasattr(self, "tray") and self.tray:
                self.tray.showMessage(
                    "RipSync - Port Çakışması",
                    f"Port {port} başka bir program tarafından kullanılıyor. Lütfen Ayarlar'dan portu değiştirin.",
                    QSystemTrayIcon.MessageIcon.Critical,
                    6000
                )
        elif status == "error":
            self.lbl_ext_status.setText(f"🔴 Tarayıcı Köprüsü: Hata (Port {port})")
            self.lbl_ext_status.setStyleSheet(f"color: {T['danger']}; font-weight: bold; margin-left: 10px; cursor: pointer;")
            self.lbl_ext_status.setToolTip(f"Köprü sunucusu hatası: {message}\nTekrar denemek için tıklayın.")
        elif status == "stopped":
            self.lbl_ext_status.setText("⚪ Tarayıcı Köprüsü: Kapalı")
            self.lbl_ext_status.setStyleSheet(f"color: {T['disabled_text']}; font-weight: bold; margin-left: 10px; cursor: pointer;")
            self.lbl_ext_status.setToolTip("Köprü sunucusu durduruldu.")

    def _on_lbl_ext_status_clicked(self, event):
        """Opens settings if there is a conflict/error, or guide if running."""
        if self.bridge_server and not self.bridge_server.is_running and self.bridge_server.conflict_detected:
            self._show_settings_dialog()
        else:
            self._show_extension_guide()

    def _check_clipboard_first_run_consent(self):
        """Prompt user on first launch to ask if they want clipboard monitoring enabled."""
        if "PYTEST_CURRENT_TEST" in os.environ:
            return

        clip_cfg = self.db.get_clipboard_settings()
        if clip_cfg.get("prompted", False):
            return

        from ui.clipboard_consent_dialog import ClipboardConsentDialog
        consent = ClipboardConsentDialog.ask_consent(self)

        self.db.save_clipboard_settings({
            "enabled": consent,
            "prompted": True
        })
        self.clip_monitor.set_enabled(consent)

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
            # Duplicate check
            if self.db.get_duplicate_warning_setting():
                dup = self.db.find_duplicate_download(url=url, filename=candidate_filename)
                if dup:
                    dlg_dup = DuplicateDownloadDialog(dup, current_url=url, parent=self)
                    if dlg_dup.exec():
                        act = dlg_dup.get_action()
                        if act in (DuplicateDownloadDialog.ACTION_CANCEL, DuplicateDownloadDialog.ACTION_OPEN_EXISTING):
                            return
                    else:
                        return

            # Add directly to queue with user's default settings
            default_dir = self.db.get_setting("default_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
            conns = int(self.db.get_setting("connections", 8))
            pref_quality = self.db.get_setting("preferred_quality", "max")

            # Check overwrite conflict if action is overwrite
            conflict_action = self.db.get_conflict_setting()
            target_check_path = os.path.join(default_dir, candidate_filename) if candidate_filename else ""
            if conflict_action == "overwrite" and target_check_path and os.path.exists(target_check_path):
                from ui.overwrite_dialog import OverwriteConfirmDialog
                dlg_ow = OverwriteConfirmDialog(default_dir, candidate_filename, parent=self)
                if dlg_ow.exec():
                    ow_act = dlg_ow.get_action()
                    if ow_act == OverwriteConfirmDialog.ACTION_CANCEL:
                        return
                    elif ow_act == OverwriteConfirmDialog.ACTION_AUTO_RENAME:
                        candidate_filename = dlg_ow.get_resolved_filename()
                else:
                    return

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
            site_rules=self.site_rules_mgr,
            db=self.db,
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

        conflict_action = self.db.get_conflict_setting()
        if conflict_action == "overwrite":
            conflicted_items = [
                it for it in items
                if os.path.exists(os.path.join(it["save_dir"], it["filename"]))
            ]
            if conflicted_items:
                names_summary = "\n".join([f"- {it['filename']}" for it in conflicted_items[:5]])
                if len(conflicted_items) > 5:
                    names_summary += f"\n... ve {len(conflicted_items) - 5} dosya daha"
                
                reply = QMessageBox.warning(
                    self,
                    "⚠️ Çalma Listesi Dosya Üzerine Yazma Onayı",
                    f"Çalma listesindeki {len(conflicted_items)} dosya hedef klasörde zaten mevcut:\n\n"
                    f"{names_summary}\n\n"
                    "Dosya çakışması ayarınız 'Üzerine Yaz' olarak seçilmiş.\n"
                    "Bu dosyaların üzerine yazılmasını onaylıyor musunuz?\n\n"
                    "- 'Evet': Mevcut dosyaların üzerine yazılır.\n"
                    "- 'Hayır': Çakışan dosyalar otomatik yeniden adlandırılır ('dosya (1).ext').\n"
                    "- 'İptal': İndirme işlemi iptal edilir.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Cancel:
                    return
                elif reply == QMessageBox.StandardButton.No:
                    from core.paths import resolve_file_conflict
                    for it in items:
                        new_name, _ = resolve_file_conflict(it["save_dir"], it["filename"], action="auto_rename")
                        it["filename"] = new_name

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
                start_now=start_now,
                tags=item.get("tags", "")
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
        self._refresh_tags_tree()

    def _on_download_confirmed(self, data: dict):
        did = self.queue_mgr.add_download(
            url=data["url"],
            save_dir=data["save_dir"],
            filename=data["filename"],
            connections=data["connections"],
            quality=data.get("quality", "max"),
            headers=data.get("headers"),
            start_now=data["start_now"],
            auto_open=data.get("auto_open", False),
            auto_extract=data.get("auto_extract", False),
            priority=data.get("priority", "normal"),
            tags=data.get("tags", ""),
            queue_id=data.get("queue_id", "default")
        )
        self._refresh_tags_tree()
        self._refresh_queues_tree()
        if data["start_now"]:
            self._open_progress_dialog(did)

    def _open_progress_dialog(self, download_id: str):
        if download_id in self.active_dialogs:
            self.active_dialogs[download_id].show()
            self.active_dialogs[download_id].raise_()
            return

        rec = self.queue_mgr.get_download(download_id)
        if not rec:
            return

        # Determine current active limit for this downloader
        active_dl = self.queue_mgr.get_downloader(download_id)
        current_limit = active_dl.speed_limiter.get_limit() if active_dl else self.queue_mgr.global_speed_limit_bps

        dlg = ProgressDialog(
            download_id,
            rec["filename"],
            rec["save_path"],
            initial_speed_limit=current_limit,
            initial_auto_open=bool(rec.get("auto_open", False)),
            parent=self
        )
        dlg.pause_requested.connect(self.queue_mgr.pause_download)
        dlg.resume_requested.connect(self.queue_mgr.resume_download)
        dlg.cancel_requested.connect(self.queue_mgr.cancel_download)
        dlg.speed_limit_changed.connect(self._handle_single_task_speed_limit)
        dlg.auto_open_changed.connect(lambda did, chk: self.db.update_download(did, auto_open=1 if chk else 0))
        dlg.refresh_url_requested.connect(self._show_refresh_url_dialog)

        self.active_dialogs[download_id] = dlg
        dlg.show()

    def _on_row_double_click(self, row: int, col: int):
        item = self.table.item(row, 0)
        if not item:
            return
        download_id = item.data(Qt.ItemDataRole.UserRole)
        rec = self.queue_mgr.get_download(download_id)
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
        if not dids:
            return

        count = len(dids)
        title = "İndirmeyi İptal Et" if count == 1 else "İndirmeleri İptal Et"
        target_desc = "seçili indirmeyi" if count == 1 else f"seçili {count} adet indirmeyi"

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(f"{title} - RipSync")
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setText(f"<h3>{target_desc.capitalize()} iptal etmek yerine duraklatmak ister misiniz?</h3>")
        msg_box.setInformativeText(
            "Duraklatırsanız indirilen kısımlar diskte korunur ve dilediğiniz zaman kaldığı yerden devam edebilirsiniz.\n\n"
            "İptal ederseniz indirme süreci sonlandırılacaktır."
        )

        btn_pause = msg_box.addButton("⏸️ Duraklat (Önerilen)", QMessageBox.ButtonRole.AcceptRole)
        btn_cancel_keep = msg_box.addButton("⏹️ İptal Et (Dosyaları Koru)", QMessageBox.ButtonRole.ActionRole)
        btn_cancel_delete = msg_box.addButton("🗑️ İptal Et ve Dosyaları Sil", QMessageBox.ButtonRole.DestructiveRole)
        btn_dismiss = msg_box.addButton("Vazgeç", QMessageBox.ButtonRole.RejectRole)

        try:
            msg_box.setDefaultButton(btn_pause)
        except Exception:
            pass
        msg_box.exec()

        clicked = msg_box.clickedButton()
        if clicked == btn_pause:
            for did in dids:
                self.queue_mgr.pause_download(did)
        elif clicked == btn_cancel_keep:
            for did in dids:
                self.queue_mgr.cancel_download(did, delete_file=False)
        elif clicked == btn_cancel_delete:
            for did in dids:
                self.queue_mgr.cancel_download(did, delete_file=True)

    def _delete_selected(self):
        dids = self._get_selected_download_ids()
        if not dids:
            return
        records = [self.queue_mgr.get_download(did) for did in dids if self.queue_mgr.get_download(did)]
        if not records:
            records = [{"id": did, "filename": f"İndirme #{did}", "save_path": "", "status": "Unknown"} for did in dids]

        dlg = DeleteConfirmDialog(records, initial_delete_file=False, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            del_file = dlg.get_delete_file_choice()
            if del_file is not None:
                for did in dids:
                    self.queue_mgr.delete_download(did, delete_file=del_file)
                self._load_downloads_to_table()
                if del_file:
                    self.statusBar().showMessage(f"💥 {len(dids)} adet indirme ve dosyası kalıcı olarak silindi.", 4000)
                else:
                    self.statusBar().showMessage(f"🗑 {len(dids)} adet indirme listeden kaldırıldı (dosya diskte korundu).", 4000)

    def _delete_selected_with_files(self):
        dids = self._get_selected_download_ids()
        if not dids:
            return
        records = [self.queue_mgr.get_download(did) for did in dids if self.queue_mgr.get_download(did)]
        if not records:
            records = [{"id": did, "filename": f"İndirme #{did}", "save_path": "", "status": "Unknown"} for did in dids]

        dlg = DeleteConfirmDialog(records, initial_delete_file=True, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            del_file = dlg.get_delete_file_choice()
            if del_file is not None:
                for did in dids:
                    self.queue_mgr.delete_download(did, delete_file=del_file)
                self._load_downloads_to_table()
                if del_file:
                    self.statusBar().showMessage(f"💥 {len(dids)} adet indirme ve dosyası kalıcı olarak silindi.", 4000)
                else:
                    self.statusBar().showMessage(f"🗑 {len(dids)} adet indirme listeden kaldırıldı (dosya diskte korundu).", 4000)

    def _open_selected_file(self):
        did = self._get_selected_download_id()
        if not did:
            return
        rec = self.queue_mgr.get_download(did)
        if rec and os.path.exists(rec["save_path"]):
            os.startfile(rec["save_path"])
        else:
            QMessageBox.warning(self, "Uyarı", "Dosya henüz indirilmedi veya bulunamadı.")

    def _open_selected_folder(self):
        did = self._get_selected_download_id()
        if not did:
            return
        rec = self.queue_mgr.get_download(did)
        if rec:
            save_path = rec["save_path"]
            folder = os.path.dirname(save_path)
            if os.path.exists(save_path) or os.path.exists(folder):
                show_in_explorer(save_path)
            else:
                QMessageBox.warning(self, "Uyarı", "Klasör bulunamadı.")

    def _open_checksum_dialog(self, download_id: str):
        rec = self.queue_mgr.get_download(download_id)
        if not rec:
            return
        spath = rec.get("save_path", "")
        if not spath or not os.path.exists(spath):
            QMessageBox.warning(self, "Uyarı", "Dosya disk üzerinde bulunamadı veya henüz indirilmedi.")
            return

        dlg = ChecksumDialog(spath, parent=self)
        dlg.exec()

    def _open_properties_dialog(self, download_id: str):
        rec = self.queue_mgr.get_download(download_id)
        if not rec:
            return
        dlg = DownloadPropertiesDialog(rec, parent=self)
        dlg.exec()

    def _show_batch_add_dialog(self, initial_text: str = ""):
        default_dir = self.db.get_setting("default_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
        conns = int(self.db.get_setting("connections", 8))
        quality = self.db.get_setting("preferred_quality", "max")
        auto_cat = bool(self.db.get_setting("auto_categorize", True))

        dlg = BatchAddDialog(
            base_download_dir=default_dir,
            default_connections=conns,
            default_quality=quality,
            auto_categorize=auto_cat,
            initial_text=initial_text,
            site_rules=self.site_rules_mgr,
            parent=self
        )
        dlg.batch_download_confirmed.connect(self._on_batch_add_confirmed)
        dlg.exec()

    def _on_batch_add_confirmed(self, items: list, start_now: bool):
        if not items:
            return

        conflict_action = self.db.get_conflict_setting()
        if conflict_action == "overwrite":
            conflicted_items = [
                it for it in items
                if os.path.exists(os.path.join(it["save_dir"], it["filename"]))
            ]
            if conflicted_items:
                names_summary = "\n".join([f"- {it['filename']}" for it in conflicted_items[:5]])
                if len(conflicted_items) > 5:
                    names_summary += f"\n... ve {len(conflicted_items) - 5} dosya daha"
                
                reply = QMessageBox.warning(
                    self,
                    "⚠️ Toplu İndirme Dosya Üzerine Yazma Onayı",
                    f"Toplu indirme listenizdeki {len(conflicted_items)} dosya hedef klasörde zaten mevcut:\n\n"
                    f"{names_summary}\n\n"
                    "Dosya çakışması ayarınız 'Üzerine Yaz' olarak seçilmiş.\n"
                    "Bu dosyaların üzerine yazılmasını onaylıyor musunuz?\n\n"
                    "- 'Evet': Mevcut dosyaların üzerine yazılır.\n"
                    "- 'Hayır': Çakışan dosyalar otomatik yeniden adlandırılır ('dosya (1).ext').\n"
                    "- 'İptal': Toplu indirme işlemi iptal edilir.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Cancel:
                    return
                elif reply == QMessageBox.StandardButton.No:
                    from core.paths import resolve_file_conflict
                    for it in items:
                        new_name, _ = resolve_file_conflict(it["save_dir"], it["filename"], action="auto_rename")
                        it["filename"] = new_name

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
                start_now=start_now,
                priority=item.get("priority", "normal"),
                tags=item.get("tags", "")
            )
            added_ids.append(did)
            if not first_id:
                first_id = did

        total = len(added_ids)
        self._refresh_tags_tree()
        if start_now:
            msg = f"{total} adet bağlantı toplu olarak indirme kuyruğuna alındı ve sırayla başlatıldı."
            self.statusBar().showMessage(msg, 5000)
            self.tray.showMessage("Toplu İndirme Başlatıldı", msg, QSystemTrayIcon.MessageIcon.Information, 3500)
            if first_id:
                self._open_progress_dialog(first_id)
        else:
            msg = f"{total} adet bağlantı indirme kuyruğuna eklendi."
            self.statusBar().showMessage(msg, 5000)
            self.tray.showMessage("Kuyruğa Eklendi", msg, QSystemTrayIcon.MessageIcon.Information, 3000)

        self._load_downloads_to_table()

    def _export_downloads_list(self, selected_ids: Optional[List[str]] = None):
        """Export all or selected downloads to a .txt or .json file."""
        if selected_ids:
            records = [self.queue_mgr.get_download(did) for did in selected_ids]
            records = [r for r in records if r]
        else:
            records = self.queue_mgr.get_all_downloads()

        if not records:
            QMessageBox.information(self, "Bilgi", "Dışa aktarılacak herhangi bir indirme bulunamadı.")
            return

        path, flt = QFileDialog.getSaveFileName(
            self,
            "İndirme Listesini Dışa Aktar",
            os.path.join(os.path.expanduser("~"), "Documents", "ripsync_downloads.txt"),
            "Metin Dosyası (*.txt);;JSON Dosyası (*.json)"
        )
        if not path:
            return

        try:
            if path.endswith(".json") or "JSON" in flt:
                import json
                clean_records = []
                for r in records:
                    clean_records.append({
                        "url": r.get("url"),
                        "filename": r.get("filename"),
                        "status": r.get("status"),
                        "save_path": r.get("save_path"),
                        "total_size": r.get("total_size"),
                        "date_added": r.get("date_added")
                    })
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(clean_records, f, indent=2, ensure_ascii=False)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    for r in records:
                        url = r.get("url", "").strip()
                        if url:
                            f.write(url + "\n")

            QMessageBox.information(self, "Başarılı", f"{len(records)} adet indirme bağlantısı başarıyla dışa aktarıldı:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Dışa aktarma başarısız:\n{str(e)}")

    def _import_downloads_list(self):
        """Import download URLs from a .txt or .json file and launch Batch Add Dialog."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "İçe Aktarılacak Dosyayı Seç",
            os.path.expanduser("~"),
            "Metin / JSON Dosyaları (*.txt *.json *.m3u *.m3u8);;Tüm Dosyalar (*.*)"
        )
        if not path or not os.path.exists(path):
            return

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            urls = extract_valid_urls(content)
            if not urls:
                QMessageBox.warning(self, "Uyarı", "Seçilen dosyada geçerli bir indirme bağlantısı bulunamadı.")
                return

            self._show_batch_add_dialog(initial_text="\n".join(urls))
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Dosya okunamadı:\n{str(e)}")

    def _apply_search_and_filter(self):
        query = self.edit_search.text().strip().lower() if hasattr(self, "edit_search") else ""
        active_chip = "all"
        if hasattr(self, "filter_btn_group"):
            for chip_id, btn in self.filter_btn_group.items():
                if btn.isChecked():
                    active_chip = chip_id
                    break

        visible_count = 0
        total_count = self.table.rowCount()

        for r in range(total_count):
            item_name = self.table.item(r, 0)
            item_status = self.table.item(r, 5)
            if not item_name:
                continue

            name = item_name.text().lower()
            did = item_name.data(Qt.ItemDataRole.UserRole)
            rec = self.queue_mgr.get_download(did) if did else None
            url = (rec.get("url", "") if rec else "").lower()
            raw_status = item_status.data(Qt.ItemDataRole.UserRole) if item_status else (rec.get("status", "") if rec else "")
            status = item_status.text() if item_status else (rec.get("status", "") if rec else "")

            # Filter by chip
            status_match = True
            if active_chip != "all":
                if active_chip == "Downloading":
                    status_match = raw_status in ("Downloading", "Probing", "Retrying") or status in ("Downloading", "Probing", "Retrying")
                elif active_chip == "Completed":
                    status_match = raw_status == "Completed" or status in ("Completed", "⚠️ Dosya Eksik")
                else:
                    status_match = (raw_status == active_chip) or (status == active_chip)

            # Filter by search query
            query_match = True
            if query:
                query_match = (query in name) or (query in url)

            # Filter by size
            size_match = True
            if hasattr(self, "combo_size_filter"):
                sz_filter = self.combo_size_filter.currentData()
                if sz_filter and sz_filter != "all":
                    item_sz = self.table.item(r, 1)
                    raw_bytes = item_sz.data(Qt.ItemDataRole.UserRole) if item_sz else 0
                    if not isinstance(raw_bytes, (int, float)):
                        raw_bytes = 0
                    if sz_filter == "small":
                        size_match = raw_bytes < 50 * 1024 * 1024
                    elif sz_filter == "medium":
                        size_match = (50 * 1024 * 1024 <= raw_bytes < 500 * 1024 * 1024)
                    elif sz_filter == "large":
                        size_match = (500 * 1024 * 1024 <= raw_bytes < 2 * 1024 * 1024 * 1024)
                    elif sz_filter == "huge":
                        size_match = raw_bytes >= 2 * 1024 * 1024 * 1024

            # Filter by date
            date_match = True
            if hasattr(self, "combo_date_filter"):
                dt_filter = self.combo_date_filter.currentData()
                if dt_filter and dt_filter != "all":
                    item_dt_w = self.table.item(r, 6)
                    date_str = item_dt_w.text() if item_dt_w else ""
                    if date_str:
                        try:
                            item_dt = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
                            now_date = datetime.now().date()
                            diff_days = (now_date - item_dt).days
                            if dt_filter == "today":
                                date_match = (diff_days == 0)
                            elif dt_filter == "yesterday":
                                date_match = (diff_days == 1)
                            elif dt_filter == "week":
                                date_match = (diff_days <= 7)
                            elif dt_filter == "older":
                                date_match = (diff_days > 7)
                        except Exception:
                            date_match = True

            # Filter by tag
            tag_match = True
            if getattr(self, "current_tag", None):
                rec_tags = (rec.get("tags", "") if rec else "").lower()
                tag_match = bool(self.current_tag.lower() in rec_tags)

            # Filter by queue
            queue_match = True
            if getattr(self, "current_queue_id", None):
                rec_qid = (rec.get("queue_id", "default") if rec else "default") or "default"
                queue_match = (rec_qid == self.current_queue_id)

            should_show = status_match and query_match and size_match and date_match and tag_match and queue_match
            self.table.setRowHidden(r, not should_show)
            if should_show:
                visible_count += 1

        if hasattr(self, "lbl_filter_count"):
            self.lbl_filter_count.setText(f"{visible_count} / {total_count}")
        self._sync_empty_state()

    def _on_filter_chip_clicked(self, clicked_chip: str):
        for chip_id, btn in self.filter_btn_group.items():
            btn.blockSignals(True)
            btn.setChecked(chip_id == clicked_chip)
            btn.blockSignals(False)
        self._apply_search_and_filter()

    def _clear_search(self):
        if hasattr(self, "edit_search"):
            self.edit_search.clear()
            self._apply_search_and_filter()

    def _on_speed_decay_tick(self):
        active_cnt = len([d for d in self.queue_mgr.active_downloaders.values() if d.status in ("Downloading", "Probing", "Retrying")])
        if active_cnt == 0:
            if hasattr(self, "speed_graph"):
                self.speed_graph.add_speed_sample(0.0)
            if hasattr(self, "lbl_speed_stat"):
                self.lbl_speed_stat.setText("Toplam Hız: 0 KB/s")

        if not hasattr(self, "_disk_tick_count"):
            self._disk_tick_count = 0
        self._disk_tick_count += 1
        if self._disk_tick_count % 5 == 0:
            self._update_disk_space_ui()

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
            self.lbl_tb_limit_val.setStyleSheet(f"font-weight: bold; color: {T['color_orange']}; min-width: 75px;")
            self.lbl_limiter_stat.setText(f"⚡ Hız Sınırı: Aktif ({txt})")
            self.lbl_limiter_stat.setStyleSheet(f"color: {T['color_orange']}; font-weight: bold; margin-left: 20px;")
        else:
            self.lbl_tb_limit_val.setText("Tam Hız")
            self.lbl_tb_limit_val.setStyleSheet(f"font-weight: bold; color: {T['success']}; min-width: 75px;")
            self.lbl_limiter_stat.setText("⚡ Hız Sınırı: Kapalı (Tam Hız)")
            self.lbl_limiter_stat.setStyleSheet(f"color: {T['success']}; font-weight: bold; margin-left: 20px;")

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

    def _set_download_priority(self, download_id: str, priority: str):
        self.queue_mgr.set_download_priority(download_id, priority)
        p_names = {"high": "Yüksek (🚀)", "normal": "Normal (⚖️)", "low": "Düşük (🐢)"}
        self.statusBar().showMessage(f"Öncelik güncellendi: {p_names.get(priority, priority)}", 3000)
        self._load_downloads_to_table()

    def _set_bulk_priority(self, download_ids: List[str], priority: str):
        for did in download_ids:
            self.queue_mgr.set_download_priority(did, priority)
        p_names = {"high": "Yüksek (🚀)", "normal": "Normal (⚖️)", "low": "Düşük (🐢)"}
        self.statusBar().showMessage(f"{len(download_ids)} indirme önceliği güncellendi: {p_names.get(priority, priority)}", 3000)
        self._load_downloads_to_table()

    def _show_settings_dialog(self):
        old_port = int(self.db.get_setting("extension_port", 28710))
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

            clip_cfg = self.db.get_clipboard_settings()
            self.clip_monitor.configure(
                enabled=bool(clip_cfg.get("enabled", False)),
                only_media=bool(clip_cfg.get("only_media", False)),
                ignore_domains=clip_cfg.get("ignore_domains")
            )

            # Apply appearance / theme dynamically
            thm_cfg = self.db.get_theme_settings()
            app = QApplication.instance()
            from ui import styles as _styles
            _styles.refresh_tokens(thm_cfg.get("theme", "dark"), thm_cfg.get("accent", "blue"))
            sheet = _styles.get_app_stylesheet()
            if app:
                app.setStyleSheet(sheet)
            else:
                self.setStyleSheet(sheet)
            self._apply_toolbar_icons()

            # Apply UI mode if modified in settings
            self.apply_ui_mode(self.db.get_ui_mode())

            # Check if extension port was modified or server needs restart
            new_port = int(self.db.get_setting("extension_port", 28710))
            needs_restart = (new_port != old_port) or (self.bridge_server and not self.bridge_server.is_running)
            if needs_restart:
                restarted = self.restart_bridge_server(new_port)
                if restarted:
                    actual = self.bridge_server.actual_port if self.bridge_server else new_port
                    self.statusBar().showMessage(f"Tarayıcı köprüsü {actual} portunda yeniden başlatıldı.", 4000)
                else:
                    self.statusBar().showMessage(f"Uyarı: {new_port} portunda köprü sunucusu başlatılamadı!", 5000)

    def _show_extension_guide(self):
        if self.bridge_server and self.bridge_server.actual_port:
            port = self.bridge_server.actual_port
        else:
            port = int(self.db.get_setting("extension_port", 28710))
        token = self.db.get_or_create_bridge_token()
        from ui.extension_guide_dialog import ExtensionGuideDialog
        dlg = ExtensionGuideDialog(self, bridge_port=port, bridge_token=token)
        dlg.exec()

    def _select_and_open_extension_dir(self):
        """Opens the extension directory in Explorer and copies the path to clipboard."""
        from core.extension_installer import copy_extension_path_to_clipboard, get_extension_folder_path
        from core.paths import show_in_explorer
        ext_dir = get_extension_folder_path()
        copy_extension_path_to_clipboard()
        show_in_explorer(ext_dir)
        self.statusBar().showMessage(f"Eklenti klasörü açıldı ve panoya kopyalandı: {ext_dir}", 6000)
        QMessageBox.information(
            self,
            "Eklenti Klasörü Seçildi & Açıldı 📁",
            f"RipSync eklenti klasörü Dosya Gezgini'nde açıldı ve yol panoya kopyalandı:\n\n{ext_dir}\n\n"
            "Tarayıcınızda (chrome://extensions) 'Paketlenmemiş öğe yükle' penceresi açıldığında "
            "Ctrl+V ile bu yolu yapıştırıp Klasörü Seç butonuna basabilirsiniz!"
        )

    def _copy_extension_dir_path(self):
        """Copies the unpacked extension directory path to the system clipboard."""
        from core.extension_installer import copy_extension_path_to_clipboard
        success, path = copy_extension_path_to_clipboard()
        if success:
            self.statusBar().showMessage(f"Eklenti yolu panoya kopyalandı: {path}", 5000)
            QMessageBox.information(
                self,
                "Yol Kopyalandı 📋",
                f"Eklenti klasör yolu panoya kopyalandı:\n\n{path}\n\n"
                "Tarayıcınızın 'Paketlenmemiş öğe yükle' penceresine Ctrl+V ile yapıştırabilirsiniz."
            )
        else:
            QMessageBox.warning(self, "Hata", f"Yol kopyalanamadı: {path}")

    def _launch_browser_with_ext(self, browser_key: str):
        """Launches the specified browser with --load-extension flag."""
        from core.extension_installer import launch_browser_with_extension
        success, msg = launch_browser_with_extension(browser_key)
        if success:
            self.statusBar().showMessage(msg, 5000)
            QMessageBox.information(self, "Tarayıcı Başlatıldı 🚀", f"{msg}\n\nEklenti otomatik olarak yüklendi!")
        else:
            QMessageBox.warning(self, "Başlatılamadı", msg)

    def _show_setup_wizard(self):
        """Opens the first-run / setup onboarding wizard."""
        from ui.setup_wizard_dialog import SetupWizardDialog
        dlg = SetupWizardDialog(self.db, self)
        dlg.exec()

    def _show_onboarding_dialog(self):
        """Opens the guided onboarding interactive tour dialog."""
        from ui.onboarding_dialog import OnboardingDialog
        dlg = OnboardingDialog(self.db, self)
        if hasattr(self, "apply_ui_mode"):
            dlg.tour_finished.connect(self.apply_ui_mode)
        dlg.exec()

    def _check_first_run_onboarding(self):
        """Checks if initial onboarding tour should be automatically displayed."""
        if "PYTEST_CURRENT_TEST" in os.environ:
            return
        if not self.db.is_onboarding_completed():
            self._show_onboarding_dialog()

    def _show_about_dialog(self):
        """Displays About RipSync information dialog."""
        QMessageBox.about(
            self,
            "RipSync Hakkında",
            "<h2>RipSync Download Manager</h2>"
            "<p>Hızlı, güvenli, gizlilik odaklı ve çok iş parçacıklı indirme yöneticisi.</p>"
            "<p><b>Sürüm:</b> 3.8.0</p>"
        )

    def _show_about_dialog(self):
        """Displays About RipSync information dialog."""
        QMessageBox.about(
            self,
            "RipSync Hakkında",
            "<h3>RipSync - Internet Download Manager</h3>"
            "<p><b>Sürüm:</b> 1.0.1</p>"
            "<p>Yüksek performanslı, çok kanallı (multi-segmented) internet indirme yöneticisi.</p>"
            "<p>Tarayıcı eklentisi, YouTube ve akış medyası yakalama motoru entegredir.</p>"
        )

    def apply_ui_mode(self, mode: str):
        """Basit Mod veya Gelişmiş Mod görünümünü uygular.

        Araç çubuğu her iki modda da sade kalır; Basit modda gizlenen
        hiçbir işlev kaybolmaz: tümü `⋯ Daha Fazla` menüsünden erişilir.
        Sürekli ayarlar (hız limiti, zamanlayıcı, sıralı indirme, kuyruk
        eylemi) ikincil şeritte yalnızca Gelişmiş modda görünür.
        """
        self.ui_mode = "advanced" if mode == "advanced" else "simple"
        self.db.save_ui_mode(self.ui_mode)
        is_simple = (self.ui_mode == "simple")

        # 1. İkincil ayar şeridi yalnızca Gelişmiş modda görünür
        if hasattr(self, 'quick_bar') and self.quick_bar is not None:
            self.quick_bar.setVisible(not is_simple)

        # 2. Sol panel (Kategori Ağacı): Etiketler / Kuyruklar gelişmiş kalır
        if hasattr(self, 'root_tags') and self.root_tags is not None:
            self.root_tags.setHidden(is_simple)
        if hasattr(self, 'root_queues') and self.root_queues is not None:
            self.root_queues.setHidden(is_simple)

        # 3. Arama & Filtreleme Çubuğu
        if hasattr(self, 'edit_search') and self.edit_search is not None:
            self.edit_search.setVisible(True)
        if hasattr(self, 'filter_btn_group'):
            for btn in self.filter_btn_group.values():
                btn.setVisible(not is_simple)
        if hasattr(self, 'combo_size_filter') and self.combo_size_filter is not None:
            self.combo_size_filter.setVisible(not is_simple)
        if hasattr(self, 'combo_date_filter') and self.combo_date_filter is not None:
            self.combo_date_filter.setVisible(not is_simple)
        if hasattr(self, 'lbl_filter_count') and self.lbl_filter_count is not None:
            self.lbl_filter_count.setVisible(not is_simple)

        # 4. Tablo Sütunları (Basit modda 7. sütun: Eklenme Tarihi gizlenir)
        if hasattr(self, 'table') and self.table is not None:
            self.table.setColumnHidden(6, is_simple)

        # 6. Mod Değiştirme Butonu ve Menü Durumu
        if hasattr(self, 'btn_mode_toggle') and self.btn_mode_toggle is not None:
            if is_simple:
                self.btn_mode_toggle.setText("🟢 Basit Mod (Geç: Gelişmiş ❯)")
                self.btn_mode_toggle.setToolTip("Şu an Basit Moddasınız. Tüm gelişmiş araçları görmek için tıklayın.")
                self.btn_mode_toggle.setStyleSheet(f"""
                    QPushButton#btn_mode_toggle {{
                        background-color: {T['bg_panel']};
                        border: 1px solid {T['success']};
                        color: {T['success']};
                        font-weight: bold;
                        border-radius: 6px;
                        padding: 4px 10px;
                        font-size: 11px;
                    }}
                    QPushButton#btn_mode_toggle:hover {{
                        background-color: {T['success']};
                        color: {T['bg_main']};
                    }}
                """)
            else:
                self.btn_mode_toggle.setText("⚡ Gelişmiş Mod (Geç: Basit ❮)")
                self.btn_mode_toggle.setToolTip("Şu an Gelişmiş Moddasınız. Sade görünüme dönmek için tıklayın.")
                self.btn_mode_toggle.setStyleSheet(f"""
                    QPushButton#btn_mode_toggle {{
                        background-color: {T['bg_panel']};
                        border: 1px solid {T['color_purple']};
                        color: {T['color_purple']};
                        font-weight: bold;
                        border-radius: 6px;
                        padding: 4px 10px;
                        font-size: 11px;
                    }}
                    QPushButton#btn_mode_toggle:hover {{
                        background-color: {T['color_purple']};
                        color: {T['bg_main']};
                    }}
                """)

        if hasattr(self, 'act_view_simple') and self.act_view_simple is not None:
            self.act_view_simple.blockSignals(True)
            self.act_view_simple.setChecked(is_simple)
            self.act_view_simple.blockSignals(False)

        if hasattr(self, 'act_view_advanced') and self.act_view_advanced is not None:
            self.act_view_advanced.blockSignals(True)
            self.act_view_advanced.setChecked(not is_simple)
            self.act_view_advanced.blockSignals(False)

    def _toggle_ui_mode(self):
        new_mode = "advanced" if getattr(self, 'ui_mode', 'simple') == "simple" else "simple"
        self.apply_ui_mode(new_mode)
        mod_label = "Gelişmiş Mod" if new_mode == "advanced" else "Basit Mod"
        self.statusBar().showMessage(f"Arayüz modu değiştirildi: {mod_label}", 4000)

    def _check_first_run_onboarding(self):
        """Uygulama ilk kez çalıştırıldığında rehberli turu (Onboarding) otomatik açar."""
        if "PYTEST_CURRENT_TEST" in os.environ:
            return
        import sys
        is_tour_arg = "--onboarding" in sys.argv or "--tour" in sys.argv
        has_completed = self.db.is_onboarding_completed()
        if not has_completed or is_tour_arg:
            self._show_onboarding_dialog()

    def _show_onboarding_dialog(self):
        """Hızlı Başlangıç Rehberli Tur sihirbazını açar."""
        from ui.onboarding_dialog import OnboardingDialog
        dlg = OnboardingDialog(self.db, parent=self)
        dlg.tour_finished.connect(self.apply_ui_mode)
        dlg.exec()

    def _check_first_run_setup(self):
        """Checks if initial setup wizard should be automatically displayed."""
        if "PYTEST_CURRENT_TEST" in os.environ:
            return
        import sys
        has_setup = self.db.get_setting("setup_completed", False)
        is_wizard_arg = "--setup-wizard" in sys.argv
        if not has_setup or is_wizard_arg:
            self._show_setup_wizard()

    def _show_table_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        did = self.table.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        rec = self.queue_mgr.get_download(did)
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
            act_export_bulk = menu.addAction(f"📤 Seçilenleri Dışa Aktar ({count})")
            act_export_bulk.triggered.connect(lambda: self._export_downloads_list(selected_ids=selected_ids))

            menu.addSeparator()
            menu_prio_bulk = menu.addMenu(f"⚖️ Bant Genişliği Önceliği ({count})")
            act_bh = menu_prio_bulk.addAction("🚀 Yüksek Öncelik (%70 Hız Payı)")
            act_bh.triggered.connect(lambda: self._set_bulk_priority(selected_ids, "high"))
            act_bn = menu_prio_bulk.addAction("⚖️ Normal Öncelik (Dengeli)")
            act_bn.triggered.connect(lambda: self._set_bulk_priority(selected_ids, "normal"))
            act_bl = menu_prio_bulk.addAction("🐢 Düşük Öncelik (Arka Plan - %10)")
            act_bl.triggered.connect(lambda: self._set_bulk_priority(selected_ids, "low"))

            menu.addSeparator()
            act_tags_bulk = menu.addAction(f"🏷️ Seçilenlere Etiket Ata ({count})...")
            act_tags_bulk.triggered.connect(lambda: self._edit_bulk_tags(selected_ids))

            menu.addSeparator()
            menu_queue_bulk = menu.addMenu(f"🗂️ Seçilenleri Kuyruğa Taşı ({count})")
            for q in self.db.get_all_queues():
                act_mq = menu_queue_bulk.addAction(f"🗂️ {q['name']}")
                act_mq.triggered.connect(lambda checked, qid=q["id"], dids=selected_ids: self._move_downloads_to_queue(dids, qid))

            menu.addSeparator()
            act_del_bulk = menu.addAction(f"🗑 Seçilenleri Listeden Kaldır ({count}) [Dosyalar diskte kalır]")
            act_del_bulk.setToolTip("İndirme kayıtlarını listeden kaldırır, indirilen dosyaları diskte korur.")
            act_del_bulk.triggered.connect(self._delete_selected)

            act_del_files_bulk = menu.addAction(f"💥 Seçilenleri ve Dosyalarını Tamamen Sil ({count}) [Diskten sil]")
            act_del_files_bulk.setToolTip("İndirme kayıtlarını ve indirilmiş dosyaları kalıcı olarak diskten siler.")
            act_del_files_bulk.triggered.connect(self._delete_selected_with_files)

            menu.exec(self.table.viewport().mapToGlobal(pos))
            return

        if status in ("Downloading", "Probing", "Retrying"):
            act = menu.addAction("⏸ Duraklat")
            act.triggered.connect(lambda: self.queue_mgr.pause_download(did))
        else:
            act = menu.addAction("▶ Başlat / Devam Et")
            act.triggered.connect(lambda: self.queue_mgr.resume_download(did))

        act_prog = menu.addAction("📊 İlerleme Detayı (IDM Segment Penceresi)")
        act_prog.triggered.connect(lambda: self._open_progress_dialog(did))

        # Queue reordering options if Queued or Paused
        if status in ("Queued", "Paused"):
            menu_queue = menu.addMenu("📋 Kuyruk Sırası (Öncelik)")
            act_up = menu_queue.addAction("⬆ Kuyrukta Bir Yukarı Taşı (Ctrl+Yukarı)")
            act_up.triggered.connect(lambda: self._move_download_order(did, "up"))
            act_down = menu_queue.addAction("⬇ Kuyrukta Bir Aşağı Taşı (Ctrl+Aşağı)")
            act_down.triggered.connect(lambda: self._move_download_order(did, "down"))
            act_top = menu_queue.addAction("⏫ En Başa Al (Öncelikli)")
            act_top.triggered.connect(lambda: self._move_download_order(did, "top"))
            act_bottom = menu_queue.addAction("⏬ En Sona Gönder")
            act_bottom.triggered.connect(lambda: self._move_download_order(did, "bottom"))

        act_auto_open = menu.addAction("🏁 İndirme Tamamlandığında Otomatik Aç")
        act_auto_open.setCheckable(True)
        act_auto_open.setChecked(bool(rec.get("auto_open", False)))
        act_auto_open.toggled.connect(lambda chk, d=did: self._toggle_download_auto_open(d, chk))

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

        # Bandwidth Priority Submenu (Feature 5)
        curr_prio = (rec.get("priority") or "normal").lower()
        menu_prio = menu.addMenu("⚖️ Bant Genişliği Önceliği")

        act_prio_high = menu_prio.addAction("🚀 Yüksek Öncelik (%70 Hız Payı)")
        act_prio_high.setCheckable(True)
        act_prio_high.setChecked(curr_prio == "high")
        act_prio_high.triggered.connect(lambda: self._set_download_priority(did, "high"))

        act_prio_norm = menu_prio.addAction("⚖️ Normal Öncelik (Dengeli Paylaşım)")
        act_prio_norm.setCheckable(True)
        act_prio_norm.setChecked(curr_prio == "normal")
        act_prio_norm.triggered.connect(lambda: self._set_download_priority(did, "normal"))

        act_prio_low = menu_prio.addAction("🐢 Düşük Öncelik (Arka Plan - %10 Hız Payı)")
        act_prio_low.setCheckable(True)
        act_prio_low.setChecked(curr_prio == "low")
        act_prio_low.triggered.connect(lambda: self._set_download_priority(did, "low"))

        menu.addSeparator()

        if status == "Completed":
            act_open = menu.addAction("📂 Dosyayı Aç")
            act_open.triggered.connect(self._open_selected_file)

            act_checksum = menu.addAction("🛡️ Dosya Bütünlüğünü Doğrula (Hash / Checksum)")
            act_checksum.triggered.connect(lambda: self._open_checksum_dialog(did))

            spath = rec.get("save_path", "")
            if spath and is_archive_file(spath):
                act_extract = menu.addAction("📦 Arşivi Buraya Çıkart")
                act_extract.triggered.connect(lambda: self._extract_selected_archive(did))

        act_folder = menu.addAction("📁 Klasörde Göster")
        act_folder.triggered.connect(self._open_selected_folder)

        act_props = menu.addAction("ℹ️ İndirme Özellikleri (Properties)")
        act_props.triggered.connect(lambda: self._open_properties_dialog(did))

        act_edit_tags = menu.addAction("🏷️ Etiketleri Düzenle...")
        act_edit_tags.triggered.connect(lambda: self._edit_download_tags(did))

        menu_move_queue = menu.addMenu("🗂️ Kuyruğa Taşı")
        for q in self.db.get_all_queues():
            act_mq = menu_move_queue.addAction(f"🗂️ {q['name']}")
            act_mq.triggered.connect(lambda checked, qid=q["id"], d=did: self._move_downloads_to_queue([d], qid))

        if status in ("Paused", "Error", "Cancelled"):
            is_soc = is_stream_url(rec.get("url", ""))
            act_label = "🔗 Manuel Link Gir / Bağlantıyı Yenile" if is_soc else "🔄 Bağlantı Adresini Yenile (Refresh URL)"
            act_refresh = menu.addAction(act_label)
            act_refresh.triggered.connect(lambda: self._show_refresh_url_dialog(did))

        menu.addSeparator()

        act_clean_missing = menu.addAction("🧹 Eksik Dosyaları Listeden Temizle")
        act_clean_missing.triggered.connect(self._clean_missing_files)

        menu.addSeparator()

        act_export = menu.addAction("📤 İndirme Listesini Dışa Aktar (.txt / .json)")
        act_export.triggered.connect(lambda: self._export_downloads_list())

        act_import = menu.addAction("📥 Bağlantıları İçe Aktar (.txt)")
        act_import.triggered.connect(self._import_downloads_list)

        menu.addSeparator()

        act_del = menu.addAction("🗑 Listeden Kaldır (Dosya diskte kalır)")
        act_del.setToolTip("İndirme kaydını listeden kaldırır, dosya bilgisayarınızda korunur (Delete).")
        act_del.triggered.connect(self._delete_selected)

        act_del_all = menu.addAction("💥 Dosya ile Birlikte Tamamen Sil (Diskten sil)")
        act_del_all.setToolTip("İndirme kaydını ve indirilmiş dosyayı kalıcı olarak diskten siler (Shift+Delete).")
        act_del_all.triggered.connect(self._delete_selected_with_files)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _show_refresh_url_dialog(self, download_id: str):
        rec = self.queue_mgr.get_download(download_id)
        if not rec:
            return
        dlg = RefreshUrlDialog(rec, parent=self)
        dlg.url_refreshed.connect(self._on_url_refreshed)
        dlg.exec()

    def _on_url_refreshed(self, download_id: str, new_url: str, new_headers: dict):
        ok = self.queue_mgr.update_download_url(download_id, new_url, new_headers)
        if ok:
            self._load_downloads_to_table()
            reply = QMessageBox.question(
                self,
                "Bağlantı Güncellendi",
                "İndirme adresi başarıyla yenilendi.\n\nİndirme kaldığı yerden şimdi devam ettirilsin mi?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.queue_mgr.resume_download(download_id)
                self._open_progress_dialog(download_id)
        else:
            QMessageBox.critical(self, "Hata", "Bağlantı adresi güncellenemedi.")

    def _clean_missing_files(self):
        """Finds completed downloads whose files no longer exist on disk and offers to remove them from history."""
        all_dls = self.queue_mgr.get_all_downloads()
        missing = []
        for dl in all_dls:
            if dl.get("status") == "Completed":
                spath = dl.get("save_path", "")
                if spath and not os.path.exists(spath):
                    missing.append(dl)

        if not missing:
            QMessageBox.information(self, "Bilgi", "Diskte eksik olan herhangi bir dosya bulunamadı.\nTüm tamamlanmış dosyalar disk üzerinde mevcuttur.")
            return

        sample_names = "\n".join(f"• {m.get('filename')}" for m in missing[:5])
        if len(missing) > 5:
            sample_names += f"\n... ve {len(missing) - 5} adet daha"

        reply = QMessageBox.question(
            self,
            "Eksik Dosyaları Temizle",
            f"Diskte artık bulunamayan {len(missing)} adet tamamlanmış dosya tespit edildi:\n\n{sample_names}\n\nBu kayıtları indirme geçmişinden temizlemek istiyor musunuz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            for m in missing:
                self.queue_mgr.delete_download(m["id"], delete_file=False)
            self._load_downloads_to_table()
            self.statusBar().showMessage(f"🧹 {len(missing)} adet eksik dosya kaydı listeden temizlendi.", 4000)

    def _extract_selected_archive(self, download_id: str):
        rec = self.queue_mgr.get_download(download_id)
        if not rec:
            return
        spath = rec.get("save_path", "")
        if not spath or not os.path.exists(spath):
            QMessageBox.warning(self, "Uyarı", "Arşiv dosyası disk üzerinde bulunamadı.")
            return
        if not is_archive_file(spath):
            QMessageBox.warning(self, "Uyarı", "Seçilen dosya desteklenen bir arşiv formatında (.zip, .tar vb.) değil.")
            return

        self.statusBar().showMessage(f"📦 Arşiv çıkartılıyor: {rec['filename']}...", 5000)
        def _cb(success: bool, msg: str):
            if success:
                self.statusBar().showMessage(f"📦 {rec['filename']} başarıyla çıkartıldı.", 5000)
                QMessageBox.information(self, "Arşiv Çıkartıldı", msg)
            else:
                QMessageBox.warning(self, "Hata", msg)

        extract_archive_async(spath, callback=_cb)

    def _delete_with_file(self, download_id: Optional[str] = None):
        if download_id:
            rec = self.queue_mgr.get_download(download_id)
            records = [rec] if rec else [{"id": download_id, "filename": f"İndirme #{download_id}", "save_path": "", "status": "Unknown"}]
            dlg = DeleteConfirmDialog(records, initial_delete_file=True, parent=self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                del_file = dlg.get_delete_file_choice()
                if del_file is not None:
                    self.queue_mgr.delete_download(download_id, delete_file=del_file)
                    self._load_downloads_to_table()
                    if del_file:
                        self.statusBar().showMessage("💥 İndirme ve dosyası kalıcı olarak silindi.", 4000)
                    else:
                        self.statusBar().showMessage("🗑 İndirme listeden kaldırıldı (dosya diskte korundu).", 4000)
        else:
            self._delete_selected_with_files()

    def _refresh_tags_tree(self):
        if not hasattr(self, "root_tags"):
            return
        while self.root_tags.childCount() > 0:
            self.root_tags.removeChild(self.root_tags.child(0))

        all_tags = self.db.get_all_tags()
        if not all_tags:
            item_none = QTreeWidgetItem(["  (Henüz etiket yok)"])
            item_none.setData(0, Qt.ItemDataRole.UserRole, "")
            self.root_tags.addChild(item_none)
        else:
            for t in all_tags:
                t_item = QTreeWidgetItem([f"🏷️ {t}"])
                t_item.setData(0, Qt.ItemDataRole.UserRole, f"tag:{t}")
                self.root_tags.addChild(t_item)

    def _refresh_queues_tree(self):
        if not hasattr(self, "root_queues"):
            return
        while self.root_queues.childCount() > 0:
            self.root_queues.removeChild(self.root_queues.child(0))

        queues = self.db.get_all_queues()
        for q in queues:
            cnt = len(self.db.get_all_downloads(queue_id=q["id"]))
            item = QTreeWidgetItem([f"🗂️ {q['name']} ({cnt})"])
            item.setData(0, Qt.ItemDataRole.UserRole, f"queue:{q['id']}")
            self.root_queues.addChild(item)

        item_add = QTreeWidgetItem(["  ➕ Yeni Kuyruk Oluştur..."])
        item_add.setData(0, Qt.ItemDataRole.UserRole, "__ADD_QUEUE__")
        self.root_queues.addChild(item_add)

    def _create_new_queue_dialog(self):
        name, ok = QInputDialog.getText(self, "Yeni İndirme Kuyruğu", "Kuyruk Adı:")
        if ok and name.strip():
            self.db.add_queue(name.strip())
            self._refresh_queues_tree()
            self.statusBar().showMessage(f"🗂️ '{name.strip()}' kuyruğu oluşturuldu.", 3500)

    def _delete_queue(self, queue_id: str):
        if queue_id == "default":
            QMessageBox.warning(self, "Uyarı", "Varsayılan 'Ana Kuyruk' silinemez.")
            return
        q_info = self.db.get_queue(queue_id)
        q_name = q_info.get("name", "Kuyruk") if q_info else "Kuyruk"
        reply = QMessageBox.question(
            self,
            "Kuyruğu Sil",
            f"'{q_name}' kuyruğunu silmek istiyor musunuz?\nBu kuyruktaki indirmeler 'Ana Kuyruk' içine aktarılacaktır.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_queue(queue_id)
            self._refresh_queues_tree()
            self._load_downloads_to_table()
            self.statusBar().showMessage(f"Kuyruk silindi: {q_name}", 3500)

    def _move_downloads_to_queue(self, download_ids: List[str], queue_id: str):
        for did in download_ids:
            self.db.move_download_to_queue(did, queue_id)
        q_info = self.db.get_queue(queue_id)
        q_name = q_info.get("name", "Kuyruk") if q_info else "Kuyruk"
        self.statusBar().showMessage(f"{len(download_ids)} indirme '{q_name}' kuyruğuna taşındı.", 3500)
        self._refresh_queues_tree()
        self._load_downloads_to_table()

    def _show_categories_tree_context_menu(self, pos):
        item = self.tree_categories.itemAt(pos)
        if not item:
            return
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if not key:
            return
        if key.startswith("queue:"):
            qid = key[6:]
            q_info = self.db.get_queue(qid)
            q_name = q_info.get("name", "Kuyruk") if q_info else "Kuyruk"

            menu = QMenu(self)
            menu.addAction(f"🗂️ {q_name}").setEnabled(False)
            menu.addSeparator()

            act_start = menu.addAction("▶ Bu Kuyruğu Başlat")
            act_start.triggered.connect(lambda: self.queue_mgr.start_queue(queue_id=qid))

            act_pause = menu.addAction("⏸ Bu Kuyruğu Duraklat")
            act_pause.triggered.connect(lambda: self.queue_mgr.pause_queue(queue_id=qid))

            if qid != "default":
                menu.addSeparator()
                act_del = menu.addAction("🗑️ Bu Kuyruğu Sil")
                act_del.triggered.connect(lambda: self._delete_queue(qid))

            menu.exec(self.tree_categories.viewport().mapToGlobal(pos))
        elif key == "__QUEUES_ROOT__":
            menu = QMenu(self)
            act_add = menu.addAction("➕ Yeni Kuyruk Oluştur...")
            act_add.triggered.connect(self._create_new_queue_dialog)
            menu.exec(self.tree_categories.viewport().mapToGlobal(pos))

    def _on_metered_status_changed(self, is_metered: bool):
        metered_cfg = self.db.get_metered_settings()
        if is_metered and metered_cfg.get("pause_on_metered", True) and not self.queue_mgr.metered_bypass:
            self.btn_metered_stat.show()
            self.statusBar().showMessage("📶 Tarifeli Mobil Bağlantı Algılandı (Kota Koruması Devrede)", 6000)
        else:
            self.btn_metered_stat.hide()

    def _on_metered_blocked(self, download_id: str):
        self.btn_metered_stat.show()
        self.statusBar().showMessage("📶 Tarifeli bağlantı nedeniyle indirmeler bekletildi. Devam etmek için butona tıklayın.", 6000)
        self.tray.showMessage(
            "Tarifeli Ağ Koruması",
            "Mobil veri / Hotspot algılandı. Kota koruması nedeniyle indirmeler bekletildi.",
            QSystemTrayIcon.MessageIcon.Warning,
            4000
        )

    def _on_metered_btn_clicked(self):
        reply = QMessageBox.question(
            self,
            "Tarifeli Ağ Kota Koruması",
            "Şu anda tarifeli bir mobil veri veya hotspot bağlantısındasınız.\n\n"
            "Kota korumasını bu oturum için geçici olarak devre dışı bırakıp indirmeleri devam ettirmek istiyor musunuz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.queue_mgr.set_metered_bypass(True)
            self.btn_metered_stat.hide()
            self.statusBar().showMessage("Kota koruması devre dışı bırakıldı, kuyruk devam ediyor...", 4000)
            self.queue_mgr.start_queue()

    def _edit_download_tags(self, download_id: str):
        rec = self.queue_mgr.get_download(download_id)
        if not rec:
            return
        curr_tags = rec.get("tags") or ""
        new_tags, ok = QInputDialog.getText(
            self,
            "🏷️ İndirme Etiketlerini Düzenle",
            f"'{rec.get('filename', 'Dosya')}' için etiketler (Virgülle ayırın):",
            text=curr_tags
        )
        if ok:
            clean_tags = ", ".join([t.strip() for t in new_tags.split(",") if t.strip()])
            self.db.update_download(download_id, tags=clean_tags)
            self._load_downloads_to_table()
            self._refresh_tags_tree()

    def _edit_bulk_tags(self, download_ids: List[str]):
        new_tags, ok = QInputDialog.getText(
            self,
            "🏷️ Toplu Etiket Ata",
            f"Seçilen {len(download_ids)} indirme için etiketler (Virgülle ayırın):"
        )
        if ok:
            clean_tags = ", ".join([t.strip() for t in new_tags.split(",") if t.strip()])
            for did in download_ids:
                self.db.update_download(did, tags=clean_tags)
            self._load_downloads_to_table()
            self._refresh_tags_tree()

    def _on_category_changed(self, current: QTreeWidgetItem, previous: QTreeWidgetItem):
        if not current:
            return
        key = current.data(0, Qt.ItemDataRole.UserRole)
        if key in ("__TAGS_ROOT__", "__QUEUES_ROOT__"):
            return
        if key == "__ADD_QUEUE__":
            self._create_new_queue_dialog()
            return

        if key and key.startswith("tag:"):
            self.current_tag = key[4:]
            self.current_category = "All"
            self.current_queue_id = None
            downloads = self.db.get_all_downloads(tag=self.current_tag)
        elif key and key.startswith("queue:"):
            self.current_queue_id = key[6:]
            self.current_tag = None
            self.current_category = "All"
            downloads = self.db.get_all_downloads(queue_id=self.current_queue_id)
        else:
            self.current_tag = None
            self.current_queue_id = None
            self.current_category = key or "All"
            if key in ("Downloading", "Completed", "Paused", "Error"):
                downloads = self.db.get_all_downloads(status=key)
            elif key == "All":
                downloads = self.db.get_all_downloads()
            else:
                downloads = self.db.get_all_downloads(category=key)

        self.table.setRowCount(0)
        for dl in downloads:
            self._add_or_update_table_row(dl)
        self._apply_search_and_filter()

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

        # Settings
        suspend_if_active = bool(self.db.get_setting("suspend_power_action_if_active", True))
        idle_threshold = int(self.db.get_setting("active_idle_threshold_seconds", 60))
        show_desktop_notif = bool(self.db.get_setting("power_desktop_notification", True))
        show_browser_notif = bool(self.db.get_setting("power_browser_notification", True))

        # Check if user is actively using the computer right now
        if suspend_if_active and is_user_active(idle_threshold):
            idle_sec = get_idle_duration_seconds()
            reason = f"Aktif bilgisayar kullanımı algılandı (Son etkileşim: {int(idle_sec)} sn önce)"
            logger.info(f"[PowerManager] {reason}. Otomatik {action} işlemi askıya alındı.")

            # Show suspended desktop notification + sound
            if show_desktop_notif:
                notify_power_suspended(action=action, reason=reason, sound=True)

            self.tray.showMessage(
                "Güç Yönetimi (Askıya Alındı)",
                f"Aktif kullanım algılandığı için bilgisayarı {action} eylemi askıya alındı. Açık işleriniz korundu.",
                QSystemTrayIcon.MessageIcon.Information if hasattr(QSystemTrayIcon, "MessageIcon") else 1,
                5000
            )

            # Show dialog already in suspended state so user can resume or execute if they want
            self.power_dialog = PowerCountdownDialog(action=action, total_seconds=30, parent=self)
            self.power_dialog.set_suspended(True, reason=reason)
            self.power_dialog.cancelled.connect(self._cancel_power_countdown)
            self.power_dialog.confirmed.connect(self._execute_power_immediately)
            self.power_dialog.suspend_requested.connect(self._suspend_power_countdown)
            self.power_dialog.resume_requested.connect(self._resume_power_countdown)

            # Put manager in suspended state
            self.power_mgr.start_countdown(action, seconds=30)
            self.power_mgr.suspend(reason=reason)

            self.power_dialog.show()
            self.power_dialog.raise_()
            self.power_dialog.activateWindow()
            return

        # User is away / idle: start countdown
        self.power_dialog = PowerCountdownDialog(action=action, total_seconds=30, parent=self)
        self.power_dialog.cancelled.connect(self._cancel_power_countdown)
        self.power_dialog.confirmed.connect(self._execute_power_immediately)
        self.power_dialog.suspend_requested.connect(self._suspend_power_countdown)
        self.power_dialog.resume_requested.connect(self._resume_power_countdown)

        self.power_mgr.start_countdown(action, seconds=30)

        # 1. Desktop notification + warning chime
        if show_desktop_notif:
            notify_power_countdown(action=action, remaining_seconds=30, sound=True)

        # 2. Browser notification / tab alert
        if show_browser_notif and self.bridge_server:
            open_browser_power_alert(port=self.bridge_server.actual_port, token=self.bridge_server.auth_token or "")

        self.power_dialog.show()
        self.power_dialog.raise_()
        self.power_dialog.activateWindow()

    def _handle_countdown_tick(self, remaining: int, action: str):
        # Auto-suspend during countdown if user starts using the computer
        suspend_if_active = bool(self.db.get_setting("suspend_power_action_if_active", True))
        if suspend_if_active and is_user_active(threshold_seconds=5) and not self.power_mgr.is_suspended:
            reason = "Geri sayım sırasında klavye/fare etkileşimi algılandı"
            self.power_mgr.suspend(reason=reason)
            return

        if self.power_dialog and self.power_dialog.isVisible():
            self.power_dialog.update_countdown(remaining)

    def _handle_countdown_suspended(self, reason: str = ""):
        if self.power_dialog and self.power_dialog.isVisible():
            self.power_dialog.set_suspended(True, reason=reason)
        if bool(self.db.get_setting("power_desktop_notification", True)):
            notify_power_suspended(action=self.current_queue_action, reason=reason, sound=True)
        self.tray.showMessage(
            "Güç Yönetimi",
            f"Kapatma işlemi askıya alındı: {reason}",
            QSystemTrayIcon.MessageIcon.Information if hasattr(QSystemTrayIcon, "MessageIcon") else 1,
            4000
        )

    def _handle_countdown_resumed(self):
        if self.power_dialog and self.power_dialog.isVisible():
            self.power_dialog.set_suspended(False)
        self.tray.showMessage(
            "Güç Yönetimi",
            "Kapatma geri sayımı yeniden başlatıldı.",
            QSystemTrayIcon.MessageIcon.Information if hasattr(QSystemTrayIcon, "MessageIcon") else 1,
            2000
        )

    def _suspend_power_countdown(self):
        self.power_mgr.suspend(reason="Kullanıcı diyalogdan askıya aldı")

    def _resume_power_countdown(self):
        self.power_mgr.resume()

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

    def _on_power_confirm_requested(self, action: str):
        """Countdown reached zero: show an explicit confirmation before acting."""
        from ui.power_countdown_dialog import PowerCountdownDialog
        if PowerCountdownDialog.request_confirmation(action, self):
            self._execute_power_immediately()

    def _move_download_order(self, download_id: str, direction: str):
        if direction == "top":
            self.queue_mgr.move_queue_to_top(download_id)
        elif direction == "bottom":
            self.queue_mgr.move_queue_to_bottom(download_id)
        else:
            self.queue_mgr.reorder_queue(download_id, direction)
        self._load_downloads_to_table()
        row = self._find_row_by_id(download_id)
        if row >= 0:
            self.table.selectRow(row)

    def _move_selected_queue(self, direction: str):
        dids = self._get_selected_download_ids()
        if not dids:
            return
        self._move_download_order(dids[0], direction)

    def _toggle_download_auto_open(self, download_id: str, enabled: bool):
        self.db.update_download(download_id, auto_open=1 if enabled else 0)
        if download_id in self.active_dialogs:
            self.active_dialogs[download_id].chk_auto_open.setChecked(enabled)

    def _update_disk_space_ui(self):
        default_dir = self.db.get_setting("default_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
        free_bytes, total_bytes, drive = get_disk_total_and_free(default_dir)
        if free_bytes >= 0:
            self.lbl_disk_stat.setText(f"💾 {drive}: {format_size(free_bytes)} Boş")
            if free_bytes < 1024 * 1024 * 1024:  # < 1 GB
                self.lbl_disk_stat.setStyleSheet(f"color: {T['danger']}; font-weight: bold; margin-left: 15px;")
            else:
                self.lbl_disk_stat.setStyleSheet(f"color: {T['color_cyan']}; font-weight: bold; margin-left: 15px;")
        else:
            self.lbl_disk_stat.setText("💾 Disk: Bilgi alınamadı")
            self.lbl_disk_stat.setStyleSheet(f"color: {T['color_orange']}; font-weight: bold; margin-left: 15px;")

    def _show_statistics_dialog(self):
        default_dir = self.db.get_setting("default_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
        dlg = StatisticsDialog(self.db, default_download_dir=default_dir, parent=self)
        dlg.exec()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        urls = []
        if event.mimeData().hasUrls():
            for u in event.mimeData().urls():
                if u.isLocalFile():
                    local_p = u.toLocalFile()
                    if local_p.lower().endswith(('.txt', '.json', '.m3u', '.m3u8', '.list')):
                        try:
                            with open(local_p, 'r', encoding='utf-8', errors='ignore') as f:
                                extracted = extract_valid_urls(f.read())
                                urls.extend(extracted)
                        except Exception as e:
                            logger.warning(f"Sürüklenen dosya okunamadı ({local_p}): {e}")
                            self.statusBar().showMessage(f"❌ Dosya okunamadı: {os.path.basename(local_p)}", 4000)
                else:
                    s = u.toString().strip()
                    if s.startswith(('http://', 'https://')):
                        urls.append(s)

        if event.mimeData().hasText():
            text = event.mimeData().text()
            extracted = extract_valid_urls(text)
            for eu in extracted:
                if eu not in urls:
                    urls.append(eu)

        if len(urls) == 1:
            event.acceptProposedAction()
            self._show_add_dialog(initial_url=urls[0])
        elif len(urls) > 1:
            event.acceptProposedAction()
            self._show_batch_add_dialog(initial_text="\n".join(urls))

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
            self.lbl_scheduler_stat.setStyleSheet(f"color: {T['text_secondary']}; font-weight: bold; margin-left: 20px;")
        elif info["is_in_window"]:
            txt = f"⏱ Zamanlayıcı: {info['state_text']} (Kalan: {info['time_remaining_str']})"
            self.lbl_scheduler_stat.setText(txt)
            self.lbl_scheduler_stat.setStyleSheet(f"color: {T['success']}; font-weight: bold; margin-left: 20px;")
        else:
            txt = f"⏱ Zamanlayıcı: {info['state_text']} (Kalan: {info['time_remaining_str']})"
            self.lbl_scheduler_stat.setText(txt)
            self.lbl_scheduler_stat.setStyleSheet(f"color: {T['warning']}; font-weight: bold; margin-left: 20px;")

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
            self.lbl_tb_sched_badge.setStyleSheet(f"font-weight: bold; color: {T['text_secondary']}; min-width: 60px;")
        elif info.get("is_in_window"):
            self.lbl_tb_sched_badge.setText("İndiriliyor")
            self.lbl_tb_sched_badge.setStyleSheet(f"font-weight: bold; color: {T['success']}; min-width: 60px;")
        else:
            self.lbl_tb_sched_badge.setText("Beklemede")
            self.lbl_tb_sched_badge.setStyleSheet(f"font-weight: bold; color: {T['warning']}; min-width: 60px;")

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
        self.power_dialog.confirmed.connect(self._execute_power_immediately)
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
        try:
            self.queue_manager.flush_progress()
        except Exception:
            pass
        self.scheduler.stop()
        self.power_mgr.cancel()
        self.tray.hide()
        try:
            self.db.close()
        except Exception:
            pass
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
            try:
                self.queue_manager.flush_progress()
            except Exception:
                pass
            self.scheduler.stop()
            self.power_mgr.cancel()
            self.tray.hide()
            try:
                self.db.close()
            except Exception:
                pass
            event.accept()
