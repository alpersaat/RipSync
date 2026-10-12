import time
import threading

class SpeedLimiter:
    """
    Thread-safe token bucket rate limiter for controlling download speed.
    """
    def __init__(self, max_bytes_per_sec: int = 0):
        """
        :param max_bytes_per_sec: Max allowed bytes per second. 0 means unlimited.
        """
        self.max_bytes_per_sec = max_bytes_per_sec
        # Bucket capacity: Allow up to 1 full second burst or at least 256KB
        self.bucket_capacity = max(256 * 1024.0, float(max_bytes_per_sec)) if max_bytes_per_sec > 0 else 0.0
        self.tokens = self.bucket_capacity
        self.last_update = time.perf_counter()
        self.lock = threading.Lock()

    def set_limit(self, max_bytes_per_sec: int):
        with self.lock:
            self.max_bytes_per_sec = max(0, max_bytes_per_sec)
            self.bucket_capacity = max(256 * 1024.0, float(self.max_bytes_per_sec)) if self.max_bytes_per_sec > 0 else 0.0
            self.tokens = min(self.tokens, self.bucket_capacity)
            self.last_update = time.perf_counter()

    def get_limit(self) -> int:
        with self.lock:
            return self.max_bytes_per_sec

    def acquire(self, requested_bytes: int):
        """
        Blocks or sleeps as necessary to maintain the rate limit.
        Handles requests of any size (even if larger than current tokens).
        """
        if self.max_bytes_per_sec <= 0 or requested_bytes <= 0:
            return

        bytes_to_acquire = requested_bytes
        while bytes_to_acquire > 0:
            with self.lock:
                now = time.perf_counter()
                elapsed = now - self.last_update
                self.last_update = now

                # Add refilled tokens
                self.tokens += elapsed * self.max_bytes_per_sec
                # Ensure bucket capacity is at least large enough for incoming chunk size
                effective_capacity = max(self.bucket_capacity, float(bytes_to_acquire))
                if self.tokens > effective_capacity:
                    self.tokens = effective_capacity

                # If we have any tokens, consume what is available
                if self.tokens > 0:
                    take = min(self.tokens, float(bytes_to_acquire))
                    self.tokens -= take
                    bytes_to_acquire -= int(take)
                    if bytes_to_acquire <= 0:
                        return

                # Calculate sleep duration needed for remaining bytes (up to 1 chunk)
                sleep_time = min(bytes_to_acquire, 64 * 1024) / self.max_bytes_per_sec

            if sleep_time > 0:
                time.sleep(min(sleep_time, 0.1))
