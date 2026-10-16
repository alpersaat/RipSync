import os
import tempfile
import pytest
from PyQt6.QtWidgets import QApplication, QDialog, QLabel
from PyQt6.QtCore import Qt

from ui.delete_dialog import DeleteConfirmDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_delete_dialog_single_item_default_retention(qapp, tmp_path):
    # Geçici bir dosya oluşturalım
    test_file = tmp_path / "test_download.zip"
    test_file.write_bytes(b"A" * 2048)

    rec = {
        "id": "dl_1",
        "filename": "test_download.zip",
        "save_path": str(test_file),
        "status": "Completed"
    }

    dlg = DeleteConfirmDialog([rec], initial_delete_file=False)

    # Başlık ve banner kontrolleri
    assert "İndirmeyi Kaldır / Sil" in dlg.windowTitle()
    assert dlg.chk_delete_file.isChecked() is False
    assert "VARSAYILAN DAVRANIŞ" in dlg.banner_default.findChildren(QLabel)[0].text()

    # Varsayılan "Yalnızca Listeden Kaldır" tıklandığında
    dlg.btn_remove_list.click()
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert dlg.get_delete_file_choice() is False


def test_delete_dialog_single_item_file_exists_info(qapp, tmp_path):
    test_file = tmp_path / "data.iso"
    test_file.write_bytes(b"B" * (1024 * 1024 * 5))  # 5 MB

    rec = {
        "id": "dl_2",
        "filename": "data.iso",
        "save_path": str(test_file),
        "status": "Completed"
    }

    dlg = DeleteConfirmDialog([rec], initial_delete_file=False)
    # Form içeriğinde dosyanın diskte mevcut olduğunu gösteren metin olmalı
    labels = [lbl.text() for lbl in dlg.findChildren(dlg.findChild(type(dlg.chk_delete_file)).__class__)]
    # Dialog metinlerinde 5.00 MB veya Diskte Mevcut yer almalı
    all_texts = " ".join([l.text() for l in dlg.findChildren(object) if hasattr(l, "text") and callable(l.text)])
    assert "Diskte Mevcut" in all_texts
    assert "5.00 MB" in all_texts


def test_delete_dialog_initial_delete_file_true(qapp, tmp_path):
    rec = {
        "id": "dl_3",
        "filename": "video.mp4",
        "save_path": str(tmp_path / "video.mp4"),
        "status": "Completed"
    }

    dlg = DeleteConfirmDialog([rec], initial_delete_file=True)
    assert dlg.chk_delete_file.isChecked() is True
    assert "💥 Dosyayla Birlikte Sil" in dlg.btn_remove_list.text()

    dlg.btn_remove_list.click()
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert dlg.get_delete_file_choice() is True


def test_delete_dialog_direct_delete_both_button(qapp, tmp_path):
    rec = {
        "id": "dl_4",
        "filename": "document.pdf",
        "save_path": str(tmp_path / "document.pdf"),
        "status": "Paused"
    }

    # initial_delete_file False olmasına rağmen doğrudan "💥 Dosyayla Birlikte Sil" butonuna tıklanıyor
    dlg = DeleteConfirmDialog([rec], initial_delete_file=False)
    assert dlg.chk_delete_file.isChecked() is False

    dlg.btn_delete_both.click()
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert dlg.get_delete_file_choice() is True


def test_delete_dialog_cancel_behavior(qapp):
    rec = {
        "id": "dl_5",
        "filename": "archive.rar",
        "save_path": "C:\\nonexistent\\archive.rar",
        "status": "Error"
    }

    dlg = DeleteConfirmDialog([rec], initial_delete_file=False)
    dlg.btn_cancel.click()
    assert dlg.result() == QDialog.DialogCode.Rejected
    assert dlg.get_delete_file_choice() is None


def test_delete_dialog_checkbox_toggle_updates_ui(qapp):
    rec = {
        "id": "dl_6",
        "filename": "sample.bin",
        "save_path": "C:\\fake\\sample.bin",
        "status": "Downloading"
    }

    dlg = DeleteConfirmDialog([rec], initial_delete_file=False)
    assert "Yalnızca Listeden Kaldır" in dlg.btn_remove_list.text()

    # Kullanıcı checkbox'ı işaretler
    dlg.chk_delete_file.setChecked(True)
    assert "Dosyayla Birlikte Sil" in dlg.btn_remove_list.text()
    assert "kalıcı olarak diskten silinecektir" in dlg.lbl_status_desc.text()

    # Kullanıcı checkbox işaretini kaldırır
    dlg.chk_delete_file.setChecked(False)
    assert "Yalnızca Listeden Kaldır" in dlg.btn_remove_list.text()
    assert "Dosya diskte korunacaktır" in dlg.lbl_status_desc.text()


def test_delete_dialog_multiple_downloads(qapp, tmp_path):
    f1 = tmp_path / "file1.txt"
    f1.write_text("1")

    downloads = [
        {"id": "dl_m1", "filename": "file1.txt", "save_path": str(f1), "status": "Completed"},
        {"id": "dl_m2", "filename": "file2.txt", "save_path": str(tmp_path / "missing.txt"), "status": "Completed"},
        {"id": "dl_m3", "filename": "file3.txt", "save_path": str(tmp_path / "missing2.txt"), "status": "Queued"},
    ]

    dlg = DeleteConfirmDialog(downloads, initial_delete_file=False)
    assert "Toplu İndirme Silme (3 Öğe)" in dlg.windowTitle()

    all_texts = " ".join([l.text() for l in dlg.findChildren(object) if hasattr(l, "text") and callable(l.text)])
    assert "3 adet indirme seçildi" in all_texts
    assert "1 / 3 dosya disk üzerinde mevcut" in all_texts


def test_main_window_delete_actions_and_shortcuts(qapp):
    from core.database import Database
    from core.queue_manager import QueueManager
    from ui.main_window import MainWindow

    db = Database(":memory:")
    qm = QueueManager(db)
    win = MainWindow(db, qm)

    # 1. Toolbar butonları kontrolü
    assert hasattr(win, "act_delete")
    assert hasattr(win, "act_delete_file")
    assert win.act_delete.isVisible() is True
    assert win.act_delete_file.isVisible() is True
    assert "Varsayılan: Dosya diskte korunur" in win.act_delete.toolTip()
    assert "Shift+Delete" in win.act_delete_file.toolTip()

    # 2. Shift+Delete kısayolu kontrolü
    assert hasattr(win, "shortcut_shift_delete")
    assert win.shortcut_shift_delete.key().toString() == "Shift+Del"

