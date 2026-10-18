from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QMessageBox
)
from PyQt6.QtGui import QFont
from ui.styles import T  # noqa: F401  (tema tokenlari)


class PowerCountdownDialog(QDialog):
    """Shutdown/sleep countdown dialog.

    The actual power action is *never* performed automatically: when the
    countdown reaches zero (or the user clicks "Şimdi Kapat/Uyut") a blocking
    confirmation is shown first, warning about unsaved work. Only an explicit
    user confirmation triggers ``confirmed``.
    """
    cancelled = pyqtSignal()
    suspend_requested = pyqtSignal()
    resume_requested = pyqtSignal()
    confirmed = pyqtSignal()  # user explicitly confirmed shutdown/sleep

    FLASH_THRESHOLD = 10  # seconds remaining when countdown starts flashing

    def __init__(self, action: str, total_seconds: int = 30, parent=None):
        super().__init__(parent)
        self.action = action  # "shutdown" or "sleep"
        self.total_seconds = total_seconds
        self.remaining_seconds = total_seconds
        self.is_suspended = False
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._toggle_flash)
        self._flashing = False

        action_name = "Bilgisayarı Kapat" if action == "shutdown" else "Uyku Moduna Al"
        self.setWindowTitle(f"RipSync - {action_name} Onayı")
        self.setFixedSize(520, 300)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint
        )

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 22, 24, 22)

        action_icon = "🛑" if self.action == "shutdown" else "🌙"
        action_title = "Bilgisayar Kapatılıyor" if self.action == "shutdown" else "Uyku Moduna Geçiliyor"

        self.lbl_title = QLabel(f"{action_icon} Kuyruk Bitti: {action_title}")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {T['text_primary']};")
        layout.addWidget(self.lbl_title)

        self.lbl_info = QLabel(
            "Kuyruktaki tüm indirmeler tamamlandı.\n"
            "İşlemin gerçekleşmesine kalan süre:"
        )
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_info.setStyleSheet(f"color: {T['text_muted']}; font-size: 12px;")
        layout.addWidget(self.lbl_info)

        self.lbl_warning = QLabel(
            "⚠️ Kaydedilmemiş işleriniz kaybolabilir. "
            "İşlemi onaylamanız gerekecek."
        )
        self.lbl_warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_warning.setStyleSheet(
            f"color: {T['danger']}; font-size: 12px; font-weight: bold;"
        )
        self.lbl_warning.setWordWrap(True)
        layout.addWidget(self.lbl_warning)

        self.lbl_countdown = QLabel(f"{self.remaining_seconds} saniye")
        self.lbl_countdown.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_countdown.setStyleSheet(
            f"font-size: 38px; font-weight: bold; color: {T['color_orange']}; margin: 4px;"
        )
        layout.addWidget(self.lbl_countdown)

        self.progress = QProgressBar()
        self.progress.setRange(0, self.total_seconds)
        self.progress.setValue(self.total_seconds)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(14)
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {T['border']};
                border-radius: 7px;
                background-color: {T['bg_main']};
            }}
            QProgressBar::chunk {{
                background-color: {T['danger']};
                border-radius: 7px;
            }}
        """)
        layout.addWidget(self.progress)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.btn_cancel = QPushButton("İşlemi İptal Et")
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: {T['border']};
                color: {T['text_primary']};
                font-weight: bold;
                padding: 8px 14px;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {T['border']};
            }}
        """)
        self.btn_cancel.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_suspend = QPushButton("⏸️ Askıya Al")
        self.btn_suspend.setStyleSheet(f"""
            QPushButton {{
                background-color: {T['accent']};
                color: {T['bg_main']};
                font-weight: bold;
                padding: 8px 14px;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {T['color_blue']};
            }}
        """)
        self.btn_suspend.clicked.connect(self._toggle_suspend)
        btn_layout.addWidget(self.btn_suspend)

        btn_layout.addStretch()

        self.btn_now = QPushButton("Şimdi Kapat" if self.action == "shutdown" else "Şimdi Uyut")
        self.btn_now.setObjectName("btn_now")
        self.btn_now.setStyleSheet(f"""
            QPushButton#btn_now {{
                background-color: {T['danger']};
                color: {T['text_on_accent']};
                font-weight: bold;
                padding: 10px 18px;
                border-radius: 6px;
                font-size: 13px;
            }}
            QPushButton#btn_now:hover {{
                background-color: {T['danger']};
            }}
        """)
        self.btn_now.clicked.connect(self._on_now)
        btn_layout.addWidget(self.btn_now)

        layout.addLayout(btn_layout)

    def update_countdown(self, seconds: int):
        if not self.is_suspended:
            self.remaining_seconds = seconds
            self.lbl_countdown.setText(f"{seconds} saniye")
            self.progress.setValue(seconds)
            self._apply_flash_state(seconds)

    def _apply_flash_state(self, seconds: int):
        if seconds <= self.FLASH_THRESHOLD and seconds > 0 and not self._flashing:
            self._flashing = True
            self._flash_timer.start(500)
        elif seconds > self.FLASH_THRESHOLD and self._flashing:
            self._stop_flash()
            self.lbl_countdown.setStyleSheet(
                f"font-size: 38px; font-weight: bold; color: {T['color_orange']}; margin: 4px;"
            )

    def _toggle_flash(self):
        current = self.lbl_countdown.styleSheet()
        flash_color = T['danger'] if self.action == "shutdown" else T['color_purple']
        if flash_color in current:
            self.lbl_countdown.setStyleSheet(
                f"font-size: 38px; font-weight: bold; color: {T['color_orange']}; margin: 4px;"
            )
        else:
            self.lbl_countdown.setStyleSheet(
                f"font-size: 38px; font-weight: bold; color: {flash_color}; margin: 4px;"
            )

    def _stop_flash(self):
        self._flashing = False
        self._flash_timer.stop()

    def set_suspended(self, suspended: bool, reason: str = "Aktif kullanım algılandı"):
        self._stop_flash()
        self.is_suspended = suspended
        if suspended:
            self.lbl_countdown.setText("⏸️ Askıya Alındı")
            self.lbl_countdown.setStyleSheet(f"font-size: 26px; font-weight: bold; color: {T['accent']}; margin: 2px;")
            self.lbl_info.setText(f"⚠️ {reason}.\nAçık işlerinizi korumak için geri sayım durduruldu.")
            self.lbl_info.setStyleSheet(f"color: {T['accent']}; font-size: 12px; font-weight: bold;")
            self.btn_suspend.setText("▶️ Devam Ettir")
            self.btn_suspend.setStyleSheet(f"""
                QPushButton {{
                    background-color: {T['success']};
                    color: {T['bg_main']};
                    font-weight: bold;
                    padding: 8px 14px;
                    border-radius: 6px;
                }}
                QPushButton:hover {{
                    background-color: {T['success']};
                }}
            """)
        else:
            self.lbl_countdown.setText(f"{self.remaining_seconds} saniye")
            self.lbl_countdown.setStyleSheet(f"font-size: 38px; font-weight: bold; color: {T['color_orange']}; margin: 4px;")
            self.lbl_info.setText(
                "Kuyruktaki tüm indirmeler tamamlandı.\n"
                "İşlemin gerçekleşmesine kalan süre:"
            )
            self.lbl_info.setStyleSheet(f"color: {T['text_muted']}; font-size: 12px;")
            self.btn_suspend.setText("⏸️ Askıya Al")
            self.btn_suspend.setStyleSheet(f"""
                QPushButton {{
                    background-color: {T['accent']};
                    color: {T['bg_main']};
                    font-weight: bold;
                    padding: 8px 14px;
                    border-radius: 6px;
                }}
                QPushButton:hover {{
                    background-color: {T['color_blue']};
                }}
            """)

    def _toggle_suspend(self):
        if self.is_suspended:
            self.resume_requested.emit()
        else:
            self.suspend_requested.emit()

    def _on_cancel(self):
        self._stop_flash()
        self.cancelled.emit()
        self.reject()

    def _on_now(self):
        """User wants to execute immediately: require explicit confirmation."""
        self._stop_flash()
        if self._request_confirmation():
            self.confirmed.emit()
            self.accept()

    def closeEvent(self, event):
        self._stop_flash()
        self.cancelled.emit()
        event.accept()

    @staticmethod
    def request_confirmation(action: str, parent=None) -> bool:
        """Blocking confirmation shown before shutdown/sleep.

        Returns True only when the user explicitly confirms.
        """
        is_shutdown = action == "shutdown"
        verb = "Kapatılacak" if is_shutdown else "Uyku moduna alınacak"
        title = "Bilgisayar Kapatma Onayı" if is_shutdown else "Uyku Modu Onayı"
        icon = QMessageBox.Icon.Warning if is_shutdown else QMessageBox.Icon.Question

        box = QMessageBox(parent)
        box.setIcon(icon)
        box.setWindowTitle(f"RipSync - {title}")
        box.setText(f"{verb}. Bu işlem geri alınamaz.")
        box.setInformativeText(
            "Kaydedilmemiş işleriniz (açık indirmeler, açık dosyalar) kaybolabilir.\n"
            "İşleme devam etmek istediğinizden emin misiniz?"
        )
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        box.setEscapeButton(QMessageBox.StandardButton.No)
        yes_btn = box.button(QMessageBox.StandardButton.Yes)
        yes_btn.setText("Evet, Onaylıyorum")
        no_btn = box.button(QMessageBox.StandardButton.No)
        no_btn.setText("Hayır, İptal Et")
        return box.exec() == QMessageBox.StandardButton.Yes
