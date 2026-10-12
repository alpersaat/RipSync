import sys
import unittest
from unittest.mock import MagicMock, patch

from core.playlist_parser import is_youtube_playlist_url, normalize_playlist_url, fetch_playlist_metadata
from core.database import Database
from core.queue_manager import QueueManager
from ui.clipboard_monitor import ClipboardMonitor

class TestYouTubePlaylistDownloader(unittest.TestCase):
    def test_playlist_url_detection(self):
        # Valid playlist URLs
        self.assertTrue(is_youtube_playlist_url("https://www.youtube.com/playlist?list=PL6gx4Cwl9DGAcbMi1sH6oAMk4JHw91mC_"))
        self.assertTrue(is_youtube_playlist_url("https://youtube.com/playlist?list=PL6gx4Cwl9DGAcbMi1sH6oAMk4JHw91mC_"))
        self.assertTrue(is_youtube_playlist_url("https://m.youtube.com/playlist?list=PL6gx4Cwl9DGAcbMi1sH6oAMk4JHw91mC_"))
        self.assertTrue(is_youtube_playlist_url("https://www.youtube.com/watch?v=HBxCHonP6Ro&list=PL6gx4Cwl9DGAcbMi1sH6oAMk4JHw91mC_"))
        self.assertTrue(is_youtube_playlist_url("https://youtu.be/HBxCHonP6Ro?list=PL6gx4Cwl9DGAcbMi1sH6oAMk4JHw91mC_"))

        # Single video URLs or other domains
        self.assertFalse(is_youtube_playlist_url("https://www.youtube.com/watch?v=HBxCHonP6Ro"))
        self.assertFalse(is_youtube_playlist_url("https://youtu.be/HBxCHonP6Ro"))
        self.assertFalse(is_youtube_playlist_url("https://vimeo.com/12345678"))
        self.assertFalse(is_youtube_playlist_url("https://example.com/playlist?list=PL123"))
        self.assertFalse(is_youtube_playlist_url(""))

    def test_normalize_playlist_url(self):
        watch_with_list = "https://www.youtube.com/watch?v=HBxCHonP6Ro&list=PL6gx4Cwl9DGAcbMi1sH6oAMk4JHw91mC_&index=3"
        normalized = normalize_playlist_url(watch_with_list)
        self.assertEqual(normalized, "https://www.youtube.com/playlist?list=PL6gx4Cwl9DGAcbMi1sH6oAMk4JHw91mC_")

        pure_list = "https://www.youtube.com/playlist?list=PL6gx4Cwl9DGAcbMi1sH6oAMk4JHw91mC_"
        self.assertEqual(normalize_playlist_url(pure_list), pure_list)

    def test_clipboard_analyzer_detects_playlist(self):
        info = ClipboardMonitor.analyze_url("https://www.youtube.com/playlist?list=PL6gx4Cwl9DGAcbMi1sH6oAMk4JHw91mC_")
        self.assertIsNotNone(info)
        self.assertTrue(info.get("is_video"))
        self.assertTrue(info.get("is_playlist"))
        self.assertEqual(info.get("service"), "YouTube Oynatma Listesi")

        # Single video test
        single_info = ClipboardMonitor.analyze_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertIsNotNone(single_info)
        self.assertTrue(single_info.get("is_video"))
        self.assertFalse(single_info.get("is_playlist"))

    def test_batch_download_queuing(self):
        db = Database(":memory:")
        qm = QueueManager(db, max_concurrent=2)

        # Simulate batch adding playlist items
        items = [
            {"url": f"https://www.youtube.com/watch?v=vid{i}", "filename": f"{i:02d} - Video {i}.mp4", "save_dir": "C:/Downloads/Videolar", "quality": "1080p"}
            for i in range(1, 6)
        ]

        added_ids = []
        for it in items:
            did = qm.add_download(
                url=it["url"],
                save_dir=it["save_dir"],
                filename=it["filename"],
                quality=it["quality"],
                start_now=True
            )
            added_ids.append(did)

        self.assertEqual(len(added_ids), 5)
        # Verify they are registered in DB
        records = [db.get_download(did) for did in added_ids]
        for idx, rec in enumerate(records, 1):
            self.assertIsNotNone(rec)
            self.assertEqual(rec["filename"], f"{idx:02d} - Video {idx}.mp4")

        # Check queue status: first up to max_concurrent (2) are actively downloading/probing or queued
        active_count = qm.get_active_count()
        self.assertLessEqual(active_count, 2)

    def test_fetch_playlist_metadata(self):
        # Test real extraction on public playlist
        url = "https://www.youtube.com/playlist?list=PL6gx4Cwl9DGAcbMi1sH6oAMk4JHw91mC_"
        meta = fetch_playlist_metadata(url)
        self.assertIn("title", meta)
        self.assertGreater(meta["count"], 0)
        self.assertGreater(len(meta["entries"]), 0)

        first = meta["entries"][0]
        self.assertIn("title", first)
        self.assertIn("url", first)
        self.assertIn("duration_str", first)
        self.assertIn("thumbnail", first)
        self.assertEqual(first["index"], 1)

if __name__ == "__main__":
    unittest.main()
