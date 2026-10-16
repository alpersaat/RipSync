import os
import time
import threading
import httpx
from typing import Optional, Callable
from core.speed_limiter import SpeedLimiter
from core.paths import to_long_path

CHUNK_SIZE = 64 * 1024  # 64 KB
FLUSH_EVERY = 1 * 1024 * 1024  # 1 MB

class Segment(threading.Thread):
    def __init__(self,
                 index: int,
                 url: str,
                 save_path: str,
                 start_byte: int,
                 end_byte: int,
                 current_byte: Optional[int] = None,
                 headers: Optional[dict] = None,
                 speed_limiter: Optional[SpeedLimiter] = None,
                 proxy: Optional[str] = None,
                 on_progress: Optional[Callable[[int, int], None]] = None,
                 on_error: Optional[Callable[[int, Exception], None]] = None,
                 on_complete: Optional[Callable[[int], None]] = None):
        super().__init__(name=f"SegmentWorker-{index}", daemon=True)
        self.index = index
        self.url = url
        self.save_path = save_path
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.current_byte = current_byte if current_byte is not None else start_byte
        self.headers = headers or {}
        self.speed_limiter = speed_limiter
        self.proxy = proxy
        self.on_progress = on_progress
        self.on_error = on_error
        self.on_complete = on_complete

        self.status = "pending"  # pending, downloading, completed, paused, error
        self.bytes_downloaded_session = 0
        self.current_speed = 0.0
        self.error: Optional[Exception] = None

        self._stop_event = threading.Event()
        self.lock = threading.Lock()

    @property
    def remaining_bytes(self) -> int:
        with self.lock:
            if self.end_byte < 0:
                return -1
            return max(0, self.end_byte - self.current_byte + 1)

    @property
    def total_bytes(self) -> int:
        if self.end_byte < 0:
            return -1
        return max(0, self.end_byte - self.start_byte + 1)

    @property
    def progress_ratio(self) -> float:
        with self.lock:
            tot = self.total_bytes
            if tot <= 0:
                return 1.0 if self.status == "completed" else 0.0
            done = self.current_byte - self.start_byte
            return min(1.0, max(0.0, done / tot))

    def stop(self):
        self._stop_event.set()

    def run(self):
        if self.end_byte >= 0 and self.current_byte > self.end_byte:
            self.status = "completed"
            if self.on_complete:
                self.on_complete(self.index)
            return

        self.status = "downloading"
        req_headers = dict(self.headers)
        if self.end_byte >= 0:
            req_headers["Range"] = f"bytes={self.current_byte}-{self.end_byte}"
        elif self.current_byte > 0:
            req_headers["Range"] = f"bytes={self.current_byte}-"

        # Provide standard browser user-agent if not given
        if "User-Agent" not in req_headers and "user-agent" not in req_headers:
            req_headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

        speed_window = []
        speed_window_size = 5

        try:
            client_kwargs = {"follow_redirects": True, "timeout": httpx.Timeout(30.0, read=60.0)}
            if self.proxy:
                client_kwargs["proxy"] = self.proxy
            with httpx.Client(**client_kwargs) as client:
                with client.stream("GET", self.url, headers=req_headers) as response:
                    # 206 Partial Content or 200 OK
                    if response.status_code not in (200, 206):
                        raise Exception(f"HTTP {response.status_code}: {response.reason_phrase}")

                    # Open target file for random access
                    with open(to_long_path(self.save_path), "r+b") as f:
                        f.seek(self.current_byte)

                        last_time = time.perf_counter()
                        last_bytes = 0
                        bytes_since_flush = 0

                        for chunk in response.iter_bytes(chunk_size=CHUNK_SIZE):
                            if self._stop_event.is_set():
                                self.status = "paused"
                                return

                            if not chunk:
                                continue

                            chunk_len = len(chunk)
                            if self.speed_limiter:
                                self.speed_limiter.acquire(chunk_len)

                            f.seek(self.current_byte)
                            f.write(chunk)
                            bytes_since_flush += chunk_len
                            if bytes_since_flush >= FLUSH_EVERY:
                                f.flush()
                                bytes_since_flush = 0

                            with self.lock:
                                self.current_byte += chunk_len
                                self.bytes_downloaded_session += chunk_len

                            # Calculate instantaneous speed
                            now = time.perf_counter()
                            dt = now - last_time
                            if dt >= 0.5:
                                bytes_diff = self.bytes_downloaded_session - last_bytes
                                inst_speed = bytes_diff / dt
                                speed_window.append(inst_speed)
                                if len(speed_window) > speed_window_size:
                                    speed_window.pop(0)
                                self.current_speed = sum(speed_window) / len(speed_window)
                                last_time = now
                                last_bytes = self.bytes_downloaded_session

                            if self.on_progress:
                                self.on_progress(self.index, chunk_len)

                            if self.end_byte >= 0 and self.current_byte > self.end_byte:
                                break

                        if bytes_since_flush > 0:
                            f.flush()

            self.status = "completed"
            if self.on_complete:
                self.on_complete(self.index)

        except Exception as e:
            if not self._stop_event.is_set():
                self.status = "error"
                self.error = e
                if self.on_error:
                    self.on_error(self.index, e)
            else:
                self.status = "paused"
