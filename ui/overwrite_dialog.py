import os
import time
from datetime import datetime
from typing import Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QFormLayout
)
from PyQt6.QtCore import Qt
from ui.styles import format_size
from core.paths import resolve_file_conflict


class OverwriteConfirmDialog(QDialog):
    """
    Dialog displayed when an incoming download would overwrite an existing file on disk.
    
    Prevents silent data loss by asking the user to explicitly confirm overwrite,
    safely auto-rename the new download (e.g. file (1).ext), or cancel.
    """
    ACTION_CANCEL = "cancel"
    ACTION_OVERWRITE = "overwrite"
    ACTION_AUTO_RENAME = "auto_rename"

    def __init__(self, target_dir: str, filename: str, parent=None):
        super().__init__(parent)
        self.target_dir = os.path.abspath(target_dir) if target_dir else ""
        self.filename = filename or ""
        self.full_path = os.path.join(self.target_dir, self.filename) if self.target_dir and self.filename else ""
        self.action = self.ACTION_CANCEL
        self.resolved_filename = self.filename

        self.setWindowTitle("⚠️ Dosya Üzerine Yazma Onayı - RipSync")
        self.resize(520, 320)
        self.setMinimumWidth(460)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(18, 18, 18, 18)

        # Header alert banner
        lbl_banner = QLabel("⚠️ DİKKAT: Hedef klasörde aynı isimde bir dosya zaten mevcut!")
        lbl_banner.setStyleSheet("""
            QLabel {
                background-color: #2b1f1f;
                color: #f7768e;
                font-weight: bold;
                font-size: 13px;
                padding: 10px 14px;
                border-radius: 6px;
                border: 1px solid #f7768e;
            }
        """)
        lbl_banner.setWordWrap(True)
        layout.addWidget(lbl_banner)

        # Warning explanation text
        lbl_info = QLabel(
            "Dosya çakışması kuralınız <b>'Üzerine Yaz'</b> olarak ayarlanmış.<br>"
            "Bu indirme başlatılırsa mevcut dosyanın içeriği <b>kalıcı olarak silinecek veya değiştirilecektir</b>."
        )
        lbl_info.setStyleSheet("color: #cfc9c2; font-size: 12px; line-height: 1.4;")
        lbl_info.setWordWrap(True)
        layout.addWidget(lbl_info)

        # Details box
        grp = QGroupBox("Mevcut Dosya Bilgileri")
        form = QFormLayout(grp)
        form.setSpacing(8)

        form.addRow("Dosya Adı:", QLabel(f"<b>{self.filename}</b>"))
        form.addRow("Klasör:", QLabel(self.target_dir or "Bilinmiyor"))

        file_exists = bool(self.full_path and os.path.exists(self.full_path))
        if file_exists:
            try:
                st = os.stat(self.full_path)
                form.addRow("Mevcut Boyut:", QLabel(format_size(st.st_size)))
                mtime_str = datetime.fromtimestamp(st.st_mtime).strftime("%d.%m.%Y %H:%M:%S")
                form.addRow("Değiştirilme:", QLabel(mtime_str))
            except Exception:
                form.addRow("Durum:", QLabel("Dosya mevcut (bilgiler okunamadı)"))
        else:
            form.addRow("Durum:", QLabel("⚠️ Dosya mevcut değil"))

        layout.addWidget(grp)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        # Auto Rename Button (Recommended safe choice)
        self.btn_rename = QPushButton("🔄 Otomatik Yeniden Adlandır")
        self.btn_rename.setStyleSheet("""
            QPushButton {
                background-color: #7aa2f7;
                color: #1a1b26;
                font-weight: bold;
                padding: 7px 14px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #89b4fa;
            }
        """)
        self.btn_rename.setToolTip("Mevcut dosyayı korur, yeni indirmeyi 'dosya (1).ext' olarak adlandırır.")
        self.btn_rename.clicked.connect(self._on_auto_rename)
        btn_layout.addWidget(self.btn_rename)

        btn_layout.addStretch()

        # Overwrite Button (Danger button)
        self.btn_overwrite = QPushButton("⚠️ Üzerine Yaz")
        self.btn_overwrite.setStyleSheet("""
            QPushButton {
                background-color: #c53b53;
                color: #ffffff;
                font-weight: bold;
                padding: 7px 14px;
                border-radius: 5px;
                border: 1px solid #f7768e;
            }
            QPushButton:hover {
                background-color: #f7768e;
                color: #1a1b26;
            }
        """)
        self.btn_overwrite.setToolTip("Mevcut dosyanın içeriğini kalıcı olarak silip yeni indirilen ile değiştirir.")
        self.btn_overwrite.clicked.connect(self._on_overwrite)
        btn_layout.addWidget(self.btn_overwrite)

        # Cancel Button
        self.btn_cancel = QPushButton("İptal")
        self.btn_cancel.setObjectName("btn_secondary")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def _on_auto_rename(self):
        new_name, _ = resolve_file_conflict(self.target_dir, self.filename, action="auto_rename")
        self.resolved_filename = new_name
        self.action = self.ACTION_AUTO_RENAME
        self.accept()

    def _on_overwrite(self):
        self.resolved_filename = self.filename
        self.action = self.ACTION_OVERWRITE
        self.accept()

    def get_action(self) -> str:
        return self.action

    def get_resolved_filename(self) -> str:
        return self.resolved_filename
