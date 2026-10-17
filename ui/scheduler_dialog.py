import os
from typing import Dict, Any, List, Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QGroupBox, QComboBox,
    QSpinBox, QTimeEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QTabWidget, QWidget, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt, QTime, QTimer, pyqtSignal

from core.database import Database
from core.queue_manager import QueueManager
from core.scheduler import DownloadScheduler, DAY_NAMES_TR, parse_time_str
from ui.styles import format_size, T

class SchedulerDialog(QDialog):
    queue_started = pyqtSignal()
    queue_paused = pyqtSignal()

    def __init__(self, db: Database, queue_mgr: QueueManager, scheduler: DownloadScheduler, parent=None):
        super().__init__(parent)
        self.db = db
        self.queue_mgr = queue_mgr
        self.scheduler = scheduler

        self.setWindowTitle("RipSync - Zamanlayıcı ve İndirme Kuyruğu Planlama")
        self.resize(680, 560)
        self.setMinimumSize(620, 520)

        self.day_checkboxes: List[QCheckBox] = []

        self._init_ui()
        self._load_settings()
        self._refresh_queued_table()

        # Timer to refresh live countdown status and table
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(1000)
        self.status_timer.timeout.connect(self._update_live_status)
        self.status_timer.start()
        self._update_live_status()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(18, 16, 18, 16)

        # Header Title Banner
        header = QFrame()
        header.setStyleSheet(f"background-color: {T['bg_panel']}; border: 1px solid {T['bg_hover']}; border-radius: 8px; padding: 10px;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 6, 10, 6)

        lbl_icon = QLabel("⏱")
        lbl_icon.setStyleSheet("font-size: 26px;")
        h_layout.addWidget(lbl_icon)

        title_box = QVBoxLayout()
        lbl_title = QLabel("Zamanlayıcı & Sıralı İndirme Kuyruğu")
        lbl_title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {T['accent']};")
        lbl_desc = QLabel("Gece indirmelerini otomatik başlatıp durdurun, sıralı indirme limitini ve önceliklerini yönetin.")
        lbl_desc.setStyleSheet(f"color: {T['text_muted']}; font-size: 12px;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_desc)
        h_layout.addLayout(title_box)
        h_layout.addStretch()

        main_layout.addWidget(header)

        # Tabs: Tab 1: Zamanlayıcı (Scheduler), Tab 2: Sıralı İndirme & Kuyruk (Queue)
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        tab_schedule = QWidget()
        self._init_schedule_tab(tab_schedule)
        self.tabs.addTab(tab_schedule, "🕒 Zamanlayıcı & Gece İndirmesi")

        tab_queue = QWidget()
        self._init_queue_tab(tab_queue)
        self.tabs.addTab(tab_queue, "📋 Sıralı İndirme & Kuyruk Sırası")

        # Live Status Bar at bottom of dialog
        self.status_frame = QFrame()
        self.status_frame.setStyleSheet(f"background-color: {T['bg_card']}; border: 1px solid {T['border']}; border-radius: 6px; padding: 8px;")
        sf_layout = QHBoxLayout(self.status_frame)
        sf_layout.setContentsMargins(10, 6, 10, 6)

        self.lbl_live_status = QLabel("Zamanlayıcı Durumu: Bekleniyor...")
        self.lbl_live_status.setStyleSheet(f"font-weight: bold; color: {T['accent']}; font-size: 13px;")
        sf_layout.addWidget(self.lbl_live_status)

        sf_layout.addStretch()

        self.lbl_countdown = QLabel("--")
        self.lbl_countdown.setStyleSheet(f"font-weight: bold; color: {T['color_orange']}; font-size: 13px;")
        sf_layout.addWidget(self.lbl_countdown)

        main_layout.addWidget(self.status_frame)

        # Action Buttons
        btn_layout = QHBoxLayout()

        self.btn_start_queue = QPushButton("⚡ Şimdi Kuyruğu Başlat")
        self.btn_start_queue.setStyleSheet(f"background-color: {T['color_sky']}; color: {T['bg_main']}; font-weight: bold; padding: 7px 14px;")
        self.btn_start_queue.clicked.connect(self._start_queue_now)
        btn_layout.addWidget(self.btn_start_queue)

        self.btn_pause_queue = QPushButton("⏸ Kuyruğu Durdur")
        self.btn_pause_queue.setObjectName("btn_secondary")
        self.btn_pause_queue.clicked.connect(self._pause_queue_now)
        btn_layout.addWidget(self.btn_pause_queue)

        btn_layout.addStretch()

        btn_save = QPushButton("Kaydet ve Kapat")
        btn_save.clicked.connect(self._save_and_close)
        btn_layout.addWidget(btn_save)

        btn_cancel = QPushButton("İptal")
        btn_cancel.setObjectName("btn_secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        main_layout.addLayout(btn_layout)

    def _init_schedule_tab(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setSpacing(12)
        layout.setContentsMargins(14, 14, 14, 14)

        # Master Checkbox
        self.chk_enable_scheduler = QCheckBox("Zamanlayıcıyı Etkinleştir (Otomatik Başlatma / Durdurma)")
        self.chk_enable_scheduler.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {T['success']};")
        self.chk_enable_scheduler.toggled.connect(self._on_scheduler_toggled)
        layout.addWidget(self.chk_enable_scheduler)

        # Time Group
        self.grp_times = QGroupBox("İndirme Zaman Aralığı")
        t_layout = QVBoxLayout(self.grp_times)
        t_layout.setSpacing(10)

        # Start Time Row
        row_start = QHBoxLayout()
        self.chk_start = QCheckBox("İndirmeyi Belirlenen Saatte Başlat:")
        self.chk_start.setChecked(True)
        self.chk_start.setEnabled(False)  # Start time is always required when scheduler is on
        row_start.addWidget(self.chk_start)

        self.time_start = QTimeEdit()
        self.time_start.setDisplayFormat("HH:mm")
        self.time_start.setTime(QTime(2, 0))
        self.time_start.setFixedWidth(80)
        row_start.addWidget(self.time_start)

        lbl_s_info = QLabel("(Örn. Gece 02:00)")
        lbl_s_info.setStyleSheet(f"color: {T['text_secondary']}; font-size: 11px;")
        row_start.addWidget(lbl_s_info)
        row_start.addStretch()
        t_layout.addLayout(row_start)

        # Stop Time Row
        row_stop = QHBoxLayout()
        self.chk_stop = QCheckBox("İndirmeyi Belirlenen Saatte Durdur:")
        self.chk_stop.setChecked(True)
        self.chk_stop.toggled.connect(lambda chk: self.time_stop.setEnabled(chk))
        row_stop.addWidget(self.chk_stop)

        self.time_stop = QTimeEdit()
        self.time_stop.setDisplayFormat("HH:mm")
        self.time_stop.setTime(QTime(7, 0))
        self.time_stop.setFixedWidth(80)
        row_stop.addWidget(self.time_stop)

        lbl_e_info = QLabel("(Örn. Sabah 07:00)")
        lbl_e_info.setStyleSheet(f"color: {T['text_secondary']}; font-size: 11px;")
        row_stop.addWidget(lbl_e_info)
        row_stop.addStretch()
        t_layout.addLayout(row_stop)

        # Quick Presets Buttons Row
        preset_row = QHBoxLayout()
        lbl_pr = QLabel("Hızlı Şablonlar:")
        lbl_pr.setStyleSheet(f"color: {T['text_secondary']}; font-size: 11px;")
        preset_row.addWidget(lbl_pr)

        btn_night = QPushButton("🌙 Gece İndirmesi (02:00 - 07:00)")
        btn_night.setObjectName("btn_secondary")
        btn_night.clicked.connect(lambda: self._set_preset_time(2, 0, 7, 0))
        preset_row.addWidget(btn_night)

        btn_midnight = QPushButton("⭐ Gece Yarısı (00:00 - 06:00)")
        btn_midnight.setObjectName("btn_secondary")
        btn_midnight.clicked.connect(lambda: self._set_preset_time(0, 0, 6, 0))
        preset_row.addWidget(btn_midnight)

        btn_offhours = QPushButton("🏢 Mesai Dışı (19:00 - 08:00)")
        btn_offhours.setObjectName("btn_secondary")
        btn_offhours.clicked.connect(lambda: self._set_preset_time(19, 0, 8, 0))
        preset_row.addWidget(btn_offhours)

        preset_row.addStretch()
        t_layout.addLayout(preset_row)

        layout.addWidget(self.grp_times)

        # Days of Week Group
        self.grp_days = QGroupBox("Tekrarlama Günleri")
        d_layout = QVBoxLayout(self.grp_days)

        days_box = QHBoxLayout()
        self.day_checkboxes = []
        for day_idx in range(7):
            name = DAY_NAMES_TR[day_idx]
            chk = QCheckBox(name)
            chk.setChecked(True)
            self.day_checkboxes.append(chk)
            days_box.addWidget(chk)
        d_layout.addLayout(days_box)

        # Days helper buttons
        days_btn_row = QHBoxLayout()
        btn_all_days = QPushButton("Her Gün")
        btn_all_days.setObjectName("btn_secondary")
        btn_all_days.setFixedHeight(24)
        btn_all_days.clicked.connect(lambda: self._set_days_filter([0, 1, 2, 3, 4, 5, 6]))
        days_btn_row.addWidget(btn_all_days)

        btn_weekdays = QPushButton("Hafta İçi (Pzt-Cum)")
        btn_weekdays.setObjectName("btn_secondary")
        btn_weekdays.setFixedHeight(24)
        btn_weekdays.clicked.connect(lambda: self._set_days_filter([0, 1, 2, 3, 4]))
        days_btn_row.addWidget(btn_weekdays)

        btn_weekends = QPushButton("Hafta Sonu (Cts-Paz)")
        btn_weekends.setObjectName("btn_secondary")
        btn_weekends.setFixedHeight(24)
        btn_weekends.clicked.connect(lambda: self._set_days_filter([5, 6]))
        days_btn_row.addWidget(btn_weekends)

        days_btn_row.addStretch()
        d_layout.addLayout(days_btn_row)

        layout.addWidget(self.grp_days)

        # On Stop Action Group
        self.grp_actions = QGroupBox("Zamanlayıcı Durduğunda (Sabah Eylemi)")
        a_layout = QHBoxLayout(self.grp_actions)

        lbl_act = QLabel("Bitiş saatine ulaşıldığında:")
        a_layout.addWidget(lbl_act)

        self.combo_stop_action = QComboBox()
        self.combo_stop_action.addItem("⏸ Tüm İndirmeleri Duraklat (Uygulama Açık Kalsın)", "pause_all")
        self.combo_stop_action.addItem("🛑 Tümünü Duraklat ve Bilgisayarı Kapat (Shutdown)", "shutdown")
        self.combo_stop_action.addItem("🌙 Tümünü Duraklat ve Uyku Moduna Al (Sleep)", "sleep")
        self.combo_stop_action.addItem("❌ Eylem Yok (İndirme devam etsin)", "none")
        self.combo_stop_action.setMinimumWidth(320)
        a_layout.addWidget(self.combo_stop_action)
        a_layout.addStretch()

        layout.addWidget(self.grp_actions)

        # Speed Schedule Throttling Group
        self.grp_speed_schedule = QGroupBox("⚡ Akıllı Hız Limiti Zamanlaması (Gündüz Sınırla / Gece Tam Hız)")
        ss_layout = QVBoxLayout(self.grp_speed_schedule)

        self.chk_enable_speed_schedule = QCheckBox("Belirli saatlerde hız limiti uygula (Diğer saatlerde sınırsız tam hız)")
        self.chk_enable_speed_schedule.setStyleSheet(f"font-weight: bold; color: {T['color_sky']};")
        self.chk_enable_speed_schedule.toggled.connect(self._on_speed_schedule_toggled)
        ss_layout.addWidget(self.chk_enable_speed_schedule)

        row_ss = QHBoxLayout()
        row_ss.addWidget(QLabel("Saat Aralığı:"))
        self.time_speed_start = QTimeEdit(QTime(9, 0))
        self.time_speed_start.setDisplayFormat("HH:mm")
        self.time_speed_start.setFixedWidth(75)
        row_ss.addWidget(self.time_speed_start)

        row_ss.addWidget(QLabel("-"))
        self.time_speed_end = QTimeEdit(QTime(18, 0))
        self.time_speed_end.setDisplayFormat("HH:mm")
        self.time_speed_end.setFixedWidth(75)
        row_ss.addWidget(self.time_speed_end)

        row_ss.addWidget(QLabel("Hız Limiti:"))
        self.combo_speed_schedule_limit = QComboBox()
        for label, val in [
            ("512 KB/s", 512),
            ("1 MB/s", 1024),
            ("2 MB/s (Önerilen)", 2048),
            ("5 MB/s", 5120),
            ("10 MB/s", 10240),
            ("25 MB/s", 25600)
        ]:
            self.combo_speed_schedule_limit.addItem(label, val)
        self.combo_speed_schedule_limit.setCurrentIndex(2)
        row_ss.addWidget(self.combo_speed_schedule_limit)
        row_ss.addStretch()
        ss_layout.addLayout(row_ss)

        lbl_ss_note = QLabel("💡 Belirlenen saatlerde (ör. 09:00 - 18:00) hız sınırı otomatik devreye girer; bu saatler dışında indirmeler tam hızda çalışır.")
        lbl_ss_note.setStyleSheet(f"color: {T['text_secondary']}; font-size: 11px;")
        ss_layout.addWidget(lbl_ss_note)

        layout.addWidget(self.grp_speed_schedule)
        layout.addStretch()

    def _on_speed_schedule_toggled(self, checked: bool):
        self.time_speed_start.setEnabled(checked)
        self.time_speed_end.setEnabled(checked)
        self.combo_speed_schedule_limit.setEnabled(checked)

    def _init_queue_tab(self, parent: QWidget):
        layout = QVBoxLayout(parent)
        layout.setSpacing(12)
        layout.setContentsMargins(14, 14, 14, 14)

        # Concurrency Limit Group
        grp_conc = QGroupBox("Sıralı İndirme Kapasitesi")
        c_layout = QVBoxLayout(grp_conc)

        row_c = QHBoxLayout()
        lbl_c = QLabel("Aynı anda kaç dosya indirilsin (Eşzamanlı Limit):")
        lbl_c.setStyleSheet(f"font-weight: bold; color: {T['accent']};")
        row_c.addWidget(lbl_c)

        self.spin_concurrent = QSpinBox()
        self.spin_concurrent.setRange(1, 10)
        self.spin_concurrent.setValue(2)
        self.spin_concurrent.setSuffix(" Dosya")
        self.spin_concurrent.setFixedWidth(110)
        row_c.addWidget(self.spin_concurrent)

        row_c.addStretch()
        c_layout.addLayout(row_c)

        lbl_conc_help = QLabel(
            "💡 Mantık: Örneğin 2 seçildiğinde, kuyruktan aynı anda en fazla 2 dosya indirilir.\n"
            "Dosyalardan biri tamamlandığında, duraklatıldığında veya hata verdiğinde sıradaki dosya otomatik olarak başlar."
        )
        lbl_conc_help.setStyleSheet(f"color: {T['text_secondary']}; font-size: 11px;")
        c_layout.addWidget(lbl_conc_help)

        layout.addWidget(grp_conc)

        # Queue Order Table Group
        grp_table = QGroupBox("Kuyruk Sıralaması (İndirme Önceliği)")
        t_layout = QHBoxLayout(grp_table)

        self.table_queued = QTableWidget()
        self.table_queued.setColumnCount(4)
        self.table_queued.setHorizontalHeaderLabels(["Sıra", "Dosya Adı", "Boyut", "Durum"])
        self.table_queued.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_queued.setColumnWidth(0, 50)
        self.table_queued.setColumnWidth(2, 90)
        self.table_queued.setColumnWidth(3, 90)
        self.table_queued.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_queued.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t_layout.addWidget(self.table_queued)

        # Side reordering buttons
        btn_box = QVBoxLayout()
        btn_box.setSpacing(8)

        self.btn_move_up = QPushButton("⬆ Yukarı")
        self.btn_move_up.setObjectName("btn_secondary")
        self.btn_move_up.clicked.connect(self._move_selected_up)
        btn_box.addWidget(self.btn_move_up)

        self.btn_move_down = QPushButton("⬇ Aşağı")
        self.btn_move_down.setObjectName("btn_secondary")
        self.btn_move_down.clicked.connect(self._move_selected_down)
        btn_box.addWidget(self.btn_move_down)

        self.btn_move_top = QPushButton("⚡ Başa Al")
        self.btn_move_top.setObjectName("btn_secondary")
        self.btn_move_top.clicked.connect(self._move_selected_top)
        btn_box.addWidget(self.btn_move_top)

        btn_box.addStretch()

        btn_refresh = QPushButton("🔄 Yenile")
        btn_refresh.setObjectName("btn_secondary")
        btn_refresh.clicked.connect(self._refresh_queued_table)
        btn_box.addWidget(btn_refresh)

        t_layout.addLayout(btn_box)

        layout.addWidget(grp_table)

    def _set_preset_time(self, s_h: int, s_m: int, e_h: int, e_m: int):
        self.time_start.setTime(QTime(s_h, s_m))
        self.time_stop.setTime(QTime(e_h, e_m))
        self.chk_stop.setChecked(True)

    def _set_days_filter(self, active_days: List[int]):
        for idx, chk in enumerate(self.day_checkboxes):
            chk.setChecked(idx in active_days)

    def _on_scheduler_toggled(self, checked: bool):
        self.grp_times.setEnabled(checked)
        self.grp_days.setEnabled(checked)
        self.grp_actions.setEnabled(checked)

    def _load_settings(self):
        # Load scheduler settings
        sched = self.db.get_scheduler_settings()
        self.chk_enable_scheduler.setChecked(bool(sched.get("enabled", False)))
        self._on_scheduler_toggled(bool(sched.get("enabled", False)))

        start_str = sched.get("start_time", "02:00")
        st = parse_time_str(start_str)
        self.time_start.setTime(QTime(st.hour, st.minute))

        stop_str = sched.get("stop_time", "07:00")
        et = parse_time_str(stop_str)
        self.time_stop.setTime(QTime(et.hour, et.minute))

        stop_en = sched.get("stop_enabled", True)
        self.chk_stop.setChecked(bool(stop_en))
        self.time_stop.setEnabled(bool(stop_en))

        days = sched.get("days", [0, 1, 2, 3, 4, 5, 6])
        for idx, chk in enumerate(self.day_checkboxes):
            chk.setChecked(idx in days)

        act = sched.get("on_stop_action", "pause_all")
        idx_act = self.combo_stop_action.findData(act)
        if idx_act >= 0:
            self.combo_stop_action.setCurrentIndex(idx_act)

        # Load speed schedule settings
        ss_en = sched.get("speed_schedule_enabled", False)
        self.chk_enable_speed_schedule.setChecked(bool(ss_en))
        self._on_speed_schedule_toggled(bool(ss_en))

        ss_start = parse_time_str(sched.get("speed_schedule_start", "09:00"))
        self.time_speed_start.setTime(QTime(ss_start.hour, ss_start.minute))

        ss_end = parse_time_str(sched.get("speed_schedule_end", "18:00"))
        self.time_speed_end.setTime(QTime(ss_end.hour, ss_end.minute))

        ss_limit = sched.get("speed_schedule_limit_kb", 2048)
        idx_ss = self.combo_speed_schedule_limit.findData(int(ss_limit))
        if idx_ss >= 0:
            self.combo_speed_schedule_limit.setCurrentIndex(idx_ss)

        # Load concurrency settings
        max_c = self.db.get_setting("max_concurrent", 2)
        self.spin_concurrent.setValue(int(max_c))

    def _save_and_close(self):
        # Build days list
        active_days = [i for i, chk in enumerate(self.day_checkboxes) if chk.isChecked()]
        if not active_days:
            QMessageBox.warning(self, "Uyarı", "Lütfen en az bir gün seçin.")
            return

        start_str = self.time_start.time().toString("HH:mm")
        stop_str = self.time_stop.time().toString("HH:mm")
        enabled = self.chk_enable_scheduler.isChecked()
        stop_en = self.chk_stop.isChecked()
        action = self.combo_stop_action.currentData() or "pause_all"
        max_concurrent = self.spin_concurrent.value()

        # Speed schedule values
        speed_schedule_enabled = self.chk_enable_speed_schedule.isChecked()
        speed_schedule_start = self.time_speed_start.time().toString("HH:mm")
        speed_schedule_end = self.time_speed_end.time().toString("HH:mm")
        speed_schedule_limit_kb = self.combo_speed_schedule_limit.currentData() or 2048

        sched_settings = {
            "enabled": enabled,
            "start_time": start_str,
            "stop_enabled": stop_en,
            "stop_time": stop_str,
            "days": active_days,
            "on_stop_action": action,
            "auto_start_if_in_window": True,
            "speed_schedule_enabled": speed_schedule_enabled,
            "speed_schedule_start": speed_schedule_start,
            "speed_schedule_end": speed_schedule_end,
            "speed_schedule_limit_kb": speed_schedule_limit_kb
        }

        # Save to database
        self.db.save_scheduler_settings(sched_settings)
        self.db.set_setting("max_concurrent", max_concurrent)

        # Apply to live scheduler & queue manager
        self.scheduler.update_config(**sched_settings)
        self.queue_mgr.set_max_concurrent(max_concurrent)

        self.accept()

    def _refresh_queued_table(self):
        queued = self.db.get_queued_downloads_ordered()
        self.table_queued.setRowCount(0)
        for i, dl in enumerate(queued, start=1):
            row = self.table_queued.rowCount()
            self.table_queued.insertRow(row)

            item_num = QTableWidgetItem(f"#{i}")
            item_num.setData(Qt.ItemDataRole.UserRole, dl["id"])
            item_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_queued.setItem(row, 0, item_num)

            item_name = QTableWidgetItem(dl.get("filename", "download"))
            self.table_queued.setItem(row, 1, item_name)

            tot = dl.get("total_size", -1)
            item_size = QTableWidgetItem(format_size(tot))
            item_size.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table_queued.setItem(row, 2, item_size)

            item_status = QTableWidgetItem("Kuyrukta (Sırada)")
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_queued.setItem(row, 3, item_status)

    def _get_selected_queued_id(self) -> Optional[str]:
        items = self.table_queued.selectedItems()
        if not items:
            return None
        row = items[0].row()
        item = self.table_queued.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _move_selected_up(self):
        did = self._get_selected_queued_id()
        if did:
            row = self.table_queued.currentRow()
            if self.queue_mgr.reorder_queue(did, "up"):
                self._refresh_queued_table()
                new_row = max(0, row - 1)
                self.table_queued.selectRow(new_row)

    def _move_selected_down(self):
        did = self._get_selected_queued_id()
        if did:
            row = self.table_queued.currentRow()
            if self.queue_mgr.reorder_queue(did, "down"):
                self._refresh_queued_table()
                new_row = min(self.table_queued.rowCount() - 1, row + 1)
                self.table_queued.selectRow(new_row)

    def _move_selected_top(self):
        did = self._get_selected_queued_id()
        if did:
            if self.queue_mgr.move_queue_to_top(did):
                self._refresh_queued_table()
                self.table_queued.selectRow(0)

    def _start_queue_now(self):
        self.queue_mgr.start_queue()
        self.queue_started.emit()
        self._refresh_queued_table()

    def _pause_queue_now(self):
        self.queue_mgr.pause_queue()
        self.queue_paused.emit()
        self._refresh_queued_table()

    def _update_live_status(self):
        status = self.scheduler.get_status()
        if not status["enabled"]:
            self.lbl_live_status.setText("⏱ Zamanlayıcı: Devre Dışı")
            self.lbl_live_status.setStyleSheet(f"color: {T['text_secondary']}; font-weight: bold;")
            self.lbl_countdown.setText("Kapalı")
            self.lbl_countdown.setStyleSheet(f"color: {T['text_secondary']}; font-weight: bold;")
        elif status["is_in_window"]:
            self.lbl_live_status.setText(f"🟢 Zamanlayıcı Aktif ({status['state_text']})")
            self.lbl_live_status.setStyleSheet(f"color: {T['success']}; font-weight: bold;")
            self.lbl_countdown.setText(f"⏳ Kalan Süre: {status['time_remaining_str']}")
            self.lbl_countdown.setStyleSheet(f"color: {T['color_sky']}; font-weight: bold;")
        else:
            self.lbl_live_status.setText(f"🟡 Zamanlayıcı Beklemede ({status['state_text']})")
            self.lbl_live_status.setStyleSheet(f"color: {T['warning']}; font-weight: bold;")
            self.lbl_countdown.setText(f"⏳ Başlamaya: {status['time_remaining_str']}")
            self.lbl_countdown.setStyleSheet(f"color: {T['color_orange']}; font-weight: bold;")
