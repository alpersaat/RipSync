import os
import hashlib
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QProgressBar, QGroupBox,
    QFormLayout, QApplication
)

from ui.styles import format_size


class ChecksumWorker(QThread):
    """Calculates MD5, SHA-1, and SHA-256 hashes of a file in the background."""
    sig_progress = pyqtSignal(int)
    sig_finished = pyqtSignal(dict)
    sig_error = pyqtSignal(str)

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if not os.path.exists(self.file_path):
            self.sig_error.emit("Dosya disk üzerinde bulunamadı.")
            return

        try:
            total_size = os.path.getsize(self.file_path)
            md5 = hashlib.md5()
            sha1 = hashlib.sha1()
            sha256 = hashlib.sha256()

            processed = 0
            chunk_size = 1024 * 1024  # 1 MB chunk

            with open(self.file_path, "rb") as f:
                while True:
                    if self._is_cancelled:
                        return
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    md5.update(chunk)
                    sha1.update(chunk)
                    sha256.update(chunk)
                    processed += len(chunk)

                    if total_size > 0:
                        pct = int((processed / total_size) * 100)
                        self.sig_progress.emit(min(100, pct))

            self.sig_finished.emit({
                "md5": md5.hexdigest().lower(),
                "sha1": sha1.hexdigest().lower(),
                "sha256": sha256.hexdigest().lower(),
                "size": total_size
            })
        except Exception as e:
            self.sig_error.emit(f"Hash hesaplama hatası: {str(e)}")


class ChecksumDialog(QDialog):
    """
    Dialog for verifying file integrity using MD5, SHA-1, and SHA-256 hashes.
    Provides instant comparison against expected hashes.
    """
    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.calculated_hashes = {}

        self.setWindowTitle("RipSync - Dosya Bütünlüğü Doğrulayıcı (Checksum / Hash)")
        self.resize(580, 440)
        self._init_ui()
        self._start_calculation()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        # File Info Group
        grp_file = QGroupBox("📁 Dosya Bilgileri")
        f_file = QFormLayout(grp_file)

        fname = os.path.basename(self.file_path)
        fsize = os.path.getsize(self.file_path) if os.path.exists(self.file_path) else 0

        lbl_name = QLabel(fname)
        lbl_name.setStyleSheet("font-weight: bold; color: #7aa2f7;")
        f_file.addRow("Dosya Adı:", lbl_name)

        lbl_path = QLabel(self.file_path)
        lbl_path.setStyleSheet("color: #a9b1d6; font-size: 11px;")
        lbl_path.setWordWrap(True)
        f_file.addRow("Dosya Konumu:", lbl_path)

        lbl_sz = QLabel(format_size(fsize))
        lbl_sz.setStyleSheet("color: #9ece6a; font-weight: bold;")
        f_file.addRow("Boyut:", lbl_sz)

        layout.addWidget(grp_file)

        # Progress bar
        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        self.prog_bar.setStyleSheet("QProgressBar { min-height: 14px; text-align: center; }")
        layout.addWidget(self.prog_bar)

        self.lbl_status = QLabel("Hesaplanıyor... Lütfen bekleyin.")
        self.lbl_status.setStyleSheet("color: #e0af68; font-weight: bold;")
        layout.addWidget(self.lbl_status)

        # Calculated Hashes Group
        grp_hashes = QGroupBox("🔑 Hesaplanan Bütünlük Değerleri (Hashes)")
        f_hashes = QFormLayout(grp_hashes)
        f_hashes.setSpacing(8)

        # MD5
        row_md5 = QHBoxLayout()
        self.edit_md5 = QLineEdit("Hesaplanıyor...")
        self.edit_md5.setReadOnly(True)
        btn_copy_md5 = QPushButton("📋 Kopyala")
        btn_copy_md5.setObjectName("btn_secondary")
        btn_copy_md5.clicked.connect(lambda: self._copy_to_clipboard(self.edit_md5.text()))
        row_md5.addWidget(self.edit_md5)
        row_md5.addWidget(btn_copy_md5)
        f_hashes.addRow("MD5:", row_md5)

        # SHA-1
        row_sha1 = QHBoxLayout()
        self.edit_sha1 = QLineEdit("Hesaplanıyor...")
        self.edit_sha1.setReadOnly(True)
        btn_copy_sha1 = QPushButton("📋 Kopyala")
        btn_copy_sha1.setObjectName("btn_secondary")
        btn_copy_sha1.clicked.connect(lambda: self._copy_to_clipboard(self.edit_sha1.text()))
        row_sha1.addWidget(self.edit_sha1)
        row_sha1.addWidget(btn_copy_sha1)
        f_hashes.addRow("SHA-1:", row_sha1)

        # SHA-256
        row_sha256 = QHBoxLayout()
        self.edit_sha256 = QLineEdit("Hesaplanıyor...")
        self.edit_sha256.setReadOnly(True)
        btn_copy_sha256 = QPushButton("📋 Kopyala")
        btn_copy_sha256.setObjectName("btn_secondary")
        btn_copy_sha256.clicked.connect(lambda: self._copy_to_clipboard(self.edit_sha256.text()))
        row_sha256.addWidget(self.edit_sha256)
        row_sha256.addWidget(btn_copy_sha256)
        f_hashes.addRow("SHA-256:", row_sha256)

        layout.addWidget(grp_hashes)

        # Verification Match Group
        grp_verify = QGroupBox("🛡️ Hash Karşılaştırma & Doğrulama")
        v_verify = QVBoxLayout(grp_verify)

        lbl_prompt = QLabel("Web sitesinde veya indirme sayfasında belirtilen orijinal hash değerini buraya yapıştırın:")
        lbl_prompt.setStyleSheet("color: #c0caf5; font-size: 11px;")
        v_verify.addWidget(lbl_prompt)

        self.edit_expected = QLineEdit()
        self.edit_expected.setPlaceholderText("Beklenen MD5, SHA-1 veya SHA-256 hash değerini yapıştırın...")
        self.edit_expected.textChanged.connect(self._check_match)
        v_verify.addWidget(self.edit_expected)

        self.lbl_verdict = QLabel("ℹ️ Karşılaştırmak için bir hash değeri girin.")
        self.lbl_verdict.setStyleSheet("color: #7982a9; font-weight: bold; padding: 4px;")
        v_verify.addWidget(self.lbl_verdict)

        layout.addWidget(grp_verify)

        # Bottom Close button
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_close = QPushButton("Kapat")
        btn_close.setObjectName("btn_secondary")
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)

    def _start_calculation(self):
        self.worker = ChecksumWorker(self.file_path)
        self.worker.sig_progress.connect(self.prog_bar.setValue)
        self.worker.sig_finished.connect(self._on_finished)
        self.worker.sig_error.connect(self._on_error)
        self.worker.start()

    def _on_finished(self, data: dict):
        self.calculated_hashes = data
        self.edit_md5.setText(data.get("md5", ""))
        self.edit_sha1.setText(data.get("sha1", ""))
        self.edit_sha256.setText(data.get("sha256", ""))

        self.prog_bar.setValue(100)
        self.lbl_status.setText("✔ Hash değerleri başarıyla hesaplandı.")
        self.lbl_status.setStyleSheet("color: #9ece6a; font-weight: bold;")
        self._check_match()

    def _on_error(self, err_msg: str):
        self.lbl_status.setText(f"❌ {err_msg}")
        self.lbl_status.setStyleSheet("color: #f7768e; font-weight: bold;")

    def _check_match(self):
        if not self.calculated_hashes:
            return

        expected = self.edit_expected.text().strip().lower()
        if not expected:
            self.lbl_verdict.setText("ℹ️ Karşılaştırmak için beklenen hash değerini buraya yapıştırın.")
            self.lbl_verdict.setStyleSheet("color: #7982a9; font-weight: bold; padding: 4px;")
            return

        md5 = self.calculated_hashes.get("md5", "")
        sha1 = self.calculated_hashes.get("sha1", "")
        sha256 = self.calculated_hashes.get("sha256", "")

        if expected == md5:
            self.lbl_verdict.setText("✅ MD5 Hash Doğrulandı! (Dosya %100 Orijinal ve Bozulmamış)")
            self.lbl_verdict.setStyleSheet("background-color: #1e3a2e; color: #73daca; font-weight: bold; padding: 6px; border-radius: 4px; border: 1px solid #73daca;")
        elif expected == sha1:
            self.lbl_verdict.setText("✅ SHA-1 Hash Doğrulandı! (Dosya %100 Orijinal ve Bozulmamış)")
            self.lbl_verdict.setStyleSheet("background-color: #1e3a2e; color: #73daca; font-weight: bold; padding: 6px; border-radius: 4px; border: 1px solid #73daca;")
        elif expected == sha256:
            self.lbl_verdict.setText("✅ SHA-256 Hash Doğrulandı! (Dosya %100 Orijinal ve Bozulmamış)")
            self.lbl_verdict.setStyleSheet("background-color: #1e3a2e; color: #73daca; font-weight: bold; padding: 6px; border-radius: 4px; border: 1px solid #73daca;")
        else:
            self.lbl_verdict.setText("❌ Hash Uyuşmuyor! Dosya eksik indirilmiş, bozuk veya değiştirilmiş olabilir.")
            self.lbl_verdict.setStyleSheet("background-color: #3b1e28; color: #f7768e; font-weight: bold; padding: 6px; border-radius: 4px; border: 1px solid #f7768e;")

    def _copy_to_clipboard(self, text: str):
        if text and not text.startswith("Hesaplanıyor"):
            cb = QApplication.clipboard()
            if cb:
                cb.setText(text)

    def closeEvent(self, event):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(1000)
        super().closeEvent(event)

