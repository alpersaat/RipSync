import os
import re
import urllib.parse
from typing import List, Dict, Any
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QFileDialog, QSpinBox,
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QLineEdit,
    QMessageBox, QApplication
)

from core.categories import detect_category, get_category_folder
from core.pattern_generator import generate_urls_from_pattern
from ui.styles import T  # noqa: F401  (tema tokenlari)


def extract_valid_urls(text: str) -> List[str]:
    """Extract all valid http:// and https:// URLs from raw multi-line text."""
    urls = []
    lines = text.strip().splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Check if line contains a URL
        matches = re.findall(r'https?://[^\s<>"]+', line)
        for m in matches:
            clean_url = m.strip().rstrip(".,;)>]!?'\"")
            if clean_url and clean_url not in urls:
                urls.append(clean_url)
    return urls


class PatternWizardDialog(QDialog):
    """
    Wizard dialog to generate sequential batch URLs from templates.
    Supports formats like:
      - https://site.com/file_[01-20].zip
      - https://site.com/part_[a-z].rar
      - https://site.com/img_(*).jpg with start/end/digits
    """
    urls_generated = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🪄 Ardışık Bağlantı Kalıp Sihirbazı (Pattern Generator)")
        self.resize(540, 420)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        lbl_desc = QLabel(
            "<b>Şablon Kalıbı Örnekleri:</b><br>"
            "• Gömülü Aralık: <code>https://sunucu.com/dosya_[01-20].zip</code><br>"
            "• Adımlı Aralık: <code>https://sunucu.com/resim_[1-50:2].jpg</code><br>"
            "• Harf Aralığı: <code>https://sunucu.com/part_[a-e].rar</code><br>"
            "• Yer Tutucu: <code>https://sunucu.com/sayfa_(*).html</code>"
        )
        lbl_desc.setStyleSheet(f"color: {T['text_muted']}; background-color: {T['bg_main']}; border: 1px solid {T['bg_hover']}; border-radius: 6px; padding: 10px; font-size: 11px;")
        layout.addWidget(lbl_desc)

        form = QFormLayout()
        form.setSpacing(10)

        self.edit_template = QLineEdit("https://site.com/dosya_[01-10].zip")
        self.edit_template.setPlaceholderText("https://site.com/file_[01-20].zip")
        self.edit_template.textChanged.connect(self._update_preview)
        form.addRow("Şablon URL:", self.edit_template)

        # Range controls
        range_box = QHBoxLayout()
        self.spin_start = QSpinBox()
        self.spin_start.setRange(0, 999999)
        self.spin_start.setValue(1)
        self.spin_start.valueChanged.connect(self._update_preview)

        self.spin_end = QSpinBox()
        self.spin_end.setRange(0, 999999)
        self.spin_end.setValue(10)
        self.spin_end.valueChanged.connect(self._update_preview)

        self.spin_step = QSpinBox()
        self.spin_step.setRange(1, 1000)
        self.spin_step.setValue(1)
        self.spin_step.valueChanged.connect(self._update_preview)

        self.spin_digits = QSpinBox()
        self.spin_digits.setRange(0, 10)
        self.spin_digits.setValue(2)
        self.spin_digits.setToolTip("Basamak sayısı (örn: 2 basamak -> 01, 02)")
        self.spin_digits.valueChanged.connect(self._update_preview)

        range_box.addWidget(QLabel("Başlangıç:"))
        range_box.addWidget(self.spin_start)
        range_box.addWidget(QLabel("Bitiş:"))
        range_box.addWidget(self.spin_end)
        range_box.addWidget(QLabel("Adım:"))
        range_box.addWidget(self.spin_step)
        range_box.addWidget(QLabel("Basamak:"))
        range_box.addWidget(self.spin_digits)
        form.addRow("Aralık Ayarları:", range_box)

        layout.addLayout(form)

        # Preview area
        lbl_prev_title = QLabel("Canlı Önizleme:")
        lbl_prev_title.setStyleSheet(f"font-weight: bold; color: {T['accent']};")
        layout.addWidget(lbl_prev_title)

        self.txt_preview = QPlainTextEdit()
        self.txt_preview.setReadOnly(True)
        self.txt_preview.setStyleSheet(f"background-color: {T['bg_main']}; border: 1px solid {T['border']}; border-radius: 6px; font-family: Consolas; font-size: 11px; color: {T['success']};")
        layout.addWidget(self.txt_preview, stretch=1)

        self.lbl_preview_count = QLabel("Üretilecek Bağlantı: 0")
        self.lbl_preview_count.setStyleSheet(f"color: {T['color_purple']}; font-weight: bold;")
        layout.addWidget(self.lbl_preview_count)

        # Dialog Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_insert = QPushButton("🪄 Bağlantıları Üret ve Ekle")
        btn_insert.setStyleSheet(f"background-color: {T['accent']}; color: {T['bg_main']}; font-weight: bold; padding: 6px 16px;")
        btn_insert.clicked.connect(self._on_insert)
        btn_box.addWidget(btn_insert)

        btn_close = QPushButton("Vazgeç")
        btn_close.setObjectName("btn_secondary")
        btn_close.clicked.connect(self.reject)
        btn_box.addWidget(btn_close)

        layout.addLayout(btn_box)

        self._update_preview()

    def _update_preview(self):
        tmpl = self.edit_template.text().strip()
        # If bracket syntax is used, start/end will be extracted automatically, else explicit params used
        st = self.spin_start.value()
        en = self.spin_end.value()
        stp = self.spin_step.value()
        dig = self.spin_digits.value()

        urls = generate_urls_from_pattern(tmpl, start=st, end=en, step=stp, digits=dig)
        self.txt_preview.setPlainText("\n".join(urls[:50]) + ("\n... (kalanlar gizlendi)" if len(urls) > 50 else ""))
        self.lbl_preview_count.setText(f"Üretilecek Bağlantı: {len(urls)} adet")

    def _on_insert(self):
        tmpl = self.edit_template.text().strip()
        st = self.spin_start.value()
        en = self.spin_end.value()
        stp = self.spin_step.value()
        dig = self.spin_digits.value()
        urls = generate_urls_from_pattern(tmpl, start=st, end=en, step=stp, digits=dig)
        if not urls:
            QMessageBox.warning(self, "Uyarı", "Geçerli bir şablon veya aralık girilmedi.")
            return
        self.urls_generated.emit(urls)
        self.accept()


class BatchAddDialog(QDialog):
    """
    Dialog for adding multiple download URLs simultaneously (Batch URL Downloader).
    Supports importing from text files, pasting from clipboard, and configuring queue settings.
    """
    # Emits (list_of_download_dicts, start_now)
    batch_download_confirmed = pyqtSignal(list, bool)

    def __init__(self, base_download_dir: str, default_connections: int = 8,
                 default_quality: str = "max", auto_categorize: bool = True,
                 initial_text: str = "", site_rules=None, parent=None):
        super().__init__(parent)
        self.base_download_dir = base_download_dir
        self.default_connections = default_connections
        self.default_quality = default_quality
        self.auto_categorize = auto_categorize
        self.site_rules = site_rules

        self.setWindowTitle("RipSync - Toplu Bağlantı İndirici (Batch URL Add)")
        self.resize(650, 520)
        self._init_ui(initial_text)

    def _init_ui(self, initial_text: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        # Header Info
        lbl_info = QLabel("İndirmek istediğiniz tüm bağlantıları her satıra bir adet gelecek şekilde yapıştırın:")
        lbl_info.setStyleSheet(f"color: {T['text_primary']}; font-size: 12px; font-weight: bold;")
        layout.addWidget(lbl_info)

        # URLs text edit
        self.txt_urls = QPlainTextEdit()
        self.txt_urls.setPlaceholderText(
            "https://ornek.com/dosya1.zip\n"
            "https://ornek.com/dosya2.iso\n"
            "https://ornek.com/video.mp4\n"
            "https://ornek.com/muzik.mp3"
        )
        self.txt_urls.setStyleSheet(
            f"QPlainTextEdit {{ background-color: {T['bg_main']}; border: 1px solid {T['border']}; border-radius: 6px; padding: 8px; color: {T['text_primary']}; font-family: Consolas, monospace; font-size: 12px; }}"
            f"QPlainTextEdit:focus {{ border: 1px solid {T['accent']}; }}"
        )
        self.txt_urls.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.txt_urls, stretch=1)

        # Actions row below text box (Paste, Load file, Clear)
        act_row = QHBoxLayout()
        btn_paste = QPushButton("📋 Panodan Yapıştır")
        btn_paste.setObjectName("btn_secondary")
        btn_paste.clicked.connect(self._paste_from_clipboard)
        act_row.addWidget(btn_paste)

        btn_import_file = QPushButton("📂 Metin Dosyasından Yükle (.txt / .m3u)")
        btn_import_file.setObjectName("btn_secondary")
        btn_import_file.clicked.connect(self._import_from_file)
        act_row.addWidget(btn_import_file)

        btn_pattern_wizard = QPushButton("🪄 Kalıp Sihirbazı ([01-50])")
        btn_pattern_wizard.setObjectName("btn_secondary")
        btn_pattern_wizard.setStyleSheet(f"color: {T['color_purple']}; font-weight: bold;")
        btn_pattern_wizard.clicked.connect(self._open_pattern_wizard)
        act_row.addWidget(btn_pattern_wizard)

        btn_clear = QPushButton("Temizle")
        btn_clear.setObjectName("btn_secondary")
        btn_clear.clicked.connect(self.txt_urls.clear)
        act_row.addWidget(btn_clear)

        act_row.addStretch()

        self.lbl_count = QLabel("⚡ Algılanan Bağlantı: 0 adet")
        self.lbl_count.setStyleSheet(f"color: {T['accent']}; font-weight: bold; font-size: 12px;")
        act_row.addWidget(self.lbl_count)

        layout.addLayout(act_row)

        # Options Group
        grp_opts = QGroupBox("İndirme ve Kuyruk Seçenekleri")
        f_opts = QFormLayout(grp_opts)
        f_opts.setSpacing(10)

        # Target directory
        dir_layout = QHBoxLayout()
        self.edit_dir = QLineEdit(self.base_download_dir)
        btn_browse = QPushButton("Gözat...")
        btn_browse.setObjectName("btn_secondary")
        btn_browse.clicked.connect(self._browse_dir)
        dir_layout.addWidget(self.edit_dir)
        dir_layout.addWidget(btn_browse)
        f_opts.addRow("Kayıt Klasörü:", dir_layout)

        # Tags input
        self.edit_tags = QLineEdit()
        self.edit_tags.setPlaceholderText("Örn: Ders, İş, Arşiv (Virgülle ayırarak birden fazla etiket girebilirsiniz)")
        f_opts.addRow("🏷️ Etiketler (Opsiyonel):", self.edit_tags)

        # Auto categorize
        self.chk_auto_cat = QCheckBox("Akıllı Kategorizasyon (Dosya uzantılarına göre Videolar, Müzik, Belgeler klasörlerine ayır)")
        self.chk_auto_cat.setChecked(self.auto_categorize)
        f_opts.addRow("", self.chk_auto_cat)

        # Connections
        self.spin_conns = QSpinBox()
        self.spin_conns.setRange(1, 32)
        self.spin_conns.setValue(self.default_connections)
        f_opts.addRow("İndirme Başına Parça Sayısı:", self.spin_conns)

        # Quality
        self.combo_quality = QComboBox()
        self.combo_quality.addItem("🚀 En Yüksek Kalite (Maksimum)", "max")
        self.combo_quality.addItem("🌟 1080p (Full HD)", "1080p")
        self.combo_quality.addItem("✨ 720p (HD)", "720p")
        self.combo_quality.addItem("📺 480p (Standart)", "480p")
        self.combo_quality.addItem("🎵 Sadece Ses / Müzik (MP3)", "audio")
        idx_q = self.combo_quality.findData(self.default_quality)
        if idx_q >= 0:
            self.combo_quality.setCurrentIndex(idx_q)
        f_opts.addRow("Medya / Video Kalitesi:", self.combo_quality)

        # Priority
        self.combo_priority = QComboBox()
        self.combo_priority.addItem("⚖️ Normal Öncelik (Dengeli Paylaşım)", "normal")
        self.combo_priority.addItem("🚀 Yüksek Öncelik (%70 Hız Payı)", "high")
        self.combo_priority.addItem("🐢 Düşük Öncelik (Arka Plan - %10)", "low")
        f_opts.addRow("Bant Genişliği Önceliği:", self.combo_priority)

        # Start now
        self.chk_start_now = QCheckBox("Hemen İndirmeye Başla (Sıralı kuyruğa alıp sırayla indir)")
        self.chk_start_now.setChecked(True)
        self.chk_start_now.setStyleSheet(f"font-weight: bold; color: {T['success']};")
        f_opts.addRow("", self.chk_start_now)

        layout.addWidget(grp_opts)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_confirm = QPushButton("▶ Kuyruğa Ekle (0 İndirme)")
        self.btn_confirm.setEnabled(False)
        self.btn_confirm.setStyleSheet(f"background-color: {T['accent']}; color: {T['bg_main']}; font-weight: bold; padding: 7px 18px;")
        self.btn_confirm.clicked.connect(self._on_confirm)
        btn_layout.addWidget(self.btn_confirm)

        btn_cancel = QPushButton("İptal")
        btn_cancel.setObjectName("btn_secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

        # Fill initial text or auto-paste from clipboard if present
        if initial_text:
            self.txt_urls.setPlainText(initial_text)
        else:
            cb = QApplication.clipboard()
            if cb:
                clip_text = cb.text()
                if clip_text and ("http://" in clip_text or "https://" in clip_text):
                    # Check if valid urls exist in clipboard
                    c_urls = extract_valid_urls(clip_text)
                    if len(c_urls) >= 1:
                        self.txt_urls.setPlainText(clip_text)

    def _open_pattern_wizard(self):
        wiz = PatternWizardDialog(self)
        wiz.urls_generated.connect(self._on_pattern_urls_generated)
        wiz.exec()

    def _on_pattern_urls_generated(self, urls: List[str]):
        if urls:
            cur = self.txt_urls.toPlainText()
            new_block = "\n".join(urls)
            new_txt = (cur + "\n" + new_block).strip() if cur else new_block
            self.txt_urls.setPlainText(new_txt)

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Kayıt Klasörü Seç", self.edit_dir.text())
        if d:
            self.edit_dir.setText(d)

    def _paste_from_clipboard(self):
        cb = QApplication.clipboard()
        if cb:
            txt = cb.text()
            if txt:
                cur = self.txt_urls.toPlainText()
                new_txt = (cur + "\n" + txt).strip() if cur else txt
                self.txt_urls.setPlainText(new_txt)

    def _import_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Bağlantı Listesi Dosyası Seç",
            "",
            "Metin Dosyaları (*.txt *.m3u *.m3u8 *.list *.urls);;Tüm Dosyalar (*.*)"
        )
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            cur = self.txt_urls.toPlainText()
            new_txt = (cur + "\n" + content).strip() if cur else content
            self.txt_urls.setPlainText(new_txt)
        except Exception as e:
            QMessageBox.warning(self, "Hata", f"Dosya okunamadı:\n{str(e)}")

    def _on_text_changed(self):
        urls = extract_valid_urls(self.txt_urls.toPlainText())
        count = len(urls)
        self.lbl_count.setText(f"⚡ Algılanan Bağlantı: {count} adet")
        if count > 0:
            self.btn_confirm.setEnabled(True)
            self.btn_confirm.setText(f"▶ Kuyruğa Ekle ({count} İndirme)")
        else:
            self.btn_confirm.setEnabled(False)
            self.btn_confirm.setText("▶ Kuyruğa Ekle (0 İndirme)")

    def _on_confirm(self):
        urls = extract_valid_urls(self.txt_urls.toPlainText())
        if not urls:
            QMessageBox.warning(self, "Uyarı", "Lütfen en az bir geçerli web adresi (URL) girin.")
            return

        base_dir = self.edit_dir.text().strip() or self.base_download_dir
        os.makedirs(base_dir, exist_ok=True)
        auto_cat = self.chk_auto_cat.isChecked()
        conns = self.spin_conns.value()
        quality = self.combo_quality.currentData() or "max"
        start_now = self.chk_start_now.isChecked()

        prio = self.combo_priority.currentData() or "normal"
        user_tags = self.edit_tags.text().strip()
        items = []
        for url in urls:
            # Guess candidate filename from URL
            parsed = urllib.parse.urlparse(url)
            cand_name = os.path.basename(parsed.path)
            clean_cand = urllib.parse.unquote(cand_name).split("?")[0] if cand_name else "download"
            if not clean_cand:
                clean_cand = "download"

            if self.site_rules:
                rule_folder = self.site_rules.match_rule(url)
                if rule_folder:
                    save_dir = rule_folder
                elif auto_cat:
                    cat = detect_category(clean_cand)
                    save_dir = get_category_folder(cat, base_dir)
                else:
                    save_dir = base_dir
            elif auto_cat:
                cat = detect_category(clean_cand)
                save_dir = get_category_folder(cat, base_dir)
            else:
                save_dir = base_dir

            items.append({
                "url": url,
                "save_dir": save_dir,
                "filename": clean_cand,
                "connections": conns,
                "quality": quality,
                "priority": prio,
                "tags": user_tags,
                "headers": {}
            })

        self.batch_download_confirmed.emit(items, start_now)
        self.accept()
