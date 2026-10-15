import pytest
from core.database import Database
from ui.clipboard_monitor import ClipboardMonitor


@pytest.fixture
def mem_db(tmp_path):
    db_file = str(tmp_path / "test_clip.db")
    return Database(db_file)


def test_clipboard_ignore_domains():
    # Built-in ignored domain (e.g. google search)
    assert ClipboardMonitor.analyze_url("https://www.google.com/search?q=test") is None

    # Custom ignored domain
    custom_ignores = ["github.com", "mycompany.internal"]
    res = ClipboardMonitor.analyze_url("https://github.com/archive.zip", ignore_domains=custom_ignores)
    assert res is None

    # Domain not in ignore list should pass
    res_valid = ClipboardMonitor.analyze_url("https://cdn.example.com/archive.zip", ignore_domains=custom_ignores)
    assert res_valid is not None
    assert res_valid["filename"] == "archive.zip"


def test_clipboard_only_media_mode():
    media_url = "https://cdn.example.com/sample_song.mp3"
    video_url = "https://cdn.example.com/movie.mp4"
    doc_url = "https://cdn.example.com/manual.pdf"
    zip_url = "https://cdn.example.com/bundle.zip"

    # In default mode (only_media=False), all files match
    assert ClipboardMonitor.analyze_url(media_url, only_media=False) is not None
    assert ClipboardMonitor.analyze_url(doc_url, only_media=False) is not None
    assert ClipboardMonitor.analyze_url(zip_url, only_media=False) is not None

    # In only_media=True mode, document and archive files must be ignored
    assert ClipboardMonitor.analyze_url(media_url, only_media=True) is not None
    assert ClipboardMonitor.analyze_url(video_url, only_media=True) is not None
    assert ClipboardMonitor.analyze_url(doc_url, only_media=True) is None
    assert ClipboardMonitor.analyze_url(zip_url, only_media=True) is None

    # Social media platforms always pass in only_media=True mode
    yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    res_yt = ClipboardMonitor.analyze_url(yt_url, only_media=True)
    assert res_yt is not None
    assert res_yt["is_video"] is True


def test_clipboard_settings_database(mem_db):
    default_cfg = mem_db.get_clipboard_settings()
    assert default_cfg["enabled"] is True
    assert default_cfg["only_media"] is False
    assert "google.com" in default_cfg["ignore_domains"]

    # Save new configuration
    new_cfg = {
        "enabled": False,
        "only_media": True,
        "ignore_domains": ["example.com", "test.com"]
    }
    mem_db.save_clipboard_settings(new_cfg)

    loaded = mem_db.get_clipboard_settings()
    assert loaded["enabled"] is False
    assert loaded["only_media"] is True
    assert "example.com" in loaded["ignore_domains"]
    # Check backward compatibility setting
    assert mem_db.get_setting("clipboard_enabled") is False

