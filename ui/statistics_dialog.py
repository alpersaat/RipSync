import os
from typing import Dict, Any
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QGridLayout, QFrame,
    QProgressBar, QScrollArea, QWidget
)

from ui.styles import format_size, T
from core.database import Database
from core.paths import get_disk_total_and_free


class StatCard(QFrame):
    """Modern metric card with title, large value, and subtle icon/subtext."""
    def __init__(self, title: str, value: str, subtext: str = "", accent_color: str = T['accent'], parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {T['bg_panel']};
                border: 1px solid {T['border']};
                border-radius: 8px;
                padding: 10px;
            }}
            QFrame:hover {{
                border-color: {accent_color};
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"color: {T['text_secondary']}; font-size: 11px; font-weight: bold;")
        layout.addWidget(lbl_title)

        lbl_val = QLabel(value)
        lbl_val.setStyleSheet(f"color: {accent_color}; font-size: 20px; font-weight: bold;")
        layout.addWidget(lbl_val)

        if subtext:
            lbl_sub = QLabel(subtext)
            lbl_sub.setStyleSheet(f"color: {T['text_muted']}; font-size: 11px;")
            layout.addWidget(lbl_sub)


class StatisticsDialog(QDialog):
    """
    Download statistics & traffic overview dialog.
    Displays all-time downloaded bytes, completed files, today's traffic, and category breakdown.
    """
    def __init__(self, db: Database, default_download_dir: str = "", parent=None):
        super().__init__(parent)
        self.db = db
        self.default_download_dir = default_download_dir or os.path.join(os.path.expanduser("~"), "Downloads")

        self.setWindowTitle("RipSync - İndirme İstatistikleri & Trafik Özeti")
        self.resize(600, 520)
        self.setMinimumWidth(540)
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(14)
        main_layout.setContentsMargins(18, 18, 18, 18)

        # Header Title
        lbl_header = QLabel("📊 İndirme İstatistikleri ve Ağ Trafiği")
        lbl_header.setStyleSheet(f"color: {T['text_primary']}; font-size: 15px; font-weight: bold;")
        main_layout.addWidget(lbl_header)

        # Key Metrics Grid (4 Cards)
        self.grid_cards = QGridLayout()
        self.grid_cards.setSpacing(10)
        main_layout.addLayout(self.grid_cards)

        # Category Breakdown Group
        grp_cat = QGroupBox("📁 Kategori Dağılımı")
        self.cat_layout = QVBoxLayout(grp_cat)
        self.cat_layout.setSpacing(6)
        main_layout.addWidget(grp_cat)

        # Disk Storage Status Group
        grp_disk = QGroupBox("💾 Disk Depolama Durumu")
        f_disk = QVBoxLayout(grp_disk)
        f_disk.setSpacing(6)

        self.lbl_disk_info = QLabel("Sürücü taranıyor...")
        self.lbl_disk_info.setStyleSheet(f"color: {T['text_primary']}; font-weight: bold;")
        f_disk.addWidget(self.lbl_disk_info)

        self.bar_disk = QProgressBar()
        self.bar_disk.setRange(0, 100)
        self.bar_disk.setValue(0)
        self.bar_disk.setTextVisible(True)
        self.bar_disk.setFixedHeight(18)
        self.bar_disk.setStyleSheet(f"""
            QProgressBar {{
                background-color: {T['bg_panel']};
                border: 1px solid {T['border']};
                border-radius: 4px;
                text-align: center;
                color: {T['text_on_accent']};
                font-size: 10px;
                font-weight: bold;
            }}
            QProgressBar::chunk {{
                background-color: {T['accent']};
                border-radius: 3px;
            }}
        """)
        f_disk.addWidget(self.bar_disk)

        main_layout.addWidget(grp_disk)

        # Action Buttons
        btn_box = QHBoxLayout()
        btn_refresh = QPushButton("🔄 Yenile")
        btn_refresh.setObjectName("btn_secondary")
        btn_refresh.clicked.connect(self._load_data)
        btn_box.addWidget(btn_refresh)

        btn_box.addStretch()

        btn_close = QPushButton("Kapat")
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)

        main_layout.addLayout(btn_box)

    def _load_data(self):
        stats = self.db.get_statistics()

        # Clear existing cards
        while self.grid_cards.count():
            item = self.grid_cards.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Card 1: All-time downloaded traffic
        comp_bytes = stats.get("completed_bytes", 0)
        card1 = StatCard(
            title="TOPLAM VERİ TRAFİĞİ",
            value=format_size(comp_bytes),
            subtext="Tamamlanan indirmelerin toplamı",
            accent_color=T['success']
        )
        self.grid_cards.addWidget(card1, 0, 0)

        # Card 2: Completed downloads count
        comp_count = stats.get("completed_count", 0)
        tot_count = stats.get("total_count", 0)
        card2 = StatCard(
            title="TAMAMLANAN DOSYALAR",
            value=f"{comp_count} Adet",
            subtext=f"Toplam {tot_count} görevden",
            accent_color=T['accent']
        )
        self.grid_cards.addWidget(card2, 0, 1)

        # Card 3: Today's traffic
        today_bytes = stats.get("today_bytes", 0)
        today_count = stats.get("today_count", 0)
        card3 = StatCard(
            title="BUGÜNKÜ TRAFİK",
            value=format_size(today_bytes),
            subtext=f"Bugün tamamlanan: {today_count} dosya",
            accent_color=T['color_sky']
        )
        self.grid_cards.addWidget(card3, 1, 0)

        # Card 4: Active & Queued Tasks
        active = stats.get("active_count", 0)
        queued = stats.get("queued_count", 0)
        card4 = StatCard(
            title="KUYRUK VE AKTİF",
            value=f"{active} İnen / {queued} Sırada",
            subtext=f"Duraklatılan: {stats.get('paused_count', 0)} | Hatalı: {stats.get('error_count', 0)}",
            accent_color=T['color_purple']
        )
        self.grid_cards.addWidget(card4, 1, 1)

        # Populate categories
        while self.cat_layout.count():
            item = self.cat_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        cats = stats.get("categories", {})
        cat_icons = {
            "Video": "🎬 Videolar",
            "Music": "🎵 Müzik",
            "Documents": "📄 Belgeler",
            "Compressed": "📦 Sıkıştırılmış",
            "Programs": "💻 Programlar",
            "Others": "📁 Diğer"
        }

        if not cats:
            lbl_empty = QLabel("Henüz kategori verisi bulunmuyor.")
            lbl_empty.setStyleSheet(f"color: {T['text_secondary']}; font-style: italic;")
            self.cat_layout.addWidget(lbl_empty)
        else:
            for cat_key, count in cats.items():
                label_text = cat_icons.get(cat_key, f"📁 {cat_key}")
                pct = int((count / tot_count) * 100) if tot_count > 0 else 0

                row_w = QWidget()
                r_layout = QHBoxLayout(row_w)
                r_layout.setContentsMargins(0, 2, 0, 2)

                lbl_cat_name = QLabel(label_text)
                lbl_cat_name.setStyleSheet(f"color: {T['text_primary']}; font-size: 12px; min-width: 140px;")
                r_layout.addWidget(lbl_cat_name)

                pbar = QProgressBar()
                pbar.setRange(0, 100)
                pbar.setValue(pct)
                pbar.setFixedHeight(12)
                pbar.setTextVisible(False)
                pbar.setStyleSheet(f"""
                    QProgressBar {{
                        background-color: {T['bg_panel']};
                        border: 1px solid {T['border']};
                        border-radius: 3px;
                    }}
                    QProgressBar::chunk {{
                        background-color: {T['accent']};
                        border-radius: 2px;
                    }}
                """)
                r_layout.addWidget(pbar, stretch=1)

                lbl_cat_val = QLabel(f"{count} dosya (%{pct})")
                lbl_cat_val.setStyleSheet(f"color: {T['text_muted']}; font-size: 11px; min-width: 100px; text-align: right;")
                r_layout.addWidget(lbl_cat_val)

                self.cat_layout.addWidget(row_w)

        # Disk Storage Info
        free_bytes, total_bytes, drive = get_disk_total_and_free(self.default_download_dir)
        if total_bytes > 0:
            used_bytes = total_bytes - free_bytes
            used_pct = int((used_bytes / total_bytes) * 100)
            self.lbl_disk_info.setText(
                f"Sürücü ({drive}): {format_size(free_bytes)} Boş / {format_size(total_bytes)} Toplam "
                f"(%{used_pct} Dolu)"
            )
            self.bar_disk.setValue(used_pct)
            if used_pct >= 90:
                self.bar_disk.setStyleSheet(self.bar_disk.styleSheet().replace(T['accent'], T['danger']))
            elif used_pct >= 75:
                self.bar_disk.setStyleSheet(self.bar_disk.styleSheet().replace(T['accent'], T['warning']))
        else:
            self.lbl_disk_info.setText(f"Kayıt Klasörü: {self.default_download_dir}")

