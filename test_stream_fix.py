import os
import sys
import tempfile
import time

# Ensure current dir is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.stream_downloader import StreamDownloader, is_stream_url

def test_video_download(url: str, label: str, quality: str = "max"):
    print(f"\n==========================================")
    print(f"Testing {label} (Quality: {quality}) -> {url}")
    print(f"==========================================")
    assert is_stream_url(url), f"{url} should be recognized as a stream URL"

    tmp_dir = tempfile.mkdtemp()
    events = []

    sd = StreamDownloader(
        download_id=f"test-{label}",
        url=url,
        save_dir=tmp_dir,
        quality=quality,
        on_progress=lambda d, t, s, eta: events.append((d, t, s, eta)),
        on_status_change=lambda st, err: print(f"[{label} Status] {st} {err if err else ''}")
    )

    sd.start()

    # Wait for completion (up to 40 seconds)
    t0 = time.time()
    while sd.status not in ("Completed", "Error") and (time.time() - t0) < 40:
        time.sleep(1)

    print(f"[{label}] Finished with status: {sd.status}")
    if sd.error_message:
        print(f"[{label}] Error: {sd.error_message}")

    assert sd.status == "Completed", f"Expected Completed, got {sd.status}: {sd.error_message}"
    assert os.path.exists(sd.save_path), f"File {sd.save_path} does not exist"

    size = os.path.getsize(sd.save_path)
    print(f"[{label}] Saved file: {sd.save_path}")
    print(f"[{label}] Size on disk: {size} bytes ({size / (1024*1024):.2f} MB)")
    assert size > 200 * 1024, f"File size too small ({size} bytes)"

    # Verify MP4 magic header
    with open(sd.save_path, "rb") as f:
        header = f.read(16)
        print(f"[{label}] Header: {header}")
        assert b"ftyp" in header or b"matroska" in header, "Invalid video container"

    # Cleanup test file
    try:
        os.remove(sd.save_path)
    except Exception:
        pass
    print(f"[PASS] {label} verified 100% working!")

def main():
    # 1. Test X.com (Twitter) Video
    test_video_download(
        url="https://x.com/MrBarneyStynson/status/2109023665203417588",
        label="X.com (Twitter)"
    )

    # 2. Test YouTube Video (720p HD Quality)
    test_video_download(
        url="https://www.youtube.com/watch?v=0rW7Fbm4S7g",
        label="YouTube (720p)",
        quality="720p"
    )

    print("\n>>> ALL STREAM DOWNLOAD TESTS PASSED WITH 100% SUCCESS! <<<")

if __name__ == "__main__":
    main()
