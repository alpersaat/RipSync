import os
import pytest
from core.database import Database
from ui.duplicate_dialog import DuplicateDownloadDialog


@pytest.fixture
def mem_db(tmp_path):
    db_file = str(tmp_path / "test_dup.db")
    return Database(db_file)


def test_find_duplicate_by_url(mem_db):
    url = "https://example.com/test_file.zip"
    save_path = "C:\\Downloads\\test_file.zip"
    did = mem_db.add_download(url=url, filename="test_file.zip", save_path=save_path)
    mem_db.update_download(did, status="Completed")

    # Query with exact url
    dup = mem_db.find_duplicate_download(url=url)
    assert dup is not None
    assert dup["id"] == did
    assert dup["status"] == "Completed"

    # Query with nonexistent url
    assert mem_db.find_duplicate_download(url="https://example.com/other.zip") is None


def test_find_duplicate_by_save_path_or_filename(mem_db):
    url = "https://cdn.example.com/video1.mp4"
    save_path = "D:\\Videos\\video1.mp4"
    did = mem_db.add_download(url=url, filename="video1.mp4", save_path=save_path)
    mem_db.update_download(did, status="Queued")

    # Match by save_path
    dup = mem_db.find_duplicate_download(save_path=save_path)
    assert dup is not None
    assert dup["id"] == did

    # Match by filename
    dup2 = mem_db.find_duplicate_download(filename="video1.mp4")
    assert dup2 is not None
    assert dup2["id"] == did


def test_duplicate_warning_settings(mem_db):
    # Default is True
    assert mem_db.get_duplicate_warning_setting() is True

    mem_db.save_duplicate_warning_setting(False)
    assert mem_db.get_duplicate_warning_setting() is False

    mem_db.save_duplicate_warning_setting(True)
    assert mem_db.get_duplicate_warning_setting() is True


def test_duplicate_dialog_actions(qapp, tmp_path):
    test_file = str(tmp_path / "existing.mp4")
    with open(test_file, "w") as f:
        f.write("dummy content")

    record = {
        "id": "123",
        "url": "https://example.com/existing.mp4",
        "filename": "existing.mp4",
        "save_path": test_file,
        "status": "Completed",
        "total_size": 1024 * 1024 * 5,
        "date_added": "2026-10-15 12:00:00",
        "date_completed": "2026-10-15 12:05:00"
    }

    dlg = DuplicateDownloadDialog(record, current_url="https://example.com/existing.mp4")
    assert dlg.btn_open.isEnabled() is True

    # Test open existing action
    dlg._on_open_existing()
    assert dlg.get_action() == DuplicateDownloadDialog.ACTION_OPEN_EXISTING

    # Test redownload action
    dlg._on_redownload()
    assert dlg.get_action() == DuplicateDownloadDialog.ACTION_RE_DOWNLOAD

