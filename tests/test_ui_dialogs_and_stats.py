import os
import sys
import tempfile
import hashlib
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from core.database import Database
from core.queue_manager import QueueManager
from core.downloader import MultiThreadDownloader
from core.social_resolver import is_twitter_url
from ui.batch_add_dialog import extract_valid_urls, BatchAddDialog
from ui.add_download_dialog import AddDownloadDialog
from ui.progress_dialog import ProgressDialog
from ui.checksum_dialog import ChecksumWorker, ChecksumDialog
from ui.properties_dialog import DownloadPropertiesDialog
from ui.bandwidth_graph import BandwidthGraphWidget
from ui.main_window import MainWindow, NumericTableWidgetItem


def test_twitter_detection():
    # 1. Valid Twitter and X URLs with status
    assert is_twitter_url("https://twitter.com/elonmusk/status/1234567890123456789") is True
    assert is_twitter_url("https://x.com/OpenAI/status/9876543210987654321") is True
    assert is_twitter_url("https://www.twitter.com/user/i/status/11223344") is True
    assert is_twitter_url("http://x.com/user/status/556677?s=20") is True

    # 2. Non-status or general URLs
    assert is_twitter_url("https://twitter.com/explore") is False
    assert is_twitter_url("https://x.com/home") is False
    assert is_twitter_url("https://youtube.com/watch?v=123") is False
    assert is_twitter_url("https://example.com/file.zip") is False


def test_extract_valid_urls():
    sample_text = """
    # This is a comment
    https://sample.com/file1.zip
    Check this link: https://sample.com/file2.iso and also https://sample.com/file3.mp4!
    invalid://not-http.com
    plain text here
    https://sample.com/file1.zip  # Duplicate should be ignored
    http://insecure.org/archive.tar.gz
    """
    urls = extract_valid_urls(sample_text)
    assert len(urls) == 4
    assert "https://sample.com/file1.zip" in urls
    assert "https://sample.com/file2.iso" in urls
    assert "https://sample.com/file3.mp4" in urls
    assert "http://insecure.org/archive.tar.gz" in urls


def test_checksum_worker_and_dialog():
    app = QApplication.instance() or QApplication(sys.argv)

    # Create temporary file with known content
    test_content = b"RipSync File Integrity Checksum Test 2026!"
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        tf.write(test_content)
        temp_path = tf.name

    try:
        expected_md5 = hashlib.md5(test_content).hexdigest().lower()
        expected_sha1 = hashlib.sha1(test_content).hexdigest().lower()
        expected_sha256 = hashlib.sha256(test_content).hexdigest().lower()

        # Test ChecksumWorker directly
        worker = ChecksumWorker(temp_path)
        result = {}
        worker.sig_finished.connect(lambda data: result.update(data))
        worker.run()

        assert result.get("md5") == expected_md5
        assert result.get("sha1") == expected_sha1
        assert result.get("sha256") == expected_sha256

        # Test ChecksumDialog matching logic
        dlg = ChecksumDialog(temp_path)
        dlg.calculated_hashes = result

        # Test match
        dlg.edit_expected.setText(expected_md5.upper())  # case insensitive
        dlg._check_match()
        assert "✅ MD5 Hash Doğrulandı!" in dlg.lbl_verdict.text()

        dlg.edit_expected.setText(expected_sha256)
        dlg._check_match()
        assert "✅ SHA-256 Hash Doğrulandı!" in dlg.lbl_verdict.text()

        # Test mismatch
        dlg.edit_expected.setText("00000000000000000000000000000000")
        dlg._check_match()
        assert "❌ Hash Uyuşmuyor!" in dlg.lbl_verdict.text()

        # Test blank
        dlg.edit_expected.setText("")
        dlg._check_match()
        assert "ℹ️ Karşılaştırmak için" in dlg.lbl_verdict.text()

        dlg.close()
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_bandwidth_graph_widget():
    app = QApplication.instance() or QApplication(sys.argv)
    widget = BandwidthGraphWidget(max_samples=20)

    assert widget.max_samples == 20
    assert widget.current_speed == 0.0
    assert widget.max_speed == 0.0

    # Add speed samples
    widget.add_speed_sample(1024 * 500)  # 500 KB/s
    assert widget.current_speed == 512000.0
    assert widget.max_speed == 512000.0

    widget.add_speed_sample(1024 * 1024 * 5)  # 5 MB/s
    assert widget.current_speed == 5242880.0
    assert widget.max_speed == 5242880.0

    # Test reset
    widget.reset()
    assert widget.current_speed == 0.0
    assert widget.max_speed == 0.0


def test_download_properties_dialog():
    app = QApplication.instance() or QApplication(sys.argv)
    rec = {
        "id": "test-did-1",
        "url": "https://example.com/test_archive.zip",
        "filename": "test_archive.zip",
        "save_path": "C:\\Downloads\\test_archive.zip",
        "total_size": 104857600,  # 100 MB
        "downloaded_size": 104857600,
        "status": "Completed",
        "connections": 16,
        "quality": "max",
        "date_added": "2026-10-15 14:00:00",
        "speed": 5242880,
        "eta": 0,
        "headers": {"Referer": "https://example.com"}
    }
    dlg = DownloadPropertiesDialog(rec)
    assert "test_archive.zip" in dlg.windowTitle()
    dlg.close()


def test_auto_retry_downloader():
    dl = MultiThreadDownloader(
        download_id="test_retry_1",
        url="https://invalid.domain.ripsync.local/never_exists.bin",
        save_dir=tempfile.gettempdir(),
        filename="never_exists.bin",
        auto_retry=True,
        max_retries=2,
        retry_delay=0.1
    )
    assert dl.auto_retry is True
    assert dl.max_retries == 2
    assert dl.retry_count == 0


def test_live_search_and_filter_in_main_window():
    app = QApplication.instance() or QApplication(sys.argv)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        db = Database(db_path)
        qm = QueueManager(db)

        # Add sample records
        d1 = db.add_download("https://site.com/movie.mp4", "movie.mp4", "C:\\Downloads\\movie.mp4")
        db.update_download(d1, status="Downloading")

        d2 = db.add_download("https://site.com/music.mp3", "music.mp3", "C:\\Downloads\\music.mp3")
        db.update_download(d2, status="Completed")

        d3 = db.add_download("https://site.com/game.iso", "game.iso", "C:\\Downloads\\game.iso")
        db.update_download(d3, status="Error")

        win = MainWindow(db, qm)
        win._load_downloads_to_table()

        assert win.table.rowCount() == 3

        # Test search query filter
        win.edit_search.setText("movie")
        assert win.table.isRowHidden(0) is False  # movie.mp4
        assert win.table.isRowHidden(1) is True   # music.mp3
        assert win.table.isRowHidden(2) is True   # game.iso
        assert win.lbl_filter_count.text() == "1 / 3"

        # Test clear search
        win._clear_search()
        assert win.table.isRowHidden(0) is False
        assert win.table.isRowHidden(1) is False
        assert win.table.isRowHidden(2) is False
        assert win.lbl_filter_count.text() == "3 / 3"

        # Test chip filter: Completed
        win._on_filter_chip_clicked("Completed")
        assert win.table.isRowHidden(0) is True   # Downloading
        assert win.table.isRowHidden(1) is False  # Completed
        assert win.table.isRowHidden(2) is True   # Error
        assert win.lbl_filter_count.text() == "1 / 3"

        # Test chip filter: Downloading
        win._on_filter_chip_clicked("Downloading")
        assert win.table.isRowHidden(0) is False  # Downloading
        assert win.table.isRowHidden(1) is True
        assert win.table.isRowHidden(2) is True
        assert win.lbl_filter_count.text() == "1 / 3"

        # Reset to all
        win._on_filter_chip_clicked("all")
        assert win.lbl_filter_count.text() == "3 / 3"

        win.close()
    finally:
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except Exception:
                pass


def test_queue_reordering_top_bottom():
    db = Database(":memory:")
    qm = QueueManager(db, max_concurrent=1)

    id1 = qm.add_download("https://site.com/file1.zip", "C:\\Downloads", "file1.zip", start_now=False)
    id2 = qm.add_download("https://site.com/file2.zip", "C:\\Downloads", "file2.zip", start_now=False)
    id3 = qm.add_download("https://site.com/file3.zip", "C:\\Downloads", "file3.zip", start_now=False)

    # Initially ordered id1, id2, id3
    queued = db.get_queued_downloads_ordered()
    assert [x["id"] for x in queued] == [id1, id2, id3]

    # Move id3 to top in database
    db.move_to_top_of_queue(id3)
    queued = db.get_queued_downloads_ordered()
    assert queued[0]["id"] == id3

    # Move id3 down
    db.reorder_download(id3, "down")
    queued = db.get_queued_downloads_ordered()
    assert queued[1]["id"] == id3

    # Move id1 to bottom
    db.move_to_bottom_of_queue(id1)
    queued = db.get_queued_downloads_ordered()
    assert queued[-1]["id"] == id1


def test_numeric_table_widget_item_sorting():
    item1 = NumericTableWidgetItem("10 MB")
    item1.setData(Qt.ItemDataRole.UserRole, 10 * 1024 * 1024)

    item2 = NumericTableWidgetItem("2 MB")
    item2.setData(Qt.ItemDataRole.UserRole, 2 * 1024 * 1024)

    item3 = NumericTableWidgetItem("500 KB")
    item3.setData(Qt.ItemDataRole.UserRole, 500 * 1024)

    # Numerically: item3 < item2 < item1
    # Whereas alphabetically "10 MB" < "2 MB" < "500 KB"
    assert (item3 < item2) is True
    assert (item2 < item1) is True
    assert (item1 < item2) is False


def test_auto_open_setting_and_payload():
    app = QApplication.instance() or QApplication(sys.argv)
    db = Database(":memory:")
    qm = QueueManager(db)

    # 1. Test AddDownloadDialog auto_open flag
    dlg = AddDownloadDialog(initial_url="https://site.com/setup.exe", initial_filename="setup.exe")
    assert hasattr(dlg, "chk_auto_open")
    dlg.chk_auto_open.setChecked(True)

    confirmed_data = {}
    dlg.download_confirmed.connect(lambda d: confirmed_data.update(d))
    dlg._submit(start_now=False)
    assert confirmed_data.get("auto_open") is True
    dlg.close()

    # 2. Test QueueManager and Database persistence of auto_open
    did = qm.add_download(
        url="https://site.com/setup.exe",
        save_dir="C:\\Downloads",
        filename="setup.exe",
        start_now=False,
        auto_open=True
    )
    rec = db.get_download(did)
    assert rec["auto_open"] == 1

    # 3. Test ProgressDialog initial_auto_open and signal
    pdlg = ProgressDialog(did, "setup.exe", "C:\\Downloads\\setup.exe", initial_auto_open=True)
    assert pdlg.chk_auto_open.isChecked() is True

    signal_received = []
    pdlg.auto_open_changed.connect(lambda d, chk: signal_received.append((d, chk)))
    pdlg.chk_auto_open.setChecked(False)
    assert len(signal_received) == 1
    assert signal_received[0] == (did, False)
    pdlg.close()


def test_sound_notification_helpers():
    # Should execute cleanly without raising errors on Windows/mock
    from core.notifier import play_completion_sound, play_error_sound
    play_completion_sound()
    play_error_sound()


def test_disk_free_space_utilities():
    from core.paths import get_disk_free_space, get_disk_total_and_free
    free = get_disk_free_space(os.path.expanduser("~"))
    assert isinstance(free, int)
    assert free > 0

    free_b, total_b, drive = get_disk_total_and_free(os.path.expanduser("~"))
    assert free_b > 0
    assert total_b > 0
    assert len(drive) > 0


def test_statistics_dialog_and_db_calculations():
    app = QApplication.instance() or QApplication(sys.argv)
    db = Database(":memory:")

    # Add sample completed and queued records
    d1 = db.add_download("https://site.com/v1.mp4", "v1.mp4", "C:\\Downloads\\v1.mp4", category="Video")
    db.update_download(d1, status="Completed", total_size=50000000, downloaded_size=50000000)

    d2 = db.add_download("https://site.com/song.mp3", "song.mp3", "C:\\Downloads\\song.mp3", category="Music")
    db.update_download(d2, status="Completed", total_size=10000000, downloaded_size=10000000)

    d3 = db.add_download("https://site.com/doc.pdf", "doc.pdf", "C:\\Downloads\\doc.pdf", category="Documents")
    db.update_download(d3, status="Queued")

    stats = db.get_statistics()
    assert stats["total_count"] == 3
    assert stats["completed_count"] == 2
    assert stats["completed_bytes"] == 60000000
    assert stats["queued_count"] == 1
    assert stats["categories"].get("Video") == 1
    assert stats["categories"].get("Music") == 1
    assert stats["categories"].get("Documents") == 1

    # Verify StatisticsDialog loads cleanly
    from ui.statistics_dialog import StatisticsDialog
    sdlg = StatisticsDialog(db)
    assert sdlg.grid_cards.count() == 4
    sdlg.close()


def test_drag_and_drop_handlers():
    from PyQt6.QtCore import QMimeData, QUrl, QPointF, Qt
    from PyQt6.QtGui import QDragEnterEvent, QDropEvent
    app = QApplication.instance() or QApplication(sys.argv)
    db = Database(":memory:")
    qm = QueueManager(db)
    win = MainWindow(db, qm)

    # 1. Test dragEnterEvent accepts URLs and text
    mime = QMimeData()
    mime.setUrls([QUrl("https://sample.com/archive.zip")])
    enter_ev = QDragEnterEvent(
        QPointF(10, 10).toPoint(),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    win.dragEnterEvent(enter_ev)
    assert enter_ev.isAccepted() is True

    # 2. Test dropEvent with valid URL
    dropped_urls = []
    win._show_add_dialog = lambda initial_url="": dropped_urls.append(initial_url)
    drop_ev = QDropEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    win.dropEvent(drop_ev)
    assert "https://sample.com/archive.zip" in dropped_urls

    win.close()


