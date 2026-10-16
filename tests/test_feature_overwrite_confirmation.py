import os
import pytest
from unittest.mock import patch, MagicMock
from core.database import Database
from ui.overwrite_dialog import OverwriteConfirmDialog
from ui.add_download_dialog import AddDownloadDialog
from ui.settings_dialog import SettingsDialog


@pytest.fixture
def mem_db(tmp_path):
    db_file = str(tmp_path / "test_conflict.db")
    return Database(db_file)


def test_overwrite_dialog_initialization_and_actions(qapp, tmp_path):
    # Create an existing file
    target_dir = str(tmp_path)
    filename = "document.pdf"
    file_path = os.path.join(target_dir, filename)
    with open(file_path, "wb") as f:
        f.write(b"Hello World PDF Content")

    dlg = OverwriteConfirmDialog(target_dir, filename)
    assert dlg.filename == "document.pdf"
    assert dlg.target_dir == os.path.abspath(target_dir)
    assert dlg.get_action() == OverwriteConfirmDialog.ACTION_CANCEL

    # Test auto-rename action
    dlg._on_auto_rename()
    assert dlg.get_action() == OverwriteConfirmDialog.ACTION_AUTO_RENAME
    assert dlg.get_resolved_filename() == "document (1).pdf"

    # Reset and test overwrite action
    dlg2 = OverwriteConfirmDialog(target_dir, filename)
    dlg2._on_overwrite()
    assert dlg2.get_action() == OverwriteConfirmDialog.ACTION_OVERWRITE
    assert dlg2.get_resolved_filename() == "document.pdf"


def test_add_download_dialog_dynamic_conflict_banner(qapp, tmp_path, mem_db):
    target_dir = str(tmp_path)
    filename = "test_video.mp4"
    file_path = os.path.join(target_dir, filename)
    with open(file_path, "wb") as f:
        f.write(b"dummy mp4 data")

    # 1. Test when conflict action is 'overwrite'
    mem_db.save_conflict_setting("overwrite")
    dlg = AddDownloadDialog(
        initial_url="https://example.com/test_video.mp4",
        initial_filename=filename,
        base_download_dir=target_dir,
        auto_categorize=False,
        db=mem_db
    )
    dlg._check_file_conflict()
    assert not dlg.banner_conflict.isHidden()
    assert "Üzerine Yaz" in dlg.banner_conflict.text()
    assert "silinecektir" in dlg.banner_conflict.text()

    # 2. Test when conflict action is 'auto_rename'
    mem_db.save_conflict_setting("auto_rename")
    dlg._check_file_conflict()
    assert not dlg.banner_conflict.isHidden()
    assert "otomatik adlandırılacak" in dlg.banner_conflict.text()

    # 3. Test when conflict action is 'skip'
    mem_db.save_conflict_setting("skip")
    dlg._check_file_conflict()
    assert not dlg.banner_conflict.isHidden()
    assert "İndirmeyi Atla" in dlg.banner_conflict.text()

    # 4. Test when file does NOT exist
    dlg.edit_filename.setText("non_existent_file.mp4")
    dlg._check_file_conflict()
    assert dlg.banner_conflict.isHidden()


def test_add_download_dialog_submit_with_overwrite_confirmed(qapp, tmp_path, mem_db):
    target_dir = str(tmp_path)
    filename = "archive.zip"
    file_path = os.path.join(target_dir, filename)
    with open(file_path, "wb") as f:
        f.write(b"existing zip data")

    mem_db.save_conflict_setting("overwrite")
    dlg = AddDownloadDialog(
        initial_url="https://example.com/archive.zip",
        initial_filename=filename,
        base_download_dir=target_dir,
        auto_categorize=False,
        db=mem_db
    )

    confirmed_results = []
    dlg.download_confirmed.connect(lambda data: confirmed_results.append(data))

    # Mock OverwriteConfirmDialog where user clicks "Üzerine Yaz" (ACTION_OVERWRITE)
    with patch("ui.overwrite_dialog.OverwriteConfirmDialog.exec", return_value=1):
        with patch("ui.overwrite_dialog.OverwriteConfirmDialog.get_action", return_value="overwrite"):
            dlg._submit(start_now=True)

    assert len(confirmed_results) == 1
    assert confirmed_results[0]["filename"] == "archive.zip"


def test_add_download_dialog_submit_with_overwrite_auto_rename(qapp, tmp_path, mem_db):
    target_dir = str(tmp_path)
    filename = "photo.png"
    file_path = os.path.join(target_dir, filename)
    with open(file_path, "wb") as f:
        f.write(b"existing photo data")

    mem_db.save_conflict_setting("overwrite")
    dlg = AddDownloadDialog(
        initial_url="https://example.com/photo.png",
        initial_filename=filename,
        base_download_dir=target_dir,
        auto_categorize=False,
        db=mem_db
    )

    confirmed_results = []
    dlg.download_confirmed.connect(lambda data: confirmed_results.append(data))

    # Mock OverwriteConfirmDialog where user chooses "Otomatik Yeniden Adlandır"
    with patch("ui.overwrite_dialog.OverwriteConfirmDialog.exec", return_value=1):
        with patch("ui.overwrite_dialog.OverwriteConfirmDialog.get_action", return_value="auto_rename"):
            with patch("ui.overwrite_dialog.OverwriteConfirmDialog.get_resolved_filename", return_value="photo (1).png"):
                dlg._submit(start_now=True)

    assert len(confirmed_results) == 1
    assert confirmed_results[0]["filename"] == "photo (1).png"


def test_add_download_dialog_submit_with_overwrite_cancelled(qapp, tmp_path, mem_db):
    target_dir = str(tmp_path)
    filename = "setup.exe"
    file_path = os.path.join(target_dir, filename)
    with open(file_path, "wb") as f:
        f.write(b"existing setup data")

    mem_db.save_conflict_setting("overwrite")
    dlg = AddDownloadDialog(
        initial_url="https://example.com/setup.exe",
        initial_filename=filename,
        base_download_dir=target_dir,
        auto_categorize=False,
        db=mem_db
    )

    confirmed_results = []
    dlg.download_confirmed.connect(lambda data: confirmed_results.append(data))

    # Mock OverwriteConfirmDialog where user clicks "İptal" (ACTION_CANCEL)
    with patch("ui.overwrite_dialog.OverwriteConfirmDialog.exec", return_value=0):
        with patch("ui.overwrite_dialog.OverwriteConfirmDialog.get_action", return_value="cancel"):
            dlg._submit(start_now=True)

    # Should not emit download_confirmed
    assert len(confirmed_results) == 0


def test_settings_dialog_conflict_hint(qapp, mem_db):
    mem_db.save_conflict_setting("auto_rename")
    sd = SettingsDialog(mem_db)

    # Initially auto_rename
    assert "güvenle yeniden adlandırılır" in sd.lbl_conflict_hint.text()

    # Switch to overwrite
    idx_ow = sd.combo_conflict_action.findData("overwrite")
    sd.combo_conflict_action.setCurrentIndex(idx_ow)
    assert "onay istenir" in sd.lbl_conflict_hint.text()

    # Switch to skip
    idx_skip = sd.combo_conflict_action.findData("skip")
    sd.combo_conflict_action.setCurrentIndex(idx_skip)
    assert "atlanır" in sd.lbl_conflict_hint.text()
