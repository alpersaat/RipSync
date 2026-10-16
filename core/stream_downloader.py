import os
import re
import time
import threading
from typing import Dict, Any, List, Optional, Callable
import imageio_ffmpeg
import yt_dlp

import html
import httpx
import xml.etree.ElementTree as ET

from core.speed_limiter import SpeedLimiter
from core.social_resolver import SocialResolver, is_tiktok_url, is_instagram_url, is_twitter_url, format_social_error
from core.logger import get_logger
from core.paths import to_long_path
from core.notifier import notify_error

logger = get_logger("stream_downloader")

STREAM_DOMAINS = (
    "youtube.com", "youtu.be",
    "twitter.com", "x.com",
    "tiktok.com", "tiktokv.com", "vt.tiktok.com", "vm.tiktok.com",
    "instagram.com", "instagr.am",
    "facebook.com", "fb.watch",
    "vimeo.com", "dailymotion.com",
    "reddit.com", "twitch.tv",
    "video.twimg.com"
)


def is_stream_url(url: str) -> bool:
    """Check if URL should be processed via yt-dlp + ffmpeg."""
    u_lower = url.lower()
    clean = u_lower.split("?")[0]
    if clean.endswith(".m3u8") or clean.endswith(".mpd"):
        return True
    return any(domain in u_lower for domain in STREAM_DOMAINS)

def sanitize_filename(title: str) -> str:
    """Sanitize title to be a safe Windows filename without invalid characters."""
    # Replace invalid Windows chars and unicode fullwidth chars like \uff5c
    cleaned = re.sub(r'[\\/*?:"<>|\uff5c\x00-\x1f]', '_', title)
    cleaned = cleaned.strip(" .")
    if len(cleaned) > 120:
        cleaned = cleaned[:120].strip(" .")
    return cleaned or "video"

QUALITY_FORMATS = {
    "max": "bestvideo+bestaudio/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
    "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]/best",
    "audio": "bestaudio/best",
    "subtitle": "subtitle"
}

class StreamDownloader:
    """
    Downloads media from video platforms (YouTube, Twitter/X, Instagram, HLS .m3u8, etc.)
    using yt-dlp and merges video+audio into a 100% playable MP4 via ffmpeg.
    """
    def __init__(self,
                 download_id: str,
                 url: str,
                 save_dir: str,
                 filename: Optional[str] = None,
                 connections: int = 8,
                 quality: str = "max",
                 headers: Optional[Dict[str, str]] = None,
                 speed_limit_bps: int = 0,
                 proxy: Optional[str] = None,
                 browser_cookies: Optional[str] = None,
                 download_subtitles: bool = False,
                 subtitles_langs: Optional[List[str]] = None,
                 download_thumbnail: bool = False,
                 embed_metadata: bool = True,
                 on_progress: Optional[Callable[[int, int, float, int], None]] = None,
                 on_segments_update: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
                 on_status_change: Optional[Callable[[str, str], None]] = None):
        self.download_id = download_id
        self.url = url
        self.save_dir = save_dir
        self.filename = filename or ""
        self.save_path = ""
        self.connections = connections
        self.quality = quality.lower() if quality else "max"
        self.headers = headers or {}
        self.speed_limiter = SpeedLimiter(speed_limit_bps)
        self.proxy = proxy
        self.browser_cookies = browser_cookies
        self.download_subtitles = download_subtitles
        self.subtitles_langs = subtitles_langs or ["tr", "en"]
        self.download_thumbnail = download_thumbnail
        self.embed_metadata = embed_metadata

        self.on_progress = on_progress
        self.on_segments_update = on_segments_update
        self.on_status_change = on_status_change

        self.total_size = -1
        self.downloaded_size = 0
        self.current_speed = 0.0
        self.status = "Queued"
        self.error_message = ""

        # Segments representation for the IDM progress bar visualizer
        self.segments: List[Any] = []
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ydl: Optional[yt_dlp.YoutubeDL] = None

    def _set_status(self, status: str, err: str = ""):
        self.status = status
        self.error_message = err
        if self.on_status_change:
            self.on_status_change(status, err)

    def _progress_hook(self, d: dict):
        if self._stop_event.is_set():
            raise Exception("İndirme kullanıcı tarafından durduruldu.")

        status = d.get("status")
        if status == "downloading":
            self.status = "Downloading"
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate", -1)
            speed = d.get("speed") or 0.0
            eta = d.get("eta") or 0

            self.downloaded_size = downloaded
            if total and total > 0:
                self.total_size = total
            elif self.total_size <= 0 and total:
                self.total_size = total
            self.current_speed = float(speed)

            # Update segments for the visualizer bar
            if total > 0:
                seg_count = min(8, self.connections)
                part_size = total // seg_count
                segs = []
                for i in range(seg_count):
                    s_start = i * part_size
                    s_end = (s_start + part_size - 1) if i < seg_count - 1 else total - 1
                    s_curr = min(s_end, s_start + max(0, int((downloaded / total) * part_size * seg_count) - (i * part_size)))
                    s_curr = max(s_start, min(s_end, s_curr))
                    ratio = (s_curr - s_start) / max(1, s_end - s_start)
                    segs.append({
                        "index": i,
                        "start": s_start,
                        "current": s_curr,
                        "end": s_end,
                        "ratio": ratio,
                        "status": "downloading" if s_curr < s_end else "completed",
                        "speed": speed / seg_count
                    })
                if self.on_segments_update:
                    self.on_segments_update(segs)

            if self.on_progress:
                self.on_progress(downloaded, total, float(speed), int(eta))

        elif status == "finished":
            self._set_status("Merging", "Ses ve görüntü birleştiriliyor...")

    def start(self):
        self._stop_event.clear()
        self._set_status("Probing")
        self._thread = threading.Thread(target=self._run_download, daemon=True)
        self._thread.start()

    def _run_download(self):
        try:
            os.makedirs(to_long_path(self.save_dir), exist_ok=True)
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

            # Handle Subtitle (.srt) downloading
            if self.quality == "subtitle":
                self._run_subtitle_download()
                return

            format_spec = QUALITY_FORMATS.get(self.quality, "bestvideo+bestaudio/best")
            is_audio_only = (self.quality == "audio")
            ext_target = "mp3" if is_audio_only else "mp4"

            ydl_opts = {
                "ffmpeg_location": ffmpeg_exe,
                "progress_hooks": [self._progress_hook],
                "format": format_spec,
                "quiet": True,
                "no_warnings": True,
                "ignoreerrors": False,
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                }
            }
            if self.proxy:
                ydl_opts["proxy"] = self.proxy

            if self.browser_cookies and self.browser_cookies.lower() not in ("none", "disabled", "devre dışı"):
                b_name = self.browser_cookies.lower().strip()
                if b_name in ("chrome", "firefox", "edge", "brave", "opera", "vivaldi", "safari"):
                    ydl_opts["cookiesfrombrowser"] = (b_name,)

            if is_audio_only:
                pps = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }]
                if self.embed_metadata:
                    ydl_opts["writethumbnail"] = True
                    pps.append({"key": "FFmpegMetadata", "add_metadata": True})
                    pps.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg"})
                    pps.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
                ydl_opts["postprocessors"] = pps
            else:
                ydl_opts["merge_output_format"] = "mp4"
                pps = []
                if self.download_thumbnail:
                    ydl_opts["writethumbnail"] = True
                    pps.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg"})
                if self.embed_metadata:
                    pps.append({"key": "FFmpegMetadata", "add_metadata": True})
                if pps:
                    ydl_opts["postprocessors"] = pps

            if self.download_subtitles:
                ydl_opts["writesubtitles"] = True
                ydl_opts["writeautomaticsub"] = True
                ydl_opts["subtitleslangs"] = self.subtitles_langs
                ydl_opts["subtitlesformat"] = "srt/best"

            # Avoid passing raw browser cookies for YouTube or Twitter/X as it triggers anti-bot blocks
            u_lower = self.url.lower()
            is_yt_or_x = any(d in u_lower for d in ("youtube.com", "youtu.be", "twitter.com", "x.com"))
            if not is_yt_or_x:
                if "Referer" in self.headers:
                    ydl_opts["http_headers"]["Referer"] = self.headers["Referer"]
                if "Cookie" in self.headers:
                    ydl_opts["http_headers"]["Cookie"] = self.headers["Cookie"]

            # 1. First probe metadata to get real video title & watermark-free stream
            social_info = None
            download_url = self.url
            if is_tiktok_url(self.url):
                self._set_status("Probing", "TikTok filigransız video bağlantısı çözülüyor...")
                def on_warn_tt(msg):
                    self._set_status("Probing", msg)
                social_info = SocialResolver.resolve_tiktok(self.url, warning_callback=on_warn_tt)
            elif is_instagram_url(self.url):
                self._set_status("Probing", "Instagram Reels bağlantısı çözülüyor...")
                def on_warn_ig(msg):
                    self._set_status("Probing", msg)
                social_info = SocialResolver.resolve_instagram(self.url, cookies=self.headers.get("Cookie"), warning_callback=on_warn_ig)
            elif is_twitter_url(self.url):
                self._set_status("Probing", "X (Twitter) video bağlantısı çözülüyor...")
                social_info = SocialResolver.resolve_twitter(self.url)

            if social_info and social_info.get("warning"):
                self._set_status("Probing", social_info["warning"])

            if social_info and social_info.get("video_url"):
                if is_audio_only and social_info.get("audio_url"):
                    download_url = social_info["audio_url"]
                else:
                    download_url = social_info["video_url"]
                raw_title = social_info.get("title") or "Video"
                clean_title = sanitize_filename(self.filename if self.filename else raw_title)
                self.filename = f"{clean_title}.{ext_target}"
                self.save_path = os.path.join(self.save_dir, self.filename)
            else:
                # Fallback to standard yt-dlp probing
                if is_tiktok_url(self.url):
                    # Filter out watermarked formats in yt-dlp
                    ydl_opts["format"] = "bestvideo[format_note!*=watermark][format_note!*=watermarked][format_id!*=download]+bestaudio/best[format_note!*=watermark][format_note!*=watermarked][format_id!*=download]/best"

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    if is_instagram_url(self.url) and "Cookie" in self.headers:
                        SocialResolver._inject_cookies(ydl.cookiejar, self.headers["Cookie"], ".instagram.com")
                    info = ydl.extract_info(self.url, download=False)
                    if not info:
                        raise Exception("Video bilgileri alınamadı.")

                    raw_title = info.get("title", "Video")
                    clean_title = sanitize_filename(self.filename if self.filename else raw_title)
                    self.filename = f"{clean_title}.{ext_target}"
                    self.save_path = os.path.join(self.save_dir, self.filename)

                    # Estimate total size early so UI shows file size before/during download
                    est_size = -1
                    try:
                        proc = ydl.process_ie_result(info, download=False)
                        req = proc.get("requested_formats") or []
                        if req:
                            sizes = [(f.get("filesize") or f.get("filesize_approx") or 0) for f in req]
                            if all(s > 0 for s in sizes):
                                est_size = sum(sizes)
                        if est_size <= 0:
                            est_size = proc.get("filesize") or proc.get("filesize_approx") or info.get("filesize") or info.get("filesize_approx") or -1
                    except Exception:
                        est_size = info.get("filesize") or info.get("filesize_approx") or -1

                    if est_size and est_size > 0:
                        self.total_size = int(est_size)
                        if self.on_progress:
                            self.on_progress(self.downloaded_size, self.total_size, 0.0, 0)

            # 2. Configure output template with the exact sanitized title
            ydl_opts["outtmpl"] = os.path.join(self.save_dir, f"{clean_title}.%(ext)s")

            # 3. Download and merge video+audio in high quality
            self._set_status("Downloading")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self._ydl = ydl
                if is_instagram_url(download_url) and "Cookie" in self.headers:
                    SocialResolver._inject_cookies(ydl.cookiejar, self.headers["Cookie"], ".instagram.com")
                ydl.download([download_url])


            # 4. Verify output file on disk
            candidate_target = os.path.join(self.save_dir, f"{clean_title}.{ext_target}")
            if os.path.exists(candidate_target):
                self.save_path = candidate_target
                self.filename = os.path.basename(self.save_path)
            else:
                for alt_ext in (".mp4", ".mp3", ".mkv", ".webm", ".m4a"):
                    c_file = os.path.join(self.save_dir, f"{clean_title}{alt_ext}")
                    if os.path.exists(c_file):
                        self.save_path = c_file
                        self.filename = os.path.basename(c_file)
                        break

            if os.path.exists(self.save_path):
                self.total_size = os.path.getsize(self.save_path)
                self.downloaded_size = self.total_size
                if self.on_progress:
                    self.on_progress(self.total_size, self.total_size, 0.0, 0)

            self._set_status("Completed")

        except Exception as e:
            if not self._stop_event.is_set():
                err_msg = str(e)
                if "İndirme kullanıcı tarafından" in err_msg:
                    self._set_status("Paused")
                else:
                    plat = "TikTok" if is_tiktok_url(self.url) else ("Instagram" if is_instagram_url(self.url) else ("X/Twitter" if is_twitter_url(self.url) else "YouTube/Medya"))
                    friendly_err = format_social_error(e, platform=plat)
                    logger.error(f"Medya indirme hatası ({self.url}): {e}", exc_info=True)
                    self._set_status("Error", friendly_err)
                    notify_error("Medya İndirme Hatası", f"{plat}: {friendly_err}")
            else:
                if self.status != "Cancelled":
                    self._set_status("Paused")

    def _run_subtitle_download(self):
        """Extract and save subtitles as standard .srt format."""
        self._set_status("Probing", "Altyazılar taranıyor...")
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(self.url, download=False)
            if not info:
                raise Exception("Altyazı bilgileri alınamadı.")

            title = info.get("title", "Video")
            clean_title = sanitize_filename(self.filename if self.filename else title)
            subs = info.get("subtitles") or {}
            auto = info.get("automatic_captions") or {}

            # Priority language: tr, en, az, de, fr or first available
            target_lang = None
            target_source = None
            for lang in ["tr", "en", "az", "de", "fr"]:
                if lang in subs:
                    target_lang = lang
                    target_source = subs
                    break
            if not target_lang:
                for lang in ["tr", "en", "az", "de", "fr"]:
                    if lang in auto:
                        target_lang = lang
                        target_source = auto
                        break
            if not target_lang:
                if subs:
                    target_lang = list(subs.keys())[0]
                    target_source = subs
                elif auto:
                    target_lang = list(auto.keys())[0]
                    target_source = auto
                else:
                    raise Exception("Bu video için mevcut altyazı bulunamadı.")

            entries = target_source.get(target_lang, [])
            chosen = None
            for fmt in ["srt", "vtt", "srv1", "srv2", "srv3", "ttml", "json3"]:
                for item in entries:
                    if item.get("ext") == fmt:
                        chosen = item
                        break
                if chosen:
                    break
            if not chosen and entries:
                chosen = entries[0]

            if not chosen or not chosen.get("url"):
                raise Exception("Altyazı akış bağlantısı alınamadı.")

            sub_url = chosen.get("url")
            ext = chosen.get("ext")

            self._set_status("Downloading", "Altyazı indiriliyor...")
            resp = httpx.get(
                sub_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=15.0,
                follow_redirects=True
            )
            raw_content = resp.text

            srt_content = ""
            if ext == "srt" or ("-->" in raw_content and ("\n1\n" in raw_content or raw_content.startswith("1\n"))):
                srt_content = raw_content
            elif ext in ("srv1", "srv2", "srv3", "ttml") or "<transcript>" in raw_content or "<text " in raw_content:
                root = ET.fromstring(raw_content)
                items = []
                idx = 1
                for p in root.findall(".//text"):
                    start = float(p.attrib.get("start", 0.0))
                    dur = float(p.attrib.get("dur", 2.0))
                    end = start + dur
                    text = html.unescape("".join(p.itertext())).strip()
                    if not text:
                        continue
                    def fmt_time(secs):
                        h = int(secs // 3600)
                        m = int((secs % 3600) // 60)
                        s = int(secs % 60)
                        ms = int((secs - int(secs)) * 1000)
                        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
                    items.append(f"{idx}\n{fmt_time(start)} --> {fmt_time(end)}\n{text}\n")
                    idx += 1
                srt_content = "\n".join(items)
            elif "WEBVTT" in raw_content:
                lines = raw_content.splitlines()
                items = []
                idx = 1
                for line in lines:
                    if "-->" in line:
                        line = line.replace(".", ",")
                        tokens = line.split(" ")
                        if len(tokens) >= 3:
                            line = tokens[0] + " --> " + tokens[2]
                        items.append(f"{idx}\n{line}")
                        idx += 1
                    elif line.strip() and not line.startswith("WEBVTT") and not line.startswith("NOTE"):
                        items.append(line.strip())
                srt_content = "\n".join(items)
            else:
                srt_content = raw_content

            self.filename = f"{clean_title}.srt"
            self.save_path = os.path.join(self.save_dir, self.filename)
            with open(to_long_path(self.save_path), "w", encoding="utf-8") as f:
                f.write(srt_content)

            self.total_size = os.path.getsize(to_long_path(self.save_path))
            self.downloaded_size = self.total_size
            if self.on_progress:
                self.on_progress(self.total_size, self.total_size, 0.0, 0)
            self._set_status("Completed")

    def pause(self):
        self._stop_event.set()
        self._set_status("Paused")

    def resume(self):
        if self.status in ("Paused", "Error"):
            self.start()

    def cancel(self, delete_file: bool = False):
        self._stop_event.set()
        self._set_status("Cancelled")
        if delete_file:
            candidates = []
            if self.save_path:
                candidates.extend([self.save_path, f"{self.save_path}.part", f"{self.save_path}.ytdl"])
            if self.save_dir and self.filename:
                base_path = os.path.join(self.save_dir, self.filename)
                candidates.extend([base_path, f"{base_path}.part", f"{base_path}.ytdl"])
            for target in set(candidates):
                if target and os.path.exists(to_long_path(target)):
                    try:
                        os.remove(to_long_path(target))
                    except Exception as e:
                        logger.debug(f"İptal edilen medya dosyası silinemedi ({target}): {e}")

    def set_speed_limit(self, bps: int):
        self.speed_limiter.set_limit(bps)

    def update_url(self, new_url: str, new_headers: Optional[Dict[str, str]] = None):
        """Updates target URL for refresh and resets error state."""
        self.url = new_url
        if new_headers is not None:
            self.headers = new_headers
        if self.status == "Error":
            self.status = "Paused"
            self.error_message = ""

