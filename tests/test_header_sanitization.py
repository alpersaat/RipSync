import pytest
from core.downloader import clean_http_headers, MultiThreadDownloader
from core.segment import Segment, _clean_headers

def test_clean_http_headers_removes_internal_options():
    raw_headers = {
        "Referer": "https://example.com",
        "User-Agent": "Mozilla/5.0 TestBrowser",
        "download_subtitles": False,
        "download_thumbnail": False,
        "embed_metadata": True,
        "quality": "max",
        "browser_cookies": "session=123",
        "auto_open": True,
        "auto_extract": False,
        "Custom-Header": "Allowed",
        "X-Numeric-Header": 12345
    }
    cleaned = clean_http_headers(raw_headers)
    assert cleaned == {
        "Referer": "https://example.com",
        "User-Agent": "Mozilla/5.0 TestBrowser",
        "Custom-Header": "Allowed",
        "X-Numeric-Header": "12345"
    }
    assert "download_subtitles" not in cleaned
    assert "download_thumbnail" not in cleaned
    assert "embed_metadata" not in cleaned
    assert "quality" not in cleaned
    assert "browser_cookies" not in cleaned

def test_clean_http_headers_filters_booleans_and_invalid_types():
    raw_headers = {
        "Valid-String": "hello",
        "Bool-True": True,
        "Bool-False": False,
        "None-Val": None,
        "Dict-Val": {"a": 1},
        "List-Val": [1, 2, 3]
    }
    cleaned = clean_http_headers(raw_headers)
    assert cleaned == {"Valid-String": "hello"}

def test_segment_clean_headers():
    raw = {
        "User-Agent": "RipSyncBot",
        "download_subtitles": False,
        "embed_metadata": True
    }
    cleaned = _clean_headers(raw)
    assert cleaned == {"User-Agent": "RipSyncBot"}

import tempfile

def test_downloader_init_cleans_headers():
    raw_headers = {
        "Referer": "https://example.com",
        "download_subtitles": False,
        "embed_metadata": True,
        "quality": "1080p"
    }
    dl = MultiThreadDownloader(
        download_id="test-clean",
        url="http://127.0.0.1/test.zip",
        save_dir=tempfile.gettempdir(),
        filename="test.zip",
        headers=raw_headers
    )
    assert dl.headers == {"Referer": "https://example.com"}
