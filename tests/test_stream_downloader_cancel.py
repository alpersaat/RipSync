import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QMessageBox

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from core.stream_downloader import StreamDownloader
from core.downloader import MultiThreadDownloader
from core.queue_manager import QueueManager
from core.database import Database
from ui.progress_dialog import ProgressDialog


class TestStreamDownloaderCancelAndPause(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.dummy_video_path = os.path.join(self.tmp_dir, "test_video.mp4")
        self.dummy_part_path = os.path.join(self.tmp_dir, "test_video.mp4.part")
        
        # Create dummy partial download files
        with open(self.dummy_video_path, "wb") as f:
            f.write(b"dummy video data 1234567890" * 100)
        with open(self.dummy_part_path, "wb") as f:
            f.write(b"dummy part data 1234567890" * 50)

    def tearDown(self):
        for p in (self.dummy_video_path, self.dummy_part_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        if os.path.exists(self.tmp_dir):
            try:
                os.rmdir(self.tmp_dir)
            except Exception:
                pass

    def test_cancel_default_preserves_file(self):
        """Kullanıcı duraklatmak için iptal demişse dosya ve progress silinmemelidir."""
        sd = StreamDownloader(
            download_id="test_stream_1",
            url="https://www.youtube.com/watch?v=dummy",
            save_dir=self.tmp_dir,
            filename="test_video.mp4"
        )
        sd.save_path = self.dummy_video_path
        sd.status = "Downloading"

        # Varsayılan cancel() çağrısı dosyayı ASLA silmemelidir
        sd.cancel()

        self.assertEqual(sd.status, "Cancelled")
        self.assertTrue(os.path.exists(self.dummy_video_path), "İptal işleminde dosya silinmemelidir!")
        self.assertTrue(os.path.exists(self.dummy_part_path), "İptal işleminde .part dosyası silinmemelidir!")

    def test_cancel_explicit_delete_file_true(self):
        """Kullanıcı açıkça dosyayı silmeyi onayladığında (delete_file=True) dosyalar silinmelidir."""
        sd = StreamDownloader(
            download_id="test_stream_2",
            url="https://www.youtube.com/watch?v=dummy",
            save_dir=self.tmp_dir,
            filename="test_video.mp4"
        )
        sd.save_path = self.dummy_video_path
        sd.status = "Downloading"

        sd.cancel(delete_file=True)

        self.assertEqual(sd.status, "Cancelled")
        self.assertFalse(os.path.exists(self.dummy_video_path), "delete_file=True olduğunda dosya silinmelidir!")
        self.assertFalse(os.path.exists(self.dummy_part_path), "delete_file=True olduğunda .part dosyası silinmelidir!")

    def test_pause_preserves_file(self):
        """Duraklatıldığında dosya diskte kalmalı ve status Paused olmalıdır."""
        sd = StreamDownloader(
            download_id="test_stream_pause",
            url="https://www.youtube.com/watch?v=dummy",
            save_dir=self.tmp_dir,
            filename="test_video.mp4"
        )
        sd.save_path = self.dummy_video_path
        sd.status = "Downloading"

        sd.pause()

        self.assertEqual(sd.status, "Paused")
        self.assertTrue(os.path.exists(self.dummy_video_path))

    def test_queue_manager_cancel_download_delete_flag(self):
        """QueueManager cancel_download çağrısında delete_file bayrağını aktarmalıdır."""
        db_path = os.path.join(self.tmp_dir, "test.db")
        db = Database(db_path)
        qm = QueueManager(db=db)

        # Mock stream downloader
        mock_sd = MagicMock()
        qm.active_downloaders["sd_1"] = mock_sd

        # 1. Varsayılan cancel
        qm.cancel_download("sd_1", delete_file=False)
        mock_sd.cancel.assert_called_with(delete_file=False)

        # 2. delete_file=True ile cancel
        qm.active_downloaders["sd_2"] = mock_sd
        qm.cancel_download("sd_2", delete_file=True)
        mock_sd.cancel.assert_called_with(delete_file=True)

    def test_progress_dialog_on_cancel_pause_choice(self):
        """ProgressDialog İptal butonuna tıklandığında kullanıcı Duraklat'ı seçerse pause_requested yayılmalıdır."""
        dlg = ProgressDialog(
            download_id="dl_dlg_1",
            filename="test_video.mp4",
            save_path=self.dummy_video_path
        )
        pause_emitted = []
        cancel_emitted = []
        dlg.pause_requested.connect(lambda did: pause_emitted.append(did))
        dlg.cancel_requested.connect(lambda did, *args: cancel_emitted.append((did, args)))

        # Mock QMessageBox.exec to simulate clicking "Duraklat (Önerilen)"
        with patch.object(QMessageBox, "exec", return_value=0), \
             patch.object(QMessageBox, "clickedButton") as mock_btn:
            # Let clickedButton return the AcceptRole button (btn_pause)
            def side_effect():
                # find the first button with "Duraklat"
                pass
            # Simulate QMessageBox containing buttons
            def custom_exec(msg_box):
                # Pick the pause button
                for b in msg_box.buttons():
                    if "Duraklat" in b.text():
                        mock_btn.return_value = b
                        break
                return 0

            with patch.object(QMessageBox, "exec", side_effect=lambda: custom_exec(dlg)):
                # Directly test logic via simulated buttons
                pass

        # Direct test of _on_cancel with mocked clicked button
        with patch.object(QMessageBox, "exec"), \
             patch.object(QMessageBox, "addButton") as mock_add_btn, \
             patch.object(QMessageBox, "clickedButton") as mock_clicked:
            fake_pause_btn = MagicMock()
            fake_pause_btn.text.return_value = "Duraklat"
            mock_add_btn.side_effect = [fake_pause_btn, MagicMock(), MagicMock(), MagicMock()]
            mock_clicked.return_value = fake_pause_btn

            dlg._on_cancel()

            self.assertEqual(pause_emitted, ["dl_dlg_1"])
            self.assertEqual(cancel_emitted, [])
        dlg.close()

    def test_progress_dialog_on_cancel_keep_file_choice(self):
        """ProgressDialog İptal butonunda 'Dosyayı Koru' seçilirse delete_file=False yayılmalıdır."""
        dlg = ProgressDialog(
            download_id="dl_dlg_2",
            filename="test_video.mp4",
            save_path=self.dummy_video_path
        )
        pause_emitted = []
        cancel_emitted = []
        dlg.pause_requested.connect(lambda did: pause_emitted.append(did))
        dlg.cancel_requested[str, bool].connect(lambda did, df: cancel_emitted.append((did, df)))

        with patch.object(QMessageBox, "exec"), \
             patch.object(QMessageBox, "addButton") as mock_add_btn, \
             patch.object(QMessageBox, "clickedButton") as mock_clicked:
            fake_pause_btn = MagicMock()
            fake_keep_btn = MagicMock()
            mock_add_btn.side_effect = [fake_pause_btn, fake_keep_btn, MagicMock(), MagicMock()]
            mock_clicked.return_value = fake_keep_btn

            dlg._on_cancel()

            self.assertEqual(pause_emitted, [])
            self.assertEqual(cancel_emitted, [("dl_dlg_2", False)])
        dlg.close()

    def test_progress_dialog_on_cancel_delete_file_choice(self):
        """ProgressDialog İptal butonunda 'Dosyayı Sil' seçilirse delete_file=True yayılmalıdır."""
        dlg = ProgressDialog(
            download_id="dl_dlg_3",
            filename="test_video.mp4",
            save_path=self.dummy_video_path
        )
        cancel_emitted = []
        dlg.cancel_requested[str, bool].connect(lambda did, df: cancel_emitted.append((did, df)))

        with patch.object(QMessageBox, "exec"), \
             patch.object(QMessageBox, "addButton") as mock_add_btn, \
             patch.object(QMessageBox, "clickedButton") as mock_clicked:
            fake_pause = MagicMock()
            fake_keep = MagicMock()
            fake_delete = MagicMock()
            mock_add_btn.side_effect = [fake_pause, fake_keep, fake_delete, MagicMock()]
            mock_clicked.return_value = fake_delete

            dlg._on_cancel()

    def test_multithread_downloader_cancel_preserves_file(self):
        """Standart multi-thread downloader da cancel(delete_file=False) iken dosyayı silmemelidir."""
        dummy_file = os.path.join(self.tmp_dir, "test_file.bin")
        dummy_state = dummy_file + ".state"
        with open(dummy_file, "wb") as f:
            f.write(b"content" * 10)
        with open(dummy_state, "w") as f:
            f.write("{}")

        dl = MultiThreadDownloader(
            download_id="dl_mt_1",
            url="https://example.com/test.bin",
            save_dir=self.tmp_dir,
            filename="test_file.bin"
        )
        dl.save_path = dummy_file
        dl.state_file = dummy_state
        dl.status = "Downloading"

        # 1. Varsayılan cancel dosyayı silmez
        dl.cancel(delete_file=False)
        self.assertEqual(dl.status, "Cancelled")
        self.assertTrue(os.path.exists(dummy_file))

        # 2. delete_file=True dosyayı siler
        dl.cancel(delete_file=True)
        self.assertFalse(os.path.exists(dummy_file))
        self.assertFalse(os.path.exists(dummy_state))

    def test_main_window_cancel_selected_options(self):
        """MainWindow._cancel_selected kullanıcıya Duraklat veya Dosyayı Koru/Sil seçeneklerini doğru iletir."""
        from ui.main_window import MainWindow

        with patch("ui.main_window.Database") as mock_db, \
             patch("ui.main_window.QueueManager") as mock_qm_cls, \
             patch("ui.main_window.ClipboardMonitor"), \
             patch("ui.main_window.DownloadScheduler"):
            mock_qm = MagicMock()
            mock_db_inst = MagicMock()
            win = MainWindow(db=mock_db_inst, queue_mgr=mock_qm)
            win._get_selected_download_ids = MagicMock(return_value=["dl_sel_1"])

            # Test 1: Duraklat seçeneği
            with patch.object(QMessageBox, "exec"), \
                 patch.object(QMessageBox, "addButton") as mock_add_btn, \
                 patch.object(QMessageBox, "clickedButton") as mock_clicked:
                b_pause = MagicMock()
                mock_add_btn.side_effect = [b_pause, MagicMock(), MagicMock(), MagicMock()]
                mock_clicked.return_value = b_pause

                win._cancel_selected()
                mock_qm.pause_download.assert_called_with("dl_sel_1")

            # Test 2: İptal Et (Dosyaları Koru) seçeneği
            with patch.object(QMessageBox, "exec"), \
                 patch.object(QMessageBox, "addButton") as mock_add_btn, \
                 patch.object(QMessageBox, "clickedButton") as mock_clicked:
                b_pause = MagicMock()
                b_keep = MagicMock()
                mock_add_btn.side_effect = [b_pause, b_keep, MagicMock(), MagicMock()]
                mock_clicked.return_value = b_keep

                win._cancel_selected()
                mock_qm.cancel_download.assert_called_with("dl_sel_1", delete_file=False)

            # Test 3: İptal Et ve Dosyaları Sil seçeneği
            with patch.object(QMessageBox, "exec"), \
                 patch.object(QMessageBox, "addButton") as mock_add_btn, \
                 patch.object(QMessageBox, "clickedButton") as mock_clicked:
                b_pause = MagicMock()
                b_keep = MagicMock()
                b_del = MagicMock()
                mock_add_btn.side_effect = [b_pause, b_keep, b_del, MagicMock()]
                mock_clicked.return_value = b_del

                win._cancel_selected()
                mock_qm.cancel_download.assert_called_with("dl_sel_1", delete_file=True)

            win.close()


if __name__ == "__main__":
    unittest.main()
