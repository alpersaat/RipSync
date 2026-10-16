import os
import re
import json
import time
import urllib.parse
import threading
from typing import List, Dict, Optional, Callable, Any
import httpx

from core.segment import Segment
from core.speed_limiter import SpeedLimiter
from core.paths import sanitize_filename, resolve_file_conflict, to_long_path
from core.logger import get_logger
from core.notifier import notify_error

logger = get_logger("downloader")

MIN_SPLIT_SIZE = 1024 * 1024  # 1 MB minimum remaining to split a segment

class MultiThreadDownloader:
    def __init__(self,
                 download_id: str,
                 url: str,
                 save_dir: str,
                 filename: Optional[str] = None,
                 connections: int = 8,
                 headers: Optional[Dict[str, str]] = None,
                 speed_limit_bps: int = 0,
                 proxy: Optional[str] = None,
                 auto_retry: bool = True,
                 max_retries: int = 3,
                 retry_delay: float = 3.0,
                 on_progress: Optional[Callable[[int, int, float, int], None]] = None,
                 on_segments_update: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
                 on_status_change: Optional[Callable[[str, str], None]] = None):
        self.download_id = download_id
        self.url = url
        self.save_dir = save_dir
        self.filename = filename or ""
        self.save_path = ""
        self.connections = max(1, min(32, connections))
        self.headers = headers or {}
        self.speed_limiter = SpeedLimiter(speed_limit_bps)
        self.proxy = proxy

        self.auto_retry = auto_retry
        self.max_retries = max(1, max_retries)
        self.retry_delay = retry_delay
        self.retry_count = 0

        self.on_progress = on_progress
        self.on_segments_update = on_segments_update
        self.on_status_change = on_status_change

        self.total_size = -1
        self.accept_ranges = False
        self.status = "Queued"  # Queued, Probing, Downloading, Paused, Completed, Error
        self.error_message = ""

        self.segments: List[Segment] = []
        self._segment_configs: List[Dict[str, Any]] = []

        self.lock = threading.Lock()
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None

        self.state_file = ""

        # Bozuk durum dosyası durumunda kullanıcıya 'yeniden dene' / 'devam et' seçimi sunulur
        self.state_corrupt = False
        self._awaiting_state_decision = False

    def _get_clean_filename(self, candidate: str) -> str:
        # Strip query parameters or fragments if any
        candidate = candidate.split("?")[0].split("#")[0]
        # Remove invalid Windows filename characters
        clean = re.sub(r'[\\/*?:"<>|]', "_", candidate).strip(" .")
        return clean or "download_file"

    def probe_url(self) -> bool:
        """Inspect headers to determine filename, size, and range support."""
        self._set_status("Probing")
        req_headers = dict(self.headers)
        if "User-Agent" not in req_headers and "user-agent" not in req_headers:
            req_headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

        attempts = self.max_retries if self.auto_retry else 1
        for attempt in range(attempts):
            try:
                client_kwargs = {"follow_redirects": True, "timeout": 20.0}
                if self.proxy:
                    client_kwargs["proxy"] = self.proxy
                with httpx.Client(**client_kwargs) as client:
                    resp = None
                    # Try HEAD first
                    try:
                        resp = client.head(self.url, headers=req_headers)
                    except Exception as e:
                        logger.debug(f"HEAD isteği başarısız ({self.url}): {e}")

                    # If HEAD fails or returns 405/403, fallback to GET with Range: bytes=0-0
                    if not resp or resp.status_code >= 400 or "content-length" not in resp.headers:
                        probe_headers = dict(req_headers)
                        probe_headers["Range"] = "bytes=0-0"
                        resp = client.get(self.url, headers=probe_headers)

                    # Extract filename if not set
                    if not self.filename:
                        cd = resp.headers.get("content-disposition", "")
                        if "filename*=" in cd:
                            match = re.search(r"filename\*=UTF-8''([^;]+)", cd, re.IGNORECASE)
                            if match:
                                self.filename = urllib.parse.unquote(match.group(1))
                        elif "filename=" in cd:
                            match = re.search(r'filename="?([^";]+)"?', cd, re.IGNORECASE)
                            if match:
                                self.filename = match.group(1)

                        if not self.filename:
                            # Extract from URL path
                            parsed = urllib.parse.urlparse(str(resp.url))
                            path_name = os.path.basename(parsed.path)
                            self.filename = urllib.parse.unquote(path_name) if path_name else "download.bin"

                    if not self.save_path:
                        self.filename = sanitize_filename(self.filename)
                        try:
                            os.makedirs(to_long_path(self.save_dir), exist_ok=True)
                        except Exception as e:
                            logger.error(f"Kayıt dizini oluşturulamadı ({self.save_dir}): {e}", exc_info=True)
                            self.error_message = f"Kayıt klasörü oluşturulamadı: {e}"
                            self._set_status("Error", self.error_message)
                            notify_error("Klasör Hatası", f"{self.save_dir} klasörü oluşturulamadı: {e}")
                            return False

                        resolved_name, _ = resolve_file_conflict(self.save_dir, self.filename, action="auto_rename")
                        self.filename = resolved_name
                        self.save_path = os.path.join(self.save_dir, self.filename)
                        self.state_file = self.save_path + f".{self.download_id}.ripsync_state"

                    # Check Content-Length and Range support
                    cr = resp.headers.get("content-range", "")
                    if cr and "/" in cr:
                        try:
                            tot = cr.split("/")[1].strip()
                            if tot != "*":
                                self.total_size = int(tot)
                                self.accept_ranges = True
                        except Exception as e:
                            logger.debug(f"Content-range ayrıştırma hatası: {e}")

                    if self.total_size <= 0 and "content-length" in resp.headers:
                        try:
                            self.total_size = int(resp.headers["content-length"])
                        except Exception as e:
                            logger.debug(f"Content-length ayrıştırma hatası: {e}")

                    if resp.headers.get("accept-ranges", "").lower() == "bytes" or resp.status_code == 206:
                        self.accept_ranges = True

                    return True
            except Exception as e:
                logger.warning(f"URL bağlantı denemesi {attempt + 1}/{attempts} başarısız ({self.url}): {e}")
                if self.auto_retry and attempt < attempts - 1 and not self._stop_event.is_set():
                    self._set_status("Retrying", f"Bağlantı kuruluyor: Yeniden deneniyor ({attempt + 1}/{self.max_retries})...")
                    time.sleep(2.0)
                    continue
                self.error_message = f"Bağlantı hatası: {str(e)}"
                self._set_status("Error", self.error_message)
                notify_error("Bağlantı Hatası", f"{self.filename or self.url} indirilemedi: {self.error_message}")
                return False
        return False

    def _allocate_file(self) -> bool:
        """Allocate destination file. Avoid zero-filling if file already exists."""
        try:
            if not os.path.exists(to_long_path(self.save_path)):
                with open(to_long_path(self.save_path), "wb") as f:
                    if self.total_size > 0:
                        # Sparse / fast allocate on Windows: seek and write 1 byte
                        f.seek(self.total_size - 1)
                        f.write(b"\0")
            else:
                cur_size = os.path.getsize(to_long_path(self.save_path))
                if self.total_size > 0 and cur_size < self.total_size:
                    with open(to_long_path(self.save_path), "r+b") as f:
                        f.seek(self.total_size - 1)
                        f.write(b"\0")
            return True
        except Exception as e:
            logger.error(f"Dosya alanı ayrılamadı ({self.save_path}): {e}", exc_info=True)
            self.error_message = f"Dosya alanı ayrılamadı: {e}"
            self._set_status("Error", self.error_message)
            notify_error("Dosya Yazma Hatası", f"{self.filename} için disk alanı ayrılamadı: {e}")
            return False

    def _load_or_create_segments(self):
        # Try loading state file (check ripsync_state, or fallback to legacy indirici_state)
        s_file = self.state_file
        if not s_file or not os.path.exists(to_long_path(s_file)):
            legacy = self.save_path + f".{self.download_id}.indirici_state" if self.save_path else ""
            if legacy and os.path.exists(to_long_path(legacy)):
                s_file = legacy

        is_corrupted = False

        if s_file and os.path.exists(to_long_path(s_file)):
            try:
                with open(to_long_path(s_file), "r", encoding="utf-8") as f:
                    data = json.load(f)
                segments = data.get("segments", [])
                if not isinstance(segments, list) or len(segments) == 0:
                    is_corrupted = True
                else:
                    for s in segments:
                        if not isinstance(s, dict):
                            is_corrupted = True
                            break
                        if "start" not in s or "current" not in s or "end" not in s:
                            is_corrupted = True
                            break
                        if not isinstance(s["start"], int) or not isinstance(s["current"], int) or not isinstance(s["end"], int):
                            is_corrupted = True
                            break
                        if s["current"] < s["start"] or (s["end"] >= 0 and s["current"] > s["end"] + 1):
                            is_corrupted = True
                            break
                if not is_corrupted:
                    self._segment_configs = segments
                    return
            except Exception as e:
                logger.warning(f"Durum dosyası okunamadı veya biçimi bozuk ({s_file}): {e}")
                is_corrupted = True

        if is_corrupted:
            # Bozuk state dosyası tespit edildi: durum dosyalarını temizle, ama yarıda biten
            # hedef dosyayı diskte koru (veri kaybını önle) ve kullanıcıya seçim sun.
            logger.warning(f"Bozuk state dosyası tespit edildi, dosya korunuyor: {self.filename}")
            for fpath in (s_file, self.state_file, f"{self.state_file}.tmp" if self.state_file else None):
                try:
                    if fpath and os.path.exists(to_long_path(fpath)):
                        os.remove(to_long_path(fpath))
                except Exception as e:
                    logger.debug(f"Eski state dosyası silinemedi ({fpath}): {e}")

            self.state_corrupt = True
            self._awaiting_state_decision = True
            self.connections = 1
            self._segment_configs = [{
                "index": 0,
                "start": 0,
                "current": 0,
                "end": self.total_size - 1 if self.total_size > 0 else -1
            }]
            self._set_status("CorruptState", f"Bozuk durum dosyası: {self.filename or self.url}")
            return

        self._segment_configs = []
        if self.accept_ranges and self.total_size > 0 and self.connections > 1:
            part_size = self.total_size // self.connections
            for i in range(self.connections):
                start = i * part_size
                end = (start + part_size - 1) if (i < self.connections - 1) else (self.total_size - 1)
                self._segment_configs.append({
                    "index": i,
                    "start": start,
                    "current": start,
                    "end": end
                })
        else:
            # Single connection
            self._segment_configs.append({
                "index": 0,
                "start": 0,
                "current": 0,
                "end": self.total_size - 1 if self.total_size > 0 else -1
            })

    def _save_state(self):
        if not self.state_file:
            return
        with self.lock:
            cfgs = []
            for seg in self.segments:
                cfgs.append({
                    "index": seg.index,
                    "start": seg.start_byte,
                    "current": seg.current_byte,
                    "end": seg.end_byte
                })
        long_state = to_long_path(self.state_file)
        tmp_file = f"{long_state}.tmp"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump({"total_size": self.total_size, "segments": cfgs}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, long_state)
        except Exception as e:
            logger.error(f"İndirme durumu kaydedilemedi ({self.filename}): {e}", exc_info=True)
            if not getattr(self, "_state_error_notified", False):
                self._state_error_notified = True
                notify_error("Durum Kayıt Hatası", f"{self.filename} için indirme durumu diske kaydedilemedi: {e}")
            try:
                if os.path.exists(tmp_file):
                    os.remove(tmp_file)
            except Exception as ex:
                logger.debug(f"Geçici state dosyası silinemedi ({tmp_file}): {ex}")

    def start(self, segment_configs: Optional[List[Dict[str, Any]]] = None):
        self._stop_event.clear()
        self.retry_count = 0
        if not self.save_path:
            if not self.probe_url():
                return

        if segment_configs is None:
            self._load_or_create_segments()
            if self._awaiting_state_decision:
                # Kullanıcının 'yeniden dene' / 'devam et' kararı bekleniyor
                return
        else:
            self._segment_configs = segment_configs

        if not self._allocate_file():
            return

        self.segments = []
        for cfg in self._segment_configs:
            seg = Segment(
                index=cfg["index"],
                url=self.url,
                save_path=self.save_path,
                start_byte=cfg["start"],
                end_byte=cfg["end"],
                current_byte=cfg["current"],
                headers=self.headers,
                speed_limiter=self.speed_limiter,
                proxy=self.proxy
            )
            self.segments.append(seg)
            seg.start()

        self._set_status("Downloading")
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def update_url(self, new_url: str, new_headers: Optional[Dict[str, str]] = None):
        """Updates target URL (for expired link refresh) and preserves existing downloaded bytes."""
        with self.lock:
            self.url = new_url
            if new_headers is not None:
                self.headers = new_headers
            if self.status == "Error":
                self.status = "Paused"
                self.error_message = ""

    def pause(self):
        self._stop_event.set()
        for seg in self.segments:
            seg.stop()
        self._set_status("Paused")
        self._save_state()

    def resume(self):
        if self.status == "CorruptState" and self.state_corrupt:
            # Devam et: diskteki yarıda biten dosyayı koru, tek bağlantıyla
            # dosyanın mevcut boyutundan kaldığı yerden indirmeye devam et.
            cur_size = 0
            if self.save_path and os.path.exists(to_long_path(self.save_path)):
                try:
                    cur_size = os.path.getsize(to_long_path(self.save_path))
                except OSError:
                    cur_size = 0
            with self.lock:
                self.state_corrupt = False
                self._awaiting_state_decision = False
                self.connections = 1
                self._segment_configs = [{
                    "index": 0,
                    "start": cur_size,
                    "current": cur_size,
                    "end": self.total_size - 1 if self.total_size > 0 else -1,
                }]
            self.start(self._segment_configs)
            return
        if self.status in ("Paused", "Error"):
            self.start()

    def retry(self):
        """Kullanıcı onaylı: bozuk durum dosyasını atıp tek bağlantılı indirmeyi baştan yeniden dener."""
        with self.lock:
            self.state_corrupt = False
            self._awaiting_state_decision = False
            self.connections = 1
        self.start()

    def cancel(self, delete_file: bool = False):
        self.pause()
        self._set_status("Cancelled")
        if delete_file:
            candidates = [self.save_path, f"{self.save_path}.part"] if self.save_path else []
            for fpath in (self.state_file, f"{self.state_file}.tmp" if self.state_file else None, *candidates):
                try:
                    if fpath and os.path.exists(to_long_path(fpath)):
                        os.remove(to_long_path(fpath))
                except Exception as e:
                    logger.debug(f"İptal edilen dosya silinemedi ({fpath}): {e}")


    def set_speed_limit(self, bps: int):
        self.speed_limiter.set_limit(bps)

    def _set_status(self, status: str, err: str = ""):
        self.status = status
        self.error_message = err
        if self.on_status_change:
            self.on_status_change(status, err)

    def _try_split_longest_segment(self):
        """Dynamic chunk splitting: splits the segment with highest remaining bytes to speed up download."""
        if not self.accept_ranges or self.total_size <= 0:
            return
        if len(self.segments) >= self.connections:
            return

        with self.lock:
            candidate = None
            max_rem = 0
            for seg in self.segments:
                if seg.status == "downloading" and seg.remaining_bytes > max_rem:
                    max_rem = seg.remaining_bytes
                    candidate = seg

            if candidate and max_rem >= (MIN_SPLIT_SIZE * 2):
                with candidate.lock:
                    cur = candidate.current_byte
                    old_end = candidate.end_byte
                    half = cur + (old_end - cur) // 2
                    candidate.end_byte = half

                new_idx = len(self.segments)
                new_seg = Segment(
                    index=new_idx,
                    url=self.url,
                    save_path=self.save_path,
                    start_byte=half + 1,
                    end_byte=old_end,
                    current_byte=half + 1,
                    headers=self.headers,
                    speed_limiter=self.speed_limiter
                )
                self.segments.append(new_seg)
                new_seg.start()

    def _monitor_loop(self):
        last_save_time = time.time()
        while not self._stop_event.is_set():
            time.sleep(0.3)

            with self.lock:
                total_downloaded = sum(seg.current_byte - seg.start_byte for seg in self.segments)
                total_speed = sum(seg.current_speed for seg in self.segments)
                all_done = all(seg.status == "completed" for seg in self.segments)
                any_error = any(seg.status == "error" for seg in self.segments)

                # Collect segment states for UI visualization
                seg_info = []
                for seg in self.segments:
                    seg_info.append({
                        "index": seg.index,
                        "start": seg.start_byte,
                        "current": seg.current_byte,
                        "end": seg.end_byte,
                        "ratio": seg.progress_ratio,
                        "status": seg.status,
                        "speed": seg.current_speed
                    })

            # Calculate ETA
            eta = 0
            if total_speed > 0 and self.total_size > 0:
                rem = max(0, self.total_size - total_downloaded)
                eta = int(rem / total_speed)

            if self.on_progress:
                self.on_progress(total_downloaded, self.total_size, total_speed, eta)

            if self.on_segments_update:
                self.on_segments_update(seg_info)

            # Check if any segment completed, try splitting slower segments
            has_completed = any(s.status == "completed" for s in self.segments)
            has_active = any(s.status == "downloading" for s in self.segments)
            if has_completed and has_active and len(self.segments) < self.connections:
                self._try_split_longest_segment()

            # Save state every 2 seconds
            if time.time() - last_save_time > 2.0:
                self._save_state()
                last_save_time = time.time()

            if any_error:
                err_msg = next((str(s.error) for s in self.segments if s.error), "İndirme hatası")
                if self.auto_retry and self.retry_count < self.max_retries and not self._stop_event.is_set():
                    self.retry_count += 1
                    delay = self.retry_delay * (1.5 ** (self.retry_count - 1))
                    self._set_status("Retrying", f"Ağ kesintisi: Yeniden deneniyor ({self.retry_count}/{self.max_retries}) - {int(delay)} sn...")
                    for seg in self.segments:
                        seg.stop()
                    self._save_state()

                    waited = 0.0
                    while waited < delay and not self._stop_event.is_set():
                        time.sleep(0.2)
                        waited += 0.2

                    if not self._stop_event.is_set():
                        self._load_or_create_segments()
                        self.segments = []
                        for cfg in self._segment_configs:
                            seg = Segment(
                                index=cfg["index"],
                                url=self.url,
                                save_path=self.save_path,
                                start_byte=cfg["start"],
                                end_byte=cfg["end"],
                                current_byte=cfg["current"],
                                headers=self.headers,
                                speed_limiter=self.speed_limiter
                            )
                            self.segments.append(seg)
                            seg.start()
                        self._set_status("Downloading")
                        continue

                self._set_status("Error", err_msg)
                self._save_state()
                break

            if all_done:
                self._set_status("Completed")
                # Remove state file upon successful completion
                for fpath in (self.state_file, f"{self.state_file}.tmp" if self.state_file else None):
                    try:
                        if fpath and os.path.exists(to_long_path(fpath)):
                            os.remove(to_long_path(fpath))
                    except Exception as e:
                        logger.debug(f"Tamamlanan indirme state dosyası silinemedi ({fpath}): {e}")
                break
