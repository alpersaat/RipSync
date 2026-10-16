import os
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QWidget, QRadioButton,
    QButtonGroup, QLineEdit, QFileDialog, QCheckBox,
    QFrame
)
from core.database import Database
from ui.tray_icon import create_default_icon


class OnboardingDialog(QDialog):
    """
    İlk kullanımda kullanıcıyı karşılayan, arayüz modunu (Basit / Gelişmiş)
    seçtiren ve temel kullanımı anlatan modern rehberli tur sihirbazı.
    """
    tour_finished = pyqtSignal(str)  # Seçilen UI modu ("simple" veya "advanced")

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("RipSync'e Hoş Geldiniz - Hızlı Başlangıç Rehberi")
        self.setWindowIcon(create_default_icon())
        self.setFixedSize(680, 520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._init_ui()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 24, 24, 20)
        root_layout.setSpacing(16)

        # Üst Adım Göstergesi (Step Indicator)
        self.step_indicator_layout = QHBoxLayout()
        self.step_indicator_layout.setSpacing(8)
        self.step_dots = []
        for i in range(5):
            dot = QLabel(f"Adım {i + 1}")
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dot.setStyleSheet("""
                QLabel {
                    background-color: #24283b;
                    color: #7982a9;
                    font-size: 11px;
                    font-weight: bold;
                    border-radius: 10px;
                    padding: 4px 12px;
                    min-height: 18px;
                }
            """)
            self.step_dots.append(dot)
            self.step_indicator_layout.addWidget(dot)
        root_layout.addLayout(self.step_indicator_layout)

        # Stacked Pages
        self.stack = QStackedWidget()
        self.stack.addWidget(self._create_step1_welcome())
        self.stack.addWidget(self._create_step2_folder())
        self.stack.addWidget(self._create_step3_how_to_download())
        self.stack.addWidget(self._create_step4_tips())
        self.stack.addWidget(self._create_step5_ready())
        root_layout.addWidget(self.stack, stretch=1)

        # Alt Navigasyon Çubuğu
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(0, 8, 0, 0)

        self.btn_skip = QPushButton("Turu Atla")
        self.btn_skip.setObjectName("btn_secondary")
        self.btn_skip.setStyleSheet("color: #7982a9; background-color: transparent; border: none; font-size: 12px;")
        self.btn_skip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_skip.clicked.connect(self._on_skip)
        nav_layout.addWidget(self.btn_skip)

        nav_layout.addStretch()

        self.btn_prev = QPushButton("◀ Geri")
        self.btn_prev.setObjectName("btn_secondary")
        self.btn_prev.setFixedSize(90, 34)
        self.btn_prev.clicked.connect(self._go_prev)
        self.btn_prev.setEnabled(False)
        nav_layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton("İleri ▶")
        self.btn_next.setFixedSize(110, 34)
        self.btn_next.setStyleSheet("""
            QPushButton {
                background-color: #7aa2f7;
                color: #1a1b26;
                font-weight: bold;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #89b4fa;
            }
        """)
        self.btn_next.clicked.connect(self._go_next)
        nav_layout.addWidget(self.btn_next)

        root_layout.addLayout(nav_layout)

        self._update_step_indicator(0)

    # ==========================================
    # ADIM 1: Hoş Geldiniz & Mod Seçimi
    # ==========================================
    def _create_step1_welcome(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(14)

        lbl_hero = QLabel("🚀 RipSync'e Hoş Geldiniz!")
        lbl_hero.setStyleSheet("font-size: 20px; font-weight: bold; color: #7aa2f7;")
        layout.addWidget(lbl_hero)

        lbl_sub = QLabel(
            "RipSync, internetten dosyaları maksimum hızda indiren, çok kanallı ve modern bir indirme yöneticisidir.\n"
            "Kullanım alışkanlığınıza en uygun çalışma modunu seçerek başlayabilirsiniz:"
        )
        lbl_sub.setWordWrap(True)
        lbl_sub.setStyleSheet("color: #c0caf5; font-size: 13px; line-height: 1.4;")
        layout.addWidget(lbl_sub)

        # Mod Seçim Kartları
        self.mode_btn_group = QButtonGroup(self)

        # 1. Basit Mod Kartı
        card_simple = QFrame()
        card_simple.setStyleSheet("""
            QFrame {
                background-color: #1f2335;
                border: 2px solid #3b4261;
                border-radius: 10px;
                padding: 12px;
            }
            QFrame:hover {
                border-color: #9ece6a;
            }
        """)
        lay_s = QVBoxLayout(card_simple)
        lay_s.setSpacing(6)

        top_s = QHBoxLayout()
        self.rad_simple = QRadioButton("🟢 Basit Mod (Yeni Kullanıcılar ve Sade Tasarım Sevenler)")
        self.rad_simple.setChecked(True)
        self.rad_simple.setStyleSheet("font-weight: bold; font-size: 14px; color: #9ece6a;")
        self.mode_btn_group.addButton(self.rad_simple)
        top_s.addWidget(self.rad_simple)
        lay_s.addLayout(top_s)

        lbl_s_desc = QLabel(
            "• Yalnızca temel indirme butonları (URL Ekle, Başlat, Durdur, Klasörde Aç, Sil).\n"
            "• Karmaşık sekmeler ve kafa karıştırıcı ayarlar gizlenir.\n"
            "• Temiz dosya listesi ve en sade arama deneyimi sunar."
        )
        lbl_s_desc.setStyleSheet("color: #a9b1d6; font-size: 12px; margin-left: 24px;")
        lay_s.addWidget(lbl_s_desc)
        layout.addWidget(card_simple)

        # 2. Gelişmiş Mod Kartı
        card_adv = QFrame()
        card_adv.setStyleSheet("""
            QFrame {
                background-color: #1f2335;
                border: 2px solid #3b4261;
                border-radius: 10px;
                padding: 12px;
            }
            QFrame:hover {
                border-color: #bb9af7;
            }
        """)
        lay_a = QVBoxLayout(card_adv)
        lay_a.setSpacing(6)

        top_a = QHBoxLayout()
        self.rad_adv = QRadioButton("⚡ Gelişmiş Mod (Deneyimli Kullanıcılar ve Tam Kontrol)")
        self.rad_adv.setStyleSheet("font-weight: bold; font-size: 14px; color: #bb9af7;")
        self.mode_btn_group.addButton(self.rad_adv)
        top_a.addWidget(self.rad_adv)
        lay_a.addLayout(top_a)

        lbl_a_desc = QLabel(
            "• Gece indirme zamanlayıcısı, bant genişliği canlı hız grafiği ve hız sınırlayıcı.\n"
            "• Özel kuyruk yönetimi, dosya etiketleri (Tags) ve site bazlı klasör kuralları.\n"
            "• Otomasyon, Webhook bildirimleri ve gelişmiş arama filtreleri."
        )
        lbl_a_desc.setStyleSheet("color: #a9b1d6; font-size: 12px; margin-left: 24px;")
        lay_a.addWidget(lbl_a_desc)
        layout.addWidget(card_adv)

        lbl_tip = QLabel("💡 Not: Bu tercihi ana ekrandaki 'Mod Değiştir' butonundan dilediğiniz an tek tıkla değiştirebilirsiniz.")
        lbl_tip.setStyleSheet("color: #7aa2f7; font-size: 11px; margin-top: 4px;")
        layout.addWidget(lbl_tip)

        layout.addStretch()
        return page

    # ==========================================
    # ADIM 2: İndirme Klasörü ve Tercihler
    # ==========================================
    def _create_step2_folder(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(16)

        lbl_title = QLabel("📁 İndirme Konumu ve Klasör Tercihleri")
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #7aa2f7;")
        layout.addWidget(lbl_title)

        lbl_info = QLabel("İndirilen dosyalarınızın varsayılan olarak kaydedileceği klasörü belirleyin:")
        lbl_info.setStyleSheet("color: #c0caf5; font-size: 13px;")
        layout.addWidget(lbl_info)

        # Klasör Seçim Kutusu
        box_dir = QHBoxLayout()
        default_dl = self.db.get_default_save_dir() if hasattr(self.db, "get_default_save_dir") else os.path.join(os.path.expanduser("~"), "Downloads")
        self.edit_dir = QLineEdit(default_dl)
        self.edit_dir.setStyleSheet("padding: 8px; border-radius: 6px; background-color: #1f2335; border: 1px solid #3b4261; color: #c0caf5;")
        btn_browse = QPushButton("Gözat...")
        btn_browse.setObjectName("btn_secondary")
        btn_browse.setFixedHeight(34)
        btn_browse.clicked.connect(self._browse_folder)
        box_dir.addWidget(self.edit_dir, stretch=1)
        box_dir.addWidget(btn_browse)
        layout.addLayout(box_dir)

        layout.addSpacing(10)

        # Hızlı Ayar Seçenekleri
        grp_opts = QFrame()
        grp_opts.setStyleSheet("background-color: #1f2335; border-radius: 8px; padding: 12px;")
        lay_opts = QVBoxLayout(grp_opts)
        lay_opts.setSpacing(12)

        self.chk_categorize = QCheckBox("🗂️ Akıllı Kategorizasyon (Videolar, Müzikler, Belgeler otomatik alt klasörlere ayrılsın)")
        self.chk_categorize.setChecked(True)
        self.chk_categorize.setStyleSheet("font-size: 12px; color: #c0caf5;")
        lay_opts.addWidget(self.chk_categorize)

        self.chk_clipboard = QCheckBox("📋 Akıllı Pano İzleyici (Tarayıcıda kopyaladığınız indirme linklerini sağ altta yakala)")
        self.chk_clipboard.setChecked(True)
        self.chk_clipboard.setStyleSheet("font-size: 12px; color: #c0caf5;")
        lay_opts.addWidget(self.chk_clipboard)

        self.chk_sound = QCheckBox("🔔 İndirme tamamlandığında bildirim sesi çal")
        self.chk_sound.setChecked(True)
        self.chk_sound.setStyleSheet("font-size: 12px; color: #c0caf5;")
        lay_opts.addWidget(self.chk_sound)

        layout.addWidget(grp_opts)
        layout.addStretch()
        return page

    # ==========================================
    # ADIM 3: Nasıl İndirme Yapılır?
    # ==========================================
    def _create_step3_how_to_download(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(14)

        lbl_title = QLabel("⚡ İndirme Başlatmanın 3 Kolay Yolu")
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #7aa2f7;")
        layout.addWidget(lbl_title)

        methods = [
            ("1. Bağlantıyı Kopyalayın (En Kolayı)",
             "Tarayıcınızda veya herhangi bir uygulamada indirme bağlantısını kopyaladığınızda, "
             "RipSync bunu otomatik olarak algılar ve sağ altta tek tıkla indirme kutucuğu sunar.",
             "📋"),
            ("2. '➕ URL Ekle' Butonuna Tıklayın",
             "Ana ekrandaki büyük URL Ekle butonuna tıklayarak doğrudan web adresini yapıştırabilir, "
             "dosya adını ve indirme parçası sayısını seçebilirsiniz.",
             "🔗"),
            ("3. Tarayıcı Eklentisi (Chrome & Edge)",
             "RipSync tarayıcı uzantısı ile web sitelerindeki 'İndir' butonlarına tıklandığında indirmeler "
             "otomatik olarak RipSync'e aktarılır ve maksimum bant genişliğiyle iner.",
             "🌐")
        ]

        for m_title, m_desc, m_icon in methods:
            item_box = QFrame()
            item_box.setStyleSheet("background-color: #1f2335; border: 1px solid #3b4261; border-radius: 8px; padding: 10px;")
            lay_item = QHBoxLayout(item_box)
            lay_item.setSpacing(12)

            lbl_ico = QLabel(m_icon)
            lbl_ico.setStyleSheet("font-size: 26px;")
            lay_item.addWidget(lbl_ico)

            lay_texts = QVBoxLayout()
            lay_texts.setSpacing(4)
            lbl_t = QLabel(m_title)
            lbl_t.setStyleSheet("font-weight: bold; font-size: 13px; color: #7dcfff;")
            lbl_d = QLabel(m_desc)
            lbl_d.setWordWrap(True)
            lbl_d.setStyleSheet("color: #a9b1d6; font-size: 11px; line-height: 1.3;")
            lay_texts.addWidget(lbl_t)
            lay_texts.addWidget(lbl_d)
            lay_item.addLayout(lay_texts, stretch=1)

            layout.addWidget(item_box)

        layout.addStretch()
        return page

    # ==========================================
    # ADIM 4: Hızlı Kontroller & İpuçları
    # ==========================================
    def _create_step4_tips(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(14)

        lbl_title = QLabel("💡 Kullanışlı İpuçları ve Kısayollar")
        lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #7aa2f7;")
        layout.addWidget(lbl_title)

        tips = [
            ("Dosyayı Hızlıca Açma",
             "Tamamlanan bir indirmeye listede **çift tıkladığınızda** dosya doğrudan varsayılan programıyla açılır.",
             "📂"),
            ("Sürükle & Bırak (Drag-and-Drop)",
             "Tamamlanan dosyaları listeden tutarak masaüstünüze, başka bir klasöre veya bir programa sürükleyebilirsiniz.",
             "🖱️"),
            ("Sosyal Medya & Oynatma Listeleri",
             "YouTube, X/Twitter, Instagram ve TikTok linklerini ekleyerek video, ses veya tüm oynatma listesini indirebilirsiniz.",
             "🎬"),
            ("İstediğiniz An Mod Değiştirin",
             "Basit mod ve Gelişmiş mod arasında dilediğiniz an araç çubuğunun sağındaki düğmeden geçiş yapabilirsiniz.",
             "🔄")
        ]

        for t_title, t_desc, t_icon in tips:
            item_box = QFrame()
            item_box.setStyleSheet("background-color: #1f2335; border: 1px solid #3b4261; border-radius: 8px; padding: 8px 12px;")
            lay_item = QHBoxLayout(item_box)
            lay_item.setSpacing(12)

            lbl_ico = QLabel(t_icon)
            lbl_ico.setStyleSheet("font-size: 22px;")
            lay_item.addWidget(lbl_ico)

            lay_texts = QVBoxLayout()
            lay_texts.setSpacing(3)
            lbl_t = QLabel(t_title)
            lbl_t.setStyleSheet("font-weight: bold; font-size: 12px; color: #9ece6a;")
            lbl_d = QLabel(t_desc)
            lbl_d.setWordWrap(True)
            lbl_d.setStyleSheet("color: #c0caf5; font-size: 11px;")
            lay_texts.addWidget(lbl_t)
            lay_texts.addWidget(lbl_d)
            lay_item.addLayout(lay_texts, stretch=1)

            layout.addWidget(item_box)

        layout.addStretch()
        return page

    # ==========================================
    # ADIM 5: Tebrikler & Başlayın
    # ==========================================
    def _create_step5_ready(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_check = QLabel("🎉")
        lbl_check.setStyleSheet("font-size: 48px;")
        lbl_check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_check)

        lbl_fin = QLabel("Her Şey Hazır!")
        lbl_fin.setStyleSheet("font-size: 22px; font-weight: bold; color: #9ece6a;")
        lbl_fin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_fin)

        lbl_ready_desc = QLabel(
            "Tebrikler, temel kurulumu başarıyla tamamladınız!\n"
            "RipSync artık maksimum indirme hızı ve kolay arayüzüyle kullanıma hazır."
        )
        lbl_ready_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_ready_desc.setStyleSheet("color: #c0caf5; font-size: 13px; line-height: 1.5;")
        layout.addWidget(lbl_ready_desc)

        # Özet Kutusu
        box_summary = QFrame()
        box_summary.setFixedWidth(460)
        box_summary.setStyleSheet("background-color: #1f2335; border: 1px solid #7aa2f7; border-radius: 8px; padding: 14px;")
        lay_sum = QVBoxLayout(box_summary)
        lay_sum.setSpacing(8)

        self.lbl_sum_mode = QLabel("Seçilen Arayüz: Basit Mod")
        self.lbl_sum_mode.setStyleSheet("color: #7dcfff; font-weight: bold; font-size: 12px;")
        lay_sum.addWidget(self.lbl_sum_mode)

        self.lbl_sum_dir = QLabel("Kayıt Klasörü: -")
        self.lbl_sum_dir.setStyleSheet("color: #a9b1d6; font-size: 11px;")
        self.lbl_sum_dir.setWordWrap(True)
        lay_sum.addWidget(self.lbl_sum_dir)

        lbl_sum_help = QLabel("İpucu: Bu rehberi daha sonra 'Yardım -> Rehberli Tur' menüsünden tekrar başlatabilirsiniz.")
        lbl_sum_help.setStyleSheet("color: #7982a9; font-size: 11px; margin-top: 4px;")
        lay_sum.addWidget(lbl_sum_help)

        layout.addWidget(box_summary)

        btn_finish = QPushButton("🚀 RipSync'i Başlat")
        btn_finish.setFixedSize(200, 42)
        btn_finish.setStyleSheet("""
            QPushButton {
                background-color: #9ece6a;
                color: #1a1b26;
                font-weight: bold;
                font-size: 14px;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #b9f27c;
            }
        """)
        btn_finish.clicked.connect(self._on_finish)
        layout.addWidget(btn_finish, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()
        return page

    # ==========================================
    # Navigasyon ve Olay Yöneticileri
    # ==========================================
    def _browse_folder(self):
        d = QFileDialog.getExistingDirectory(self, "İndirme Klasörü Seç", self.edit_dir.text())
        if d:
            self.edit_dir.setText(d)

    def _update_step_indicator(self, index: int):
        for i, dot in enumerate(self.step_dots):
            if i == index:
                dot.setStyleSheet("""
                    QLabel {
                        background-color: #7aa2f7;
                        color: #1a1b26;
                        font-size: 11px;
                        font-weight: bold;
                        border-radius: 10px;
                        padding: 4px 12px;
                        min-height: 18px;
                    }
                """)
            elif i < index:
                dot.setStyleSheet("""
                    QLabel {
                        background-color: #9ece6a;
                        color: #1a1b26;
                        font-size: 11px;
                        font-weight: bold;
                        border-radius: 10px;
                        padding: 4px 12px;
                        min-height: 18px;
                    }
                """)
            else:
                dot.setStyleSheet("""
                    QLabel {
                        background-color: #24283b;
                        color: #7982a9;
                        font-size: 11px;
                        font-weight: bold;
                        border-radius: 10px;
                        padding: 4px 12px;
                        min-height: 18px;
                    }
                """)

    def _go_prev(self):
        cur = self.stack.currentIndex()
        if cur > 0:
            self._switch_to_step(cur - 1)

    def _go_next(self):
        cur = self.stack.currentIndex()
        if cur < self.stack.count() - 1:
            self._switch_to_step(cur + 1)
        else:
            self._on_finish()

    def _switch_to_step(self, idx: int):
        self.stack.setCurrentIndex(idx)
        self._update_step_indicator(idx)
        self.btn_prev.setEnabled(idx > 0)

        if idx == self.stack.count() - 1:
            self.btn_next.setText("Bitir")
            # Özet metinlerini güncelle
            mode_str = "Gelişmiş Mod (Uzman)" if self.rad_adv.isChecked() else "Basit Mod (Sade)"
            self.lbl_sum_mode.setText(f"Seçilen Arayüz: {mode_str}")
            self.lbl_sum_dir.setText(f"Kayıt Klasörü: {self.edit_dir.text()}")
        else:
            self.btn_next.setText("İleri ▶")

    def _save_preferences(self):
        mode = "advanced" if self.rad_adv.isChecked() else "simple"
        self.db.save_ui_mode(mode)

        # Klasör
        folder = self.edit_dir.text().strip()
        if folder and os.path.exists(folder):
            if hasattr(self.db, "save_default_save_dir"):
                self.db.save_default_save_dir(folder)
            else:
                self.db.set_setting("default_save_dir", folder)

        # Kategorizasyon
        self.db.set_setting("auto_categorize", bool(self.chk_categorize.isChecked()))

        # Pano ayarı
        clip_cfg = self.db.get_clipboard_settings()
        clip_cfg["enabled"] = bool(self.chk_clipboard.isChecked())
        self.db.save_clipboard_settings(clip_cfg)

        # Bildirim sesi
        self.db.set_setting("sound_notifications_enabled", bool(self.chk_sound.isChecked()))

        # Onboarding tamamlandı olarak işaretle
        self.db.set_onboarding_completed(True)
        return mode

    def _on_finish(self):
        chosen_mode = self._save_preferences()
        self.tour_finished.emit(chosen_mode)
        self.accept()

    def _on_skip(self):
        chosen_mode = "advanced" if self.rad_adv.isChecked() else "simple"
        self.db.save_ui_mode(chosen_mode)
        self.db.set_onboarding_completed(True)
        self.tour_finished.emit(chosen_mode)
        self.reject()
