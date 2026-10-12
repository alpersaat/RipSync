import os
import threading
import json
from typing import Dict, List, Optional, Callable, Any
from core.database import Database, detect_category, get_categorized_save_dir
from core.downloader import MultiThreadDownloader
from core.stream_downloader import StreamDownloader, is_stream_url
from core.scheduler import DownloadScheduler

class QueueManager:
    def __init__(self, db: Database, max_concurrent: int = 2, global_speed_limit_bps: int = 0):
        self.db = db
        self.max_concurrent = max(1, max_concurrent)
        self.global_speed_limit_bps = global_speed_limit_bps

        self.active_downloaders: Dict[str, MultiThreadDownloader] = {}
        self.lock = threading.Lock()
        self.scheduler: Optional[DownloadScheduler] = None

        # Callbacks for UI updates
        self.on_task_progress: Optional[Callable[[str, int, int, float, int], None]] = None
        self.on_task_segments: Optional[Callable[[str, List[Dict[str, Any]]], None]] = None
        self.on_task_status: Optional[Callable[[str, str, str], None]] = None
        self.on_task_added: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_queue_empty: Optional[Callable[[], None]] = None
        self.on_scheduler_power_action: Optional[Callable[[str], None]] = None

    def set_max_concurrent(self, val: int):
        with self.lock:
            self.max_concurrent = max(1, val)
        self.db.set_setting("max_concurrent", self.max_concurrent)
        self._check_queue()

    def set_global_speed_limit(self, bps: int):
        with self.lock:
            self.global_speed_limit_bps = max(0, bps)
            for downloader in self.active_downloaders.values():
                downloader.set_speed_limit(self.global_speed_limit_bps)

    def set_download_speed_limit(self, download_id: str, bps: int):
        with self.lock:
            dl = self.active_downloaders.get(download_id)
            if dl:
                dl.set_speed_limit(bps)

    def get_active_count(self) -> int:
        with self.lock:
            return len([d for d in self.active_downloaders.values() if d.status in ("Downloading", "Probing")])

    def add_download(self, url: str, save_dir: str, filename: str = "",
                     connections: int = 8, quality: str = "max",
                     headers: Optional[Dict[str, str]] = None,
                     start_now: bool = True) -> str:
        # Check auto categorization setting
        auto_cat = bool(self.db.get_setting("auto_categorize", True))
        effective_dir = save_dir
        cat = detect_category(filename) if filename else "Others"

        # If user passed base download dir or unspecified, apply smart category subfolder
        default_dir = self.db.get_setting("default_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
        if auto_cat and filename:
            if not effective_dir or os.path.abspath(effective_dir) == os.path.abspath(default_dir):
                effective_dir = get_categorized_save_dir(filename, default_dir)

        # Register in database with headers and quality
        stored_headers = dict(headers or {})
        stored_headers["quality"] = quality

        download_id = self.db.add_download(
            url=url,
            filename=filename or "download",
            save_path=os.path.join(effective_dir, filename or "download"),
            connections=connections,
            category=cat if filename else None,
            headers=stored_headers
        )

        record = self.db.get_download(download_id)
        if self.on_task_added and record:
            self.on_task_added(record)

        if start_now:
            # Sequential Queue check: only start immediately if active count < max_concurrent
            active_count = self.get_active_count()
            if active_count < self.max_concurrent:
                self.start_download(download_id, effective_dir, filename, connections, stored_headers, quality=quality, force=True)
            else:
                self.db.update_download(download_id, status="Queued")
                if self.on_task_status:
                    self.on_task_status(download_id, "Queued", "")
        else:
            self.db.update_download(download_id, status="Queued")
            if self.on_task_status:
                self.on_task_status(download_id, "Queued", "")

        return download_id

    def start_download(self, download_id: str, save_dir: Optional[str] = None,
                       filename: Optional[str] = None, connections: Optional[int] = None,
                       headers: Optional[Dict[str, str]] = None, quality: Optional[str] = None,
                       force: bool = False):
        with self.lock:
            active_count = len([d for d in self.active_downloaders.values() if d.status in ("Downloading", "Probing")])
            if not force and active_count >= self.max_concurrent:
                # Do not exceed concurrent limit; mark Queued
                self.db.update_download(download_id, status="Queued")
                if self.on_task_status:
                    self.on_task_status(download_id, "Queued", "")
                return

            if download_id in self.active_downloaders:
                dl = self.active_downloaders[download_id]
                if dl.status in ("Paused", "Error"):
                    dl.resume()
                return

            record = self.db.get_download(download_id)
            if not record:
                return

            s_dir = save_dir or os.path.dirname(record["save_path"])
            f_name = filename or record["filename"]
            conns = connections or record.get("connections", 8)

            req_headers = dict(headers or {})
            if not req_headers and record.get("headers_json"):
                try:
                    req_headers = json.loads(record["headers_json"])
                except Exception:
                    req_headers = {}

            sel_quality = quality or req_headers.get("quality") or self.db.get_setting("preferred_quality", "max")

            target_url = record["url"]
            if is_stream_url(target_url):
                downloader = StreamDownloader(
                    download_id=download_id,
                    url=target_url,
                    save_dir=s_dir,
                    filename=f_name,
                    connections=conns,
                    quality=sel_quality,
                    headers=req_headers,
                    speed_limit_bps=self.global_speed_limit_bps,
                    on_progress=lambda d, t, s, e: self._on_progress(download_id, d, t, s, e),
                    on_segments_update=lambda segs: self._on_segments(download_id, segs),
                    on_status_change=lambda st, err: self._on_status(download_id, st, err)
                )
            else:
                downloader = MultiThreadDownloader(
                    download_id=download_id,
                    url=target_url,
                    save_dir=s_dir,
                    filename=f_name,
                    connections=conns,
                    headers=req_headers,
                    speed_limit_bps=self.global_speed_limit_bps,
                    on_progress=lambda d, t, s, e: self._on_progress(download_id, d, t, s, e),
                    on_segments_update=lambda segs: self._on_segments(download_id, segs),
                    on_status_change=lambda st, err: self._on_status(download_id, st, err)
                )
            self.active_downloaders[download_id] = downloader

        # Run downloader in background thread
        threading.Thread(target=downloader.start, daemon=True).start()

    def pause_download(self, download_id: str):
        with self.lock:
            dl = self.active_downloaders.get(download_id)
            if dl:
                dl.pause()
            else:
                self.db.update_download(download_id, status="Paused")
                if self.on_task_status:
                    self.on_task_status(download_id, "Paused", "")
        # A slot freed up; check queue to schedule next waiting item
        self._check_queue()

    def resume_download(self, download_id: str, force: bool = True):
        with self.lock:
            dl = self.active_downloaders.get(download_id)
            if dl:
                dl.resume()
                return

        record = self.db.get_download(download_id)
        if record:
            self.start_download(download_id, force=force)

    def cancel_download(self, download_id: str):
        with self.lock:
            dl = self.active_downloaders.pop(download_id, None)
            if dl:
                dl.cancel()
        self.db.update_download(download_id, status="Cancelled")
        if self.on_task_status:
            self.on_task_status(download_id, "Cancelled", "")
        self._check_queue()

    def delete_download(self, download_id: str, delete_file: bool = False):
        self.cancel_download(download_id)
        record = self.db.get_download(download_id)
        if record and delete_file:
            path = record["save_path"]
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        self.db.delete_download(download_id)

    def start_queue(self):
        """
        Starts the sequential download queue.
        Marks paused/waiting downloads as Queued if appropriate, then starts up to max_concurrent downloads.
        """
        all_dls = self.db.get_all_downloads()
        for dl in all_dls:
            if dl["status"] == "Paused":
                self.db.update_download(dl["id"], status="Queued")
                if self.on_task_status:
                    self.on_task_status(dl["id"], "Queued", "")
        self._check_queue()

    def pause_queue(self):
        """Pauses all currently active downloads."""
        with self.lock:
            for dl in list(self.active_downloaders.values()):
                dl.pause()

    def reorder_queue(self, download_id: str, direction: str) -> bool:
        """Reorders item in queue: direction is 'up' or 'down'."""
        return self.db.reorder_download(download_id, direction)

    def move_queue_to_top(self, download_id: str) -> bool:
        return self.db.move_to_top_of_queue(download_id)

    def get_downloader(self, download_id: str) -> Optional[MultiThreadDownloader]:
        with self.lock:
            return self.active_downloaders.get(download_id)

    def attach_scheduler(self, scheduler: DownloadScheduler):
        self.scheduler = scheduler
        scheduler.on_schedule_start = lambda: self.start_queue()
        scheduler.on_schedule_stop = lambda act: self._handle_scheduler_stop(act)

    def _handle_scheduler_stop(self, action: str):
        self.pause_queue()
        if action in ("shutdown", "sleep") and self.on_scheduler_power_action:
            self.on_scheduler_power_action(action)

    def _on_progress(self, download_id: str, downloaded: int, total: int, speed: float, eta: int):
        self.db.update_download(
            download_id,
            downloaded_size=downloaded,
            total_size=total,
            speed=int(speed),
            eta=eta
        )
        if self.on_task_progress:
            self.on_task_progress(download_id, downloaded, total, speed, eta)

    def _on_segments(self, download_id: str, segments: List[Dict[str, Any]]):
        if self.on_task_segments:
            self.on_task_segments(download_id, segments)

    def _on_status(self, download_id: str, status: str, error: str):
        # Update filename, path, and category in db if probe resolved them
        with self.lock:
            dl = self.active_downloaders.get(download_id)
            if dl and dl.filename:
                cat = detect_category(dl.filename)
                self.db.update_download(
                    download_id,
                    filename=dl.filename,
                    save_path=dl.save_path,
                    total_size=dl.total_size,
                    category=cat,
                    status=status,
                    error_message=error
                )
            else:
                self.db.update_download(download_id, status=status, error_message=error)

        if status in ("Completed", "Cancelled", "Error", "Paused"):
            with self.lock:
                if status in ("Completed", "Cancelled", "Error"):
                    self.active_downloaders.pop(download_id, None)
            self._check_queue()

        if self.on_task_status:
            self.on_task_status(download_id, status, error)

    def _check_queue(self):
        """Schedule next queued item if concurrent capacity is available."""
        with self.lock:
            active_count = len([d for d in self.active_downloaders.values() if d.status in ("Downloading", "Probing")])
            slots_available = self.max_concurrent - active_count
            if slots_available <= 0:
                return

        queued = self.db.get_queued_downloads_ordered()
        if not queued:
            with self.lock:
                has_active = len(self.active_downloaders) > 0
            if not has_active and self.on_queue_empty:
                self.on_queue_empty()
            return

        for item in queued[:slots_available]:
            self.start_download(item["id"], force=True)
