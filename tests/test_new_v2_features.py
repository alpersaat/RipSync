import os
import io
import json
import zipfile
import tarfile
import tempfile
import pytest
from datetime import datetime, date, time as dtime, timedelta
from core.database import Database
from core.queue_manager import QueueManager
from core.downloader import MultiThreadDownloader
from core.stream_downloader import StreamDownloader
from core.scheduler import DownloadScheduler
from core.extractor import is_archive_file, extract_archive, _is_safe_path
from ui.styles import get_theme_stylesheet, ACCENT_COLORS


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(path)
    yield db
    try:
        os.remove(path)
    except Exception:
        pass


@pytest.fixture
def temp_workspace():
    td = tempfile.mkdtemp()
    yield td
    import shutil
    try:
        shutil.rmtree(td, ignore_errors=True)
    except Exception:
        pass


# ==============================================================================
# FEATURE 1: Süresi Dolan Bağlantı Adresini Yenileme (Refresh / Update Expired URL)
# ==============================================================================

def test_refresh_download_url(temp_db, temp_workspace):
    qm = QueueManager(temp_db)
    old_url = "https://example.com/expired-link-token-123"
    did = qm.add_download(
        url=old_url,
        save_dir=temp_workspace,
        filename="test_movie.mp4",
        start_now=False
    )

    # Simulate that the download was paused or had an expired-link error
    temp_db.update_download(did, status="Error", error_message="HTTP 403 Forbidden: Expired Token", downloaded_size=500000)

    # Perform URL refresh
    new_url = "https://example.com/fresh-refreshed-link-token-456"
    new_headers = {"Referer": "https://example.com/player", "Authorization": "Bearer new_tok"}
    success = qm.update_download_url(did, new_url, new_headers)
    assert success is True

    # Verify updated record
    rec = temp_db.get_download(did)
    assert rec["url"] == new_url
    assert rec["status"] == "Paused"
    assert rec["error_message"] == ""
    assert rec["downloaded_size"] == 500000  # Existing bytes preserved!
    headers_dict = json.loads(rec["headers_json"])
    assert headers_dict["Referer"] == "https://example.com/player"
    assert headers_dict["Authorization"] == "Bearer new_tok"


def test_downloader_update_url():
    dl = MultiThreadDownloader(
        download_id="test-1",
        url="http://old.com/file.zip",
        save_dir=".",
        headers={"Old": "Header"}
    )
    dl.status = "Error"
    dl.error_message = "HTTP 410 Gone"

    dl.update_url("http://new.com/file.zip", {"New": "Header"})
    assert dl.url == "http://new.com/file.zip"
    assert dl.headers == {"New": "Header"}
    assert dl.status == "Paused"
    assert dl.error_message == ""


def test_stream_downloader_update_url():
    sdl = StreamDownloader(
        download_id="stream-1",
        url="https://youtube.com/watch?v=old",
        save_dir="."
    )
    sdl.status = "Error"
    sdl.error_message = "Stream token expired"

    sdl.update_url("https://youtube.com/watch?v=new", {"Referer": "https://youtube.com"})
    assert sdl.url == "https://youtube.com/watch?v=new"
    assert sdl.headers == {"Referer": "https://youtube.com"}
    assert sdl.status == "Paused"
    assert sdl.error_message == ""


# ==============================================================================
# FEATURE 2: Kayıp / Taşınmış Dosyaları Denetleme ve Ayıklama (Missing Files Cleaner)
# ==============================================================================

def test_missing_files_detection(temp_db, temp_workspace):
    qm = QueueManager(temp_db)

    # File 1: Exists on disk
    f1_path = os.path.join(temp_workspace, "exists.zip")
    with open(f1_path, "wb") as f:
        f.write(b"data")
    did1 = qm.add_download(url="http://a.com/1", save_dir=temp_workspace, filename="exists.zip", start_now=False)
    temp_db.update_download(did1, status="Completed", save_path=f1_path)

    # File 2: Deleted from disk
    f2_path = os.path.join(temp_workspace, "deleted.zip")
    did2 = qm.add_download(url="http://a.com/2", save_dir=temp_workspace, filename="deleted.zip", start_now=False)
    temp_db.update_download(did2, status="Completed", save_path=f2_path)

    all_dls = qm.get_all_downloads()
    missing = [dl for dl in all_dls if dl.get("status") == "Completed" and not os.path.exists(dl.get("save_path", ""))]
    assert len(missing) == 1
    assert missing[0]["id"] == did2
    assert missing[0]["filename"] == "deleted.zip"


# ==============================================================================
# FEATURE 3: Proxy Desteği (HTTP / HTTPS / SOCKS5) ve Kimlik Doğrulama
# ==============================================================================

def test_proxy_settings_and_url_generation(temp_db):
    # Default: disabled
    assert temp_db.get_proxy_url() is None

    # HTTP without auth
    temp_db.save_proxy_settings({
        "enabled": True,
        "type": "http",
        "host": "127.0.0.1",
        "port": 8080,
        "username": "",
        "password": ""
    })
    assert temp_db.get_proxy_url() == "http://127.0.0.1:8080"

    # SOCKS5 with auth
    temp_db.save_proxy_settings({
        "enabled": True,
        "type": "socks5",
        "host": "proxy.corp.net",
        "port": 1080,
        "username": "alice",
        "password": "secret@123"
    })
    assert temp_db.get_proxy_url() == "socks5://alice:secret%40123@proxy.corp.net:1080"

    # Disabled
    temp_db.save_proxy_settings({"enabled": False})
    assert temp_db.get_proxy_url() is None


def test_downloader_proxy_initialization():
    dl = MultiThreadDownloader(
        download_id="proxy-test",
        url="http://example.com/test",
        save_dir=".",
        proxy="http://127.0.0.1:8888"
    )
    assert dl.proxy == "http://127.0.0.1:8888"

    sdl = StreamDownloader(
        download_id="proxy-stream-test",
        url="https://youtube.com/watch?v=abc",
        save_dir=".",
        proxy="socks5://127.0.0.1:1080"
    )
    assert sdl.proxy == "socks5://127.0.0.1:1080"


# ==============================================================================
# FEATURE 4: Akıllı Hız Limiti Zamanlaması (Gündüz Sınırla / Gece Tam Hız)
# ==============================================================================

def test_speed_schedule_window_and_callback():
    sched = DownloadScheduler(
        speed_schedule_enabled=True,
        speed_schedule_start="09:00",
        speed_schedule_end="18:00",
        speed_schedule_limit_kb=2048
    )

    # At 12:00 -> in window
    dt_midday = datetime(2026, 10, 15, 12, 0, 0)
    assert sched.is_in_speed_schedule_window(dt_midday) is True

    # At 21:00 -> outside window
    dt_night = datetime(2026, 10, 15, 21, 0, 0)
    assert sched.is_in_speed_schedule_window(dt_night) is False

    # Midnight crossing schedule: 22:00 to 06:00
    sched.speed_schedule_start = "22:00"
    sched.speed_schedule_end = "06:00"
    assert sched.is_in_speed_schedule_window(datetime(2026, 10, 15, 23, 30)) is True
    assert sched.is_in_speed_schedule_window(datetime(2026, 10, 16, 3, 0)) is True
    assert sched.is_in_speed_schedule_window(datetime(2026, 10, 16, 14, 0)) is False

    # Test callback on tick
    captured_limits = []
    sched.on_speed_limit_change = lambda bps: captured_limits.append(bps)

    # Tick during window
    sched.tick(now=datetime(2026, 10, 15, 23, 0))
    assert len(captured_limits) == 1
    assert captured_limits[0] == 2048 * 1024  # Throttled!

    # Tick outside window
    sched.tick(now=datetime(2026, 10, 16, 12, 0))
    assert len(captured_limits) == 2
    assert captured_limits[1] == 0  # Restored to unlimited!


# ==============================================================================
# FEATURE 5: Bittiğinde Otomatik Arşiv Çıkarma (Auto-Extract ZIP / TAR)
# ==============================================================================

def test_is_archive_file():
    assert is_archive_file("package.zip") is True
    assert is_archive_file("backup.tar.gz") is True
    assert is_archive_file("archive.7z") is True
    assert is_archive_file("video.mp4") is False
    assert is_archive_file("song.mp3") is False


def test_safe_path_traversal_guard():
    base = os.path.abspath("/home/user/downloads")
    safe = os.path.join(base, "folder", "file.txt")
    unsafe = os.path.join(base, "..", "etc", "passwd")
    assert _is_safe_path(base, safe) is True
    assert _is_safe_path(base, unsafe) is False


def test_extract_zip_archive(temp_workspace):
    # Create test zip file
    zip_path = os.path.join(temp_workspace, "test_archive.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("file1.txt", "Hello World 1")
        zf.writestr("sub/file2.txt", "Hello World 2")

    # Extract
    success, msg = extract_archive(zip_path, create_subfolder=True)
    assert success is True
    extracted_dir = os.path.join(temp_workspace, "test_archive")
    assert os.path.isdir(extracted_dir)
    assert os.path.exists(os.path.join(extracted_dir, "file1.txt"))
    assert os.path.exists(os.path.join(extracted_dir, "sub", "file2.txt"))
    with open(os.path.join(extracted_dir, "file1.txt"), "r") as f:
        assert f.read() == "Hello World 1"


def test_extract_tar_archive(temp_workspace):
    tar_path = os.path.join(temp_workspace, "test_archive.tar.gz")
    with tarfile.open(tar_path, "w:gz") as tf:
        data = b"Tar Content 123"
        ti = tarfile.TarInfo(name="inside_tar.txt")
        ti.size = len(data)
        tf.addfile(ti, io.BytesIO(data))

    success, msg = extract_archive(tar_path, create_subfolder=True)
    assert success is True
    extracted_dir = os.path.join(temp_workspace, "test_archive")
    assert os.path.isdir(extracted_dir)
    assert os.path.exists(os.path.join(extracted_dir, "inside_tar.txt"))


# ==============================================================================
# FEATURE 6: Aydınlık / Koyu Tema Desteği & Vurgu Rengi (Accent Color)
# ==============================================================================

def test_theme_stylesheet_generation():
    # Dark themes with accents
    for acc in ("blue", "emerald", "purple", "amber"):
        qss = get_theme_stylesheet("dark", acc)
        assert ACCENT_COLORS[acc]["primary"] in qss
        assert "#1a1b26" in qss  # Dark bg

    # Light themes
    for acc in ("blue", "emerald", "purple", "amber"):
        qss_light = get_theme_stylesheet("light", acc)
        assert ACCENT_COLORS[acc]["primary"] in qss_light
        assert "#f4f5f8" in qss_light  # Light bg


def test_theme_database_persistence(temp_db):
    # Default
    assert temp_db.get_theme_settings() == {"theme": "dark", "accent": "blue"}

    # Save
    temp_db.save_theme_settings(theme="light", accent="emerald")
    saved = temp_db.get_theme_settings()
    assert saved["theme"] == "light"
    assert saved["accent"] == "emerald"

