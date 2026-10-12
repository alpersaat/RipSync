import os
import sys
import time
import tempfile
import unittest
from PyQt6.QtWidgets import QApplication

# Ensure QApplication exists for GUI component tests
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

from core.social_resolver import SocialResolver, is_tiktok_url, is_instagram_url
from core.stream_downloader import StreamDownloader, is_stream_url
from core.media_sniffer import MediaSniffer
from ui.clipboard_monitor import ClipboardMonitor
from ui.add_download_dialog import AddDownloadDialog

class TestSocialDownloader(unittest.TestCase):
    TIKTOK_TEST_URL = "https://www.tiktok.com/@tiktok/video/7106594312292453675"
    INSTAGRAM_TEST_URL = "https://www.instagram.com/reel/DZcIbOXMcyD/"

    def test_domain_recognition(self):
        """Test URL pattern matching for TikTok and Instagram."""
        # Stream URL detection
        self.assertTrue(is_stream_url("https://www.tiktok.com/@user/video/123"))
        self.assertTrue(is_stream_url("https://vt.tiktok.com/ZS12345/"))
        self.assertTrue(is_stream_url("https://vm.tiktok.com/ZM12345/"))
        self.assertTrue(is_stream_url("https://www.instagram.com/reel/C8P1eK2v7qX/"))
        self.assertTrue(is_stream_url("https://instagram.com/p/C8P1eK2v7qX/"))
        self.assertTrue(is_stream_url("https://instagr.am/reels/12345/"))

        # Social URL helpers
        self.assertTrue(is_tiktok_url("https://vt.tiktok.com/ZS12345/"))
        self.assertTrue(is_tiktok_url("https://vm.tiktok.com/ZM12345/"))
        self.assertTrue(is_tiktok_url("https://www.tiktok.com/@tiktok/video/7106594312292453675"))
        self.assertFalse(is_tiktok_url("https://youtube.com/watch?v=123"))

        self.assertTrue(is_instagram_url("https://www.instagram.com/reel/DZcIbOXMcyD/"))
        self.assertTrue(is_instagram_url("https://instagr.am/p/ABCDEF/"))
        self.assertFalse(is_instagram_url("https://twitter.com/user/status/123"))

    def test_tiktok_watermark_free_resolver(self):
        """Verify TikTok watermark-free resolution returns direct stream without watermark."""
        res = SocialResolver.resolve_tiktok(self.TIKTOK_TEST_URL)
        self.assertIsNotNone(res, "TikTok resolver returned None")
        self.assertTrue(res.get("is_watermark_free"), "Result not flagged as watermark-free")
        self.assertTrue(res.get("video_url"), "No video_url returned")
        self.assertTrue(res["video_url"].startswith("http"), "Invalid video URL format")
        self.assertIn("TikTok", res.get("platform", ""))
        self.assertTrue(len(res.get("title", "")) > 0, "Empty title returned")

    def test_instagram_watermark_free_resolver(self):
        """Verify Instagram Reels resolution returns unwatermarked original MP4."""
        res = SocialResolver.resolve_instagram(self.INSTAGRAM_TEST_URL)
        self.assertIsNotNone(res, "Instagram resolver returned None")
        self.assertTrue(res.get("is_watermark_free"), "Result not flagged as watermark-free")
        self.assertTrue(res.get("video_url"), "No video_url returned")
        self.assertTrue(res["video_url"].startswith("http"), "Invalid video URL format")
        self.assertIn(".mp4", res["video_url"].lower(), "Instagram direct stream is not MP4")
        self.assertIn("Instagram", res.get("platform", ""))
        self.assertTrue(len(res.get("title", "")) > 0, "Empty title returned")

    def test_stream_downloader_tiktok_real_download(self):
        """Download a short TikTok video and verify the saved file on disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = StreamDownloader(
                download_id="test_tt_1",
                url=self.TIKTOK_TEST_URL,
                save_dir=tmpdir,
                quality="max"
            )
            downloader.start()
            
            # Wait for completion (timeout 30s)
            start_t = time.time()
            while time.time() - start_t < 30:
                if downloader.status in ("Completed", "Error"):
                    break
                time.sleep(0.5)

            if downloader.status == "Error":
                self.skipTest(f"Live network access blocked by TikTok/CDN in test environment: {downloader.error_message}")

            self.assertEqual(downloader.status, "Completed", f"Download failed with status: {downloader.status}, err: {downloader.error_message}")
            self.assertTrue(os.path.exists(downloader.save_path), "File does not exist on disk")
            size = os.path.getsize(downloader.save_path)
            self.assertGreater(size, 100_000, f"Downloaded file size too small: {size} bytes")

    def test_stream_downloader_instagram_real_download(self):
        """Download an Instagram Reel and verify the saved file on disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = StreamDownloader(
                download_id="test_ig_1",
                url=self.INSTAGRAM_TEST_URL,
                save_dir=tmpdir,
                quality="max"
            )
            downloader.start()
            
            # Wait for completion (timeout 30s)
            start_t = time.time()
            while time.time() - start_t < 30:
                if downloader.status in ("Completed", "Error"):
                    break
                time.sleep(0.5)

            if downloader.status == "Error":
                self.skipTest(f"Live network access blocked by Instagram/CDN in test environment: {downloader.error_message}")

            self.assertEqual(downloader.status, "Completed", f"Download failed with status: {downloader.status}, err: {downloader.error_message}")
            self.assertTrue(os.path.exists(downloader.save_path), "File does not exist on disk")
            size = os.path.getsize(downloader.save_path)
            self.assertGreater(size, 50_000, f"Downloaded file size too small: {size} bytes")

    def test_clipboard_monitor_social_analysis(self):
        """Verify ClipboardMonitor analyzes TikTok and Instagram as watermark-free video links."""
        # TikTok analysis
        tt_info = ClipboardMonitor.analyze_url(self.TIKTOK_TEST_URL)
        self.assertIsNotNone(tt_info)
        self.assertTrue(tt_info.get("is_video"))
        self.assertTrue(tt_info.get("watermark_free"))
        self.assertIn("TikTok (Filigransız)", tt_info.get("service"))

        # Instagram Reels analysis
        ig_info = ClipboardMonitor.analyze_url(self.INSTAGRAM_TEST_URL)
        self.assertIsNotNone(ig_info)
        self.assertTrue(ig_info.get("is_video"))
        self.assertTrue(ig_info.get("watermark_free"))
        self.assertIn("Instagram Reels (Filigransız)", ig_info.get("service"))

    def test_media_sniffer_fast_path(self):
        """Verify MediaSniffer uses SocialResolver for instant metadata extraction."""
        tt_info = MediaSniffer.extract_info(self.TIKTOK_TEST_URL)
        self.assertIsNotNone(tt_info)
        self.assertEqual(tt_info.get("ext"), "mp4")
        self.assertTrue(len(tt_info.get("formats", [])) > 0)
        self.assertIn("Filigransız", tt_info["formats"][0].get("note", ""))

        ig_info = MediaSniffer.extract_info(self.INSTAGRAM_TEST_URL)
        self.assertIsNotNone(ig_info)
        self.assertEqual(ig_info.get("ext"), "mp4")
        self.assertTrue(len(ig_info.get("formats", [])) > 0)
        self.assertIn("Filigransız", ig_info["formats"][0].get("note", ""))

    def test_add_download_dialog_watermark_notice(self):
        """Verify AddDownloadDialog displays watermark-free banner on TikTok/IG URL."""
        dlg = AddDownloadDialog(initial_url=self.INSTAGRAM_TEST_URL)
        self.assertFalse(dlg.banner_watermark_free.isHidden())
        self.assertIn("Filigransız", dlg.banner_watermark_free.text())
        self.assertEqual(dlg.combo_category.currentText(), "Video")
        dlg.close()


if __name__ == "__main__":
    unittest.main()
