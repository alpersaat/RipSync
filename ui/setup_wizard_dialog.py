"""
RipSync - First-Run & Setup Wizard Dialog
A modern, multi-step onboarding wizard for users during initial setup or first launch.
Features automatic browser detection, 1-click extension auto-launch, step-by-step
visual guides, and download folder configuration.
"""

import os
from typing import Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QWidget, QFrame, QFileDialog, QCheckBox,
    QMessageBox, QApplication
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from core.paths import get_default_download_dir, show_in_explorer
from core.extension_installer import (
    get_detected_browsers, launch_browser_with_extension,
    open_browser_extension_page, copy_extension_path_to_clipboard,
    get_extension_folder_path
)
from ui.extension_guide_dialog import BrowserMockupCard
from ui.tray_icon import create_default_icon


class SetupWizardDialog(QDialog):
    """
    Onboarding Setup Wizard displayed upon first launch or via command-line / menu.
    Guides intermediate users through download settings and browser extension setup.
    """
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("RipSync - Kurulum ve Başlangıç Sihirbazı")
        self.setWindowIcon(create_default_icon())
        self.setFixedSize(720, 640)
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1b26;
                color: #c0caf5;
            }
            QLabel {
                color: #c0caf5;
            }
            QPushButton {
                background-color: #24283b;
                color: #c0caf5;
                border: 1px solid #414868;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #3b4261;
                border-color: #7aa2f7;
            }
            QPushButton#primaryBtn {
                background-color: #3d59a1;
                color: #ffffff;
                border: 1px solid #7aa2f7;
            }
            QPushButton#primaryBtn:hover {
                background-color: #7aa2f7;
                color: #15161e;
            }
            QPushButton#successBtn {
                background-color: #1b4d3e;
                color: #9ece6a;
                border: 1px solid #9ece6a;
            }
            QPushButton#successBtn:hover {
                background-color: #9ece6a;
                color: #15161e;
            }
            QFrame.stepBox {
                background-color: #1f2335;
                border: 1px solid #292e42;
                border-radius: 8px;
                padding: 12px;
            }
        """)

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # Wizard Header Bar
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #16161e; border-radius: 8px; padding: 6px 12px;")
        h_layout = QHBoxLayout(header_frame)
        self.lbl_wizard_title = QLabel("🧙 RipSync Kurulum Sihirbazı")
        self.lbl_wizard_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #7aa2f7;")
        h_layout.addWidget(self.lbl_wizard_title)
        h_layout.addStretch()

        self.lbl_step_num = QLabel("Sayfa 1 / 3")
        self.lbl_step_num.setStyleSheet("color: #e0af68; font-weight: bold; font-size: 12px;")
        h_layout.addWidget(self.lbl_step_num)
        main_layout.addWidget(header_frame)

        # Multi-page Stack
        self.pages = QStackedWidget()

        # Page 1: Welcome & Download Folder
        self.page_welcome = self._create_page_welcome()
        self.pages.addWidget(self.page_welcome)

        # Page 2: Extension Setup (Auto-install & Visual Guide)
        self.page_extension = self._create_page_extension()
        self.pages.addWidget(self.page_extension)

        # Page 3: Final / Ready Page
        self.page_finish = self._create_page_finish()
        self.pages.addWidget(self.page_finish)

        main_layout.addWidget(self.pages, 1)

        # Bottom Navigation Buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

        self.chk_dont_show = QCheckBox("Açılışta bu sihirbazı bir daha gösterme")
        self.chk_dont_show.setChecked(True)
        self.chk_dont_show.setStyleSheet("color: #9aa5ce; font-size: 11px;")
        bottom_layout.addWidget(self.chk_dont_show)
        bottom_layout.addStretch()

        self.btn_back = QPushButton("◀ Geri")
        self.btn_back.setEnabled(False)
        self.btn_back.clicked.connect(self._go_back)
        bottom_layout.addWidget(self.btn_back)

        self.btn_next = QPushButton("İleri ▶")
        self.btn_next.setObjectName("primaryBtn")
        self.btn_next.clicked.connect(self._go_next)
        bottom_layout.addWidget(self.btn_next)

        main_layout.addLayout(bottom_layout)

    def _create_page_welcome(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(14)

        title = QLabel("RipSync'e Hoş Geldiniz! 🚀")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #7aa2f7;")
        layout.addWidget(title)

        desc = QLabel(
            "RipSync, modern ve yüksek hızlı bir indirme yöneticisidir. "
            "YouTube, sosyal medya videoları ve büyük dosyaları çok kanallı (multi-segmented) motoruyla "
            "en yüksek hızda indirir.\n\n"
            "Bu sihirbaz, indirme klasörünüzü belirlemenize ve tarayıcı eklentisini kurmanıza yardımcı olacaktır."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #c0caf5; font-size: 12px; line-height: 1.4;")
        layout.addWidget(desc)

        # Download Directory Selector Box
        box = QFrame()
        box.setProperty("class", "stepBox")
        b_layout = QVBoxLayout(box)
        b_layout.setSpacing(8)

        b_title = QLabel("📁 <b>Varsayılan İndirme Klasörü:</b>")
        b_title.setStyleSheet("color: #bb9af7; font-size: 12px;")
        b_layout.addWidget(b_title)

        curr_dir = self.db.get_setting("download_dir", get_default_download_dir())
        self.lbl_curr_dir = QLabel(curr_dir)
        self.lbl_curr_dir.setStyleSheet("""
            background-color: #16161e;
            border: 1px solid #3b4261;
            border-radius: 6px;
            padding: 8px;
            font-family: Consolas, monospace;
            color: #7dcfff;
        """)
        self.lbl_curr_dir.setWordWrap(True)
        b_layout.addWidget(self.lbl_curr_dir)

        btn_change_dir = QPushButton("📂 Klasörü Değiştir...")
        btn_change_dir.clicked.connect(self._choose_download_dir)
        b_layout.addWidget(btn_change_dir, 0, Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(box)
        layout.addStretch()
        return page

    def _create_page_extension(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        title = QLabel("🌐 Tarayıcı Eklentisi Kurulumu")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #7aa2f7;")
        layout.addWidget(title)

        desc = QLabel(
            "RipSync'in web sitelerindeki ve video platformlarındaki içerikleri yakalayabilmesi için "
            "eklenti kurulumu gereklidir. Aşağıdaki seçeneklerden dilediğinizi kullanabilirsiniz:"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #a9b1d6; font-size: 12px;")
        layout.addWidget(desc)

        # Quick Auto-Install Box
        auto_box = QFrame()
        auto_box.setProperty("class", "stepBox")
        ab_layout = QVBoxLayout(auto_box)
        ab_layout.setSpacing(8)

        ab_title = QLabel("⚡ <b>Seçenek 1: Otomatik Yükleme & Başlatma (Tavsiye Edilen)</b>")
        ab_title.setStyleSheet("color: #9ece6a; font-size: 12px;")
        ab_layout.addWidget(ab_title)

        detected = get_detected_browsers()
        detected_names = ", ".join([d["name"] for d in detected.values()]) if detected else "Chromium Tarayıcısı"
        ab_sub = QLabel(f"Tespit Edilen Tarayıcılar: <b>{detected_names}</b>\n"
                        "Tarayıcınızı eklentiyle birlikte tek tıkla otomatik olarak başlatabilirsiniz.")
        ab_sub.setStyleSheet("color: #c0caf5; font-size: 11px;")
        ab_layout.addWidget(ab_sub)

        btn_row = QHBoxLayout()
        btn_autolaunch = QPushButton("🚀 Eklentiyle Otomatik Başlat")
        btn_autolaunch.setObjectName("successBtn")
        btn_autolaunch.clicked.connect(self._auto_launch)
        btn_row.addWidget(btn_autolaunch)

        btn_copy = QPushButton("📋 Klasör Yolunu Kopyala")
        btn_copy.clicked.connect(self._copy_path)
        btn_row.addWidget(btn_copy)

        btn_folder = QPushButton("📁 Eklenti Klasörünü Aç")
        btn_folder.clicked.connect(self._open_folder)
        btn_row.addWidget(btn_folder)

        ab_layout.addLayout(btn_row)
        layout.addWidget(auto_box)

        # Step-by-step visual mockup
        guide_box = QFrame()
        guide_box.setProperty("class", "stepBox")
        gb_layout = QVBoxLayout(guide_box)
        gb_layout.setSpacing(6)

        gb_title = QLabel("🖼 <b>Seçenek 2: Adımlı Görsel Rehber (Manuel Kurulum)</b>")
        gb_title.setStyleSheet("color: #e0af68; font-size: 12px;")
        gb_layout.addWidget(gb_title)

        self.wizard_card_stack = QStackedWidget()
        c1 = BrowserMockupCard(1, "chrome://extensions Sayfasını Açın", "Tarayıcınızın adres çubuğuna yazın veya butona tıklayın.", "open_browser")
        c2 = BrowserMockupCard(2, "Geliştirici Modunu Açın", "Sağ üst köşedeki Geliştirici modu anahtarını açın.", "dev_mode")
        c3 = BrowserMockupCard(3, "'Paketlenmemiş Öğe Yükle'ye Tıklayın", "Sol üstteki Paketlenmemiş öğe yükle butonuna basın.", "load_unpacked")
        c4 = BrowserMockupCard(4, "Eklenti Klasörünü Seçin", "Açılan pencerede RipSync extension klasörünü seçin.", "select_folder")

        self.wizard_card_stack.addWidget(c1)
        self.wizard_card_stack.addWidget(c2)
        self.wizard_card_stack.addWidget(c3)
        self.wizard_card_stack.addWidget(c4)
        gb_layout.addWidget(self.wizard_card_stack)

        # Card controls
        c_nav = QHBoxLayout()
        self.lbl_card_num = QLabel("Adım 1 / 4")
        self.lbl_card_num.setStyleSheet("font-weight: bold; color: #7aa2f7; font-size: 11px;")
        c_nav.addWidget(self.lbl_card_num)
        c_nav.addStretch()

        btn_card_prev = QPushButton("◀ Önceki Adım")
        btn_card_prev.clicked.connect(self._prev_card)
        c_nav.addWidget(btn_card_prev)

        btn_card_next = QPushButton("Sonraki Adım ▶")
        btn_card_next.clicked.connect(self._next_card)
        c_nav.addWidget(btn_card_next)

        gb_layout.addLayout(c_nav)
        layout.addWidget(guide_box)

        return page

    def _create_page_finish(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(14)

        title = QLabel("Kurulum Tamamlandı! 🎉")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #9ece6a;")
        layout.addWidget(title)

        desc = QLabel(
            "Tebrikler! RipSync kullanıma hazır.\n\n"
            "• Tarayıcınızda video veya indirme bağlantısı bulduğunuzda 'İndir' butonu otomatik görünecektir.\n"
            "• RipSync sistem tepsisinde (sağ altta) sessizce çalışmaya devam eder.\n"
            "• İstediğiniz zaman araç çubuğundaki 'Eklenti' veya 'Ayarlar' menüsünden rehbere tekrar ulaşabilirsiniz."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #c0caf5; font-size: 13px; line-height: 1.5;")
        layout.addWidget(desc)

        # Summary box
        box = QFrame()
        box.setProperty("class", "stepBox")
        b_layout = QVBoxLayout(box)

        port = self.db.get_setting("extension_port", 28710)
        down_dir = self.db.get_setting("download_dir", get_default_download_dir())

        b_layout.addWidget(QLabel(f"✓ <b>İndirme Klasörü:</b> {down_dir}"))
        b_layout.addWidget(QLabel(f"✓ <b>Köprü Sunucu Portu:</b> {port} (Aktif)"))
        b_layout.addWidget(QLabel(f"✓ <b>Eklenti Entegrasyonu:</b> Yapılandırıldı"))
        layout.addWidget(box)

        layout.addStretch()
        return page

    def _choose_download_dir(self):
        curr = self.lbl_curr_dir.text()
        chosen = QFileDialog.getExistingDirectory(self, "İndirme Klasörü Seç", curr)
        if chosen:
            self.lbl_curr_dir.setText(chosen)
            self.db.set_setting("download_dir", chosen)

    def _auto_launch(self):
        success, msg = launch_browser_with_extension()
        if success:
            QMessageBox.information(self, "Başarılı 🚀", f"{msg}\n\nEklenti tarayıcınıza otomatik yüklendi!")
        else:
            QMessageBox.warning(self, "Hata", msg)

    def _copy_path(self):
        success, path = copy_extension_path_to_clipboard()
        if success:
            QMessageBox.information(
                self, "Yol Kopyalandı 📋",
                f"Eklenti yolu panoya kopyalandı:\n{path}\n\n"
                "Tarayıcının 'Paketlenmemiş öğe yükle' penceresine Ctrl+V ile yapıştırabilirsiniz."
            )

    def _open_folder(self):
        ext_dir = get_extension_folder_path()
        copy_extension_path_to_clipboard()
        show_in_explorer(ext_dir)
        QMessageBox.information(
            self, "Klasör Açıldı 📁",
            f"Eklenti klasörü Dosya Gezgini'nde açıldı ve yol kopyalandı:\n{ext_dir}"
        )

    def _prev_card(self):
        idx = self.wizard_card_stack.currentIndex()
        if idx > 0:
            self.wizard_card_stack.setCurrentIndex(idx - 1)
            self.lbl_card_num.setText(f"Adım {idx} / {self.wizard_card_stack.count()}")

    def _next_card(self):
        idx = self.wizard_card_stack.currentIndex()
        if idx < self.wizard_card_stack.count() - 1:
            self.wizard_card_stack.setCurrentIndex(idx + 1)
            self.lbl_card_num.setText(f"Adım {idx + 2} / {self.wizard_card_stack.count()}")

    def _go_next(self):
        curr = self.pages.currentIndex()
        if curr < self.pages.count() - 1:
            self.pages.setCurrentIndex(curr + 1)
            self.lbl_step_num.setText(f"Sayfa {curr + 2} / {self.pages.count()}")
            self.btn_back.setEnabled(True)
            if curr + 1 == self.pages.count() - 1:
                self.btn_next.setText("Tamamla & Başla ✔")
                self.btn_next.setObjectName("successBtn")
                self.btn_next.setStyle(self.btn_next.style())
        else:
            # Finish
            if self.chk_dont_show.isChecked():
                self.db.set_setting("setup_completed", True)
            self.accept()

    def _go_back(self):
        curr = self.pages.currentIndex()
        if curr > 0:
            self.pages.setCurrentIndex(curr - 1)
            self.lbl_step_num.setText(f"Sayfa {curr} / {self.pages.count()}")
            self.btn_back.setEnabled(curr - 1 > 0)
            self.btn_next.setText("İleri ▶")
            self.btn_next.setObjectName("primaryBtn")
            self.btn_next.setStyle(self.btn_next.style())
