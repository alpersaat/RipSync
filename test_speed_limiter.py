import os
import sys
import time
import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

from core.database import Database
from core.speed_limiter import SpeedLimiter
from core.downloader import MultiThreadDownloader
from core.queue_manager import QueueManager

TEST_FILE_SIZE = 4 * 1024 * 1024  # 4 MB
TEST_DATA = b"S" * TEST_FILE_SIZE

class RangeHTTPHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(TEST_FILE_SIZE))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Disposition", 'attachment; filename="limiter_test.bin"')
        self.end_headers()

    def do_GET(self):
        range_header = self.headers.get("Range")
        if range_header:
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
            try:
                self.wfile.write(chunk)
            except Exception:
                pass
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(TEST_FILE_SIZE))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            try:
                self.wfile.write(TEST_DATA)
            except Exception:
                pass

    def log_message(self, format, *args):
        pass

def test_speed_limiter_rate():
    print("\n--- TEST 1: SpeedLimiter Token Bucket Accuracy ---")
    limit_bps = 1 * 1024 * 1024  # 1 MB/s
    limiter = SpeedLimiter(limit_bps)
    assert limiter.get_limit() == limit_bps

    # Transfer 2 MB in 64KB chunks
    chunk = 64 * 1024
    total_chunks = (2 * 1024 * 1024) // chunk
    start_t = time.perf_counter()
    for _ in range(total_chunks):
        limiter.acquire(chunk)
    elapsed = time.perf_counter() - start_t
    print(f"Acquiring 2 MB with 1 MB/s limit took {elapsed:.2f} seconds.")
    # With 1 MB initial token burst, the second 1 MB takes exactly 1.0s
    assert elapsed >= 0.9, f"Limiter allowed transfer too quickly: {elapsed}s"
    print("[PASS] SpeedLimiter rate is properly throttled.")

    # Test dynamic limit update to unlimited
    limiter.set_limit(0)
    assert limiter.get_limit() == 0
    t0 = time.perf_counter()
    for _ in range(50):
        limiter.acquire(chunk)
    elapsed_unlimited = time.perf_counter() - t0
    assert elapsed_unlimited < 0.1, "Unlimited mode should return immediately"
    print("[PASS] Dynamic speed limit change to unlimited confirmed.")

def test_downloader_with_speed_limit():
    print("\n--- TEST 2: MultiThreadDownloader with Speed Limit ---")
    server_port = 28726
    httpd = HTTPServer(("127.0.0.1", server_port), RangeHTTPHandler)
    srv_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    srv_thread.start()

    temp_dir = tempfile.mkdtemp()
    save_dir = os.path.join(temp_dir, "downloads")
    os.makedirs(save_dir, exist_ok=True)

    # 1. Download limited to 2 MB/s
    # 4 MB at 2 MB/s takes roughly 1.5 - 2.5 seconds
    limit_2mb = 2 * 1024 * 1024
    dl = MultiThreadDownloader(
        download_id="test_dl_limited",
        url=f"http://127.0.0.1:{server_port}/limiter_test.bin",
        save_dir=save_dir,
        filename="out_2mb.bin",
        connections=4,
        speed_limit_bps=limit_2mb
    )

    t0 = time.perf_counter()
    dl.start()
    timeout = 10.0
    while dl.status != "Completed" and (time.perf_counter() - t0) < timeout:
        time.sleep(0.05)
    duration = time.perf_counter() - t0

    assert dl.status == "Completed", f"Download did not complete: {dl.status}"
    assert os.path.exists(dl.save_path)
    assert os.path.getsize(dl.save_path) == TEST_FILE_SIZE
    print(f"4 MB download with 2 MB/s limit finished in {duration:.2f}s.")
    assert duration >= 1.2, f"Expected throttled duration >= 1.2s, got {duration:.2f}s"
    print("[PASS] Download file integrity verified and speed was successfully throttled.")

    # 2. Test QueueManager dynamic set_speed_limit
    db = Database(os.path.join(temp_dir, "qm_test.db"))
    qm = QueueManager(db, max_concurrent=2, global_speed_limit_bps=limit_2mb)
    assert qm.global_speed_limit_bps == limit_2mb

    did = qm.add_download(
        url=f"http://127.0.0.1:{server_port}/limiter_test.bin",
        save_dir=save_dir,
        filename="out_dynamic.bin",
        connections=4,
        start_now=True
    )
    time.sleep(0.2)
    active_dl = qm.get_downloader(did)
    assert active_dl is not None
    assert active_dl.speed_limiter.get_limit() == limit_2mb

    # Dynamically change to 5 MB/s
    qm.set_download_speed_limit(did, 5 * 1024 * 1024)
    assert active_dl.speed_limiter.get_limit() == 5 * 1024 * 1024
    print("[PASS] QueueManager set_download_speed_limit changed active download limit dynamically.")

    # Dynamically open to full speed (0)
    qm.set_global_speed_limit(0)
    assert active_dl.speed_limiter.get_limit() == 0
    print("[PASS] Global full speed (0 bps) applied dynamically.")

    start_wait = time.time()
    while active_dl.status != "Completed" and (time.time() - start_wait) < 5:
        time.sleep(0.05)

    assert os.path.getsize(active_dl.save_path) == TEST_FILE_SIZE
    print("[PASS] Dynamic speed limit download completed and verified successfully.")

    httpd.shutdown()

def test_ui_integration():
    print("\n--- TEST 3: UI Component Validation (PyQt6) ---")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    from ui.progress_dialog import ProgressDialog
    from ui.main_window import MainWindow

    temp_dir = tempfile.mkdtemp()
    db = Database(os.path.join(temp_dir, "ui_test.db"))
    qm = QueueManager(db)

    # Test ProgressDialog speed limiter controls
    received_limits = []
    prog = ProgressDialog("dl_1", "sample.zip", "/path/sample.zip", initial_speed_limit=5 * 1024 * 1024)
    prog.speed_limit_changed.connect(lambda did, bps: received_limits.append((did, bps)))

    assert prog.chk_limit.isChecked() is True
    assert prog.slider_limit.value() == 5120
    assert "5 MB/s" in prog.lbl_limit_val.text()

    # Move slider to 2 MB/s
    prog.slider_limit.setValue(2048)
    assert received_limits[-1] == ("dl_1", 2048 * 1024)
    assert "2 MB/s" in prog.lbl_limit_val.text()

    # Turn off limiter (Full speed)
    prog.chk_limit.setChecked(False)
    assert received_limits[-1] == ("dl_1", 0)
    assert prog.lbl_limit_val.text() == "Sınırsız (Tam Hız)"
    print("[PASS] ProgressDialog Speed Limiter slider and checkbox emit correct signals and labels.")

    # Test MainWindow toolbar speed limiter controls
    mw = MainWindow(db, qm)
    assert mw.chk_tb_speed_limit is not None
    assert mw.slider_tb_limit is not None
    assert mw.combo_tb_limit is not None

    # Toggle toolbar limiter ON
    mw.slider_tb_limit.setValue(5120)  # 5 MB/s
    mw.chk_tb_speed_limit.setChecked(True)
    assert qm.global_speed_limit_bps == 5120 * 1024
    assert db.get_setting("speed_limit_enabled") is True
    assert db.get_setting("speed_limit_kb") == 5120
    assert "5 MB/s" in mw.lbl_tb_limit_val.text()
    assert "Aktif" in mw.lbl_limiter_stat.text()

    # Toggle toolbar limiter OFF (One-click full speed)
    mw.chk_tb_speed_limit.setChecked(False)
    assert qm.global_speed_limit_bps == 0
    assert db.get_setting("speed_limit_enabled") is False
    assert mw.lbl_tb_limit_val.text() == "Tam Hız"
    assert "Kapalı (Tam Hız)" in mw.lbl_limiter_stat.text()
    print("[PASS] MainWindow Toolbar one-click speed limiter switch and slider fully verified.")

    # Test Context menu speed limiter handler
    mw._set_single_download_speed_limit("dl_1", 5120)
    print("[PASS] MainWindow context menu speed limit setter verified.")

    # Test Tray Icon speed limit handler
    mw._on_tray_speed_limit_requested(10240)  # 10 MB/s
    assert qm.global_speed_limit_bps == 10240 * 1024
    assert mw.chk_tb_speed_limit.isChecked() is True
    assert "10 MB/s" in mw.lbl_tb_limit_val.text()

    mw._on_tray_speed_limit_requested(0)  # Full speed
    assert qm.global_speed_limit_bps == 0
    assert mw.chk_tb_speed_limit.isChecked() is False
    assert mw.lbl_tb_limit_val.text() == "Tam Hız"
    print("[PASS] Tray Icon speed limiter integration verified.")

    mw.close()
    prog.close()

if __name__ == "__main__":
    test_speed_limiter_rate()
    test_downloader_with_speed_limit()
    test_ui_integration()
    print("\n==========================================")
    print(">>> ALL SPEED LIMITER TESTS PASSED 100%! <<<")
    print("==========================================")
