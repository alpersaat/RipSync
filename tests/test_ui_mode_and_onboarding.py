import pytest
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from core.database import Database
from core.queue_manager import QueueManager
from ui.main_window import MainWindow
from ui.settings_dialog import SettingsDialog
from ui.onboarding_dialog import OnboardingDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def test_db():
    return Database(":memory:")


@pytest.fixture
def queue_mgr(test_db):
    return QueueManager(test_db)


def test_database_ui_mode_and_onboarding(test_db):
    """Veritabanında UI modu ve onboarding tamamlandı durumlarının doğru çalıştığını doğrular."""
    # Varsayılanlar
    assert test_db.get_ui_mode() == "simple"
    assert test_db.is_onboarding_completed() is False

    # UI Modu kaydetme
    test_db.save_ui_mode("advanced")
    assert test_db.get_ui_mode() == "advanced"

    test_db.save_ui_mode("invalid_mode")
    assert test_db.get_ui_mode() == "simple"

    # Onboarding tamamlama
    test_db.set_onboarding_completed(True)
    assert test_db.is_onboarding_completed() is True

    test_db.set_onboarding_completed(False)
    assert test_db.is_onboarding_completed() is False


def test_main_window_simple_and_advanced_mode(qapp, test_db, queue_mgr):
    """MainWindow üzerinde Basit Mod ve Gelişmiş Mod geçişlerinin UI bileşenlerini doğru gizleyip gösterdiğini test eder."""
    win = MainWindow(test_db, queue_mgr)

    # 1. Basit Mod Kontrolü
    win.apply_ui_mode("simple")
    assert win.ui_mode == "simple"
    assert test_db.get_ui_mode() == "simple"

    # Gelişmiş araç çubuğu öğeleri gizli olmalı
    assert win.act_playlist.isVisible() is False
    assert win.act_batch_add.isVisible() is False
    assert win.act_start_queue.isVisible() is False
    assert win.act_pause_all.isVisible() is False
    assert win.act_scheduler.isVisible() is False
    assert win.act_statistics.isVisible() is False
    assert win.act_clean_missing.isVisible() is False
    assert win.act_extension_widget.isVisible() is False
    assert win.act_conc_widget.isVisible() is False
    assert win.act_sched_widget.isVisible() is False
    assert win.act_limiter_widget.isVisible() is False
    assert win.act_queue_widget.isVisible() is False

    # Temel indirme butonları görünür olmalı
    assert win.act_add.isVisible() is True
    assert win.act_start.isVisible() is True
    assert win.act_pause.isVisible() is True
    assert win.act_stop.isVisible() is True
    assert win.act_delete.isVisible() is True
    assert win.act_open_file.isVisible() is True
    assert win.act_open_folder.isVisible() is True
    assert win.act_settings.isVisible() is True

    # Kategori ağacında Etiketler ve Kuyruklar gizli olmalı
    assert win.root_tags.isHidden() is True
    assert win.root_queues.isHidden() is True

    # Arama çubuğunda chip ve combo filtreler gizli olmalı
    for btn in win.filter_btn_group.values():
        assert btn.isHidden() is True
    assert win.combo_size_filter.isHidden() is True
    assert win.combo_date_filter.isHidden() is True
    assert win.lbl_filter_count.isHidden() is True
    assert win.edit_search.isHidden() is False

    # Durum çubuğunda sparkline grafik ve detaylar gizli olmalı
    assert win.speed_graph.isHidden() is True
    assert win.lbl_ext_status.isHidden() is True
    assert win.lbl_limiter_stat.isHidden() is True
    assert win.lbl_scheduler_stat.isHidden() is True
    assert win.lbl_speed_stat.isHidden() is False
    assert win.lbl_disk_stat.isHidden() is False


    # Tabloda 'Eklenme Tarihi' (6. sütun) gizli olmalı
    assert win.table.isColumnHidden(6) is True

    # Buton metni basit mod göstermeli
    assert "Basit Mod" in win.btn_mode_toggle.text()

    # 2. Gelişmiş Mod Kontrolü
    win.apply_ui_mode("advanced")
    assert win.ui_mode == "advanced"
    assert test_db.get_ui_mode() == "advanced"

    # Gelişmiş araç çubuğu öğeleri görünür olmalı
    assert win.act_playlist.isVisible() is True
    assert win.act_batch_add.isVisible() is True
    assert win.act_start_queue.isVisible() is True
    assert win.act_pause_all.isVisible() is True
    assert win.act_scheduler.isVisible() is True
    assert win.act_statistics.isVisible() is True
    assert win.act_clean_missing.isVisible() is True
    assert win.act_extension_widget.isVisible() is True
    assert win.act_conc_widget.isVisible() is True
    assert win.act_sched_widget.isVisible() is True
    assert win.act_limiter_widget.isVisible() is True
    assert win.act_queue_widget.isVisible() is True

    # Kategori ağacında Etiketler ve Kuyruklar görünür olmalı
    assert win.root_tags.isHidden() is False
    assert win.root_queues.isHidden() is False

    # Arama çubuğunda filtreler görünür olmalı
    for btn in win.filter_btn_group.values():
        assert btn.isHidden() is False
    assert win.combo_size_filter.isHidden() is False
    assert win.combo_date_filter.isHidden() is False
    assert win.lbl_filter_count.isHidden() is False

    # Durum çubuğu öğeleri görünür olmalı
    assert win.speed_graph.isHidden() is False
    assert win.lbl_ext_status.isHidden() is False
    assert win.lbl_limiter_stat.isHidden() is False
    assert win.lbl_scheduler_stat.isHidden() is False

    # Tablo 6. sütun açık olmalı
    assert win.table.isColumnHidden(6) is False

    # Buton metni gelişmiş mod göstermeli
    assert "Gelişmiş Mod" in win.btn_mode_toggle.text()

    # 3. Tek Tıkla Geçiş (Toggle) Testi
    win._toggle_ui_mode()
    assert win.ui_mode == "simple"
    win._toggle_ui_mode()
    assert win.ui_mode == "advanced"

    win.close()


def test_settings_dialog_ui_mode_and_tabs(qapp, test_db):
    """SettingsDialog içinde UI Modu seçimi ve gelişmiş sekme gizleme/gösterme kontrolü."""
    test_db.save_ui_mode("simple")
    dlg = SettingsDialog(test_db)

    # Basit moddayken Proxy (1), Otomasyon (5) ve Site Kuralları (6) gizli olmalı
    assert dlg.combo_ui_mode.currentData() == "simple"
    assert dlg.chk_show_advanced_tabs.isChecked() is False
    assert dlg.tabs.isTabVisible(1) is False
    assert dlg.tabs.isTabVisible(5) is False
    assert dlg.tabs.isTabVisible(6) is False
    # Temel sekmeler açık olmalı
    assert dlg.tabs.isTabVisible(0) is True  # Genel
    assert dlg.tabs.isTabVisible(2) is True  # Görünüm

    # Gelişmiş modu seç
    dlg.combo_ui_mode.setCurrentIndex(dlg.combo_ui_mode.findData("advanced"))
    assert dlg.chk_show_advanced_tabs.isChecked() is True
    assert dlg.tabs.isTabVisible(1) is True
    assert dlg.tabs.isTabVisible(5) is True
    assert dlg.tabs.isTabVisible(6) is True

    # Ayarları kaydet
    dlg._save_settings()
    assert test_db.get_ui_mode() == "advanced"

    dlg.close()


def test_onboarding_dialog_steps_and_save(qapp, test_db, tmp_path):
    """Onboarding rehberli tur sihirbazının adımlarını ve tercih kaydetmesini test eder."""
    dlg = OnboardingDialog(test_db)
    assert dlg.stack.count() == 5

    # Başlangıçta 1. adımda olmalı
    assert dlg.stack.currentIndex() == 0

    # İleri git
    dlg._go_next()
    assert dlg.stack.currentIndex() == 1

    # Klasör ayarla
    test_folder = str(tmp_path / "OnboardingDownloads")
    os.makedirs(test_folder, exist_ok=True)
    dlg.edit_dir.setText(test_folder)

    # Mod seçimi (Basit mod)
    dlg.rad_simple.setChecked(True)
    dlg.chk_categorize.setChecked(True)
    dlg.chk_clipboard.setChecked(True)

    # Tercihleri kaydet
    mode = dlg._save_preferences()
    assert mode == "simple"
    assert test_db.get_ui_mode() == "simple"
    assert test_db.is_onboarding_completed() is True
    assert test_db.get_setting("auto_categorize") is True

    dlg.close()
