import os
from typing import Dict, Any, Optional
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QGroupBox, QFormLayout,
    QApplication, QMessageBox
)

from ui.styles import format_size, format_speed, format_eta, T
from core.paths import show_in_explorer


class DownloadPropertiesDialog(QDialog):
    """
    Detailed properties dialog for a download task.
    Displays file paths, URLs, server capabilities, connections, and progress timestamps.
    """
    def __init__(self, download_rec: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.rec = download_rec

        self.setWindowTitle(f"RipSync - İndirme Özellikleri ({self.rec.get('filename', 'Dosya')})")
        self.resize(620, 520)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        # 1. File Details Group
        grp_file = QGroupBox("📁 Dosya Bilgileri")
        f_file = QFormLayout(grp_file)
        f_file.setSpacing(8)

        fname = self.rec.get("filename", "--")
        lbl_name = QLabel(fname)
        lbl_name.setStyleSheet(f"font-weight: bold; color: {T['accent']}; font-size: 13px;")
        lbl_name.setWordWrap(True)
        f_file.addRow("Dosya Adı:", lbl_name)

        spath = self.rec.get("save_path", "--")
        path_row = QHBoxLayout()
        edit_path = QLineEdit(spath)
        edit_path.setReadOnly(True)
        btn_copy_path = QPushButton("📋 Kopyala")
        btn_copy_path.setObjectName("btn_secondary")
        btn_copy_path.clicked.connect(lambda: self._copy_text(spath))

        btn_show_folder = QPushButton("📂 Klasörde Göster")
        btn_show_folder.setObjectName("btn_secondary")
        btn_show_folder.clicked.connect(self._open_in_folder)

        path_row.addWidget(edit_path)
        path_row.addWidget(btn_copy_path)
        path_row.addWidget(btn_show_folder)
        f_file.addRow("Kayıt Konumu:", path_row)

        tot = self.rec.get("total_size", -1)
        done = self.rec.get("downloaded_size", 0)
        status = self.rec.get("status", "Queued")

        size_str = format_size(tot) if tot > 0 else "Bilinmiyor"
        done_str = format_size(done) if done > 0 else "0 KB"
        pct_val = int((done / tot) * 100) if tot > 0 else (100 if status == "Completed" else 0)

        lbl_sizes = QLabel(f"{done_str} / {size_str} (%{pct_val})")
        lbl_sizes.setStyleSheet(f"color: {T['success']}; font-weight: bold;")
        f_file.addRow("İndirilen / Toplam:", lbl_sizes)

        # Status Badge
        lbl_status = QLabel(status)
        if status == "Completed":
            lbl_status.setStyleSheet(f"color: {T['success']}; font-weight: bold;")
        elif status in ("Downloading", "Probing", "Retrying"):
            lbl_status.setStyleSheet(f"color: {T['accent']}; font-weight: bold;")
        elif status == "Paused":
            lbl_status.setStyleSheet(f"color: {T['warning']}; font-weight: bold;")
        else:
            lbl_status.setStyleSheet(f"color: {T['danger']}; font-weight: bold;")
        f_file.addRow("İndirme Durumu:", lbl_status)

        layout.addWidget(grp_file)

        # 2. Connection & Server Group
        grp_net = QGroupBox("🌐 Bağlantı ve Sunucu Detayları")
        f_net = QFormLayout(grp_net)
        f_net.setSpacing(8)

        url = self.rec.get("url", "--")
        url_row = QHBoxLayout()
        edit_url = QLineEdit(url)
        edit_url.setReadOnly(True)
        btn_copy_url = QPushButton("📋 Kopyala")
        btn_copy_url.setObjectName("btn_secondary")
        btn_copy_url.clicked.connect(lambda: self._copy_text(url))
        url_row.addWidget(edit_url)
        url_row.addWidget(btn_copy_url)
        f_net.addRow("Kaynak Bağlantı (URL):", url_row)

        headers = self.rec.get("headers") or {}
        referer = headers.get("Referer") or "--"
        ref_row = QHBoxLayout()
        edit_ref = QLineEdit(referer)
        edit_ref.setReadOnly(True)
        btn_copy_ref = QPushButton("📋 Kopyala")
        btn_copy_ref.setObjectName("btn_secondary")
        btn_copy_ref.clicked.connect(lambda: self._copy_text(referer))
        ref_row.addWidget(edit_ref)
        ref_row.addWidget(btn_copy_ref)
        f_net.addRow("Yönlendiren (Referer):", ref_row)

        conns = self.rec.get("connections", 8)
        lbl_conns = QLabel(f"{conns} Eşzamanlı Parça / Bağlantı (Range Split)")
        lbl_conns.setStyleSheet(f"color: {T['color_purple']};")
        f_net.addRow("Kanal Sayısı:", lbl_conns)

        quality = self.rec.get("quality", "max")
        lbl_quality = QLabel(quality.upper() if quality else "Maksimum")
        f_net.addRow("Medya Kalitesi:", lbl_quality)

        prio = (self.rec.get("priority") or "normal").lower()
        prio_map = {
            "high": ("🚀 Yüksek Öncelik (%70 Hız Payı)", T['accent']),
            "normal": ("⚖️ Normal Öncelik (Dengeli)", T['success']),
            "low": ("🐢 Düşük Öncelik (Arka Plan - %10 Hız Payı)", T['warning'])
        }
        p_txt, p_col = prio_map.get(prio, ("⚖️ Normal", T['success']))
        lbl_prio = QLabel(p_txt)
        lbl_prio.setStyleSheet(f"color: {p_col}; font-weight: bold;")
        f_net.addRow("Bant Genişliği Önceliği:", lbl_prio)

        layout.addWidget(grp_net)

        # 3. Timestamps & Performance Group
        grp_time = QGroupBox("⏱ Tarih ve Performans")
        f_time = QFormLayout(grp_time)
        f_time.setSpacing(8)

        date_add = self.rec.get("date_added", "--")
        f_time.addRow("Eklenme Tarihi:", QLabel(date_add))

        spd = self.rec.get("speed", 0)
        lbl_speed = QLabel(format_speed(spd) if spd > 0 else "--")
        lbl_speed.setStyleSheet(f"color: {T['accent']}; font-weight: bold;")
        f_time.addRow("Anlık / Son Hız:", lbl_speed)

        eta = self.rec.get("eta", 0)
        lbl_eta = QLabel(format_eta(eta) if eta > 0 else "--")
        f_time.addRow("Kalan Süre:", lbl_eta)

        layout.addWidget(grp_time)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_close = QPushButton("Kapat")
        btn_close.setObjectName("btn_secondary")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _copy_text(self, text: str):
        if text and text != "--":
            cb = QApplication.clipboard()
            if cb:
                cb.setText(text)

    def _open_in_folder(self):
        spath = self.rec.get("save_path", "")
        if os.path.exists(spath) or os.path.exists(os.path.dirname(spath)):
            show_in_explorer(spath)
        else:
            QMessageBox.warning(self, "Uyarı", "Dosya veya klasör diskte bulunamadı.")

