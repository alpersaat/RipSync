"""
RipSync Clipboard Privacy & First-Run Consent Dialog
Displays a clear, privacy-focused consent prompt on first launch or when clipboard monitoring is configured.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QWidget
)
from ui.styles import T  # noqa: F401  (tema tokenlari)


class ClipboardConsentDialog(QDialog):
    """
    Dialog asking the user whether they want to enable clipboard link monitoring.
    Explicitly informs the user about privacy safeguards (passwords/cards never scanned).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pano İzleme ve Gizlilik - RipSync")
        self.setFixedSize(480, 310)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setModal(True)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header with icon
        header_layout = QHBoxLayout()
        lbl_icon = QLabel("📋")
        lbl_icon.setStyleSheet("font-size: 32px;")
        
        lbl_title = QLabel("Pano İzleme Özelliği")
        lbl_title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {T['text_primary']};")
        
        header_layout.addWidget(lbl_icon)
        header_layout.addWidget(lbl_title)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Main explanation card
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {T['bg_card']};
                border: 1px solid {T['border_panel']};
                border-radius: 8px;
                padding: 8px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(8)

        lbl_desc = QLabel(
            "RipSync, kopyaladığınız medya (YouTube, Instagram vb.) ve dosya indirme "
            "bağlantılarını otomatik olarak algılayıp hızlı indirme penceresi sunabilir."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"color: {T['text_muted']}; font-size: 12px;")
        card_layout.addWidget(lbl_desc)

        lbl_privacy = QLabel(
            "🔒 <b>Gizliliğiniz Güvende:</b><br>"
            "• Şifreler, kredi kartları, API tokenları ve özel metinler asla taranmaz veya bellekte tutulmaz.<br>"
            "• Yalnızca doğrudan indirilebilir web URL'leri kontrol edilir.<br>"
            "• Bu ayarı istediğiniz an Ayarlar penceresinden değiştirebilirsiniz."
        )
        lbl_privacy.setWordWrap(True)
        lbl_privacy.setStyleSheet(f"color: {T['text_muted']}; font-size: 11px; background-color: {T['bg_panel']}; border-radius: 6px; padding: 8px;")
        card_layout.addWidget(lbl_privacy)

        layout.addWidget(card)

        # Prompt question
        lbl_question = QLabel("Pano izlemeyi etkinleştirmek istiyor musunuz?")
        lbl_question.setStyleSheet(f"font-weight: 600; color: {T['text_primary']}; font-size: 13px;")
        layout.addWidget(lbl_question)

        layout.addStretch()

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_disable = QPushButton("Hayır, Kapalı Kalsın")
        self.btn_disable.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_disable.setStyleSheet(f"""
            QPushButton {{
                background-color: {T['bg_panel']};
                color: {T['text_primary']};
                border: 1px solid {T['border']};
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {T['bg_hover']};
            }}
        """)
        self.btn_disable.clicked.connect(self.reject)

        self.btn_enable = QPushButton("✓ Evet, Etkinleştir")
        self.btn_enable.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_enable.setDefault(True)
        self.btn_enable.setStyleSheet(f"""
            QPushButton {{
                background-color: {T['accent_primary']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {T['accent_hover']};
            }}
        """)
        self.btn_enable.clicked.connect(self.accept)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_disable)
        btn_layout.addWidget(self.btn_enable)
        layout.addLayout(btn_layout)

    @classmethod
    def ask_consent(cls, parent=None) -> bool:
        """Helper to show modal consent dialog and return True if user approved."""
        dlg = cls(parent)
        result = dlg.exec()
        return result == QDialog.DialogCode.Accepted
