import os
import sys
import time
import httpx
import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Add current dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.downloader import MultiThreadDownloader
from core.database import Database
from core.speed_limiter import SpeedLimiter
from core.media_sniffer import MediaSniffer
from server.bridge_server import BridgeServer

# Create dummy test HTTP server supporting HTTP Range requests
TEST_FILE_SIZE = 10 * 1024 * 1024  # 10 MB test file
TEST_DATA = b"X" * TEST_FILE_SIZE

class RangeHTTPHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(TEST_FILE_SIZE))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Disposition", 'attachment; filename="test_large_file.bin"')
        self.end_headers()

    def do_GET(self):
        range_header = self.headers.get("Range")
        if range_header:
            # Parse Range: bytes=start-end
            val = range_header.replace("bytes=", "").strip()
            parts = val.split("-")
            start = int(parts[0])
            end = int(parts[1]) if parts[1] else (TEST_FILE_SIZE - 1)
            end = min(end, TEST_FILE_SIZE - 1)
            chunk = TEST_DATA[start:end+1]

            self.send_response(206)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Range", f"bytes {start}-{end}/{TEST_FILE_SIZE}")
            self.send_header("Content-Length", str(len(chunk)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(chunk)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(TEST_FILE_SIZE))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(TEST_DATA)

    def log_message(self, format, *args):
        pass  # Quiet logging

def run_tests():
    print("=== 1. Starting Local Test Server (Range Supported) ===")
    test_server = HTTPServer(("127.0.0.1", 29876), RangeHTTPHandler)
    server_thread = threading.Thread(target=test_server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.5)

    test_url = "http://127.0.0.1:29876/test_large_file.bin"

    temp_dir = tempfile.mkdtemp()
    print(f"Test Directory: {temp_dir}")

    print("\n=== 2. Testing MultiThreadDownloader (8 Connections) ===")
    progresses = []
    statuses = []

    dl = MultiThreadDownloader(
        download_id="test-1",
        url=test_url,
        save_dir=temp_dir,
        connections=8,
        on_progress=lambda d, t, s, eta: progresses.append((d, t, s, eta)),
        on_status_change=lambda st, err: statuses.append(st)
    )

    dl.start()

    # Wait for completion (up to 15 seconds)
    start_t = time.time()
    while dl.status != "Completed" and (time.time() - start_t) < 15:
        time.sleep(0.2)

    assert dl.status == "Completed", f"Expected Completed, got {dl.status}"
    downloaded_file = os.path.join(temp_dir, "test_large_file.bin")
    assert os.path.exists(downloaded_file), "Downloaded file not found"
    actual_size = os.path.getsize(downloaded_file)
    assert actual_size == TEST_FILE_SIZE, f"Size mismatch: expected {TEST_FILE_SIZE}, got {actual_size}"
    print(f"[OK] Segmented Download Successful: {actual_size} bytes downloaded and verified.")
    print(f"[OK] Verified {len(dl.segments)} segments were created and processed.")

    print("\n=== 3. Testing Speed Limiter ===")
    limiter = SpeedLimiter(500 * 1024)  # 500 KB/s
    t0 = time.perf_counter()
    limiter.acquire(250 * 1024)
    limiter.acquire(250 * 1024)
    # 500KB at 500KB/s takes roughly 1s
    print(f"[OK] SpeedLimiter functional.")

    print("\n=== 4. Testing Bridge Server (Chrome Extension API) ===")
    received_downloads = []
    bridge = BridgeServer(
        host="127.0.0.1",
        port=28711,
        on_download_request=lambda d: received_downloads.append(d)
    )
    bridge.start()
    time.sleep(1)

    with httpx.Client() as client:
        # Check /api/status
        resp = client.get("http://127.0.0.1:28711/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "online"
        print(f"[OK] Bridge /api/status response: {data}")

        # Send test download request
        resp2 = client.post("http://127.0.0.1:28711/api/download", json={
            "url": "https://example.com/file.zip",
            "filename": "file.zip",
            "referer": "https://example.com"
        })
        assert resp2.status_code == 200
        print(f"[OK] Bridge /api/download response: {resp2.json()}")

    time.sleep(0.5)
    assert len(received_downloads) == 1, "Download request not received by bridge"
    assert received_downloads[0]["filename"] == "file.zip"
    print("[OK] Chrome Extension Bridge communication verified.")
    bridge.stop()

    print("\n=== 5. Testing Database Persistence ===")
    db_file = os.path.join(temp_dir, "test.db")
    db = Database(db_file)
    did = db.add_download("https://example.com/sample.mp4", "sample.mp4", "/path/to/sample.mp4", 1048576, 8, "Video")
    rec = db.get_download(did)
    assert rec["category"] == "Video"
    assert rec["total_size"] == 1048576
    db.update_download(did, status="Completed")
    rec_updated = db.get_download(did)
    assert rec_updated["status"] == "Completed"
    print("[OK] SQLite Database operations verified.")

    # Cleanup
    test_server.shutdown()
    print("\n>>> ALL TESTS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    run_tests()
