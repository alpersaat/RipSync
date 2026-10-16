import os
import json
import tempfile
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import pytest

from core.downloader import MultiThreadDownloader
from core.segment import Segment


class MockRangeHTTPHandler(BaseHTTPRequestHandler):
    FILE_CONTENT = b"A" * (256 * 1024)  # 256 KB

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(self.FILE_CONTENT)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self):
        range_header = self.headers.get("Range")
        total_len = len(self.FILE_CONTENT)

        if range_header and range_header.startswith("bytes="):
            byte_range = range_header.replace("bytes=", "").split("-")
            start = int(byte_range[0])
            end = int(byte_range[1]) if byte_range[1] else total_len - 1
            end = min(end, total_len - 1)

            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{total_len}")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(self.FILE_CONTENT[start:end + 1])
        else:
            self.send_response(200)
            self.send_header("Content-Length", str(total_len))
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(self.FILE_CONTENT)

    def log_message(self, format, *args):
        pass


@pytest.fixture(scope="module")
def local_server():
    server = HTTPServer(("127.0.0.1", 0), MockRangeHTTPHandler)
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.1)
    yield f"http://127.0.0.1:{port}/sample.bin"
    server.shutdown()


def test_atomic_state_save():
    with tempfile.TemporaryDirectory() as tmpdir:
        dl = MultiThreadDownloader(
            download_id="atomic-1",
            url="http://example.com/test.bin",
            save_dir=tmpdir,
            filename="test.bin",
            connections=4
        )
        dl.save_path = os.path.join(tmpdir, "test.bin")
        dl.state_file = dl.save_path + f".{dl.download_id}.ripsync_state"
        dl.total_size = 4000

        # Create mock segments
        seg0 = Segment(0, dl.url, dl.save_path, 0, 999, current_byte=500)
        seg1 = Segment(1, dl.url, dl.save_path, 1000, 1999, current_byte=1000)
        seg2 = Segment(2, dl.url, dl.save_path, 2000, 2999, current_byte=2500)
        seg3 = Segment(3, dl.url, dl.save_path, 3000, 3999, current_byte=3999)
        dl.segments = [seg0, seg1, seg2, seg3]

        # Save state atomically
        dl._save_state()

        # Target state file must exist and temp file must not be left behind
        assert os.path.exists(dl.state_file), "State file should exist after atomic save"
        assert not os.path.exists(dl.state_file + ".tmp"), "Temp file should be renamed/cleaned up"

        # Verify contents
        with open(dl.state_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["total_size"] == 4000
        assert len(data["segments"]) == 4
        assert data["segments"][0]["current"] == 500
        assert data["segments"][2]["current"] == 2500


def test_valid_state_file_loaded_successfully():
    with tempfile.TemporaryDirectory() as tmpdir:
        dl = MultiThreadDownloader(
            download_id="resume-1",
            url="http://example.com/test.bin",
            save_dir=tmpdir,
            filename="test.bin",
            connections=4
        )
        dl.save_path = os.path.join(tmpdir, "test.bin")
        dl.state_file = dl.save_path + f".{dl.download_id}.ripsync_state"
        dl.total_size = 4000
        dl.accept_ranges = True

        valid_data = {
            "total_size": 4000,
            "segments": [
                {"index": 0, "start": 0, "current": 400, "end": 999},
                {"index": 1, "start": 1000, "current": 1200, "end": 1999},
                {"index": 2, "start": 2000, "current": 2000, "end": 2999},
                {"index": 3, "start": 3000, "current": 3500, "end": 3999}
            ]
        }
        with open(dl.state_file, "w", encoding="utf-8") as f:
            json.dump(valid_data, f)

        dl._load_or_create_segments()

        # Should load the 4 saved segments and retain connections count
        assert len(dl._segment_configs) == 4
        assert dl._segment_configs[0]["current"] == 400
        assert dl.connections == 4
        assert os.path.exists(dl.state_file)


def test_corrupted_json_state_falls_back_to_single_connection():
    with tempfile.TemporaryDirectory() as tmpdir:
        dl = MultiThreadDownloader(
            download_id="corrupt-1",
            url="http://example.com/test.bin",
            save_dir=tmpdir,
            filename="test.bin",
            connections=8
        )
        dl.save_path = os.path.join(tmpdir, "test.bin")
        dl.state_file = dl.save_path + f".{dl.download_id}.ripsync_state"
        dl.total_size = 8000
        dl.accept_ranges = True

        # Write truncated/broken JSON
        with open(dl.state_file, "w", encoding="utf-8") as f:
            f.write('{"total_size": 8000, "segments": [{"index": 0, "start": 0, "curr')

        # Also create a partial destination file
        with open(dl.save_path, "wb") as f:
            f.write(b"partially_downloaded_garbage")

        dl._load_or_create_segments()

        # Must fall back to single connection and flag corrupt state awaiting user decision
        assert dl.status == "CorruptState"
        assert dl.state_corrupt is True
        assert dl._awaiting_state_decision is True
        assert dl.connections == 1
        assert len(dl._segment_configs) == 1
        assert dl._segment_configs[0]["index"] == 0
        assert dl._segment_configs[0]["start"] == 0
        assert dl._segment_configs[0]["current"] == 0
        assert dl._segment_configs[0]["end"] == 7999

        # Corrupted state file must be removed
        assert not os.path.exists(dl.state_file)

        # Yarıda biten hedef dosya SILINMEMELİ (veri kaybını önle)
        assert os.path.exists(dl.save_path)


def test_empty_zero_byte_state_file_falls_back_to_single_connection():
    with tempfile.TemporaryDirectory() as tmpdir:
        dl = MultiThreadDownloader(
            download_id="corrupt-empty",
            url="http://example.com/test.bin",
            save_dir=tmpdir,
            filename="test.bin",
            connections=8
        )
        dl.save_path = os.path.join(tmpdir, "test.bin")
        dl.state_file = dl.save_path + f".{dl.download_id}.ripsync_state"
        dl.total_size = 5000
        dl.accept_ranges = True

        # Empty 0-byte file (e.g. crash right after open() in old logic)
        with open(dl.state_file, "w", encoding="utf-8") as f:
            pass

        dl._load_or_create_segments()

        assert dl.status == "CorruptState"
        assert dl.state_corrupt is True
        assert dl._awaiting_state_decision is True
        assert dl.connections == 1
        assert len(dl._segment_configs) == 1
        assert dl._segment_configs[0]["index"] == 0
        assert not os.path.exists(dl.state_file)


def test_invalid_segment_structure_falls_back_to_single_connection():
    with tempfile.TemporaryDirectory() as tmpdir:
        dl = MultiThreadDownloader(
            download_id="corrupt-badschema",
            url="http://example.com/test.bin",
            save_dir=tmpdir,
            filename="test.bin",
            connections=6
        )
        dl.save_path = os.path.join(tmpdir, "test.bin")
        dl.state_file = dl.save_path + f".{dl.download_id}.ripsync_state"
        dl.total_size = 6000
        dl.accept_ranges = True

        # Valid JSON but invalid schema: missing 'start' and current > end + 1
        bad_data = {
            "total_size": 6000,
            "segments": [
                {"index": 0, "current": 5000, "end": 100}
            ]
        }
        with open(dl.state_file, "w", encoding="utf-8") as f:
            json.dump(bad_data, f)

        dl._load_or_create_segments()

        assert dl.status == "CorruptState"
        assert dl.state_corrupt is True
        assert dl._awaiting_state_decision is True
        assert dl.connections == 1
        assert len(dl._segment_configs) == 1
        assert not os.path.exists(dl.state_file)


def test_empty_segments_list_falls_back_to_single_connection():
    with tempfile.TemporaryDirectory() as tmpdir:
        dl = MultiThreadDownloader(
            download_id="corrupt-empty-list",
            url="http://example.com/test.bin",
            save_dir=tmpdir,
            filename="test.bin",
            connections=4
        )
        dl.save_path = os.path.join(tmpdir, "test.bin")
        dl.state_file = dl.save_path + f".{dl.download_id}.ripsync_state"
        dl.total_size = 4000
        dl.accept_ranges = True

        # Valid JSON with empty segments list
        with open(dl.state_file, "w", encoding="utf-8") as f:
            json.dump({"total_size": 4000, "segments": []}, f)

        dl._load_or_create_segments()

        assert dl.status == "CorruptState"
        assert dl.state_corrupt is True
        assert dl._awaiting_state_decision is True
        assert dl.connections == 1
        assert len(dl._segment_configs) == 1
        assert not os.path.exists(dl.state_file)


def test_download_recovers_from_corrupted_state_with_local_server(local_server):
    with tempfile.TemporaryDirectory() as tmpdir:
        filename = "recovered_file.bin"
        save_path = os.path.join(tmpdir, filename)

        # Pre-create a corrupt state file
        download_id = "test-recovery-1"
        state_file = save_path + f".{download_id}.ripsync_state"
        with open(state_file, "w", encoding="utf-8") as f:
            f.write("{invalid_json_state_data_crash")

        dl = MultiThreadDownloader(
            download_id=download_id,
            url=local_server,
            save_dir=tmpdir,
            filename=filename,
            connections=4
        )

        dl.start()

        # Bozuk durum dosyası tespitendiğinde indirme başlatılmaz,
        # kullanıcıya 'yeniden dene' / 'devam et' kararı bırakılır.
        assert dl.status == "CorruptState"
        assert dl.state_corrupt is True
        assert not os.path.exists(state_file)

        # Kullanıcı 'Devam Et' seçer: yarıda biten dosya korunur, tek bağlantıyla kaldığı yerden devam edilir.
        dl.resume()

        start_t = time.time()
        while dl.status != "Completed" and (time.time() - start_t) < 10:
            time.sleep(0.1)

        assert dl.status == "Completed"
        assert dl.connections == 1
        assert os.path.exists(save_path)
        assert os.path.getsize(save_path) == len(MockRangeHTTPHandler.FILE_CONTENT)
        # Corrupted state and temporary files should be removed upon completion
        assert not os.path.exists(state_file)
        assert not os.path.exists(state_file + ".tmp")

