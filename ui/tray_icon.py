from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QActionGroup
from PyQt6.QtCore import pyqtSignal
from core.notifier import notify_download_completed, notify_error, notify_warning

import os
from core.paths import get_icon_path

def create_default_icon() -> QIcon:
    """Generate or load icon for tray and window."""
    icon_file = get_icon_path()
    if icon_file and os.path.isfile(icon_file):
        icon = QIcon(icon_file)
        if not icon.isNull():
            return icon

    pix = QPixmap(64, 64)
    pix.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Rounded blue background
    painter.setBrush(QColor("#3d59a1"))
    painter.setPen(QColor("#7aa2f7"))
    painter.drawRoundedRect(4, 4, 56, 56, 12, 12)

    # Down arrow
    painter.setBrush(QColor("#ffffff"))
    painter.setPen(QColor("#ffffff"))
    # Arrow stem
    painter.drawRect(26, 14, 12, 18)
    # Arrow head points
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QPolygon
    points = QPolygon([
        QPoint(18, 32),
        QPoint(46, 32),
        QPoint(32, 48)
    ])
    painter.drawPolygon(points)
    painter.end()
    return QIcon(pix)

class TrayIcon(QSystemTrayIcon):
    show_window_requested = pyqtSignal()
    start_all_requested = pyqtSignal()
    pause_all_requested = pyqtSignal()
    speed_limit_requested = pyqtSignal(int)  # 0 for unlimited, or kb value
    queue_action_changed = pyqtSignal(str)   # "none", "shutdown", "sleep"
    scheduler_requested = pyqtSignal()
    scheduler_toggle_requested = pyqtSignal(bool)
    playlist_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, current_queue_action: str = "none", parent=None):
        super().__init__(parent)
        self.current_queue_action = current_queue_action
        self.scheduler_enabled = False
        self.setIcon(create_default_icon())
        self.setToolTip("RipSync - Download Manager")
        self._init_menu()
        self.activated.connect(self._on_activated)

    def _init_menu(self):
        menu = QMenu()
        act_show = menu.addAction("Göster / Gizle")
        act_show.triggered.connect(self.show_window_requested.emit)

        menu.addSeparator()
        act_playlist = menu.addAction("📑 Oynatma Listesi İndir...")
        act_playlist.triggered.connect(self.playlist_requested.emit)

        menu.addSeparator()
        act_start = menu.addAction("▶ Kuyruğu Başlat")
        act_start.triggered.connect(self.start_all_requested.emit)

        act_pause = menu.addAction("⏸ Tümünü Duraklat")
        act_pause.triggered.connect(self.pause_all_requested.emit)

        # Scheduler submenu in tray
        self.menu_scheduler = menu.addMenu("⏱ Zamanlayıcı (Scheduler)")
        self.act_sched_toggle = self.menu_scheduler.addAction("Zamanlayıcıyı Etkinleştir")
        self.act_sched_toggle.setCheckable(True)
        self.act_sched_toggle.toggled.connect(self.scheduler_toggle_requested.emit)

        act_sched_settings = self.menu_scheduler.addAction("Planlama & Zamanlayıcı Ayarları...")
        act_sched_settings.triggered.connect(self.scheduler_requested.emit)

        # Speed limiter in tray
        menu_limiter = menu.addMenu("⚡ Hız Sınırı (Speed Limiter)")
        act_unlimit = menu_limiter.addAction("🚀 Tam Hız (Sınırsız)")
        act_unlimit.triggered.connect(lambda: self.speed_limit_requested.emit(0))
        menu_limiter.addSeparator()
        for label, kb_val in [
            ("512 KB/s", 512),
            ("1 MB/s", 1024),
            ("2 MB/s", 2048),
            ("5 MB/s (Önerilen)", 5120),
            ("10 MB/s", 10240),
            ("25 MB/s", 25600),
        ]:
            act_preset = menu_limiter.addAction(f"⏱ {label}")
            act_preset.triggered.connect(lambda checked, k=kb_val: self.speed_limit_requested.emit(k))

        # Queue completion action submenu
        self.menu_queue_action = menu.addMenu("⚙ Kuyruk Bittiğinde")
        self.queue_action_group = QActionGroup(self)
        self.queue_action_group.setExclusive(True)

        self.act_qa_none = self.menu_queue_action.addAction("Doğrudan Bitir (Eylem Yok)")
        self.act_qa_none.setCheckable(True)
        self.queue_action_group.addAction(self.act_qa_none)
        self.act_qa_none.triggered.connect(lambda: self._set_queue_action("none"))

        self.act_qa_shutdown = self.menu_queue_action.addAction("🛑 Bilgisayarı Kapat")
        self.act_qa_shutdown.setCheckable(True)
        self.queue_action_group.addAction(self.act_qa_shutdown)
        self.act_qa_shutdown.triggered.connect(lambda: self._set_queue_action("shutdown"))

        self.act_qa_sleep = self.menu_queue_action.addAction("🌙 Uyku Moduna Al")
        self.act_qa_sleep.setCheckable(True)
        self.queue_action_group.addAction(self.act_qa_sleep)
        self.act_qa_sleep.triggered.connect(lambda: self._set_queue_action("sleep"))

        self.update_queue_action_ui(self.current_queue_action)

        menu.addSeparator()
        act_quit = menu.addAction("Çıkış")
        act_quit.triggered.connect(self.quit_requested.emit)

        self.setContextMenu(menu)

    def update_scheduler_ui(self, enabled: bool, status_text: str = ""):
        self.scheduler_enabled = enabled
        self.act_sched_toggle.blockSignals(True)
        self.act_sched_toggle.setChecked(enabled)
        self.act_sched_toggle.blockSignals(False)
        tip = f"RipSync - Download Manager\n⏱ Zamanlayıcı: {status_text or ('Aktif' if enabled else 'Kapalı')}"
        self.setToolTip(tip[:127])


    def _set_queue_action(self, action: str):
        self.update_queue_action_ui(action)
        self.queue_action_changed.emit(action)

    def update_queue_action_ui(self, action: str):
        self.current_queue_action = action
        if action == "shutdown":
            self.act_qa_shutdown.setChecked(True)
        elif action == "sleep":
            self.act_qa_sleep.setChecked(True)
        else:
            self.act_qa_none.setChecked(True)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window_requested.emit()

    def notify_completed(self, filename: str, save_path: str = "", is_video: bool = False):
        # 1. Native Windows 10/11 Toast Notification with "Klasörde Göster" action
        notify_download_completed(filename, save_path=save_path, is_video=is_video)

        # 2. System Tray message balloon as secondary fallback / tray indicator
        title = "Video başarıyla indirildi" if is_video else "İndirme Tamamlandı"
        self.showMessage(
            title,
            f"{filename} başarıyla indirildi.",
            QSystemTrayIcon.MessageIcon.Information,
            3000
        )

    def notify_error(self, title: str, message: str):
        # 1. Native Windows 10/11 Toast + sound
        notify_error(title, message)

        # 2. System Tray critical balloon
        self.showMessage(
            f"❌ {title}",
            message[:150],
            QSystemTrayIcon.MessageIcon.Critical,
            4000
        )

    def notify_warning(self, title: str, message: str):
        # 1. Native Windows 10/11 Toast
        notify_warning(title, message)

        # 2. System Tray warning balloon
        self.showMessage(
            f"⚠️ {title}",
            message[:150],
            QSystemTrayIcon.MessageIcon.Warning,
            3500
        )

