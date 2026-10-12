import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
from PyQt6.QtWidgets import QApplication
from ui.clipboard_monitor import ClipboardMonitor
from ui.clipboard_popup import ClipboardNotificationPopup

def test_clipboard_detection():
    # Test link analyzing logic
    test_urls = [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", True, "YouTube"),
        ("https://youtu.be/dQw4w9WgXcQ", True, "YouTube"),
        ("https://x.com/user/status/123456789", True, "X (Twitter)"),
        ("https://www.tiktok.com/@user/video/123456789", True, "TikTok (Filigransız)"),
        ("https://www.instagram.com/reel/C-12345/", True, "Instagram Reels (Filigransız)"),
        ("https://vimeo.com/76979871", True, "Vimeo"),
        ("https://sample.com/archive.zip", True, "Dosya"),
        ("https://sample.com/setup.exe", True, "Dosya"),
        ("https://sample.com/music.mp3", True, "Dosya"),
        ("https://google.com/search?q=test", False, None),
        ("plain text not url", False, None),
    ]

    for url, should_detect, expected_service in test_urls:
        info = ClipboardMonitor.analyze_url(url)
        if should_detect:
            assert info is not None, f"Expected detection for {url}"
            assert info.get("service") == expected_service, f"Expected {expected_service}, got {info.get('service')}"
            print(f"PASS: {url} -> {info.get('service')} (Icon: {info.get('icon')})")
        else:
            assert info is None, f"Expected NO detection for {url}, got {info}"
            print(f"PASS (ignored): {url}")

    print("\nAll URL analyzer tests passed!")

def test_qt_popup_ui():
    app = QApplication.instance() or QApplication(sys.argv)
    popup = ClipboardNotificationPopup()
    
    # Test show_for_url
    sample_info = {"service": "YouTube", "icon": "▶️", "is_video": True}
    popup.show_for_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ", sample_info)
    assert popup.lbl_title.text() == "YouTube Bağlantısı Kopyalandı"
    print("PASS: Popup UI elements configured properly.")

    # Test quick download signal emission
    signals_received = []
    popup.download_requested.connect(lambda url, start_now: signals_received.append((url, start_now)))
    popup.btn_quick_download.click()
    assert len(signals_received) == 1
    assert signals_received[0] == ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", True)
    popup.close()
    print("PASS: Quick Download signal emitted successfully.")

if __name__ == "__main__":
    test_clipboard_detection()
    test_qt_popup_ui()
    print("\nALL CLIPBOARD MONITOR TESTS PASSED SUCCESSFULLY! 🚀")
