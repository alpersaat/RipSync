"""
RipSync - Modern, Step-by-Step Visual Browser Extension Guide Dialog
Provides casual and intermediate users with visual step-by-step instructions,
one-click extension path copying, direct folder selection, and automatic browser
launching with --load-extension.
"""

import os
import sys
from typing import Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QTabWidget, QWidget, QStackedWidget,
    QApplication, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette

from core.paths import get_extension_dir, show_in_explorer
from core.extension_installer import (
    get_detected_browsers, launch_browser_with_extension,
    open_browser_extension_page, copy_extension_path_to_clipboard,
    get_extension_folder_path
)
from ui.tray_icon import create_default_icon


class BrowserMockupCard(QFrame):
    """
    Renders a clean, realistic browser mockup card illustrating a specific
    installation step with intuitive UI cues, buttons, and badges.
    """
    def __init__(self, step_number: int, title: str, subtitle: str, mockup_type: str, parent=None):
        super().__init__(parent)
        self.setObjectName("mockupCard")
        self.setStyleSheet("""
            QFrame#mockupCard {
                background-color: #1a1b26;
                border: 2px solid #292e42;
                border-radius: 10px;
                padding: 12px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Header with step badge
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        badge = QLabel(f" {step_number} ")
        badge.setStyleSheet("""
            background-color: #7aa2f7;
            color: #15161e;
            font-weight: bold;
            font-size: 13px;
            border-radius: 12px;
            min-width: 24px;
            max-height: 24px;
            qproperty-alignment: AlignCenter;
        """)
        header_layout.addWidget(badge)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #7aa2f7;")
        header_layout.addWidget(title_lbl, 1)

        layout.addLayout(header_layout)

        desc_lbl = QLabel(subtitle)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: #a9b1d6; font-size: 12px; margin-bottom: 4px;")
        layout.addWidget(desc_lbl)

        # Visual Illustration Mockup Box
        mockup_box = self._create_mockup(mockup_type)
        layout.addWidget(mockup_box)

    def _create_mockup(self, mockup_type: str) -> QWidget:
        container = QFrame()
        container.setStyleSheet("""
            background-color: #16161e;
            border: 1px solid #3b4261;
            border-radius: 8px;
            padding: 8px;
        """)
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(10, 8, 10, 8)
        c_layout.setSpacing(8)

        # Fake browser titlebar / tab
        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)
        for col in ["#f7768e", "#e0af68", "#9ece6a"]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {col}; font-size: 11px;")
            top_bar.addWidget(dot)

        url_bar = QLabel(" chrome://extensions ")
        url_bar.setStyleSheet("""
            background-color: #1f2335;
            color: #7aa2f7;
            border-radius: 4px;
            padding: 2px 8px;
            font-family: Consolas, monospace;
            font-size: 11px;
        """)
        top_bar.addWidget(url_bar, 1)
        c_layout.addLayout(top_bar)

        # Visual illustration content
        if mockup_type == "open_browser":
            row = QHBoxLayout()
            info = QLabel("🌐 <b>Adres Çubuğu:</b> <code>chrome://extensions</code> veya <code>edge://extensions</code>")
            info.setStyleSheet("color: #c0caf5; font-size: 11px;")
            row.addWidget(info)
            c_layout.addLayout(row)

        elif mockup_type == "dev_mode":
            row = QHBoxLayout()
            row.addStretch()
            lbl = QLabel("Geliştirici modu (Developer mode)")
            lbl.setStyleSheet("color: #c0caf5; font-size: 12px; font-weight: bold;")
            toggle = QLabel(" [ AÇIK 🔵 ] ")
            toggle.setStyleSheet("""
                background-color: #2ac3de;
                color: #15161e;
                font-weight: bold;
                border-radius: 10px;
                padding: 4px 10px;
                font-size: 11px;
            """)
            arrow = QLabel("👈 <b>1. Bunu Açın</b>")
            arrow.setStyleSheet("color: #e0af68; font-weight: bold;")
            row.addWidget(lbl)
            row.addWidget(toggle)
            row.addWidget(arrow)
            c_layout.addLayout(row)

        elif mockup_type == "load_unpacked":
            row = QHBoxLayout()
            btn_fake = QLabel(" 📥 Paketlenmemiş öğe yükle ")
            btn_fake.setStyleSheet("""
                background-color: #7aa2f7;
                color: #15161e;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
            """)
            arrow = QLabel("👈 <b>2. Bu Butona Tıklayın</b>")
            arrow.setStyleSheet("color: #9ece6a; font-weight: bold; font-size: 12px;")
            row.addWidget(btn_fake)
            row.addWidget(arrow)
            row.addStretch()
            c_layout.addLayout(row)

        elif mockup_type == "select_folder":
            row = QVBoxLayout()
            f_box = QLabel("🗂 <b>Açılan pencerede RipSync 'extension' klasörünü seçin:</b><br>"
                           f"<span style='color: #7dcfff; font-family: Consolas;'>{get_extension_folder_path()}</span>")
            f_box.setStyleSheet("""
                background-color: #1f2335;
                color: #c0caf5;
                border: 1px dashed #7aa2f7;
                border-radius: 6px;
                padding: 8px;
                font-size: 11px;
            """)
            f_box.setWordWrap(True)
            row.addWidget(f_box)

            tip = QLabel("💡 <i>İpucu: 'Yolu Kopyala' butonuna bastıktan sonra pencerede 'Klasör:' kutusuna Ctrl+V yapıp Klasörü Seç'e basabilirsiniz!</i>")
            tip.setStyleSheet("color: #e0af68; font-size: 11px;")
            tip.setWordWrap(True)
            row.addWidget(tip)

            c_layout.addLayout(row)

        return container


class ExtensionGuideDialog(QDialog):
    """
    User-friendly modal dialog guiding users through installing the RipSync
    Chrome / Edge browser extension with visual steps, direct folder selection,
    and 1-click automatic browser launcher.
    """
    def __init__(self, parent=None, bridge_port: int = 28710, bridge_token: Optional[str] = None):
        super().__init__(parent)
        self.bridge_port = bridge_port
        if not bridge_token and hasattr(parent, "db"):
            self.bridge_token = parent.db.get_or_create_bridge_token()
        else:
            self.bridge_token = bridge_token or ""

        self.setWindowTitle("RipSync - Tarayıcı Eklentisi Kurulum Kılavuzu")
        self.setWindowIcon(create_default_icon())
        self.setMinimumSize(680, 620)
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
                padding: 8px 14px;
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
            QTabWidget::pane {
                border: 1px solid #292e42;
                background-color: #1f2335;
                border-radius: 8px;
            }
            QTabBar::tab {
                background: #16161e;
                color: #7aa2f7;
                padding: 8px 16px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background: #1f2335;
                color: #ffffff;
                border-bottom: 2px solid #7aa2f7;
            }
        """)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header Title & Bridge Indicator
        header_row = QHBoxLayout()
        title = QLabel("🌐 Tarayıcı Eklentisi Kurulumu")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #7aa2f7;")
        header_row.addWidget(title)

        status_badge = QLabel(f"● Köprü Hazır (Port: {self.bridge_port})")
        status_badge.setStyleSheet("color: #9ece6a; font-weight: bold; font-size: 11px;")
        header_row.addStretch()
        header_row.addWidget(status_badge)
        layout.addLayout(header_row)

        intro = QLabel(
            "RipSync eklentisi, YouTube ve video sitelerinden videoları anında yakalamanızı sağlar. "
            "Aşağıdaki hızlı seçeneklerle veya 4 adımlı görsel rehberle eklentiyi 10 saniyede kurabilirsiniz:"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #9aa5ce; font-size: 12px;")
        layout.addWidget(intro)

        # Quick Actions Bar (Tek Tıkla Eylemler)
        actions_frame = QFrame()
        actions_frame.setStyleSheet("""
            background-color: #1f2335;
            border: 1px solid #3b4261;
            border-radius: 8px;
            padding: 10px;
        """)
        act_layout = QVBoxLayout(actions_frame)
        act_layout.setContentsMargins(12, 10, 12, 10)
        act_layout.setSpacing(8)

        act_title = QLabel("⚡ <b>Hızlı Seçenekler (Orta & İleri Seviye Kullanıcılar İçin)</b>")
        act_title.setStyleSheet("color: #e0af68; font-size: 12px;")
        act_layout.addWidget(act_title)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        # Button 1: Copy Path
        btn_copy = QPushButton("📋 Klasör Yolunu Kopyala")
        btn_copy.setToolTip("Eklenti klasörünün tam yolunu panoya kopyalar (Ctrl+V ile yapıştırabilirsiniz)")
        btn_copy.clicked.connect(self._copy_extension_path)
        btn_row.addWidget(btn_copy)

        # Button 2: Open Folder in Explorer
        btn_open_folder = QPushButton("📁 Eklenti Klasörünü Aç")
        btn_open_folder.setObjectName("primaryBtn")
        btn_open_folder.setToolTip("Eklenti dosyalarının bulunduğu klasörü Dosya Gezgini'nde açar ve gösterir")
        btn_open_folder.clicked.connect(self._open_extension_dir)
        btn_row.addWidget(btn_open_folder)

        # Button 3: Auto-launch with extension
        btn_autolaunch = QPushButton("🚀 Eklentiyle Başlat")
        btn_autolaunch.setObjectName("successBtn")
        btn_autolaunch.setToolTip("Tarayıcınızı --load-extension parametresiyle doğrudan eklenti yüklü olarak başlatır")
        btn_autolaunch.clicked.connect(self._auto_launch_browser)
        btn_row.addWidget(btn_autolaunch)

        act_layout.addLayout(btn_row)
        layout.addWidget(actions_frame)

        # Step-by-Step Visual Guide
        tabs = QTabWidget()

        # Tab 1: Adım Adım Görsel Rehber (Step-by-Step Wizard)
        tab_steps = QWidget()
        steps_layout = QVBoxLayout(tab_steps)
        steps_layout.setContentsMargins(12, 12, 12, 12)
        steps_layout.setSpacing(10)

        # Stacked steps for interactive wizard
        self.step_stack = QStackedWidget()

        card1 = BrowserMockupCard(
            step_number=1,
            title="Tarayıcıda Uzantılar Sayfasına Gidin",
            subtitle="Chrome veya Edge adres çubuğuna 'chrome://extensions' yazın veya aşağıdaki butona tıklayın.",
            mockup_type="open_browser"
        )
        card2 = BrowserMockupCard(
            step_number=2,
            title="Geliştirici Modunu (Developer Mode) Açın",
            subtitle="Sayfanın sağ üst köşesindeki 'Geliştirici modu' anahtarını aktif hale getirin.",
            mockup_type="dev_mode"
        )
        card3 = BrowserMockupCard(
            step_number=3,
            title="'Paketlenmemiş Öğe Yükle' Butonuna Tıklayın",
            subtitle="Sol üstte beliren 'Paketlenmemiş öğe yükle' (Load unpacked) butonuna tıklayın.",
            mockup_type="load_unpacked"
        )
        card4 = BrowserMockupCard(
            step_number=4,
            title="RipSync Eklenti Klasörünü Seçin",
            subtitle="Açılan pencerede 'Eklenti Klasörünü Aç' ile açtığınız klasörü seçin veya yolu yapıştırın.",
            mockup_type="select_folder"
        )

        self.step_stack.addWidget(card1)
        self.step_stack.addWidget(card2)
        self.step_stack.addWidget(card3)
        self.step_stack.addWidget(card4)

        steps_layout.addWidget(self.step_stack)

        # Step navigation controls
        nav_layout = QHBoxLayout()
        self.lbl_step_indicator = QLabel("Adım 1 / 4")
        self.lbl_step_indicator.setStyleSheet("font-weight: bold; color: #7aa2f7;")
        nav_layout.addWidget(self.lbl_step_indicator)
        nav_layout.addStretch()

        self.btn_open_page = QPushButton("🌐 Uzantılar Sayfasını Aç")
        self.btn_open_page.clicked.connect(self._open_browser_extensions)
        nav_layout.addWidget(self.btn_open_page)

        self.btn_prev_step = QPushButton("◀ Önceki")
        self.btn_prev_step.setEnabled(False)
        self.btn_prev_step.clicked.connect(self._prev_step)
        nav_layout.addWidget(self.btn_prev_step)

        self.btn_next_step = QPushButton("Sonraki ▶")
        self.btn_next_step.setObjectName("primaryBtn")
        self.btn_next_step.clicked.connect(self._next_step)
        nav_layout.addWidget(self.btn_next_step)

        steps_layout.addLayout(nav_layout)
        tabs.addTab(tab_steps, "🖼 Adımlı Ekran Görüntülü Rehber")

        layout.addWidget(tabs, 1)

        # Security Token Info
        if self.bridge_token:
            token_frame = QFrame()
            token_frame.setStyleSheet("""
                background-color: #16161e;
                border: 1px solid #292e42;
                border-radius: 6px;
                padding: 6px 12px;
            """)
            tf_layout = QHBoxLayout(token_frame)
            tf_layout.setContentsMargins(8, 4, 8, 4)

            token_display = f"{self.bridge_token[:6]}...{self.bridge_token[-6:]}" if len(self.bridge_token) > 16 else self.bridge_token
            lbl_tok = QLabel(f"🔒 <b>Köprü Token:</b> <code style='color:#7aa2f7;'>{token_display}</code> "
                            "<span style='color:#9ece6a;'>(config.json ile otomatik eşleşmiştir)</span>")
            lbl_tok.setTextFormat(Qt.TextFormat.RichText)
            tf_layout.addWidget(lbl_tok, 1)

            btn_copy_tok = QPushButton("📋 Token Kopyala")
            btn_copy_tok.clicked.connect(self._copy_token)
            tf_layout.addWidget(btn_copy_tok, 0)

            layout.addWidget(token_frame)

        # Bottom Close Button
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        btn_close = QPushButton("Kapat")
        btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(btn_close)
        layout.addLayout(bottom_layout)

    def _next_step(self):
        curr = self.step_stack.currentIndex()
        if curr < self.step_stack.count() - 1:
            self.step_stack.setCurrentIndex(curr + 1)
            self._update_step_buttons()

    def _prev_step(self):
        curr = self.step_stack.currentIndex()
        if curr > 0:
            self.step_stack.setCurrentIndex(curr - 1)
            self._update_step_buttons()

    def _update_step_buttons(self):
        curr = self.step_stack.currentIndex()
        total = self.step_stack.count()
        self.lbl_step_indicator.setText(f"Adım {curr + 1} / {total}")
        self.btn_prev_step.setEnabled(curr > 0)
        self.btn_next_step.setEnabled(curr < total - 1)

    def _copy_extension_path(self):
        success, path = copy_extension_path_to_clipboard()
        if success:
            QMessageBox.information(
                self,
                "Yol Kopyalandı 📋",
                f"Eklenti klasör yolu panoya kopyalandı:\n\n{path}\n\n"
                "Tarayıcınızda 'Paketlenmemiş öğe yükle' penceresi açıldığında "
                "Ctrl+V yapıp Enter'a basarak doğrudan seçebilirsiniz!"
            )
        else:
            QMessageBox.warning(self, "Kopyalanamadı", f"Yol kopyalanamadı: {path}")

    def _open_extension_dir(self):
        ext_dir = get_extension_folder_path()
        if os.path.exists(ext_dir):
            copy_extension_path_to_clipboard()
            show_in_explorer(ext_dir)
            QMessageBox.information(
                self,
                "Klasör Açıldı 📁",
                f"Eklenti klasörü Dosya Gezgini'nde açıldı ve yol panoya kopyalandı:\n\n{ext_dir}\n\n"
                "Tarayıcınızda 'Paketlenmemiş öğe yükle'ye basarak bu klasörü seçebilirsiniz."
            )
        else:
            QMessageBox.warning(self, "Bulunamadı", f"Eklenti klasörü bulunamadı: {ext_dir}")

    def _auto_launch_browser(self):
        success, msg = launch_browser_with_extension()
        if success:
            QMessageBox.information(
                self,
                "Otomatik Başlatıldı 🚀",
                f"{msg}\n\nEklenti tarayıcınıza otomatik olarak yüklendi! "
                "RipSync simgesini tarayıcı araç çubuğunda görebilirsiniz."
            )
        else:
            QMessageBox.warning(
                self,
                "Otomatik Başlatılamadı",
                f"{msg}\n\nLütfen görsel rehberdeki adımları izleyerek manuel olarak yükleyiniz."
            )

    def _open_browser_extensions(self):
        success, msg = open_browser_extension_page()
        copy_extension_path_to_clipboard()
        QMessageBox.information(
            self,
            "Tarayıcı Açıldı 🌐",
            "Tarayıcınızın uzantılar sayfası açıldı.\n"
            "Eklenti klasör yolu da panonuza otomatik kopyalandı.\n\n"
            "1. Sağ üstten 'Geliştirici Modu'nu açın.\n"
            "2. 'Paketlenmemiş Öğe Yükle' butonuna tıklayın.\n"
            "3. Açılan pencerede Ctrl+V yapıp Klasörü Seç'e tıklayın!"
        )

    def _copy_token(self):
        if self.bridge_token:
            app = QApplication.instance()
            if app:
                QApplication.clipboard().setText(self.bridge_token)
            QMessageBox.information(self, "Kopyalandı", "Köprü güvenlik anahtarı (token) panoya kopyalandı!")
