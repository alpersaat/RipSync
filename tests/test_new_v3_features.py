import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch, ANY

from core.database import Database
from core.paths import sanitize_filename, resolve_file_conflict
from core.queue_manager import QueueManager, PRIORITY_WEIGHTS
from core.post_download import (
    build_template_context,
    substitute_variables,
    format_size_simple,
    execute_post_download,
    send_webhook_notification
)

@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    db = Database(db_path)
    yield db
    try:
        os.remove(db_path)
    except Exception:
        pass


# =========================================================================
# FEATURE 3 TESTS: File Conflict & Auto-Rename
# =========================================================================

def test_sanitize_filename():
    assert sanitize_filename("test.zip") == "test.zip"
    assert sanitize_filename("file.zip?query=1#frag") == "file.zip"
    assert sanitize_filename('illegal:*?"<>|name.bin') == "illegal_______name.bin"
    assert sanitize_filename("trailing.spaces. ... ") == "trailing.spaces"
    assert sanitize_filename("") == "download.bin"
    # Reserved windows names
    assert sanitize_filename("con.txt") == "_con.txt"
    assert sanitize_filename("aux.pdf") == "_aux.pdf"
    assert sanitize_filename("NUL") == "_NUL"

def test_resolve_file_conflict_no_conflict():
    with tempfile.TemporaryDirectory() as tmpdir:
        name, conflicted = resolve_file_conflict(tmpdir, "myfile.txt", action="auto_rename")
        assert name == "myfile.txt"
        assert conflicted is False

def test_resolve_file_conflict_auto_rename():
    with tempfile.TemporaryDirectory() as tmpdir:
        target = os.path.join(tmpdir, "document.pdf")
        with open(target, "w") as f:
            f.write("content")

        # 1st conflict
        name1, conf1 = resolve_file_conflict(tmpdir, "document.pdf", action="auto_rename")
        assert name1 == "document (1).pdf"
        assert conf1 is True

        # Create document (1).pdf and test 2nd conflict
        with open(os.path.join(tmpdir, name1), "w") as f:
            f.write("content2")

        name2, conf2 = resolve_file_conflict(tmpdir, "document.pdf", action="auto_rename")
        assert name2 == "document (2).pdf"
        assert conf2 is True

def test_resolve_file_conflict_tar_gz():
    with tempfile.TemporaryDirectory() as tmpdir:
        target = os.path.join(tmpdir, "archive.tar.gz")
        with open(target, "w") as f:
            f.write("content")

        name, conf = resolve_file_conflict(tmpdir, "archive.tar.gz", action="auto_rename")
        assert name == "archive (1).tar.gz"
        assert conf is True

def test_resolve_file_conflict_overwrite_and_skip():
    with tempfile.TemporaryDirectory() as tmpdir:
        target = os.path.join(tmpdir, "file.iso")
        with open(target, "w") as f:
            f.write("data")

        # overwrite
        name_ow, conf_ow = resolve_file_conflict(tmpdir, "file.iso", action="overwrite")
        assert name_ow == "file.iso"
        assert conf_ow is True

        # skip
        name_sk, conf_sk = resolve_file_conflict(tmpdir, "file.iso", action="skip")
        assert name_sk == "file.iso"
        assert conf_sk is True

def test_conflict_setting_in_database(temp_db):
    assert temp_db.get_conflict_setting() == "auto_rename"
    temp_db.save_conflict_setting("overwrite")
    assert temp_db.get_conflict_setting() == "overwrite"
    temp_db.save_conflict_setting("skip")
    assert temp_db.get_conflict_setting() == "skip"


# =========================================================================
# FEATURE 5 TESTS: Bandwidth Priority Weighting
# =========================================================================

def test_priority_in_database(temp_db):
    did = temp_db.add_download(
        url="https://example.com/file.bin",
        filename="file.bin",
        save_path="/tmp/file.bin",
        priority="high"
    )
    rec = temp_db.get_download(did)
    assert rec["priority"] == "high"

    temp_db.update_download(did, priority="low")
    rec2 = temp_db.get_download(did)
    assert rec2["priority"] == "low"

def test_bandwidth_allocation_calculation(temp_db):
    qm = QueueManager(temp_db, max_concurrent=3, global_speed_limit_bps=433000)

    dl1 = MagicMock()
    dl1.download_id = "task1"
    dl1.status = "Downloading"

    dl2 = MagicMock()
    dl2.download_id = "task2"
    dl2.status = "Downloading"

    dl3 = MagicMock()
    dl3.download_id = "task3"
    dl3.status = "Downloading"

    temp_db.add_download("https://ex.com/1", "f1", "/tmp/f1", priority="high")
    temp_db.add_download("https://ex.com/2", "f2", "/tmp/f2", priority="normal")
    temp_db.add_download("https://ex.com/3", "f3", "/tmp/f3", priority="low")

    # Mock DB lookups
    def mock_get_dl(did):
        if did == "task1": return {"priority": "high"}
        if did == "task2": return {"priority": "normal"}
        if did == "task3": return {"priority": "low"}
        return {"priority": "normal"}

    temp_db.get_download = mock_get_dl
    qm.active_downloaders = {"task1": dl1, "task2": dl2, "task3": dl3}

    qm.recalculate_bandwidth_allocation()

    # Total weight = 3.0 + 1.0 + 0.33 = 4.33
    # Task 1 (high): 433000 * (3.0 / 4.33) ~ 300,000 bps
    # Task 2 (normal): 433000 * (1.0 / 4.33) ~ 100,000 bps
    # Task 3 (low): 433000 * (0.33 / 4.33) ~ 33,000 bps
    limit1 = dl1.set_speed_limit.call_args[0][0]
    limit2 = dl2.set_speed_limit.call_args[0][0]
    limit3 = dl3.set_speed_limit.call_args[0][0]

    assert limit1 > limit2
    assert limit2 > limit3
    assert abs(limit1 - 300000) < 5000
    assert abs(limit2 - 100000) < 5000

def test_set_download_priority(temp_db):
    qm = QueueManager(temp_db, max_concurrent=2, global_speed_limit_bps=1000000)
    did = temp_db.add_download("https://ex.com/file", "file.iso", "/tmp/file.iso", priority="normal")

    qm.set_download_priority(did, "high")
    rec = temp_db.get_download(did)
    assert rec["priority"] == "high"

    qm.set_download_priority(did, "invalid_choice")
    rec2 = temp_db.get_download(did)
    assert rec2["priority"] == "normal"


# =========================================================================
# FEATURE 7 TESTS: Post-Download Automation & Webhook
# =========================================================================

def test_format_size_simple():
    assert format_size_simple(500) == "500 B"
    assert format_size_simple(2048) == "2 KB"
    assert "MB" in format_size_simple(10 * 1024 * 1024)
    assert "GB" in format_size_simple(2 * 1024 * 1024 * 1024)

def test_template_substitution():
    rec = {
        "filename": "my_video.mp4",
        "save_path": "C:\\Downloads\\my_video.mp4",
        "url": "https://example.com/my_video.mp4",
        "category": "Video",
        "total_size": 15 * 1024 * 1024,
        "downloaded_size": 15 * 1024 * 1024,
        "status": "Completed"
    }
    ctx = build_template_context(rec)
    template = 'echo "{filename}" saved to "{filepath}" ({filesize}) [{category}]'
    res = substitute_variables(template, ctx)

    assert "my_video.mp4" in res
    assert "C:\\Downloads\\my_video.mp4" in res
    assert "Video" in res
    assert "15.00 MB" in res

def test_automation_settings_database(temp_db):
    default = temp_db.get_automation_settings()
    assert default["command_enabled"] is False
    assert default["webhook_enabled"] is False
    assert default["webhook_include_filepath"] is False

    temp_db.save_automation_settings({
        "command_enabled": True,
        "command": "python script.py {filepath}",
        "webhook_enabled": True,
        "webhook_url": "https://discord.com/api/webhooks/123/abc",
        "webhook_include_filepath": True
    })
    saved = temp_db.get_automation_settings()
    assert saved["command_enabled"] is True
    assert saved["command"] == "python script.py {filepath}"
    assert saved["webhook_enabled"] is True
    assert saved["webhook_url"] == "https://discord.com/api/webhooks/123/abc"
    assert saved["webhook_include_filepath"] is True

@patch("httpx.Client")
def test_send_webhook_notification_privacy_default(mock_client_cls):
    """By default, filepath must NOT be included in the webhook payload (prevent leaks)."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value.__enter__.return_value = mock_client

    ctx = {
        "{filename}": "package.zip",
        "{filepath}": "C:\\Users\\SecretUser\\Downloads\\package.zip",
        "{filesize}": "50 MB",
        "{category}": "Sıkıştırılmış",
        "{url}": "https://example.com/package.zip"
    }

    # Default include_filepath=False
    success, msg = send_webhook_notification("https://discord.com/api/webhooks/test", ctx)
    assert success is True
    assert "204" in msg
    mock_client.post.assert_called_once()
    payload = mock_client.post.call_args[1]["json"]
    assert "package.zip" in payload["content"]
    assert "filepath" not in payload
    embed_fields = payload["embeds"][0]["fields"]
    field_names = [f["name"] for f in embed_fields]
    assert "📍 Kayıt Konumu" not in field_names
    assert "📁 Dosya Adı" in field_names
    assert "💾 Boyut" in field_names
    assert "🔗 Bağlantı" in field_names

@patch("httpx.Client")
def test_send_webhook_notification_with_filepath(mock_client_cls):
    """When explicitly requested (include_filepath=True), filepath is included."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value.__enter__.return_value = mock_client

    ctx = {
        "{filename}": "package.zip",
        "{filepath}": "C:\\Users\\SecretUser\\Downloads\\package.zip",
        "{filesize}": "50 MB",
        "{category}": "Sıkıştırılmış",
        "{url}": "https://example.com/package.zip"
    }

    success, msg = send_webhook_notification("https://discord.com/api/webhooks/test", ctx, include_filepath=True)
    assert success is True
    payload = mock_client.post.call_args[1]["json"]
    assert payload.get("filepath") == "C:\\Users\\SecretUser\\Downloads\\package.zip"
    embed_fields = payload["embeds"][0]["fields"]
    field_names = [f["name"] for f in embed_fields]
    assert "📍 Kayıt Konumu" in field_names

@patch("core.post_download.send_webhook_notification_async")
def test_execute_post_download_webhook_include_filepath(mock_send_async):
    rec = {
        "filename": "demo.mp3",
        "save_path": "C:\\Downloads\\demo.mp3",
        "url": "https://example.com/demo.mp3",
        "category": "Müzik",
        "total_size": 5000000,
        "status": "Completed"
    }
    settings_no_leak = {
        "command_enabled": False,
        "webhook_enabled": True,
        "webhook_url": "https://discord.com/api/webhooks/test",
        "webhook_include_filepath": False
    }
    execute_post_download(rec, settings_no_leak)
    mock_send_async.assert_called_with("https://discord.com/api/webhooks/test", ANY, include_filepath=False)

    settings_with_fp = {
        "command_enabled": False,
        "webhook_enabled": True,
        "webhook_url": "https://discord.com/api/webhooks/test",
        "webhook_include_filepath": True
    }
    execute_post_download(rec, settings_with_fp)
    mock_send_async.assert_called_with("https://discord.com/api/webhooks/test", ANY, include_filepath=True)

@patch("subprocess.run")
def test_execute_post_download(mock_run):
    rec = {
        "filename": "demo.mp3",
        "save_path": "/tmp/demo.mp3",
        "url": "https://example.com/demo.mp3",
        "category": "Müzik",
        "total_size": 5000000,
        "status": "Completed"
    }
    settings = {
        "command_enabled": True,
        "command": 'python notify.py "{filepath}"',
        "webhook_enabled": False,
        "webhook_url": ""
    }
    execute_post_download(rec, settings)
    # Background thread is spawned; give small tick
    import time
    time.sleep(0.15)
    mock_run.assert_called_once()
    call_args, call_kwargs = mock_run.call_args
    assert call_kwargs.get("shell") is False
    cmd_args = call_args[0]
    assert any("demo.mp3" in arg for arg in cmd_args)

