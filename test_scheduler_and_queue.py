import os
import sys
import unittest
import tempfile
import time
from datetime import datetime, date, time as dtime, timedelta
from unittest.mock import MagicMock

# Ensure current directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database import Database
from core.scheduler import DownloadScheduler, parse_time_str
from core.queue_manager import QueueManager

class TestSchedulerLogic(unittest.TestCase):
    def test_parse_time_str(self):
        t1 = parse_time_str("02:00")
        self.assertEqual(t1, dtime(2, 0, 0))

        t2 = parse_time_str("07:30")
        self.assertEqual(t2, dtime(7, 30, 0))

        t3 = parse_time_str("invalid")
        self.assertEqual(t3, dtime(2, 0, 0))

    def test_in_window_same_day(self):
        # 02:00 to 07:00
        sched = DownloadScheduler(enabled=True, start_time="02:00", stop_enabled=True, stop_time="07:00")

        # 01:59 -> False
        dt_before = datetime(2026, 10, 12, 1, 59, 59)
        self.assertFalse(sched.is_in_schedule_window(dt_before))

        # 02:00 -> True
        dt_start = datetime(2026, 10, 12, 2, 0, 0)
        self.assertTrue(sched.is_in_schedule_window(dt_start))

        # 04:30 -> True
        dt_mid = datetime(2026, 10, 12, 4, 30, 0)
        self.assertTrue(sched.is_in_schedule_window(dt_mid))

        # 06:59:59 -> True
        dt_end = datetime(2026, 10, 12, 6, 59, 59)
        self.assertTrue(sched.is_in_schedule_window(dt_end))

        # 07:00 -> False
        dt_after = datetime(2026, 10, 12, 7, 0, 0)
        self.assertFalse(sched.is_in_schedule_window(dt_after))

        # 14:00 -> False
        dt_day = datetime(2026, 10, 12, 14, 0, 0)
        self.assertFalse(sched.is_in_schedule_window(dt_day))

    def test_in_window_cross_midnight(self):
        # 23:00 to 06:00
        sched = DownloadScheduler(enabled=True, start_time="23:00", stop_enabled=True, stop_time="06:00")

        # 22:59 -> False
        self.assertFalse(sched.is_in_schedule_window(datetime(2026, 10, 12, 22, 59, 0)))

        # 23:00 -> True
        self.assertTrue(sched.is_in_schedule_window(datetime(2026, 10, 12, 23, 0, 0)))

        # 03:00 next morning -> True
        self.assertTrue(sched.is_in_schedule_window(datetime(2026, 10, 13, 3, 0, 0)))

        # 05:59:59 -> True
        self.assertTrue(sched.is_in_schedule_window(datetime(2026, 10, 13, 5, 59, 59)))

        # 06:00 -> False
        self.assertFalse(sched.is_in_schedule_window(datetime(2026, 10, 13, 6, 0, 0)))

    def test_day_of_week_filter(self):
        # Active only on Monday (0) and Tuesday (1)
        sched = DownloadScheduler(enabled=True, days=[0, 1])

        mon = datetime(2026, 10, 12)  # Monday
        tue = datetime(2026, 10, 13)  # Tuesday
        wed = datetime(2026, 10, 14)  # Wednesday

        self.assertTrue(sched.is_day_active(mon))
        self.assertTrue(sched.is_day_active(tue))
        self.assertFalse(sched.is_day_active(wed))

    def test_status_calculation_and_countdown(self):
        sched = DownloadScheduler(
            enabled=True,
            start_time="02:00",
            stop_enabled=True,
            stop_time="07:00",
            days=[0, 1, 2, 3, 4, 5, 6]
        )

        # Before start time: 22:00 on Sunday Oct 11 -> next event start at 02:00 Oct 12 (4 hours = 14400s)
        now_dt = datetime(2026, 10, 11, 22, 0, 0)
        status = sched.get_status(now_dt)
        self.assertTrue(status["enabled"])
        self.assertFalse(status["is_in_window"])
        self.assertEqual(status["next_event"], "start")
        self.assertEqual(status["seconds_remaining"], 4 * 3600)
        self.assertIn("4 sa 00 dk", status["time_remaining_str"])

        # Inside window: 03:30 on Monday Oct 12 -> next event stop at 07:00 Oct 12 (3.5 hours = 12600s)
        now_dt2 = datetime(2026, 10, 12, 3, 30, 0)
        status2 = sched.get_status(now_dt2)
        self.assertTrue(status2["is_in_window"])
        self.assertEqual(status2["next_event"], "stop")
        self.assertEqual(status2["seconds_remaining"], 3 * 3600 + 30 * 60)
        self.assertIn("3 sa 30 dk", status2["time_remaining_str"])

    def test_exact_minute_triggers(self):
        sched = DownloadScheduler(
            enabled=True,
            start_time="02:00",
            stop_enabled=True,
            stop_time="07:00",
            days=[0]  # Monday
        )

        start_mock = MagicMock()
        stop_mock = MagicMock()
        sched.on_schedule_start = start_mock
        sched.on_schedule_stop = stop_mock

        # Tick at 02:00 on Monday
        dt_start = datetime(2026, 10, 12, 2, 0, 15)  # Monday 02:00:15
        sched.tick(dt_start)
        self.assertEqual(start_mock.call_count, 1)

        # Repeating tick inside same minute should not trigger again today
        sched.tick(datetime(2026, 10, 12, 2, 0, 45))
        self.assertEqual(start_mock.call_count, 1)

        # Tick at 07:00 on Monday
        dt_stop = datetime(2026, 10, 12, 7, 0, 5)
        sched.tick(dt_stop)
        self.assertEqual(stop_mock.call_count, 1)

class TestSequentialQueueManager(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.qm = QueueManager(self.db, max_concurrent=2)
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        self.qm.pause_queue()

    def test_database_queue_ordering(self):
        """Test queue order assignment and reordering."""
        id1 = self.db.add_download("http://example.com/file1.zip", "file1.zip", self.temp_dir)
        id2 = self.db.add_download("http://example.com/file2.zip", "file2.zip", self.temp_dir)
        id3 = self.db.add_download("http://example.com/file3.zip", "file3.zip", self.temp_dir)

        queued = self.db.get_queued_downloads_ordered()
        self.assertEqual([q["id"] for q in queued], [id1, id2, id3])

        # Move file3 UP
        res = self.db.reorder_download(id3, "up")
        self.assertTrue(res)
        queued = self.db.get_queued_downloads_ordered()
        self.assertEqual([q["id"] for q in queued], [id1, id3, id2])

        # Move file3 to TOP
        res_top = self.db.move_to_top_of_queue(id2)
        self.assertTrue(res_top)
        queued = self.db.get_queued_downloads_ordered()
        self.assertEqual(queued[0]["id"], id2)

    def test_sequential_concurrency_limit(self):
        """
        Test: max_concurrent = 2
        Adding 4 downloads with start_now=True:
        Only 2 should be started, 2 should remain queued.
        When one finishes, the next queued download should start automatically.
        """
        self.qm.set_max_concurrent(2)

        # Mock start_download internal thread execution
        started_ids = []
        original_start = self.qm.start_download

        def mock_start(download_id, *args, **kwargs):
            started_ids.append(download_id)
            # Create a mock active downloader
            mock_dl = MagicMock()
            mock_dl.status = "Downloading"
            mock_dl.download_id = download_id
            with self.qm.lock:
                self.qm.active_downloaders[download_id] = mock_dl
            self.db.update_download(download_id, status="Downloading")

        self.qm.start_download = mock_start

        # Add 4 downloads with start_now=True
        d1 = self.qm.add_download("http://example.com/1.zip", self.temp_dir, "1.zip", start_now=True)
        d2 = self.qm.add_download("http://example.com/2.zip", self.temp_dir, "2.zip", start_now=True)
        d3 = self.qm.add_download("http://example.com/3.zip", self.temp_dir, "3.zip", start_now=True)
        d4 = self.qm.add_download("http://example.com/4.zip", self.temp_dir, "4.zip", start_now=True)

        # Exactly 2 should have started
        self.assertEqual(started_ids, [d1, d2])
        self.assertEqual(self.qm.get_active_count(), 2)

        # d3 and d4 must be queued
        rec3 = self.db.get_download(d3)
        rec4 = self.db.get_download(d4)
        self.assertEqual(rec3["status"], "Queued")
        self.assertEqual(rec4["status"], "Queued")

        # Now simulate d1 completing
        with self.qm.lock:
            self.qm.active_downloaders.pop(d1, None)
        self.db.update_download(d1, status="Completed")
        self.qm._check_queue()

        # Slot freed! d3 must now have been started
        self.assertIn(d3, started_ids)
        self.assertEqual(self.qm.get_active_count(), 2)

        # Now simulate d2 completing
        with self.qm.lock:
            self.qm.active_downloaders.pop(d2, None)
        self.db.update_download(d2, status="Completed")
        self.qm._check_queue()

        # d4 must now have started
        self.assertIn(d4, started_ids)
        self.assertEqual(self.qm.get_active_count(), 2)

    def test_pause_frees_slot_for_queued_item(self):
        """When an active download is paused, slot frees up and the next queued item starts."""
        self.qm.set_max_concurrent(1)
        started_ids = []

        def mock_start(download_id, *args, **kwargs):
            started_ids.append(download_id)
            mock_dl = MagicMock()
            mock_dl.status = "Downloading"
            mock_dl.download_id = download_id
            with self.qm.lock:
                self.qm.active_downloaders[download_id] = mock_dl
            self.db.update_download(download_id, status="Downloading")

        self.qm.start_download = mock_start

        d1 = self.qm.add_download("http://example.com/1.zip", self.temp_dir, "1.zip", start_now=True)
        d2 = self.qm.add_download("http://example.com/2.zip", self.temp_dir, "2.zip", start_now=True)

        self.assertEqual(started_ids, [d1])
        self.assertEqual(self.db.get_download(d2)["status"], "Queued")

        # Pause d1
        mock_dl = self.qm.active_downloaders[d1]
        def mock_pause():
            mock_dl.status = "Paused"
            self.db.update_download(d1, status="Paused")
        mock_dl.pause = mock_pause

        self.qm.pause_download(d1)

        # d2 should now be started
        self.assertIn(d2, started_ids)

    def test_scheduler_attaches_and_triggers_queue(self):
        """Verify scheduler start triggers queue_mgr.start_queue and stop pauses queue."""
        sched = DownloadScheduler(enabled=True, on_stop_action="shutdown")

        start_called = [False]
        pause_called = [False]
        power_action = [None]

        self.qm.start_queue = lambda: start_called.__setitem__(0, True)
        self.qm.pause_queue = lambda: pause_called.__setitem__(0, True)
        self.qm.on_scheduler_power_action = lambda act: power_action.__setitem__(0, act)
        self.qm.attach_scheduler(sched)

        # Trigger start
        sched._trigger_start()
        self.assertTrue(start_called[0])

        # Trigger stop
        sched._trigger_stop()
        self.assertTrue(pause_called[0])
        self.assertEqual(power_action[0], "shutdown")

from PyQt6.QtWidgets import QApplication
from ui.scheduler_dialog import SchedulerDialog
from ui.main_window import MainWindow

app = QApplication.instance()
if not app:
    app = QApplication([])

class TestSchedulerAndQueueUI(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.qm = QueueManager(self.db, max_concurrent=2)
        self.sched = DownloadScheduler(
            enabled=False,
            start_time="02:00",
            stop_enabled=True,
            stop_time="07:00",
            days=[0, 1, 2, 3, 4, 5, 6]
        )
        self.win = MainWindow(self.db, self.qm)

    def tearDown(self):
        self.win.scheduler.stop()
        self.win.power_mgr.cancel()
        self.win.tray.hide()
        self.win.close()

    def test_mainwindow_toolbar_scheduler_and_concurrency(self):
        """Test: Toolbar has scheduler and concurrent spinbox properly initialized."""
        self.assertEqual(self.win.spin_tb_concurrent.value(), 2)
        self.assertFalse(self.win.chk_tb_scheduler.isChecked())
        self.assertEqual(self.win.lbl_tb_sched_time.text(), "02:00 - 07:00")
        self.assertEqual(self.win.lbl_tb_sched_badge.text(), "Kapalı")

        # Change concurrent spinbox
        self.win.spin_tb_concurrent.setValue(3)
        self.assertEqual(self.qm.max_concurrent, 3)

        # Toggle scheduler from toolbar
        self.win.chk_tb_scheduler.setChecked(True)
        self.assertTrue(self.win.scheduler.enabled)
        saved_settings = self.db.get_scheduler_settings()
        self.assertTrue(saved_settings["enabled"])

    def test_scheduler_dialog_controls_and_save(self):
        """Test: SchedulerDialog loads, allows configuration changes, and saves correctly."""
        dlg = SchedulerDialog(self.db, self.qm, self.win.scheduler, parent=self.win)

        # Verify defaults
        self.assertEqual(dlg.time_start.time().toString("HH:mm"), "02:00")
        self.assertEqual(dlg.time_stop.time().toString("HH:mm"), "07:00")
        self.assertEqual(dlg.spin_concurrent.value(), self.qm.max_concurrent)

        # Add mock queued downloads to test table
        d1 = self.db.add_download("http://example.com/a.zip", "a.zip", "C:/Downloads")
        d2 = self.db.add_download("http://example.com/b.zip", "b.zip", "C:/Downloads")
        dlg._refresh_queued_table()
        self.assertEqual(dlg.table_queued.rowCount(), 2)

        # Test presets
        dlg._set_preset_time(1, 0, 5, 0)
        self.assertEqual(dlg.time_start.time().toString("HH:mm"), "01:00")
        self.assertEqual(dlg.time_stop.time().toString("HH:mm"), "05:00")

        # Test save and close
        dlg.chk_enable_scheduler.setChecked(True)
        dlg.spin_concurrent.setValue(4)
        dlg._save_and_close()

        # Check DB and Live objects
        self.assertEqual(self.qm.max_concurrent, 4)
        self.assertTrue(self.win.scheduler.enabled)
        self.assertEqual(self.win.scheduler.start_time_str, "01:00")
        self.assertEqual(self.win.scheduler.stop_time_str, "05:00")

if __name__ == "__main__":
    unittest.main()

