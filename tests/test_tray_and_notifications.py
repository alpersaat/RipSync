import os
import sys
import unittest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QCloseEvent

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import Database
from core.queue_manager import QueueManager
from core.power_manager import PowerCountdownManager, abort_shutdown
from core.notifier import notify_download_completed
from ui.main_window import MainWindow
from ui.tray_icon import TrayIcon

# Global QApplication for test suite
app = QApplication.instance()
if not app:
    app = QApplication([])

class TestTrayAndNotifications(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.qm = QueueManager(self.db, max_concurrent=2)
        self.win = MainWindow(self.db, self.qm)

    def tearDown(self):
        self.win.power_mgr.cancel()
        self.win.tray.hide()
        self.win.close()

    def test_window_close_minimizes_to_tray(self):
        """Test: Pencereyi kapattığınızda (X tuşu) tamamen kapanmak yerine saatin yanındaki sistem tepsisine (Tray) küçülsün."""
        self.win.show()
        self.assertTrue(self.win.isVisible())

        # Simulate clicking 'X' (close event)
        close_event = QCloseEvent()
        self.win.closeEvent(close_event)

        # The close event should be ignored (not accepted) so window doesn't destroy
        self.assertFalse(close_event.isAccepted())
        # Window should now be hidden (minimized to tray)
        self.assertFalse(self.win.isVisible())
        # Tray icon remains active
        self.assertTrue(self.win.tray.isVisible())

        # Calling toggle window from tray brings it back
        self.win._toggle_window()
        self.assertTrue(self.win.isVisible())

    def test_toast_notification_function(self):
        """Test: İndirme bittiğinde Windows Toast bildirimi: 'Video başarıyla indirildi - Klasörde Göster'."""
        # Test function runs cleanly in thread without exceptions
        temp_file = os.path.abspath(__file__)
        notify_download_completed("test_video.mp4", temp_file, is_video=True)
        notify_download_completed("archive.zip", temp_file, is_video=False)

    def test_queue_action_settings_and_tray_sync(self):
        """Test: Kuyruk bittiğinde 'Bilgisayarı Kapat' veya 'Uyku Moduna Al' seçeneği senkronizasyonu."""
        # Change via MainWindow toolbar combo
        idx_shutdown = self.win.combo_tb_queue_action.findData("shutdown")
        self.win.combo_tb_queue_action.setCurrentIndex(idx_shutdown)

        self.assertEqual(self.win.current_queue_action, "shutdown")
        self.assertEqual(self.db.get_setting("on_queue_complete_action"), "shutdown")
        self.assertEqual(self.win.tray.current_queue_action, "shutdown")
        self.assertTrue(self.win.tray.act_qa_shutdown.isChecked())

        # Change via Tray
        self.win.tray._set_queue_action("sleep")
        self.assertEqual(self.win.current_queue_action, "sleep")
        self.assertEqual(self.db.get_setting("on_queue_complete_action"), "sleep")
        self.assertEqual(self.win.combo_tb_queue_action.currentData(), "sleep")
        self.assertTrue(self.win.tray.act_qa_sleep.isChecked())

    def test_queue_empty_triggers_countdown(self):
        """Test: Kuyruk bittiğinde otomatik geri sayım diyaloğunun tetiklenmesi ve iptal mekanizması."""
        self.win.current_queue_action = "shutdown"

        # Trigger queue empty
        self.win._handle_queue_empty()

        self.assertIsNotNone(self.win.power_dialog)
        self.assertTrue(self.win.power_mgr.is_active())
        self.assertEqual(self.win.power_mgr.action, "shutdown")

        # Test countdown tick
        self.win._handle_countdown_tick(28, "shutdown")
        self.assertEqual(self.win.power_dialog.remaining_seconds, 28)

        # Test cancel
        self.win._cancel_power_countdown()
        self.assertFalse(self.win.power_mgr.is_active())
        self.assertIsNone(self.win.power_dialog)

if __name__ == "__main__":
    unittest.main()
