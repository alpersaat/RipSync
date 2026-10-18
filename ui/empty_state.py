"""Basit kullanıcı katmanı: boş durum ekranı.

Liste boşken tablo yerine yönlendirme ekranı gösterir: kullanıcı ya
"➕ URL Ekle"ye basar ya da bir linki pencereye bırakır.
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget, QFrame,
)

from ui.styles import T


class EmptyStateWidget(QFrame):
    """Tablo boş iken görünen yönlendirme ekranı."""

    add_clicked = pyqtSignal()
    batch_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("empty_state_panel")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 8, 12, 8)

        lbl_emoji = QLabel("⬇️")
        lbl_emoji.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_emoji.setStyleSheet(f"font-size: 48px; color: {T['accent']};")
        layout.addWidget(lbl_emoji)

        lbl_title = QLabel("Henüz indirme yok")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setStyleSheet(f"font-size: 17px; font-weight: bold; color: {T['text_primary']};")
        layout.addWidget(lbl_title)

        lbl_hint = QLabel(
            "Başlamak için bir indirme ekleyin:\n"
            "➕ URL Ekle'ye basın ya da bir bağlantıyı bu pencereye bırakın."
        )
        lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_hint.setWordWrap(True)
        lbl_hint.setStyleSheet(f"font-size: 13px; color: {T['text_muted']};")
        layout.addWidget(lbl_hint)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_row.setSpacing(8)

        btn_add = QPushButton("➕ URL Ekle")
        btn_add.setStyleSheet(
            f"QPushButton {{ background-color: {T['accent_primary']}; color: {T['text_on_accent']};"
            f" border: none; border-radius: 6px; padding: 8px 20px; font-weight: bold; font-size: 13px; }}"
            f"QPushButton:hover {{ background-color: {T['accent_hover']}; }}"
            f"QPushButton:pressed {{ background-color: {T['accent_active']}; }}"
        )
        btn_add.clicked.connect(self.add_clicked.emit)
        btn_row.addWidget(btn_add)

        btn_batch = QPushButton("📋 Toplu Link Ekle")
        btn_batch.setObjectName("btn_secondary")
        btn_batch.clicked.connect(self.batch_clicked.emit)
        btn_row.addWidget(btn_batch)

        layout.addLayout(btn_row)
