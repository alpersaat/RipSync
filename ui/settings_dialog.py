import os
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QSpinBox,
    QCheckBox, QFormLayout, QGroupBox, QComboBox, QSlider,
    QTabWidget, QWidget, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView
)
from core.database import Database
from core.site_rules import SiteRulesManager
from core.post_download import send_webhook_notification
from ui.styles import ACCENT_COLORS


class SiteRuleAddDialog(QDialog):
    """Dialog to add or edit a domain-specific folder rule."""
    def __init__(self, initial_domain: str = "", initial_folder: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("🌐 Yeni Site Kuralı Ekle")
        self.resize(460, 180)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        form = QFormLayout()
        form.setSpacing(10)

        self.edit_domain = QLineEdit(initial_domain)
        self.edit_domain.setPlaceholderText("Örn: github.com veya artstation.com")
        form.addRow("Alan Adı (Domain):", self.edit_domain)

        dir_box = QHBoxLayout()
        self.edit_folder = QLineEdit(initial_folder or os.path.join(os.path.expanduser("~"), "Downloads"))
        btn_br = QPushButton("Gözat...")
        btn_br.setObjectName("btn_secondary")
        btn_br.clicked.connect(self._browse)
        dir_box.addWidget(self.edit_folder)
        dir_box.addWidget(btn_br)
        form.addRow("Hedef Kayıt Klasörü:", dir_box)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_ok = QPushButton("Kuralı Kaydet")
        btn_ok.setStyleSheet("background-color: #7aa2f7; color: #1a1b26; font-weight: bold; padding: 6px 16px;")
        btn_ok.clicked.connect(self._on_ok)
        btn_box.addWidget(btn_ok)

        btn_cancel = QPushButton("İptal")
        btn_cancel.setObjectName("btn_secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        layout.addLayout(btn_box)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Hedef Klasörü Seç", self.edit_folder.text())
        if d:
            self.edit_folder.setText(d)

    def _on_ok(self):
        dom = self.edit_domain.text().strip()
        fol = self.edit_folder.text().strip()
        if not dom:
            QMessageBox.warning(self, "Uyarı", "Lütfen geçerli bir alan adı (domain) girin.")
            return
        if not fol:
            QMessageBox.warning(self, "Uyarı", "Lütfen bir hedef klasör seçin.")
            return
        self.accept()

    def get_data(self):
        return self.edit_domain.text().strip(), self.edit_folder.text().strip()


class SettingsDialog(QDialog):
    settings_saved = pyqtSignal()

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.site_rules_mgr = SiteRulesManager(self.db)
        self.setWindowTitle("RipSync - Ayarlar")
        self.resize(580, 540)
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(14)
        main_layout.setContentsMargins(16, 16, 16, 16)

        self.tabs = QTabWidget()

        # ==========================================
        # TAB 1: Genel & Dosyalar
        # ==========================================
        tab_general = QWidget()
        lay_gen = QVBoxLayout(tab_general)
        lay_gen.setSpacing(12)

        grp_gen = QGroupBox("İndirme & Klasör Yapılandırması")
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
        self.spin_max_concurrent.setToolTip("Aynı anda kaç dosyanın ineceği (sıralı indirme limiti).")
        f_gen.addRow("Sıralı İndirme Limiti (Eşzamanlı):", self.spin_max_concurrent)

        self.combo_default_quality = QComboBox()
        self.combo_default_quality.addItem("🚀 En Yüksek Kalite (Maksimum - 4K / 1080p)", "max")
        self.combo_default_quality.addItem("🌟 1080p (Full HD)", "1080p")
        self.combo_default_quality.addItem("✨ 720p (HD)", "720p")
        self.combo_default_quality.addItem("📺 480p (Standart)", "480p")
        self.combo_default_quality.addItem("🎵 Sadece Ses (MP3 Müzik)", "audio")
        f_gen.addRow("Varsayılan Video Kalitesi:", self.combo_default_quality)

        self.combo_conflict_action = QComboBox()
        self.combo_conflict_action.addItem("🔄 Otomatik Numaralandır (örn: dosya (1).ext)", "auto_rename")
        self.combo_conflict_action.addItem("⚠️ Mevcut Dosyanın Üzerine Yaz", "overwrite")
        self.combo_conflict_action.addItem("⏭️ İndirmeyi Atla / Bildir", "skip")
        f_gen.addRow("Aynı İsimde Dosya Varsa (Çakışma):", self.combo_conflict_action)

        self.chk_auto_categorize = QCheckBox("Akıllı Otomatik Kategorizasyon (Videolar, Müzik, Belgeler klasörleme)")
        f_gen.addRow("", self.chk_auto_categorize)

        self.chk_auto_extract = QCheckBox("📦 Arşivleri Otomatik Çıkart (.zip, .tar vb. tamamlanınca otomatik klasöre aç)")
        f_gen.addRow("", self.chk_auto_extract)

        self.chk_auto_retry = QCheckBox("Ağ Kesintilerinde Otomatik Yeniden Dene (Auto-Retry)")
        f_gen.addRow("", self.chk_auto_retry)

        self.spin_max_retries = QSpinBox()
        self.spin_max_retries.setRange(1, 10)
        self.spin_max_retries.setValue(3)
        self.spin_max_retries.setSuffix(" Kez")
        f_gen.addRow("Maksimum Yeniden Deneme Sayısı:", self.spin_max_retries)

        self.chk_warn_duplicate = QCheckBox("🛡️ Yinelenen İndirme Uyarısı (Aynı bağlantı veya dosya mevcutsa uyar)")
        self.chk_warn_duplicate.setChecked(True)
        self.chk_warn_duplicate.setStyleSheet("color: #7aa2f7; font-weight: bold;")
        f_gen.addRow("", self.chk_warn_duplicate)

        lay_gen.addWidget(grp_gen)

        grp_media = QGroupBox("Medya, Çerez & Altyazı Yapılandırması")
        f_media = QFormLayout(grp_media)

        self.combo_browser_cookies = QComboBox()
        self.combo_browser_cookies.addItem("❌ Devre Dışı (Standart Oturum)", "")
        self.combo_browser_cookies.addItem("🟢 Google Chrome", "chrome")
        self.combo_browser_cookies.addItem("🔵 Microsoft Edge", "edge")
        self.combo_browser_cookies.addItem("🦁 Brave Browser", "brave")
        self.combo_browser_cookies.addItem("🦊 Mozilla Firefox", "firefox")
        self.combo_browser_cookies.addItem("🔴 Opera", "opera")
        self.combo_browser_cookies.addItem("🟡 Vivaldi", "vivaldi")
        f_media.addRow("Tarayıcı Çerezleri Entegrasyonu:", self.combo_browser_cookies)

        self.chk_default_subtitles = QCheckBox("📝 Videolarla birlikte altyazıları otomatik indir (.srt)")
        f_media.addRow("", self.chk_default_subtitles)

        self.chk_default_thumbnail = QCheckBox("🖼️ Video ve müzik kapak resimlerini kaydet (Thumbnail)")
        f_media.addRow("", self.chk_default_thumbnail)

        self.chk_embed_metadata = QCheckBox("🎵 MP3 indirmelerine ID3 etiketlerini (Sanatçı/Başlık) ve kapağı göm")
        self.chk_embed_metadata.setChecked(True)
        f_media.addRow("", self.chk_embed_metadata)

        lay_gen.addWidget(grp_media)
        lay_gen.addStretch()
        self.tabs.addTab(tab_general, "⚙️ Genel & Dosyalar")

        # ==========================================
        # TAB 2: Ağ & Proxy
        # ==========================================
        tab_proxy = QWidget()
        lay_proxy = QVBoxLayout(tab_proxy)
        lay_proxy.setSpacing(12)

        grp_proxy = QGroupBox("Vekil Sunucu (Proxy) Yapılandırması")
        f_proxy = QFormLayout(grp_proxy)

        self.chk_proxy_enabled = QCheckBox("Proxy Sunucusu Kullan (HTTP / HTTPS / SOCKS5)")
        self.chk_proxy_enabled.setStyleSheet("font-weight: bold; color: #7aa2f7;")
        self.chk_proxy_enabled.toggled.connect(self._toggle_proxy_fields)
        f_proxy.addRow("", self.chk_proxy_enabled)

        self.combo_proxy_type = QComboBox()
        self.combo_proxy_type.addItem("HTTP", "http")
        self.combo_proxy_type.addItem("HTTPS", "https")
        self.combo_proxy_type.addItem("SOCKS5", "socks5")
        f_proxy.addRow("Proxy Türü:", self.combo_proxy_type)

        self.edit_proxy_host = QLineEdit()
        self.edit_proxy_host.setPlaceholderText("Örn: 127.0.0.1 veya proxy.example.com")
        f_proxy.addRow("Sunucu Adresi (Host):", self.edit_proxy_host)

        self.spin_proxy_port = QSpinBox()
        self.spin_proxy_port.setRange(1, 65535)
        self.spin_proxy_port.setValue(8080)
        f_proxy.addRow("Port Numarası:", self.spin_proxy_port)

        self.edit_proxy_user = QLineEdit()
        self.edit_proxy_user.setPlaceholderText("İsteğe bağlı kullanıcı adı")
        f_proxy.addRow("Kullanıcı Adı (İsteğe Bağlı):", self.edit_proxy_user)

        self.edit_proxy_pass = QLineEdit()
        self.edit_proxy_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_proxy_pass.setPlaceholderText("İsteğe bağlı şifre")
        f_proxy.addRow("Şifre (İsteğe Bağlı):", self.edit_proxy_pass)

        lay_proxy.addWidget(grp_proxy)

        lbl_proxy_hint = QLabel("💡 Not: Proxy ayarları etkinleştirildiğinde tüm indirmeler ve medya çözümlemeleri bu vekil sunucu üzerinden yönlendirilir.")
        lbl_proxy_hint.setWordWrap(True)
        lbl_proxy_hint.setStyleSheet("color: #7aa2f7; font-size: 11px;")
        lay_proxy.addWidget(lbl_proxy_hint)
        lay_proxy.addStretch()
        self.tabs.addTab(tab_proxy, "🌐 Ağ & Proxy")

        # ==========================================
        # TAB 3: Görünüm & Tema
        # ==========================================
        tab_theme = QWidget()
        lay_theme = QVBoxLayout(tab_theme)
        lay_theme.setSpacing(12)

        grp_theme = QGroupBox("Tema & Vurgu Rengi")
        f_theme = QFormLayout(grp_theme)

        self.combo_theme = QComboBox()
        self.combo_theme.addItem("🌙 Koyu Tema (Tokyo Night Dark)", "dark")
        self.combo_theme.addItem("☀️ Aydınlık Tema (Modern Fluent Light)", "light")
        f_theme.addRow("Arayüz Teması:", self.combo_theme)

        self.combo_accent = QComboBox()
        for acc_key, acc_val in ACCENT_COLORS.items():
            self.combo_accent.addItem(f"● {acc_val['name']}", acc_key)
        f_theme.addRow("Vurgu Rengi (Accent):", self.combo_accent)

        lay_theme.addWidget(grp_theme)

        lbl_theme_hint = QLabel("💡 Kaydet butonuna tıkladığınızda seçilen tema ve vurgu rengi RipSync pencerelerine anında uygulanır.")
        lbl_theme_hint.setWordWrap(True)
        lbl_theme_hint.setStyleSheet("color: #7aa2f7; font-size: 11px;")
        lay_theme.addWidget(lbl_theme_hint)
        lay_theme.addStretch()
        self.tabs.addTab(tab_theme, "🎨 Görünüm & Tema")

        # ==========================================
        # TAB 4: Hız & Güç Yönetimi
        # ==========================================
        tab_speed_power = QWidget()
        lay_sp = QVBoxLayout(tab_speed_power)
        lay_sp.setSpacing(12)

        grp_speed = QGroupBox("Hız Sınırlayıcı (Speed Limiter)")
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
        lay_sp.addWidget(grp_speed)

        grp_power = QGroupBox("Kuyruk Bitişi & Sistem Davranışı")
        f_power = QFormLayout(grp_power)

        self.combo_queue_action = QComboBox()
        self.combo_queue_action.addItem("❌ Eylem Yok (Uygulama çalışmaya devam etsin)", "none")
        self.combo_queue_action.addItem("🛑 Bilgisayarı Kapat (Shutdown)", "shutdown")
        self.combo_queue_action.addItem("🌙 Uyku Moduna Al (Sleep / Suspend)", "sleep")
        f_power.addRow("Kuyruk Bittiğinde:", self.combo_queue_action)

        self.chk_close_to_tray = QCheckBox("Pencere kapatıldığında (X tuşu) sistem tepsisine (Tray) küçült")
        self.chk_close_to_tray.setChecked(True)
        f_power.addRow("", self.chk_close_to_tray)

        self.chk_toast_notifications = QCheckBox("İndirme bittiğinde Windows Bildirimi göster")
        self.chk_toast_notifications.setChecked(True)
        f_power.addRow("", self.chk_toast_notifications)

        self.chk_sound_notifications = QCheckBox("İndirme bittiğinde ses çal (IDM tarzı bildirim sesi)")
        self.chk_sound_notifications.setChecked(True)
        f_power.addRow("", self.chk_sound_notifications)

        self.chk_keep_awake = QCheckBox("🌙 Aktif indirme varken Windows'un uyku moduna geçmesini engelle (Keep-Awake)")
        self.chk_keep_awake.setChecked(True)
        self.chk_keep_awake.setStyleSheet("color: #7aa2f7; font-weight: bold;")
        f_power.addRow("", self.chk_keep_awake)

        self.chk_pause_metered = QCheckBox("📶 Tarifeli Bağlantıda (Mobil Veri / Hotspot) indirmeleri otomatik duraklat")
        self.chk_pause_metered.setChecked(True)
        self.chk_pause_metered.setStyleSheet("color: #7dcfff; font-weight: bold;")
        f_power.addRow("", self.chk_pause_metered)

        lay_sp.addWidget(grp_power)
        lay_sp.addStretch()
        self.tabs.addTab(tab_speed_power, "⚡ Hız & Güç")

        # ==========================================
        # TAB 5: Entegrasyon & Tarayıcı
        # ==========================================
        tab_integ = QWidget()
        lay_integ = QVBoxLayout(tab_integ)
        lay_integ.setSpacing(12)

        grp_integ = QGroupBox("Pano & Tarayıcı Entegrasyonu")
        f_integ = QFormLayout(grp_integ)

        self.chk_clipboard = QCheckBox("Panoyu İzle (Kopyalanan bağlantıları sağ altta otomatik yakala)")
        f_integ.addRow("", self.chk_clipboard)

        self.chk_clip_only_media = QCheckBox("🎯 Yalnızca doğrudan medya ve dosya uzantılarını yakala (Genel sayfaları yoksay)")
        f_integ.addRow("", self.chk_clip_only_media)

        self.edit_clip_ignore = QLineEdit()
        self.edit_clip_ignore.setPlaceholderText("google.com, bing.com, localhost (virgülle ayırın)")
        f_integ.addRow("Göz Ardı Edilecek Siteler (Kara Liste):", self.edit_clip_ignore)

        self.spin_port = QSpinBox()
        self.spin_port.setRange(1024, 65535)
        self.spin_port.setValue(28710)
        f_integ.addRow("Chrome Eklenti Dinleme Portu:", self.spin_port)

        btn_ext_guide = QPushButton("🌐 Tarayıcı Eklentisi Kurulum Kılavuzu...")
        btn_ext_guide.setObjectName("btn_secondary")
        btn_ext_guide.clicked.connect(self._open_extension_guide)
        f_integ.addRow("", btn_ext_guide)

        lay_integ.addWidget(grp_integ)
        lay_integ.addStretch()
        self.tabs.addTab(tab_integ, "🔗 Entegrasyon")

        # ==========================================
        # TAB 6: Otomasyon & Webhook (Post-Download Actions)
        # ==========================================
        tab_auto = QWidget()
        lay_auto = QVBoxLayout(tab_auto)
        lay_auto.setSpacing(14)

        # 1. Custom Command Group
        grp_cmd = QGroupBox("🖥️ İndirme Tamamlandığında Özel Komut Çalıştır (CLI / Script)")
        f_cmd = QFormLayout(grp_cmd)
        f_cmd.setSpacing(10)

        self.chk_command_enabled = QCheckBox("İndirme bittiğinde özel komut veya betik çalıştır")
        self.chk_command_enabled.setStyleSheet("font-weight: bold; color: #7aa2f7;")
        self.chk_command_enabled.toggled.connect(lambda en: self.edit_command.setEnabled(en))
        f_cmd.addRow("", self.chk_command_enabled)

        self.edit_command = QLineEdit()
        self.edit_command.setPlaceholderText('Örn: python C:\\scripts\\notify.py "{filepath}" "{filename}"')
        self.edit_command.setEnabled(False)
        f_cmd.addRow("Komut Şablonu:", self.edit_command)

        lbl_cmd_hint = QLabel("💡 Kullanılabilir Şablon Değişkenleri:\n"
                              " • {filepath} ➔ Dosyanın tam disk yolu\n"
                              " • {filename} ➔ Dosya adı\n"
                              " • {filesize} ➔ Okunabilir dosya boyutu (örn: 24.5 MB)\n"
                              " • {category} ➔ Dosya kategorisi (Video, Belgeler vb.)\n"
                              " • {url} ➔ İndirilen kaynak web adresi")
        lbl_cmd_hint.setStyleSheet("color: #7982a9; font-size: 11px; margin-top: 4px;")
        f_cmd.addRow("", lbl_cmd_hint)
        lay_auto.addWidget(grp_cmd)

        # 2. Webhook Notification Group
        grp_hook = QGroupBox("🔔 Webhook Bildirimleri (Discord / Slack / Özel API)")
        f_hook = QFormLayout(grp_hook)
        f_hook.setSpacing(10)

        self.chk_webhook_enabled = QCheckBox("İndirme bittiğinde Webhook bildirimi gönder")
        self.chk_webhook_enabled.setStyleSheet("font-weight: bold; color: #9ece6a;")
        self.chk_webhook_enabled.toggled.connect(self._toggle_webhook_fields)
        f_hook.addRow("", self.chk_webhook_enabled)

        hook_row = QHBoxLayout()
        self.edit_webhook_url = QLineEdit()
        self.edit_webhook_url.setPlaceholderText("https://discord.com/api/webhooks/...")
        self.edit_webhook_url.setEnabled(False)
        hook_row.addWidget(self.edit_webhook_url)

        self.btn_test_webhook = QPushButton("🔔 Test Et")
        self.btn_test_webhook.setObjectName("btn_secondary")
        self.btn_test_webhook.setEnabled(False)
        self.btn_test_webhook.clicked.connect(self._test_webhook)
        hook_row.addWidget(self.btn_test_webhook)
        f_hook.addRow("Webhook URL:", hook_row)

        lbl_hook_hint = QLabel("💡 Discord kanalı, Slack veya kendi REST API sunucunuza JSON formatında anlık indirme tamamlandı bildirimi gönderir.")
        lbl_hook_hint.setWordWrap(True)
        lbl_hook_hint.setStyleSheet("color: #7982a9; font-size: 11px;")
        f_hook.addRow("", lbl_hook_hint)
        lay_auto.addWidget(grp_hook)

        lay_auto.addStretch()
        self.tabs.addTab(tab_auto, "🤖 Otomasyon & Webhook")

        # ==========================================
        # TAB 7: 🌐 Site Kuralları (Domain Specific Folders)
        # ==========================================
        tab_site_rules = QWidget()
        lay_sr = QVBoxLayout(tab_site_rules)
        lay_sr.setSpacing(10)

        lbl_sr_info = QLabel("Belirli web sitelerinden indirilen dosyaları otomatik olarak istediğiniz klasöre kaydedin:")
        lbl_sr_info.setStyleSheet("color: #c0caf5; font-size: 12px; font-weight: bold;")
        lay_sr.addWidget(lbl_sr_info)

        self.tbl_site_rules = QTableWidget()
        self.tbl_site_rules.setColumnCount(2)
        self.tbl_site_rules.setHorizontalHeaderLabels(["Alan Adı (Domain)", "Hedef Kayıt Klasörü"])
        self.tbl_site_rules.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.tbl_site_rules.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl_site_rules.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_site_rules.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_site_rules.setStyleSheet("QTableWidget { background-color: #1a1b26; border: 1px solid #3b4261; border-radius: 6px; }")
        lay_sr.addWidget(self.tbl_site_rules, stretch=1)

        sr_act_row = QHBoxLayout()
        btn_add_rule = QPushButton("➕ Yeni Kural Ekle...")
        btn_add_rule.setStyleSheet("background-color: #7aa2f7; color: #1a1b26; font-weight: bold; padding: 6px 14px;")
        btn_add_rule.clicked.connect(self._add_site_rule)
        sr_act_row.addWidget(btn_add_rule)

        btn_del_rule = QPushButton("🗑️ Seçili Kuralı Sil")
        btn_del_rule.setObjectName("btn_secondary")
        btn_del_rule.clicked.connect(self._delete_site_rule)
        sr_act_row.addWidget(btn_del_rule)

        sr_act_row.addStretch()
        lay_sr.addLayout(sr_act_row)

        self.tabs.addTab(tab_site_rules, "🌐 Site Kuralları")

        main_layout.addWidget(self.tabs)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("İptal")
        btn_cancel.setObjectName("btn_secondary")
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("💾 Değişiklikleri Kaydet")
        btn_save.clicked.connect(self._save_settings)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        main_layout.addLayout(btn_layout)

    def _browse_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "Klasör Seç", self.edit_default_dir.text())
        if chosen:
            self.edit_default_dir.setText(chosen)

    def _toggle_speed_limit(self, enabled: bool):
        self.slider_speed_limit.setEnabled(enabled)
        self.spin_speed_limit.setEnabled(enabled)
        for btn in self.btn_presets:
            btn.setEnabled(enabled)

    def _toggle_proxy_fields(self, enabled: bool):
        self.combo_proxy_type.setEnabled(enabled)
        self.edit_proxy_host.setEnabled(enabled)
        self.spin_proxy_port.setEnabled(enabled)
        self.edit_proxy_user.setEnabled(enabled)
        self.edit_proxy_pass.setEnabled(enabled)

    def _on_settings_slider_changed(self, value: int):
        self.spin_speed_limit.blockSignals(True)
        self.spin_speed_limit.setValue(value)
        self.spin_speed_limit.blockSignals(False)

    def _toggle_webhook_fields(self, enabled: bool):
        self.edit_webhook_url.setEnabled(enabled)
        self.btn_test_webhook.setEnabled(enabled)

    def _test_webhook(self):
        url = self.edit_webhook_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Uyarı", "Lütfen test etmek için geçerli bir Webhook URL adresi girin.")
            return

        test_context = {
            "{filename}": "Test_Dosyasi.zip",
            "{filepath}": "C:\\Downloads\\Test_Dosyasi.zip",
            "{filesize}": "25.4 MB",
            "{category}": "Sıkıştırılmış",
            "{url}": "https://example.com/test_dosyasi.zip",
            "{status}": "Completed"
        }
        success, msg = send_webhook_notification(url, test_context, timeout=5.0)
        if success:
            QMessageBox.information(self, "Başarılı", f"✅ Webhook bildirimi başarıyla gönderildi!\n{msg}")
        else:
            QMessageBox.critical(self, "Hata", f"❌ Webhook gönderimi başarısız oldu:\n{msg}")

    def _load_settings(self):
        saved_dir = self.db.get_setting("default_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
        self.edit_default_dir.setText(saved_dir)

        conns = self.db.get_setting("connections", 8)
        self.spin_connections.setValue(int(conns))

        max_conc = self.db.get_setting("max_concurrent", 3)
        self.spin_max_concurrent.setValue(int(max_conc))

        pref_q = self.db.get_setting("preferred_quality", "max")
        idx = self.combo_default_quality.findData(pref_q)
        if idx >= 0:
            self.combo_default_quality.setCurrentIndex(idx)

        # File conflict setting
        conflict_action = self.db.get_conflict_setting()
        idx_ca = self.combo_conflict_action.findData(conflict_action)
        if idx_ca >= 0:
            self.combo_conflict_action.setCurrentIndex(idx_ca)

        auto_cat = self.db.get_setting("auto_categorize", True)
        self.chk_auto_categorize.setChecked(bool(auto_cat))

        auto_extract = self.db.get_setting("auto_extract_archives", False)
        self.chk_auto_extract.setChecked(bool(auto_extract))

        auto_retry_en = self.db.get_setting("auto_retry_enabled", True)
        self.chk_auto_retry.setChecked(bool(auto_retry_en))

        max_ret = self.db.get_setting("max_retries", 3)
        self.spin_max_retries.setValue(int(max_ret))

        # Speed settings
        speed_enabled = self.db.get_setting("speed_limit_enabled", False)
        self.chk_speed_limit.setChecked(bool(speed_enabled))
        self._toggle_speed_limit(bool(speed_enabled))

        speed_val = self.db.get_setting("speed_limit_kb", 5120)
        self.slider_speed_limit.setValue(int(speed_val))
        self.spin_speed_limit.setValue(int(speed_val))

        # Duplicate warning
        self.chk_warn_duplicate.setChecked(self.db.get_duplicate_warning_setting())

        # Power & Behavior
        queue_action = self.db.get_setting("on_queue_complete_action", "none")
        idx_qa = self.combo_queue_action.findData(queue_action)
        if idx_qa >= 0:
            self.combo_queue_action.setCurrentIndex(idx_qa)

        close_to_tray = self.db.get_setting("close_to_tray", True)
        self.chk_close_to_tray.setChecked(bool(close_to_tray))

        toast_notif = self.db.get_setting("toast_notifications", True)
        self.chk_toast_notifications.setChecked(bool(toast_notif))

        sound_notif = self.db.get_setting("sound_notifications", True)
        self.chk_sound_notifications.setChecked(bool(sound_notif))

        # Metered connection
        metered_cfg = self.db.get_metered_settings()
        self.chk_pause_metered.setChecked(bool(metered_cfg.get("pause_on_metered", True)))

        # Integration & Clipboard
        clip_cfg = self.db.get_clipboard_settings()
        self.chk_clipboard.setChecked(bool(clip_cfg.get("enabled", True)))
        self.chk_clip_only_media.setChecked(bool(clip_cfg.get("only_media", False)))
        ignores = clip_cfg.get("ignore_domains", [])
        self.edit_clip_ignore.setText(", ".join(ignores) if isinstance(ignores, list) else str(ignores))

        port = self.db.get_setting("extension_port", 28710)
        self.spin_port.setValue(int(port))

        # Proxy settings
        p_cfg = self.db.get_proxy_settings()
        self.chk_proxy_enabled.setChecked(bool(p_cfg.get("enabled", False)))
        idx_pt = self.combo_proxy_type.findData(p_cfg.get("type", "http"))
        if idx_pt >= 0:
            self.combo_proxy_type.setCurrentIndex(idx_pt)
        self.edit_proxy_host.setText(p_cfg.get("host", ""))
        self.spin_proxy_port.setValue(int(p_cfg.get("port", 8080)))
        self.edit_proxy_user.setText(p_cfg.get("username", ""))
        self.edit_proxy_pass.setText(p_cfg.get("password", ""))
        self._toggle_proxy_fields(bool(p_cfg.get("enabled", False)))

        # Appearance & Themes
        t_cfg = self.db.get_theme_settings()
        idx_thm = self.combo_theme.findData(t_cfg.get("theme", "dark"))
        if idx_thm >= 0:
            self.combo_theme.setCurrentIndex(idx_thm)

        idx_acc = self.combo_accent.findData(t_cfg.get("accent", "blue"))
        if idx_acc >= 0:
            self.combo_accent.setCurrentIndex(idx_acc)

        # Automation & Webhook settings
        auto_cfg = self.db.get_automation_settings()
        cmd_en = bool(auto_cfg.get("command_enabled", False))
        self.chk_command_enabled.setChecked(cmd_en)
        self.edit_command.setEnabled(cmd_en)
        self.edit_command.setText(auto_cfg.get("command", ""))

        wh_en = bool(auto_cfg.get("webhook_enabled", False))
        self.chk_webhook_enabled.setChecked(wh_en)
        self._toggle_webhook_fields(wh_en)
        self.edit_webhook_url.setText(auto_cfg.get("webhook_url", ""))

        # Load Media & Cookies settings
        b_cookies = self.db.get_setting("browser_cookies", "")
        idx_bc = self.combo_browser_cookies.findData(b_cookies)
        if idx_bc >= 0:
            self.combo_browser_cookies.setCurrentIndex(idx_bc)

        d_subs = self.db.get_setting("download_subtitles", False)
        self.chk_default_subtitles.setChecked(bool(d_subs))

        d_thumb = self.db.get_setting("download_thumbnail", False)
        self.chk_default_thumbnail.setChecked(bool(d_thumb))

        e_meta = self.db.get_setting("embed_metadata", True)
        self.chk_embed_metadata.setChecked(bool(e_meta))

        # Load Keep Awake
        ka_enabled = self.db.get_setting("keep_awake_enabled", True)
        self.chk_keep_awake.setChecked(bool(ka_enabled))

        # Load Site Rules
        self._refresh_site_rules_table()

    def _refresh_site_rules_table(self):
        rules = self.site_rules_mgr.get_rules()
        self.tbl_site_rules.setRowCount(len(rules))
        for row_idx, r in enumerate(rules):
            item_dom = QTableWidgetItem(r.get("domain", ""))
            item_dom.setForeground(Qt.GlobalColor.white)
            item_fol = QTableWidgetItem(r.get("folder", ""))
            item_fol.setForeground(Qt.GlobalColor.lightGray)
            self.tbl_site_rules.setItem(row_idx, 0, item_dom)
            self.tbl_site_rules.setItem(row_idx, 1, item_fol)

    def _add_site_rule(self):
        dlg = SiteRuleAddDialog(parent=self)
        if dlg.exec():
            domain, folder = dlg.get_data()
            self.site_rules_mgr.add_rule(domain, folder, enabled=True)
            self._refresh_site_rules_table()

    def _delete_site_rule(self):
        cur_row = self.tbl_site_rules.currentRow()
        if cur_row < 0:
            QMessageBox.information(self, "Bilgi", "Lütfen silmek istediğiniz kuralı tablodan seçin.")
            return
        dom_item = self.tbl_site_rules.item(cur_row, 0)
        if dom_item:
            domain = dom_item.text().strip()
            self.site_rules_mgr.remove_rule(domain)
            self._refresh_site_rules_table()

    def _save_settings(self):
        self.db.set_setting("default_dir", self.edit_default_dir.text().strip())
        self.db.set_setting("connections", self.spin_connections.value())
        self.db.set_setting("max_concurrent", self.spin_max_concurrent.value())
        self.db.set_setting("preferred_quality", self.combo_default_quality.currentData())
        self.db.save_conflict_setting(self.combo_conflict_action.currentData())
        self.db.set_setting("auto_categorize", self.chk_auto_categorize.isChecked())
        self.db.set_setting("auto_extract_archives", self.chk_auto_extract.isChecked())
        self.db.set_setting("auto_retry_enabled", self.chk_auto_retry.isChecked())
        self.db.set_setting("max_retries", self.spin_max_retries.value())

        # Media & Cookies
        self.db.set_setting("browser_cookies", self.combo_browser_cookies.currentData())
        self.db.set_setting("download_subtitles", self.chk_default_subtitles.isChecked())
        self.db.set_setting("download_thumbnail", self.chk_default_thumbnail.isChecked())
        self.db.set_setting("embed_metadata", self.chk_embed_metadata.isChecked())

        # Speed settings
        self.db.set_setting("speed_limit_enabled", self.chk_speed_limit.isChecked())
        self.db.set_setting("speed_limit_kb", self.spin_speed_limit.value())

        # Power & Behavior
        self.db.set_setting("on_queue_complete_action", self.combo_queue_action.currentData())
        self.db.set_setting("close_to_tray", self.chk_close_to_tray.isChecked())
        self.db.set_setting("toast_notifications", self.chk_toast_notifications.isChecked())
        self.db.set_setting("sound_notifications", self.chk_sound_notifications.isChecked())
        self.db.set_setting("keep_awake_enabled", self.chk_keep_awake.isChecked())

        # Duplicate Warning
        self.db.save_duplicate_warning_setting(self.chk_warn_duplicate.isChecked())

        # Metered Connection
        self.db.save_metered_settings({
            "pause_on_metered": self.chk_pause_metered.isChecked()
        })

        # Clipboard & Integration
        raw_ignores = self.edit_clip_ignore.text().strip()
        ignore_list = [d.strip() for d in raw_ignores.split(",") if d.strip()]
        self.db.save_clipboard_settings({
            "enabled": self.chk_clipboard.isChecked(),
            "only_media": self.chk_clip_only_media.isChecked(),
            "ignore_domains": ignore_list
        })
        self.db.set_setting("clipboard_enabled", self.chk_clipboard.isChecked())
        self.db.set_setting("extension_port", self.spin_port.value())

        # Save Proxy
        self.db.save_proxy_settings({
            "enabled": self.chk_proxy_enabled.isChecked(),
            "type": self.combo_proxy_type.currentData(),
            "host": self.edit_proxy_host.text().strip(),
            "port": self.spin_proxy_port.value(),
            "username": self.edit_proxy_user.text().strip(),
            "password": self.edit_proxy_pass.text().strip()
        })

        # Save Appearance
        self.db.save_theme_settings(
            theme=self.combo_theme.currentData(),
            accent=self.combo_accent.currentData()
        )

        # Save Post-Download Automation
        self.db.save_automation_settings({
            "command_enabled": self.chk_command_enabled.isChecked(),
            "command": self.edit_command.text().strip(),
            "webhook_enabled": self.chk_webhook_enabled.isChecked(),
            "webhook_url": self.edit_webhook_url.text().strip()
        })

        self.settings_saved.emit()
        self.accept()

    def _open_extension_guide(self):
        from ui.extension_guide_dialog import ExtensionGuideDialog
        dlg = ExtensionGuideDialog(self, bridge_port=self.spin_port.value())
        dlg.exec()

