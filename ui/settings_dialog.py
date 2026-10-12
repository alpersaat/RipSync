import os
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QSpinBox,
    QCheckBox, QFormLayout, QGroupBox, QComboBox, QSlider
)
from core.database import Database

class SettingsDialog(QDialog):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("RipSync - Ayarlar")
        self.resize(500, 480)
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(18, 18, 18, 18)

        # General Group
        grp_gen = QGroupBox("Genel İndirme Ayarları")
        f_gen = QFormLayout(grp_gen)

        dir_layout = QHBoxLayout()
        self.edit_default_dir = QLineEdit(os.path.join(os.path.expanduser("~"), "Downloads"))
        btn_browse = QPushButton("Gözat...")
        btn_browse.setObjectName("btn_secondary")
        btn_browse.clicked.connect(self._browse_dir)
        dir_layout.addWidget(self.edit_default_dir)
        dir_layout.addWidget(btn_browse)
        f_gen.addRow("Varsayılan İndirme Klasörü:", dir_layout)

        self.spin_connections = QSpinBox()
        self.spin_connections.setRange(1, 32)
        self.spin_connections.setValue(8)
        f_gen.addRow("Varsayılan Parça (Bağlantı) Sayısı:", self.spin_connections)

        self.spin_max_concurrent = QSpinBox()
        self.spin_max_concurrent.setRange(1, 10)
        self.spin_max_concurrent.setValue(2)
        self.spin_max_concurrent.setSuffix(" Dosya")
        self.spin_max_concurrent.setToolTip("Aynı anda kaç dosyanın ineceği (ör. aynı anda en fazla 2 dosya insin, biri bitince diğeri başlasın).")
        f_gen.addRow("Sıralı İndirme Limiti (Eşzamanlı):", self.spin_max_concurrent)

        self.combo_default_quality = QComboBox()
        self.combo_default_quality.addItem("🚀 En Yüksek Kalite (Maksimum - 4K / 1080p)", "max")
        self.combo_default_quality.addItem("🌟 1080p (Full HD)", "1080p")
        self.combo_default_quality.addItem("✨ 720p (HD)", "720p")
        self.combo_default_quality.addItem("📺 480p (Standart)", "480p")
        self.combo_default_quality.addItem("🎵 Sadece Ses (MP3 Müzik)", "audio")
        f_gen.addRow("Varsayılan Video Kalitesi:", self.combo_default_quality)

        self.chk_auto_categorize = QCheckBox("Akıllı Otomatik Kategorizasyon (Dosya türüne göre ilgili alt klasöre kaydet)")
        self.chk_auto_categorize.setToolTip(
            "Etkin olduğunda:\n"
            "• .mp4, .mkv, .avi ➔ İndirilenler / Videolar\n"
            "• .mp3, .wav, .flac ➔ İndirilenler / Müzik\n"
            "• .zip, .rar, .7z ➔ İndirilenler / Arşivler\n"
            "• .exe, .msi, .iso ➔ İndirilenler / Programlar\n"
            "• .pdf, .docx ➔ İndirilenler / Belgeler"
        )
        f_gen.addRow("", self.chk_auto_categorize)

        layout.addWidget(grp_gen)

        # Queue Completion & System Power Group
        grp_queue_power = QGroupBox("Kuyruk Tamamlandığında & Güç Yönetimi")
        f_queue_power = QFormLayout(grp_queue_power)

        self.combo_queue_action = QComboBox()
        self.combo_queue_action.addItem("❌ Eylem Yok (Uygulama çalışmaya devam etsin)", "none")
        self.combo_queue_action.addItem("🛑 Bilgisayarı Kapat (Shutdown)", "shutdown")
        self.combo_queue_action.addItem("🌙 Uyku Moduna Al (Sleep / Suspend)", "sleep")
        f_queue_power.addRow("Kuyruk Bittiğinde:", self.combo_queue_action)

        self.chk_close_to_tray = QCheckBox("Pencere kapatıldığında (X tuşu) sistem tepsisine (Tray) küçült")
        self.chk_close_to_tray.setChecked(True)
        f_queue_power.addRow("", self.chk_close_to_tray)

        self.chk_toast_notifications = QCheckBox("İndirme bittiğinde Windows Bildirimi göster (Klasörde Göster butonlu)")
        self.chk_toast_notifications.setChecked(True)
        f_queue_power.addRow("", self.chk_toast_notifications)

        layout.addWidget(grp_queue_power)

        # Speed Limiter Group
        grp_speed = QGroupBox("Hız Sınırlayıcı (Speed Limiter & Bant Genişliği Kontrolü)")
        f_speed = QFormLayout(grp_speed)

        self.chk_speed_limit = QCheckBox("Genel Hız Sınırını Etkinleştir (Tek Tıkla IDM Modu)")
        self.chk_speed_limit.setStyleSheet("font-weight: bold; color: #7aa2f7;")
        self.chk_speed_limit.toggled.connect(self._toggle_speed_limit)
        f_speed.addRow("", self.chk_speed_limit)

        slider_box = QHBoxLayout()
        self.slider_speed_limit = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed_limit.setRange(256, 50 * 1024)
        self.slider_speed_limit.setSingleStep(256)
        self.slider_speed_limit.setPageStep(1024)
        self.slider_speed_limit.setValue(5120)
        self.slider_speed_limit.setEnabled(False)
        self.slider_speed_limit.valueChanged.connect(self._on_settings_slider_changed)
        slider_box.addWidget(self.slider_speed_limit)

        self.spin_speed_limit = QSpinBox()
        self.spin_speed_limit.setRange(256, 100000)
        self.spin_speed_limit.setValue(5120)
        self.spin_speed_limit.setSuffix(" KB/s")
        self.spin_speed_limit.setFixedWidth(110)
        self.spin_speed_limit.setEnabled(False)
        self.spin_speed_limit.valueChanged.connect(self._on_settings_spin_changed)
        slider_box.addWidget(self.spin_speed_limit)

        f_speed.addRow("İndirme Hız Limiti:", slider_box)

        # Quick preset buttons (1 MB/s, 2 MB/s, 5 MB/s, 10 MB/s, 25 MB/s)
        preset_row = QHBoxLayout()
        lbl_p = QLabel("Hızlı Seçim:")
        lbl_p.setStyleSheet("color: #7982a9; font-size: 11px;")
        preset_row.addWidget(lbl_p)

        self.btn_presets = []
        for p_label, p_val in [("1 MB/s", 1024), ("2 MB/s", 2048), ("5 MB/s (Önerilen)", 5120), ("10 MB/s", 10240), ("25 MB/s", 25600)]:
            btn = QPushButton(p_label)
            btn.setObjectName("btn_secondary")
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda checked, v=p_val: self.slider_speed_limit.setValue(v))
            preset_row.addWidget(btn)
            self.btn_presets.append(btn)

        f_speed.addRow("", preset_row)
        layout.addWidget(grp_speed)

        # Integration Group
        grp_integ = QGroupBox("Entegrasyon & Tarayıcı")
        f_integ = QFormLayout(grp_integ)

        self.chk_clipboard = QCheckBox("Panoyu İzle (Kopyalanan indirme bağlantılarını otomatik yakala)")
        f_integ.addRow("", self.chk_clipboard)

        self.spin_port = QSpinBox()
        self.spin_port.setRange(1024, 65535)
        self.spin_port.setValue(28710)
        f_integ.addRow("Chrome Eklenti Dinleme Portu:", self.spin_port)

        btn_ext_guide = QPushButton("🌐 Tarayıcı Eklentisi Kurulum Kılavuzu...")
        btn_ext_guide.setObjectName("btn_secondary")
        btn_ext_guide.clicked.connect(self._open_extension_guide)
        f_integ.addRow("", btn_ext_guide)

        layout.addWidget(grp_integ)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_save = QPushButton("Kaydet")
        btn_save.clicked.connect(self._save_settings)
        btn_layout.addWidget(btn_save)

        btn_cancel = QPushButton("İptal")
        btn_cancel.setObjectName("btn_secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

    def _browse_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "Klasör Seç", self.edit_default_dir.text())
        if chosen:
            self.edit_default_dir.setText(chosen)

    def _toggle_speed_limit(self, enabled: bool):
        self.slider_speed_limit.setEnabled(enabled)
        self.spin_speed_limit.setEnabled(enabled)
        for btn in self.btn_presets:
            btn.setEnabled(enabled)

    def _on_settings_slider_changed(self, value: int):
        self.spin_speed_limit.blockSignals(True)
        self.spin_speed_limit.setValue(value)
        self.spin_speed_limit.blockSignals(False)

    def _on_settings_spin_changed(self, value: int):
        self.slider_speed_limit.blockSignals(True)
        self.slider_speed_limit.setValue(value)
        self.slider_speed_limit.blockSignals(False)

    def _load_settings(self):
        saved_dir = self.db.get_setting("default_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
        self.edit_default_dir.setText(saved_dir)

        conns = self.db.get_setting("connections", 8)
        self.spin_connections.setValue(int(conns))

        max_conc = self.db.get_setting("max_concurrent", 3)
        self.spin_max_concurrent.setValue(int(max_conc))

        speed_enabled = self.db.get_setting("speed_limit_enabled", False)
        self.chk_speed_limit.setChecked(bool(speed_enabled))
        self._toggle_speed_limit(bool(speed_enabled))

        speed_val = self.db.get_setting("speed_limit_kb", 5120)
        self.slider_speed_limit.setValue(int(speed_val))
        self.spin_speed_limit.setValue(int(speed_val))

        clipboard_enabled = self.db.get_setting("clipboard_enabled", True)
        self.chk_clipboard.setChecked(bool(clipboard_enabled))

        port = self.db.get_setting("extension_port", 28710)
        self.spin_port.setValue(int(port))

        pref_q = self.db.get_setting("preferred_quality", "max")
        idx = self.combo_default_quality.findData(pref_q)
        if idx >= 0:
            self.combo_default_quality.setCurrentIndex(idx)

        auto_cat = self.db.get_setting("auto_categorize", True)
        self.chk_auto_categorize.setChecked(bool(auto_cat))

        queue_action = self.db.get_setting("on_queue_complete_action", "none")
        idx_qa = self.combo_queue_action.findData(queue_action)
        if idx_qa >= 0:
            self.combo_queue_action.setCurrentIndex(idx_qa)

        close_to_tray = self.db.get_setting("close_to_tray", True)
        self.chk_close_to_tray.setChecked(bool(close_to_tray))

        toast_notif = self.db.get_setting("toast_notifications", True)
        self.chk_toast_notifications.setChecked(bool(toast_notif))

    def _save_settings(self):
        self.db.set_setting("default_dir", self.edit_default_dir.text().strip())
        self.db.set_setting("connections", self.spin_connections.value())
        self.db.set_setting("max_concurrent", self.spin_max_concurrent.value())
        self.db.set_setting("speed_limit_enabled", self.chk_speed_limit.isChecked())
        self.db.set_setting("speed_limit_kb", self.spin_speed_limit.value())
        self.db.set_setting("clipboard_enabled", self.chk_clipboard.isChecked())
        self.db.set_setting("extension_port", self.spin_port.value())
        self.db.set_setting("preferred_quality", self.combo_default_quality.currentData())
        self.db.set_setting("auto_categorize", self.chk_auto_categorize.isChecked())
        self.db.set_setting("on_queue_complete_action", self.combo_queue_action.currentData())
        self.db.set_setting("close_to_tray", self.chk_close_to_tray.isChecked())
        self.db.set_setting("toast_notifications", self.chk_toast_notifications.isChecked())
        self.accept()

    def _open_extension_guide(self):
        from ui.extension_guide_dialog import ExtensionGuideDialog
        dlg = ExtensionGuideDialog(self, bridge_port=self.spin_port.value())
        dlg.exec()
