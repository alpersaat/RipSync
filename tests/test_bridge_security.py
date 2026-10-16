import os
import json
import time
import httpx
import pytest
from server.bridge_server import BridgeServer, write_extension_config
from core.database import Database

@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_bridge.db")
    return Database(db_file)

@pytest.fixture
def running_bridge():
    received_downloads = []
    received_sniffs = []
    test_token = "secure_token_secret_1234567890abcdef"
    server = BridgeServer(
        host="127.0.0.1",
        port=28719,
        auth_token=test_token,
        on_download_request=lambda d: received_downloads.append(d),
        on_media_detected=lambda d: received_sniffs.append(d)
    )
    server.start()
    time.sleep(0.3)
    yield {
        "server": server,
        "token": test_token,
        "port": server.actual_port,
        "downloads": received_downloads,
        "sniffs": received_sniffs
    }
    server.stop()

def test_bridge_token_generation_in_db(temp_db):
    token1 = temp_db.get_or_create_bridge_token()
    assert token1, "Token must not be empty"
    assert len(token1) >= 32, "Token should be at least 32 characters"

    token2 = temp_db.get_or_create_bridge_token()
    assert token1 == token2, "Subsequent calls should return the same token"

    new_token = temp_db.regenerate_bridge_token()
    assert new_token != token1, "Regenerated token should be different"
    assert temp_db.get_or_create_bridge_token() == new_token

def test_bridge_rejects_unauthorized_requests(running_bridge):
    port = running_bridge["port"]
    with httpx.Client() as client:
        # 1. /api/status without token
        r_status = client.get(f"http://127.0.0.1:{port}/api/status")
        assert r_status.status_code == 401

        # 2. /api/download without token
        r_down = client.post(f"http://127.0.0.1:{port}/api/download", json={"url": "https://example.com/test.zip"})
        assert r_down.status_code == 401

        # 3. /api/sniff_media without token
        r_sniff = client.post(f"http://127.0.0.1:{port}/api/sniff_media", json={"url": "https://example.com/video.mp4"})
        assert r_sniff.status_code == 401

        # 4. Invalid token
        r_invalid = client.post(
            f"http://127.0.0.1:{port}/api/download",
            headers={"X-RipSync-Token": "wrong_token_here"},
            json={"url": "https://example.com/test.zip"}
        )
        assert r_invalid.status_code == 401

    assert len(running_bridge["downloads"]) == 0

def test_bridge_accepts_authorized_requests(running_bridge):
    port = running_bridge["port"]
    token = running_bridge["token"]
    with httpx.Client() as client:
        # A. Auth via X-RipSync-Token header
        r1 = client.get(
            f"http://127.0.0.1:{port}/api/status",
            headers={"X-RipSync-Token": token}
        )
        assert r1.status_code == 200
        assert r1.json()["authenticated"] is True

        # B. Auth via Authorization: Bearer header
        r2 = client.post(
            f"http://127.0.0.1:{port}/api/download",
            headers={"Authorization": f"Bearer {token}"},
            json={"url": "https://example.com/test.zip", "filename": "test.zip"}
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "received"

        # C. Auth via query parameter
        r3 = client.post(
            f"http://127.0.0.1:{port}/api/sniff_media?token={token}",
            json={"url": "https://example.com/video.mp4", "quality": "1080p"}
        )
        assert r3.status_code == 200

    assert len(running_bridge["downloads"]) == 1
    assert running_bridge["downloads"][0]["filename"] == "test.zip"
    assert len(running_bridge["sniffs"]) == 1

def test_cors_origin_blocking_malicious_websites(running_bridge):
    port = running_bridge["port"]
    token = running_bridge["token"]
    with httpx.Client() as client:
        # Preflight from malicious website
        malicious_origin = "https://malicious-advertiser.com"
        r_opt = client.options(
            f"http://127.0.0.1:{port}/api/download",
            headers={
                "Origin": malicious_origin,
                "Access-Control-Request-Method": "POST"
            }
        )
        # Should be forbidden
        assert r_opt.status_code == 403
        assert "Access-Control-Allow-Origin" not in r_opt.headers

        # Even with valid token, a web origin is rejected
        r_post = client.post(
            f"http://127.0.0.1:{port}/api/download",
            headers={
                "Origin": malicious_origin,
                "X-RipSync-Token": token
            },
            json={"url": "https://malicious.com/stealth_download.exe"}
        )
        assert r_post.status_code == 403
        assert "Access-Control-Allow-Origin" not in r_post.headers or r_post.headers["Access-Control-Allow-Origin"] != "*"

    assert len(running_bridge["downloads"]) == 0

def test_cors_origin_allowing_browser_extensions(running_bridge):
    port = running_bridge["port"]
    token = running_bridge["token"]
    ext_origin = "chrome-extension://abcdefghijklmnopqrstuvwxyz123456"
    with httpx.Client() as client:
        # Preflight from Chrome extension
        r_opt = client.options(
            f"http://127.0.0.1:{port}/api/download",
            headers={
                "Origin": ext_origin,
                "Access-Control-Request-Method": "POST"
            }
        )
        assert r_opt.status_code == 200
        # Access-Control-Allow-Origin MUST match extension origin and MUST NOT be *
        assert r_opt.headers.get("Access-Control-Allow-Origin") == ext_origin
        assert r_opt.headers.get("Access-Control-Allow-Origin") != "*"

        # Valid download from extension
        r_post = client.post(
            f"http://127.0.0.1:{port}/api/download",
            headers={
                "Origin": ext_origin,
                "X-RipSync-Token": token
            },
            json={"url": "https://example.com/safe_file.pdf"}
        )
        assert r_post.status_code == 200
        assert r_post.headers.get("Access-Control-Allow-Origin") == ext_origin

    assert len(running_bridge["downloads"]) == 1
    assert running_bridge["downloads"][0]["url"] == "https://example.com/safe_file.pdf"

def test_write_extension_config(tmp_path, monkeypatch):
    from core import paths
    ext_dir = tmp_path / "extension"
    ext_dir.mkdir()
    monkeypatch.setattr(paths, "get_extension_dir", lambda: str(ext_dir))

    cfg_file = write_extension_config("my_secret_token_abc", 28710)
    assert cfg_file is not None
    assert os.path.exists(cfg_file)

    with open(cfg_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["bridge_token"] == "my_secret_token_abc"
    assert data["bridge_port"] == 28710
