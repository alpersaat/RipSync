from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar
)
from PyQt6.QtGui import QFont

class PowerCountdownDialog(QDialog):
    cancelled = pyqtSignal()

    def __init__(self, action: str, total_seconds: int = 30, parent=None):
        super().__init__(parent)
        self.action = action  # "shutdown" or "sleep"
        self.total_seconds = total_seconds
        self.remaining_seconds = total_seconds

        action_name = "Bilgisayarı Kapat" if action == "shutdown" else "Uyku Moduna Al"
        self.setWindowTitle(f"RipSync - {action_name}")
        self.setFixedSize(420, 210)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint
        )

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        action_icon = "🛑" if self.action == "shutdown" else "🌙"
        action_title = "Bilgisayar Kapatılıyor" if self.action == "shutdown" else "Uyku Moduna Geçiliyor"

        self.lbl_title = QLabel(f"{action_icon} Kuyruk Bitti: {action_title}")
        self.lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f7768e if self.action == 'shutdown' else #7aa2f7;")
        if self.action == "shutdown":
            self.lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f7768e;")
        else:
            self.lbl_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #bb9af7;")
        layout.addWidget(self.lbl_title)

        self.lbl_info = QLabel(
            f"Kuyruktaki tüm indirmeler tamamlandı.\n"
            f"İşlemin gerçekleşmesine kalan süre:"
        )
        self.lbl_info.setStyleSheet("color: #c0caf5; font-size: 12px;")
        layout.addWidget(self.lbl_info)

        self.lbl_countdown = QLabel(f"{self.remaining_seconds} saniye")
        self.lbl_countdown.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_countdown.setStyleSheet("font-size: 26px; font-weight: bold; color: #ff9e64; margin: 4px;")
        layout.addWidget(self.lbl_countdown)

        self.progress = QProgressBar()
        self.progress.setRange(0, self.total_seconds)
        self.progress.setValue(self.total_seconds)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        layout.addWidget(self.progress)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("İşlemi İptal Et")
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #f7768e;
                color: #ffffff;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #ff899d;
            }
        """)
        self.btn_cancel.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_now = QPushButton("Şimdi Gerçekleştir")
        self.btn_now.setObjectName("btn_secondary")
        self.btn_now.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_now)

        layout.addLayout(btn_layout)

    def update_countdown(self, seconds: int):
        self.remaining_seconds = seconds
        self.lbl_countdown.setText(f"{seconds} saniye")
        self.progress.setValue(seconds)

    def _on_cancel(self):
        self.cancelled.emit()
        self.reject()

    def closeEvent(self, event):
        self.cancelled.emit()
        event.accept()
