import os
from typing import List, Dict, Any, Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QGroupBox, QFormLayout,
    QFrame
)
from PyQt6.QtCore import Qt
from ui.styles import format_size, T


class DeleteConfirmDialog(QDialog):
    """
    RipSync İndirme Silme Onay Diyaloğu.
    
    Kullanıcıya varsayılan davranışın dosyayı diskte KORUMAK olduğunu açıkça gösterir,
    dosyanın diskteki varlık durumunu raporlar ve kullanıcının isterse tek tıkla
    dosyayı da diskten kalıcı olarak silebilmesini sağlar.
    """

    def __init__(
        self,
        downloads: List[Dict[str, Any]],
        initial_delete_file: bool = False,
        parent=None
    ):
        super().__init__(parent)
        self.downloads = downloads or []
        self.count = len(self.downloads)
        self.initial_delete_file = initial_delete_file
        
        # Sonuç: None = İptal, False = Yalnızca Listeden Sil, True = Dosyayla Birlikte Sil
        self._action_delete_file: Optional[bool] = None

        self._init_window_props()
        self._init_ui()

        # Başlangıç durumu
        if self.initial_delete_file:
            self.chk_delete_file.setChecked(True)
        self._update_state()

    def _init_window_props(self):
        if self.count <= 1:
            self.setWindowTitle("İndirmeyi Kaldır / Sil - RipSync")
        else:
            self.setWindowTitle(f"Toplu İndirme Silme ({self.count} Öğe) - RipSync")

        self.setMinimumWidth(480)
        self.resize(520, 360)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        # 1. VARSAYILAN DAVRANIŞ BİLGİ KARTİ (Çok net ve görünür)
        self.banner_default = QFrame()
        self.banner_default.setStyleSheet(f"""
            QFrame {{
                background-color: {T['info_bg']};
                border: 1px solid {T['accent']};
                border-radius: 6px;
                padding: 10px;
            }}
        """)
        banner_layout = QVBoxLayout(self.banner_default)
        banner_layout.setContentsMargins(10, 8, 10, 8)
        banner_layout.setSpacing(4)

        lbl_banner_title = QLabel("ℹ️ VARSAYILAN DAVRANIŞ: İNDİRİLEN DOSYA DİSKTE KORUNUR")
        lbl_banner_title.setStyleSheet(f"color: {T['accent']}; font-weight: bold; font-size: 13px;")
        banner_layout.addWidget(lbl_banner_title)

        lbl_banner_desc = QLabel(
            "Bu işlem indirme kaydını RipSync listesinden ve geçmişinden kaldırır.<br>"
            "<b>Varsayılan olarak dosyanız bilgisayarınızın diskinde kalmaya devam eder.</b>"
        )
        lbl_banner_desc.setStyleSheet(f"color: {T['text_primary']}; font-size: 12px; line-height: 1.4;")
        lbl_banner_desc.setWordWrap(True)
        banner_layout.addWidget(lbl_banner_desc)

        layout.addWidget(self.banner_default)

        # 2. SEÇİLEN İNDİRME / DOSYA BİLGİ KUTUSU
        grp_info = QGroupBox("İndirme Bilgisi" if self.count <= 1 else f"Seçilen İndirmeler ({self.count} Adet)")
        form_info = QFormLayout(grp_info)
        form_info.setSpacing(8)

        if self.count == 1:
            rec = self.downloads[0]
            fname = rec.get("filename") or "Bilinmeyen Dosya"
            spath = rec.get("save_path") or ""
            status = rec.get("status") or "Bilinmiyor"

            form_info.addRow("Dosya Adı:", QLabel(f"<b>{fname}</b>"))
            form_info.addRow("Durum:", QLabel(status))

            # Disk varlık kontrolü
            file_exists = bool(spath and os.path.exists(spath))
            if file_exists:
                try:
                    fsize = os.path.getsize(spath)
                    size_str = format_size(fsize)
                except Exception:
                    size_str = "Bilinmiyor"
                lbl_disk = QLabel(f"💾 <b>Diskte Mevcut</b> ({size_str})")
                lbl_disk.setStyleSheet(f"color: {T['success']}; font-weight: bold;")
            else:
                lbl_disk = QLabel("⚠️ Diskte henüz dosya yok veya taşınmış")
                lbl_disk.setStyleSheet(f"color: {T['warning']};")
            form_info.addRow("Disk Durumu:", lbl_disk)

            if spath:
                lbl_path = QLabel(spath)
                lbl_path.setStyleSheet(f"color: {T['text_muted']}; font-size: 11px;")
                lbl_path.setWordWrap(True)
                form_info.addRow("Konum:", lbl_path)

        else:
            # Çoklu seçim
            names = [r.get("filename") or "Dosya" for r in self.downloads[:4]]
            more = len(self.downloads) - len(names)
            preview = ", ".join(names)
            if more > 0:
                preview += f" ... ve {more} adet daha"

            form_info.addRow("Öğe Sayısı:", QLabel(f"<b>{self.count} adet indirme seçildi</b>"))
            lbl_list = QLabel(preview)
            lbl_list.setStyleSheet(f"color: {T['text_muted']}; font-size: 11px;")
            lbl_list.setWordWrap(True)
            form_info.addRow("Dosyalar:", lbl_list)

            # Diskte kaç tanesi var
            existing_count = sum(1 for r in self.downloads if r.get("save_path") and os.path.exists(r["save_path"]))
            lbl_disk = QLabel(f"💾 {existing_count} / {self.count} dosya disk üzerinde mevcut")
            lbl_disk.setStyleSheet(f"color: {T['success']};" if existing_count > 0 else f"color: {T['warning']};")
            form_info.addRow("Disk Durumu:", lbl_disk)

        layout.addWidget(grp_info)

        # 3. DOSYAYI DA SİLME ONAY KUTUSU (Görünür Seçenek)
        self.chk_delete_file = QCheckBox("💥 İndirilen dosyayı da diskten kalıcı olarak sil (delete_file)")
        self.chk_delete_file.setStyleSheet(f"""
            QCheckBox {{
                font-weight: bold;
                font-size: 12px;
                color: {T['danger']};
                padding: 4px 0;
            }}
        """)
        self.chk_delete_file.toggled.connect(self._on_chk_toggled)
        layout.addWidget(self.chk_delete_file)

        # Dinamik durum açıklaması
        self.lbl_status_desc = QLabel()
        self.lbl_status_desc.setStyleSheet("font-size: 11px; padding-left: 20px;")
        self.lbl_status_desc.setWordWrap(True)
        layout.addWidget(self.lbl_status_desc)

        layout.addStretch()

        # 4. AKSİYON BUTONLARI
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        # Buton 1: Listeden Kaldır (Varsayılan Odak)
        self.btn_remove_list = QPushButton("🗑 Yalnızca Listeden Kaldır")
        self.btn_remove_list.setToolTip("İndirme kaydını siler, indirilen dosya diskte korunur.")
        self.btn_remove_list.setStyleSheet(f"""
            QPushButton {{
                background-color: {T['accent_primary']};
                color: {T['text_on_accent']};
                font-weight: bold;
                padding: 8px 14px;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: {T['accent_hover']};
            }}
        """)
        self.btn_remove_list.clicked.connect(self._on_remove_list_clicked)
        btn_layout.addWidget(self.btn_remove_list)

        # Buton 2: Dosyayla Birlikte Sil (Kalıcı Silme)
        self.btn_delete_both = QPushButton("💥 Dosyayla Birlikte Sil")
        self.btn_delete_both.setToolTip("Hem listeden hem de bilgisayarınızın diskinden kalıcı olarak siler.")
        self.btn_delete_both.setStyleSheet(f"""
            QPushButton {{
                background-color: {T['danger']};
                color: {T['text_on_accent']};
                font-weight: bold;
                padding: 8px 14px;
                border-radius: 5px;
                border: 1px solid {T['danger']};
            }}
            QPushButton:hover {{
                background-color: {T['danger']};
            }}
        """)
        self.btn_delete_both.clicked.connect(self._on_delete_both_clicked)
        btn_layout.addWidget(self.btn_delete_both)

        btn_layout.addStretch()

        # Buton 3: Vazgeç
        self.btn_cancel = QPushButton("Vazgeç")
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: {T['bg_card']};
                color: {T['text_primary']};
                padding: 8px 16px;
                border-radius: 5px;
                border: 1px solid {T['border']};
            }}
            QPushButton:hover {{
                background-color: {T['bg_hover']};
            }}
        """)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def _on_chk_toggled(self, checked: bool):
        self._update_state()

    def _update_state(self):
        checked = self.chk_delete_file.isChecked()
        if checked:
            self.lbl_status_desc.setText(
                f"<span style='color: {T['danger']}; font-weight: bold;'>⚠️ Dikkat:</span> "
                f"<span style='color: {T['danger']};'>İndirilen dosya(lar) kalıcı olarak diskten silinecektir!</span>"
            )
            self.btn_remove_list.setText("💥 Dosyayla Birlikte Sil")
            self.btn_remove_list.setStyleSheet(f"""
                QPushButton {{
                    background-color: {T['danger']};
                    color: {T['text_on_accent']};
                    font-weight: bold;
                    padding: 8px 14px;
                    border-radius: 5px;
                    border: 1px solid {T['danger']};
                }}
                QPushButton:hover {{
                    background-color: {T['danger']};
                }}
            """)
        else:
            self.lbl_status_desc.setText(
                f"<span style='color: {T['success']}; font-weight: bold;'>✓ Güvenli:</span> "
                f"<span style='color: {T['text_primary']};'>Dosya diskte korunacaktır, yalnızca listeden kaldırılır.</span>"
            )
            self.btn_remove_list.setText("🗑 Yalnızca Listeden Kaldır")
            self.btn_remove_list.setStyleSheet(f"""
                QPushButton {{
                    background-color: {T['accent_primary']};
                    color: {T['text_on_accent']};
                    font-weight: bold;
                    padding: 8px 14px;
                    border-radius: 5px;
                }}
                QPushButton:hover {{
                    background-color: {T['accent_hover']};
                }}
            """)

    def _on_remove_list_clicked(self):
        # Checkbox işaretli ise dosya da silinsin, değilse sadece listeden silinsin
        self._action_delete_file = self.chk_delete_file.isChecked()
        self.accept()

    def _on_delete_both_clicked(self):
        # Doğrudan "Dosyayla Birlikte Sil" tıklandı
        self._action_delete_file = True
        self.accept()

    def get_delete_file_choice(self) -> Optional[bool]:
        """
        Diyalog sonucunu döndürür:
        - None: İptal edildi (silme yapılmayacak)
        - False: Yalnızca listeden kaldır (dosya diskte kalır)
        - True: Dosyayla birlikte diskten sil
        """
        if self.result() == QDialog.DialogCode.Accepted:
            return self._action_delete_file
        return None

