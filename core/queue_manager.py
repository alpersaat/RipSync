import os
import threading
import time
import json
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from core.database import Database
from core.categories import detect_category, get_categorized_save_dir
from core.downloader import MultiThreadDownloader, clean_http_headers
from core.stream_downloader import StreamDownloader, is_stream_url
from core.paths import resolve_file_conflict, sanitize_filename, get_disk_free_space, is_path_too_long, suggest_short_download_dir, to_long_path
from core.post_download import execute_post_download
from core.scheduler import DownloadScheduler
from core.power_manager import set_keep_awake
from core.metered_connection import is_metered_connection
from core.logger import get_logger
from core.notifier import notify_error, notify_warning

logger = get_logger("queue_manager")

PRIORITY_WEIGHTS = {
    "high": 3.0,
    "normal": 1.0,
    "low": 0.33
}

class QueueManager:
    def __init__(self, db: Database, max_concurrent: int = 2, global_speed_limit_bps: int = 0):
        self.db = db
        self.max_concurrent = max(1, max_concurrent)
        self.global_speed_limit_bps = global_speed_limit_bps

        self.active_downloaders: Dict[str, MultiThreadDownloader] = {}
        self.custom_speed_limits: Dict[str, int] = {}  # Per-task manual overrides
        self.lock = threading.Lock()
        self.scheduler: Optional[DownloadScheduler] = None
        self.metered_bypass = False

        # İlerleme güncellemelerini bellekte biriktirme (throttling / batching)
        self._progress_cache: Dict[str, Dict[str, Any]] = {}
        self._last_progress_db_sync: Dict[str, float] = {}
        self._progress_sync_interval: float = 1.0  # saniye

        # Callbacks for UI updates
        self.on_task_progress: Optional[Callable[[str, int, int, float, int], None]] = None
        self.on_task_segments: Optional[Callable[[str, List[Dict[str, Any]]], None]] = None
        self.on_task_status: Optional[Callable[[str, str, str], None]] = None
        self.on_task_added: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_queue_empty: Optional[Callable[[], None]] = None
        self.on_scheduler_power_action: Optional[Callable[[str], None]] = None
        self.on_metered_blocked: Optional[Callable[[str], None]] = None

    def set_metered_bypass(self, bypass: bool):
        self.metered_bypass = bypass
        if bypass:
            self._check_queue()

    def set_max_concurrent(self, val: int):
        with self.lock:
            self.max_concurrent = max(1, val)
        self.db.set_setting("max_concurrent", self.max_concurrent)
        self._check_queue()

    def set_global_speed_limit(self, bps: int):
        with self.lock:
            self.global_speed_limit_bps = max(0, bps)
            if self.global_speed_limit_bps == 0:
                self.custom_speed_limits.clear()
                for d in self.active_downloaders.values():
                    d.set_speed_limit(0)
                return
        self.recalculate_bandwidth_allocation()

    def _update_keep_awake(self):
        """Prevents system sleep when there are active downloads and setting is enabled."""
        try:
            enabled = bool(self.db.get_setting("keep_awake_enabled", True))
            if not enabled:
                set_keep_awake(False)
                return

            with self.lock:
                has_active = any(d.status in ("Downloading", "Probing", "Retrying") for d in self.active_downloaders.values())
            set_keep_awake(has_active)
        except Exception as e:
            print(f"[QueueManager] Keep awake update failed: {e}")

    def recalculate_bandwidth_allocation(self):
        """
        Dynamically distributes global bandwidth among active downloads according to their priority weights:
        High (3.0x), Normal (1.0x), Low (0.33x).
        """
        with self.lock:
            active_dls = [d for d in self.active_downloaders.values() if d.status in ("Downloading", "Probing", "Retrying")]
            if not active_dls:
                return

            if self.global_speed_limit_bps <= 0:
                # Unlimited global limit
                for d in active_dls:
                    d.set_speed_limit(0)
                return

            # Compute priority weights
            weights: Dict[str, float] = {}
            for d in active_dls:
                rec = self.db.get_download(d.download_id)
                prio = (rec.get("priority") or "normal").lower() if rec else "normal"
                weights[d.download_id] = PRIORITY_WEIGHTS.get(prio, 1.0)

            total_weight = sum(weights.values()) or 1.0
            for d in active_dls:
                # If user set a specific custom limit lower than allocated, keep manual override
                custom = self.custom_speed_limits.get(d.download_id, 0)
                if custom > 0:
                    d.set_speed_limit(custom)
                else:
                    w = weights.get(d.download_id, 1.0)
                    allocated = max(32 * 1024, int(self.global_speed_limit_bps * (w / total_weight)))
                    d.set_speed_limit(allocated)

    def set_download_priority(self, download_id: str, priority: str):
        """Sets download priority ('high', 'normal', 'low') and recalculates bandwidth allocation."""
        if priority not in ("high", "normal", "low"):
            priority = "normal"
        self.db.update_download(download_id, priority=priority)
        self.recalculate_bandwidth_allocation()

    def set_download_speed_limit(self, download_id: str, bps: int):
        with self.lock:
            if bps > 0:
                self.custom_speed_limits[download_id] = bps
            else:
                self.custom_speed_limits.pop(download_id, None)
            dl = self.active_downloaders.get(download_id)
            if dl:
                dl.set_speed_limit(bps)
        self.recalculate_bandwidth_allocation()

    def get_active_count(self) -> int:
        with self.lock:
            return len([d for d in self.active_downloaders.values() if d.status in ("Downloading", "Probing")])

    def add_download(self, url: str, save_dir: str, filename: str = "",
                     connections: int = 8, quality: str = "max",
                     headers: Optional[Dict[str, str]] = None,
                     start_now: bool = True,
                     auto_open: bool = False,
                     auto_extract: bool = False,
                     priority: str = "normal",
                     tags: str = "",
                     queue_id: str = "default") -> str:
        # Check auto categorization setting
        auto_cat = bool(self.db.get_setting("auto_categorize", True))
        effective_dir = save_dir
        cat = detect_category(filename) if filename else "Others"

        # If user passed base download dir or unspecified, apply smart category subfolder
        default_dir = self.db.get_setting("default_dir", os.path.join(os.path.expanduser("~"), "Downloads"))
        if auto_cat and filename:
            if not effective_dir or os.path.abspath(effective_dir) == os.path.abspath(default_dir):
                effective_dir = get_categorized_save_dir(filename, default_dir)

        # File conflict resolution
        conflict_action = self.db.get_conflict_setting()
        effective_filename = filename or "download"
        if filename:
            effective_filename, was_conflicted = resolve_file_conflict(effective_dir, filename, action=conflict_action)

        # Register in database with headers and quality
        stored_headers = dict(headers or {})
        stored_headers["quality"] = quality

        full_save_path = os.path.join(effective_dir, effective_filename)
        if is_path_too_long(full_save_path):
            short_dir = suggest_short_download_dir()
            notify_warning(
                "Kayıt yolu çok uzun",
                f"Hedef yol 260 karakteri geçti ({len(full_save_path)} kr). "
                f"Kısa bir indirme klasörü kullanmayı deneyin: {short_dir}"
            )

        download_id = self.db.add_download(
            url=url,
            filename=effective_filename,
            save_path=full_save_path,
            connections=connections,
            category=cat if filename else None,
            headers=stored_headers,
            auto_open=auto_open,
            auto_extract=auto_extract,
            priority=priority,
            tags=tags,
            queue_id=queue_id or "default"
        )

        record = self.db.get_download(download_id)
        if self.on_task_added and record:
            self.on_task_added(record)

        if start_now:
            # Sequential Queue check: only start immediately if active count < max_concurrent
            active_count = self.get_active_count()
            if active_count < self.max_concurrent:
                self.start_download(download_id, effective_dir, effective_filename, connections, stored_headers, quality=quality, force=True)
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
            # Check metered connection restriction
            metered_cfg = self.db.get_metered_settings()
            if metered_cfg.get("pause_on_metered", True) and not self.metered_bypass:
                if is_metered_connection():
                    self.db.update_download(download_id, status="Paused", error_message="Tarifeli bağlantı (Kota Koruması Aktif)")
                    if self.on_task_status:
                        self.on_task_status(download_id, "Paused", "Tarifeli bağlantı (Kota Koruması Aktif)")
                    if self.on_metered_blocked:
                        self.on_metered_blocked(download_id)
                    return

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

            # Check free disk space before starting download
            free_sp = get_disk_free_space(s_dir)
            if free_sp >= 0 and free_sp < 10 * 1024 * 1024:  # Under 10 MB
                err_msg = f"Yetersiz disk alanı ({free_sp // (1024*1024)} MB kaldı)"
                logger.error(f"İndirme başlatılamadı, hedef sürücüde disk dolu: {s_dir} ({f_name})")
                self.db.update_download(download_id, status="Error", error_message=err_msg)
                if self.on_task_status:
                    self.on_task_status(download_id, "Error", err_msg)
                notify_error("Yetersiz Disk Alanı", f"'{f_name}' indirilemiyor: Hedef sürücüde yeterli boş alan yok.")
                return

            req_headers = dict(headers or {})
            if not req_headers and record.get("headers_json"):
                try:
                    req_headers = json.loads(record["headers_json"])
                except Exception as e:
                    logger.debug(f"Headers JSON ayrıştırma hatası ({download_id}): {e}")
                    req_headers = {}

            sel_quality = quality or req_headers.get("quality") or self.db.get_setting("preferred_quality", "max")

            target_url = record["url"]
            proxy_url = self.db.get_proxy_url()

            if is_stream_url(target_url):
                browser_cookies = req_headers.get("browser_cookies") or self.db.get_setting("browser_cookies", "")
                download_subtitles = bool(req_headers.get("download_subtitles", self.db.get_setting("download_subtitles", False)))
                download_thumbnail = bool(req_headers.get("download_thumbnail", self.db.get_setting("download_thumbnail", False)))
                embed_metadata = bool(req_headers.get("embed_metadata", self.db.get_setting("embed_metadata", True)))

                downloader = StreamDownloader(
                    download_id=download_id,
                    url=target_url,
                    save_dir=s_dir,
                    filename=f_name,
                    connections=conns,
                    quality=sel_quality,
                    headers=clean_http_headers(req_headers),
                    speed_limit_bps=self.global_speed_limit_bps,
                    proxy=proxy_url,
                    browser_cookies=browser_cookies if browser_cookies else None,
                    download_subtitles=download_subtitles,
                    download_thumbnail=download_thumbnail,
                    embed_metadata=embed_metadata,
                    on_progress=lambda d, t, s, e: self._on_progress(download_id, d, t, s, e),
                    on_segments_update=lambda segs: self._on_segments(download_id, segs),
                    on_status_change=lambda st, err: self._on_status(download_id, st, err)
                )
            else:
                auto_retry_en = bool(self.db.get_setting("auto_retry_enabled", True))
                retries_cnt = int(self.db.get_setting("max_retries", 3))
                downloader = MultiThreadDownloader(
                    download_id=download_id,
                    url=target_url,
                    save_dir=s_dir,
                    filename=f_name,
                    connections=conns,
                    headers=clean_http_headers(req_headers),
                    speed_limit_bps=self.global_speed_limit_bps,
                    proxy=proxy_url,
                    auto_retry=auto_retry_en,
                    max_retries=retries_cnt,
                    on_progress=lambda d, t, s, e: self._on_progress(download_id, d, t, s, e),
                    on_segments_update=lambda segs: self._on_segments(download_id, segs),
                    on_status_change=lambda st, err: self._on_status(download_id, st, err)
                )
            self.active_downloaders[download_id] = downloader

        # Run downloader in background thread
        threading.Thread(target=downloader.start, daemon=True).start()
        self.recalculate_bandwidth_allocation()
        self._update_keep_awake()

    def pause_download(self, download_id: str):
        self.flush_progress(download_id)
        with self.lock:
            dl = self.active_downloaders.get(download_id)
            if dl:
                dl.pause()
            else:
                self.db.update_download(download_id, status="Paused", speed=0, eta=0)
                if self.on_task_status:
                    self.on_task_status(download_id, "Paused", "")
        # A slot freed up; check queue to schedule next waiting item
        self._check_queue()
        self._update_keep_awake()

    def resume_download(self, download_id: str, force: bool = True):
        with self.lock:
            dl = self.active_downloaders.get(download_id)
            if dl:
                dl.resume()
                return

        record = self.db.get_download(download_id)
        if record:
            self.start_download(download_id, force=force)

    def update_download_url(self, download_id: str, new_url: str, new_headers: Optional[Dict[str, str]] = None) -> bool:
        """
        Updates the target URL (and optional headers) for an existing download.
        Preserves existing partial download data on disk, resets error state to Paused.
        """
        with self.lock:
            rec = self.db.get_download(download_id)
            if not rec:
                return False

            dl = self.active_downloaders.get(download_id)
            if dl:
                was_running = dl.status in ("Downloading", "Probing", "Retrying")
                if was_running:
                    dl.pause()
                if hasattr(dl, "update_url"):
                    dl.update_url(new_url, new_headers)

            update_data: Dict[str, Any] = {
                "url": new_url,
                "error_message": "",
                "status": "Paused"
            }
            if new_headers is not None:
                update_data["headers_json"] = json.dumps(new_headers)

            self.db.update_download(download_id, **update_data)
            if self.on_task_status:
                self.on_task_status(download_id, "Paused", "")
            return True

    def cancel_download(self, download_id: str, delete_file: bool = False):
        with self.lock:
            self._progress_cache.pop(download_id, None)
            self._last_progress_db_sync.pop(download_id, None)
            dl = self.active_downloaders.pop(download_id, None)
            if dl:
                try:
                    dl.cancel(delete_file=delete_file)
                except TypeError:
                    dl.cancel()
        self.db.update_download(download_id, status="Cancelled", speed=0, eta=0)
        if self.on_task_status:
            self.on_task_status(download_id, "Cancelled", "")
        self._check_queue()
        self._update_keep_awake()

    def delete_download(self, download_id: str, delete_file: bool = False):
        self.cancel_download(download_id, delete_file=delete_file)
        record = self.db.get_download(download_id)
        if record and delete_file:
            path = record.get("save_path") if isinstance(record, dict) else (record["save_path"] if record else None)
            if path:
                for p in (path, f"{path}.part", f"{path}.ytdl"):
                    try:
                        if os.path.exists(to_long_path(p)):
                            os.remove(to_long_path(p))
                    except Exception as e:
                        logger.warning(f"Dosya diskten silinemedi ({p}): {e}")
        self.db.delete_download(download_id)

    def start_queue(self, queue_id: Optional[str] = None):
        """
        Starts the sequential download queue.
        If queue_id is provided, only unpauses/queues tasks belonging to that queue.
        """
        all_dls = self.db.get_all_downloads(queue_id=queue_id)
        for dl in all_dls:
            if dl["status"] in ("Paused", "Queued"):
                self.db.update_download(dl["id"], status="Queued")
                if self.on_task_status:
                    self.on_task_status(dl["id"], "Queued", "")
        self._check_queue()

    def pause_queue(self, queue_id: Optional[str] = None):
        """Pauses currently active downloads. If queue_id provided, only pauses that queue's downloads."""
        self.flush_progress()
        with self.lock:
            for did, dl in list(self.active_downloaders.items()):
                if queue_id:
                    rec = self.db.get_download(did)
                    if rec and rec.get("queue_id") == queue_id:
                        dl.pause()
                else:
                    dl.pause()
        self._update_keep_awake()

    def reorder_queue(self, download_id: str, direction: str) -> bool:
        """Reorders item in queue: direction is 'up' or 'down'."""
        res = self.db.reorder_download(download_id, direction)
        if res:
            self._check_queue()
        return res

    def move_queue_to_top(self, download_id: str) -> bool:
        res = self.db.move_to_top_of_queue(download_id)
        if res:
            self._check_queue()
        return res

    def move_queue_to_bottom(self, download_id: str) -> bool:
        res = self.db.move_to_bottom_of_queue(download_id)
        if res:
            self._check_queue()
        return res

    def get_downloader(self, download_id: str) -> Optional[MultiThreadDownloader]:
        with self.lock:
            return self.active_downloaders.get(download_id)

    def get_download(self, download_id: str) -> Optional[Dict[str, Any]]:
        return self.db.get_download(download_id)

    def get_all_downloads(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.db.get_all_downloads(category=category)

    def attach_scheduler(self, scheduler: DownloadScheduler):
        self.scheduler = scheduler
        scheduler.on_schedule_start = lambda: self.start_queue()
        scheduler.on_schedule_stop = lambda act: self._handle_scheduler_stop(act)
        scheduler.on_speed_limit_change = lambda bps: self.set_global_speed_limit(bps)

    def _handle_scheduler_stop(self, action: str):
        self.pause_queue()
        if action in ("shutdown", "sleep") and self.on_scheduler_power_action:
            self.on_scheduler_power_action(action)

    def flush_progress(self, download_id: Optional[str] = None):
        """
        Bellekte biriktirilen indirme ilerleme verilerini veritabanına yazar.
        download_id verilmezse bellekteki tüm bekleyen ilerlemeleri tek bir batch ile kaydeder.
        """
        updates = []
        with self.lock:
            if download_id:
                data = self._progress_cache.get(download_id)
                if data:
                    updates.append({"id": download_id, **data})
                    self._last_progress_db_sync[download_id] = time.monotonic()
            else:
                now = time.monotonic()
                for did, data in list(self._progress_cache.items()):
                    updates.append({"id": did, **data})
                    self._last_progress_db_sync[did] = now

        if updates:
            self.db.update_downloads_batch(updates)

    def _on_progress(self, download_id: str, downloaded: int, total: int, speed: float, eta: int):
        now = time.monotonic()
        should_sync = False
        with self.lock:
            self._progress_cache[download_id] = {
                "downloaded_size": downloaded,
                "total_size": total,
                "speed": int(speed),
                "eta": eta
            }
            last_sync = self._last_progress_db_sync.get(download_id, 0.0)
            if (now - last_sync) >= self._progress_sync_interval:
                should_sync = True
                self._last_progress_db_sync[download_id] = now

        if should_sync:
            self.db.update_download(
                download_id,
                downloaded_size=downloaded,
                total_size=total,
                speed=int(speed),
                eta=eta
            )

        # UI/arayüz akıcılığı için anlık ilerleme sinyali her zaman iletilir
        if self.on_task_progress:
            self.on_task_progress(download_id, downloaded, total, speed, eta)

    def _on_segments(self, download_id: str, segments: List[Dict[str, Any]]):
        if self.on_task_segments:
            self.on_task_segments(download_id, segments)

    def _on_status(self, download_id: str, status: str, error: str):
        # Update filename, path, and category in db if probe resolved them
        with self.lock:
            cached_prog = self._progress_cache.pop(download_id, None)
            self._last_progress_db_sync.pop(download_id, None)
            dl = self.active_downloaders.get(download_id)
            extra_kwargs = {}
            if cached_prog:
                extra_kwargs["downloaded_size"] = cached_prog["downloaded_size"]
                extra_kwargs["total_size"] = cached_prog["total_size"]
            if status in ("Completed", "Cancelled", "Error", "Paused"):
                extra_kwargs["speed"] = 0
                extra_kwargs["eta"] = 0

            if status == "Completed":
                extra_kwargs["date_completed"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if dl and dl.filename:
                cat = detect_category(dl.filename)
                # extra_kwargs içinde zaten 'total_size' olabilir (progress cache'ten).
                # Çift değer geçilmesi TypeError yaratır → açık geçilen değer önceliklidir.
                extra_kwargs.pop("total_size", None)
                self.db.update_download(
                    download_id,
                    filename=dl.filename,
                    save_path=dl.save_path,
                    total_size=dl.total_size,
                    category=cat,
                    status=status,
                    error_message=error,
                    **extra_kwargs
                )
            else:
                self.db.update_download(download_id, status=status, error_message=error, **extra_kwargs)

        if status in ("Completed", "Cancelled", "Error", "Paused"):
            with self.lock:
                if status in ("Completed", "Cancelled", "Error"):
                    self.active_downloaders.pop(download_id, None)
            self._check_queue()
            self.recalculate_bandwidth_allocation()
            self._update_keep_awake()

        if status == "Completed":
            try:
                rec = self.db.get_download(download_id)
                if rec:
                    execute_post_download(rec, self.db.get_automation_settings())
            except Exception as e:
                print(f"[QueueManager] Post download hook error: {e}")

        if self.on_task_status:
            self.on_task_status(download_id, status, error)

    def _check_queue(self):
        """Schedule next queued item if concurrent capacity is available."""
        # Check metered connection restriction before launching queued items
        metered_cfg = self.db.get_metered_settings()
        if metered_cfg.get("pause_on_metered", True) and not self.metered_bypass:
            if is_metered_connection():
                if self.on_metered_blocked:
                    self.on_metered_blocked("")
                return

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
