import os
import sys
import subprocess
import webbrowser
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from core.paths import get_extension_dir
from ui.tray_icon import create_default_icon

class ExtensionGuideDialog(QDialog):
    """
    User-friendly modal dialog guiding casual users through installing
    the RipSync Chrome / Edge browser extension in 3 easy steps.
    """
    def __init__(self, parent=None, bridge_port: int = 28710):
        super().__init__(parent)
        self.bridge_port = bridge_port
        self.setWindowTitle("RipSync - Tarayıcı Eklentisi Kurulumu")
        self.setWindowIcon(create_default_icon())
        self.setFixedSize(560, 480)
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
            }
            QFrame.stepBox {
                background-color: #1f2335;
                border: 1px solid #292e42;
                border-radius: 8px;
                padding: 10px;
            }
        """)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header Title
        title = QLabel("🌐 Chrome & Edge Eklenti Kurulumu")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #7aa2f7;")
        layout.addWidget(title)

        # Subtitle & Status
        sub = QLabel(f"RipSync köprü sunucusu hazır (Port: {self.bridge_port}) 🟢\n"
                     "Videoları ve indirmeleri tarayıcınızdan otomatik yakalamak için 3 basit adımı uygulayın:")
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #9aa5ce; font-size: 12px; margin-bottom: 4px;")
        layout.addWidget(sub)

        # Step 1
        s1 = QFrame()
        s1.setProperty("class", "stepBox")
        s1_layout = QHBoxLayout(s1)
        s1_layout.setContentsMargins(12, 10, 12, 10)
        
        s1_text = QLabel("<b>1. Adım: Eklenti Klasörünü Açın</b><br>"
                         "<span style='color:#a9b1d6; font-size:11px;'>Eklenti dosyalarının bulunduğu klasörü Dosya Gezgini'nde açar.</span>")
        s1_text.setTextFormat(Qt.TextFormat.RichText)
        s1_btn = QPushButton("📁 Klasörü Aç")
        s1_btn.setObjectName("primaryBtn")
        s1_btn.clicked.connect(self._open_extension_dir)
        
        s1_layout.addWidget(s1_text, 1)
        s1_layout.addWidget(s1_btn, 0)
        layout.addWidget(s1)

        # Step 2
        s2 = QFrame()
        s2.setProperty("class", "stepBox")
        s2_layout = QHBoxLayout(s2)
        s2_layout.setContentsMargins(12, 10, 12, 10)
        
        s2_text = QLabel("<b>2. Adım: Tarayıcı Uzantılar Sayfasına Gidin</b><br>"
                         "<span style='color:#a9b1d6; font-size:11px;'>Chrome'da <code>chrome://extensions</code> veya Edge'de <code>edge://extensions</code> açın.</span>")
        s2_text.setTextFormat(Qt.TextFormat.RichText)
        s2_btn = QPushButton("🌐 Tarayıcıyı Aç")
        s2_btn.clicked.connect(self._open_browser_extensions)
        
        s2_layout.addWidget(s2_text, 1)
        s2_layout.addWidget(s2_btn, 0)
        layout.addWidget(s2)

        # Step 3
        s3 = QFrame()
        s3.setProperty("class", "stepBox")
        s3_layout = QVBoxLayout(s3)
        s3_layout.setContentsMargins(12, 10, 12, 10)
        
        s3_text = QLabel("<b>3. Adım: Geliştirici Modu ile Yükleyin</b><br>"
                         "<span style='color:#a9b1d6; font-size:11px;'>"
                         "• Uzantılar sayfasının sağ üst köşesindeki <b>'Geliştirici Modu'</b> (Developer Mode) anahtarını açın.<br>"
                         "• Sol üstteki <b>'Paketlenmemiş Öğe Yükle'</b> (Load unpacked) butonuna tıklayın.<br>"
                         "• 1. Adımda açılan klasörü seçin. Eklenti anında aktif olacaktır! 🎉"
                         "</span>")
        s3_text.setTextFormat(Qt.TextFormat.RichText)
        s3_layout.addWidget(s3_text)
        layout.addWidget(s3)

        layout.addStretch()

        # Bottom Buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        btn_close = QPushButton("Kapat")
        btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(btn_close)

        layout.addLayout(bottom_layout)

    def _open_extension_dir(self):
        ext_dir = get_extension_dir()
        if os.path.exists(ext_dir):
            try:
                os.startfile(ext_dir)
            except Exception as e:
                QMessageBox.warning(self, "Klasör Açılamadı", f"Klasör açılamadı: {e}")
        else:
            QMessageBox.warning(self, "Bulunamadı", f"Eklenti klasörü bulunamadı: {ext_dir}")

    def _open_browser_extensions(self):
        """Attempts to open chrome extensions or edge extensions."""
        # Note: Browsers block navigation to chrome:// via standard web URLs for security,
        # but we can try launching chrome.exe or edge directly, or fallback to clipboard.
        try:
            # Try launching chrome directly if installed
            chrome_paths = [
                os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            ]
            opened = False
            for p in chrome_paths:
                if os.path.isfile(p):
                    subprocess.Popen([p, "chrome://extensions"])
                    opened = True
                    break
            
            if not opened:
                webbrowser.open("chrome://extensions")
        except Exception:
            pass
        
        QMessageBox.information(
            self,
            "Tarayıcı Açıldı",
            "Tarayıcınızda 'chrome://extensions' (veya Edge kullanıyorsanız 'edge://extensions') sayfasına gidiniz.\n\n"
            "Sağ üstten 'Geliştirici Modu'nu açıp 'Paketlenmemiş Öğe Yükle' butonuna tıklayınız."
        )

