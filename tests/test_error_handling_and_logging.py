import os
import json
import sqlite3
import pytest
from unittest.mock import patch, MagicMock

from core.logger import init_logging, get_logger, register_log_listener, unregister_log_listener
from core.notifier import notify_error, notify_warning
from core.paths import resolve_file_conflict, get_disk_free_space
from core.database import Database
from core.downloader import MultiThreadDownloader
from core.queue_manager import QueueManager


def test_logger_initialization_and_broadcast(tmp_path):
    """Test logger initialization and error broadcasting to listeners."""
    broadcasted = []

    def on_error(level, short_msg, full_msg):
        broadcasted.append((level, short_msg))

    register_log_listener(on_error)
    try:
        logger = get_logger("test_module")
        logger.error("Kritik test hatası")

        assert len(broadcasted) == 1
        assert broadcasted[0][0] == "ERROR"
        assert "Kritik test hatası" in broadcasted[0][1]
    finally:
        unregister_log_listener(on_error)


def test_notify_error_logs_and_triggers_toast():
    """Test notify_error logs the error and triggers Windows toast and chime."""
    with patch("core.notifier.play_error_sound") as mock_sound, \
         patch("core.notifier.logger.error") as mock_log, \
         patch("threading.Thread") as mock_thread:
        notify_error("Disk Hatası", "Hedef sürücüde yer kalmadı.")
        mock_log.assert_called_once()
        mock_sound.assert_called_once()
        mock_thread.assert_called_once()


def test_notify_warning_logs_and_triggers_toast():
    """Test notify_warning logs the warning."""
    with patch("core.notifier.logger.warning") as mock_log, \
         patch("threading.Thread") as mock_thread:
        notify_warning("Düşük Alan", "Sürücüde 50 MB kaldı.")
        mock_log.assert_called_once()
        mock_thread.assert_called_once()


def test_downloader_save_state_error_handling(tmp_path):
    """Test that failure during _save_state logs an error and notifies user instead of silent pass."""
    dl = MultiThreadDownloader(
        download_id="test_dl_1",
        url="http://example.com/file.zip",
        save_dir=str(tmp_path),
        filename="file.zip"
    )
    dl.state_file = str(tmp_path / "protected" / "state.json")  # non-existent directory -> causes error

    with patch("core.downloader.logger.error") as mock_log_err, \
         patch("core.downloader.notify_error") as mock_notify:
        dl._save_state()
        mock_log_err.assert_called_once()
        mock_notify.assert_called_once()


def test_downloader_allocate_file_error_handling(tmp_path):
    """Test that file allocation error is logged, status set to Error, and user notified."""
    dl = MultiThreadDownloader(
        download_id="test_dl_2",
        url="http://example.com/file.zip",
        save_dir=str(tmp_path),
        filename="file.zip"
    )
    dl.save_path = str(tmp_path / "non_existing_dir_123" / "file.zip")  # Cannot open without dir
    dl.total_size = 1024

    with patch("core.downloader.logger.error") as mock_log_err, \
         patch("core.downloader.notify_error") as mock_notify:
        result = dl._allocate_file()
        assert result is False
        assert dl.status == "Error"
        assert "Dosya alanı ayrılamadı" in dl.error_message
        mock_log_err.assert_called_once()
        mock_notify.assert_called_once()


def test_resolve_file_conflict_error_handling(tmp_path):
    """Test that resolve_file_conflict handles unexpected filesystem errors gracefully."""
    with patch("os.path.exists", side_effect=PermissionError("Erişim engellendi")), \
         patch("core.logger.get_logger") as mock_get_logger:
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        resolved_name, conflicted = resolve_file_conflict(str(tmp_path), "test.txt")
        assert resolved_name == "test.txt"
        assert conflicted is False
        mock_logger.error.assert_called_once()


def test_get_disk_free_space_error_handling():
    """Test that get_disk_free_space logs warnings on invalid drive/error instead of silent pass."""
    with patch("shutil.disk_usage", side_effect=OSError("Drive not ready")), \
         patch("core.logger.get_logger") as mock_get_logger:
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        free_sp = get_disk_free_space("Z:\\nonexistent_drive")
        assert free_sp == -1
        mock_logger.warning.assert_called_once()


def test_database_update_download_error_handling():
    """Test that sqlite error in update_download is logged and notified."""
    db = Database(":memory:")
    with patch.object(db, "_get_connection", side_effect=sqlite3.OperationalError("database is locked")), \
         patch("core.database.logger.error") as mock_db_err, \
         patch("core.database.notify_error") as mock_notify:
        db.update_download("dl_123", status="Downloading")
        mock_db_err.assert_called_once()
        mock_notify.assert_called_once()


def test_database_add_download_error_handling():
    """Test that sqlite error in add_download raises, logs and notifies."""
    db = Database(":memory:")
    with patch.object(db, "_get_connection", side_effect=sqlite3.DatabaseError("disk I/O error")), \
         patch("core.database.logger.error") as mock_db_err, \
         patch("core.database.notify_error") as mock_notify:
        with pytest.raises(sqlite3.Error):
            db.add_download(url="http://test.com", filename="file.bin", save_path="/tmp/file.bin")
        mock_db_err.assert_called_once()
        mock_notify.assert_called_once()


def test_queue_manager_disk_space_rejection(tmp_path):
    """Test that QueueManager prevents download start and notifies when disk space is critically low."""
    db = Database(":memory:")
    qm = QueueManager(db, max_concurrent=2)

    did = db.add_download(
        url="http://example.com/big_file.iso",
        filename="big_file.iso",
        save_path=str(tmp_path / "big_file.iso")
    )

    # Mock disk free space to only 5 MB (below 10 MB threshold)
    with patch("core.queue_manager.get_disk_free_space", return_value=5 * 1024 * 1024), \
         patch("core.queue_manager.logger.error") as mock_qm_err, \
         patch("core.queue_manager.notify_error") as mock_notify:
        qm.start_download(did, save_dir=str(tmp_path), filename="big_file.iso")

        rec = db.get_download(did)
        assert rec["status"] == "Error"
        assert "Yetersiz disk alanı" in rec["error_message"]
        mock_qm_err.assert_called_once()
        mock_notify.assert_called_once()
