import hashlib
import re
import urllib.parse
from typing import Dict, Any, Optional
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from core.privacy import is_sensitive_text

DOWNLOADABLE_EXTENSIONS = (
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso", ".dmg",
    ".exe", ".msi", ".apk", ".appimage", ".deb", ".rpm", ".bin",
    ".mp4", ".mkv", ".avi", ".webm", ".mov", ".ts", ".m4v", ".flv",
    ".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".wma",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".epub"
)

VIDEO_PLATFORM_MAP = {
    "youtube.com": ("YouTube", "▶️"),
    "youtu.be": ("YouTube", "▶️"),
    "twitter.com": ("X (Twitter)", "𝕏"),
    "x.com": ("X (Twitter)", "𝕏"),
    "tiktok.com": ("TikTok", "🎵"),
    "tiktokv.com": ("TikTok", "🎵"),
    "vt.tiktok.com": ("TikTok", "🎵"),
    "vm.tiktok.com": ("TikTok", "🎵"),
    "instagram.com": ("Instagram", "📸"),
    "instagr.am": ("Instagram", "📸"),
    "facebook.com": ("Facebook", "👥"),
    "fb.watch": ("Facebook", "👥"),
    "vimeo.com": ("Vimeo", "🎬"),
    "dailymotion.com": ("Dailymotion", "📺"),
    "reddit.com": ("Reddit", "💬"),
    "twitch.tv": ("Twitch", "🎮"),
    "threads.net": ("Threads", "🧵"),
    "pinterest.com": ("Pinterest", "📌"),
    "soundcloud.com": ("SoundCloud", "🎧")
}


# Ignore list to prevent false positives when browsing or copying internal links
IGNORED_DOMAINS = (
    "google.com/search", "bing.com/search", "yandex.com/search", "duckduckgo.com",
    "localhost", "127.0.0.1"
)

class ClipboardMonitor(QObject):
    """
    Monitors system clipboard for downloadable media or file URLs.
    Emits detected link with metadata (service name, icon, is_video, etc.).
    Supports privacy protection, smart exclusion domains, and only-media filtering.
    """
    # Emits (url, info_dict)
    link_detected = pyqtSignal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.enabled = False  # Privacy by default: disabled until explicitly turned on or consented
        self.only_media = False
        self.ignore_domains = list(IGNORED_DOMAINS)
        self.last_text = ""
        self.last_hash = ""  # SHA-256 hash representation to avoid storing sensitive strings in RAM
        self.clipboard = QApplication.clipboard()
        if self.clipboard:
            self.clipboard.dataChanged.connect(self._on_clipboard_change)

    def set_enabled(self, val: bool):
        self.enabled = val

    def configure(self, enabled: bool = False, only_media: bool = False, ignore_domains: Optional[list] = None):
        """Configure clipboard monitoring rules."""
        self.enabled = enabled
        self.only_media = only_media
        if ignore_domains is not None:
            self.ignore_domains = list(ignore_domains)

    def _on_clipboard_change(self):
        if not self.enabled or not self.clipboard:
            return

        try:
            text = self.clipboard.text().strip()
        except Exception:
            return

        if not text:
            return

        # Privacy hash check: avoid processing same clipboard content repeatedly
        try:
            cur_hash = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]
        except Exception:
            cur_hash = ""

        if cur_hash and cur_hash == self.last_hash:
            return

        self.last_hash = cur_hash

        # Strictly check if text looks like a URL
        if not (text.startswith("http://") or text.startswith("https://")):
            # Clear last_text so non-URL strings (e.g. copied passwords, notes) are NEVER kept in memory
            self.last_text = ""
            return

        # Sensitive content detection (passwords, auth tokens, credit cards, credentials)
        if is_sensitive_text(text):
            # Immediately discard sensitive data without storing in memory or emitting
            self.last_text = ""
            return

        self.last_text = text

        info = self.analyze_url(text, ignore_domains=self.ignore_domains, only_media=self.only_media)
        if info:
            self.link_detected.emit(text, info)

    @classmethod
    def analyze_url(cls, url: str, ignore_domains: Optional[list] = None, only_media: bool = False) -> Optional[Dict[str, Any]]:
        """
        Analyze whether a URL is a downloadable file or video link.
        Returns metadata dict if valid, None otherwise.
        """
        if not (url.startswith("http://") or url.startswith("https://")):
            return None

        # Privacy check: Ignore if URL contains sensitive patterns (passwords, tokens, keys)
        if is_sensitive_text(url):
            return None

        # Check ignore list
        u_lower = url.lower()
        effective_ignores = set(IGNORED_DOMAINS)
        if ignore_domains:
            for item in ignore_domains:
                if item and item.strip():
                    effective_ignores.add(item.strip().lower())

        if any(ign in u_lower for ign in effective_ignores):
            return None

        try:
            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
        except Exception:
            return None

        # 1. Check video platforms
        for plat_domain, (name, icon) in VIDEO_PLATFORM_MAP.items():
            if plat_domain in domain or domain.endswith("." + plat_domain):
                # Filter out channel / general root links if not actual media content
                path = parsed.path.strip("/")
                if not path and not parsed.query:
                    # Just the homepage like https://youtube.com
                    return None

                # Check if this is a YouTube playlist link
                qs = urllib.parse.parse_qs(parsed.query)
                is_playlist = False
                if plat_domain in ("youtube.com", "youtu.be"):
                    if ("list" in qs and qs["list"] and qs["list"][0]) or ("/playlist" in path.lower()):
                        is_playlist = True

                if is_playlist:
                    return {
                        "is_video": True,
                        "is_playlist": True,
                        "service": "YouTube Oynatma Listesi",
                        "icon": "📑",
                        "filename": "YouTube_Playlist"
                    }

                if plat_domain in ("tiktok.com", "tiktokv.com", "vt.tiktok.com", "vm.tiktok.com"):
                    return {
                        "is_video": True,
                        "is_playlist": False,
                        "watermark_free": True,
                        "service": "TikTok (Filigransız)",
                        "icon": "🎵",
                        "filename": "TikTok_Video"
                    }

                if plat_domain in ("instagram.com", "instagr.am"):
                    clean_p = parsed.path.lower()
                    is_reel = ("/reel/" in clean_p or "/reels/" in clean_p or clean_p.startswith("/reel"))
                    svc_title = "Instagram Reels (Filigransız)" if is_reel else "Instagram (Filigransız)"
                    fname = "Instagram_Reels" if is_reel else "Instagram_Video"

                    return {
                        "is_video": True,
                        "is_playlist": False,
                        "watermark_free": True,
                        "service": svc_title,
                        "icon": "📸",
                        "filename": fname
                    }

                if plat_domain in ("twitter.com", "x.com"):
                    clean_p = parsed.path.lower()
                    if "/status/" in clean_p or "/i/status/" in clean_p:
                        return {
                            "is_video": True,
                            "is_playlist": False,
                            "service": "X (Twitter)",
                            "icon": "𝕏",
                            "filename": "Twitter_Video"
                        }

                return {
                    "is_video": True,
                    "is_playlist": False,
                    "service": name,
                    "icon": icon,
                    "filename": f"{name}_Video"
                }


        # 2. Check stream direct playlist links (.m3u8, .mpd)
        clean_path = parsed.path.lower()
        if clean_path.endswith(".m3u8") or clean_path.endswith(".mpd"):
            return {
                "is_video": True,
                "service": "HLS/DASH Stream",
                "icon": "📺",
                "filename": "stream.mp4"
            }

        # 3. Check downloadable extensions
        MEDIA_EXTENSIONS = (
            ".mp4", ".mkv", ".avi", ".webm", ".mov", ".ts", ".m4v", ".flv",
            ".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".wma"
        )
        for ext in DOWNLOADABLE_EXTENSIONS:
            if clean_path.endswith(ext):
                if only_media and ext not in MEDIA_EXTENSIONS:
                    return None

                # Extract filename
                raw_name = clean_path.split("/")[-1]
                try:
                    raw_name = urllib.parse.unquote(raw_name)
                except Exception:
                    pass

                icon = "📦"
                if ext in (".mp4", ".mkv", ".avi", ".webm", ".mov", ".ts"):
                    icon = "🎬"
                elif ext in (".mp3", ".flac", ".wav", ".m4a", ".aac"):
                    icon = "🎵"
                elif ext in (".exe", ".msi", ".apk", ".deb"):
                    icon = "💻"
                elif ext in (".pdf", ".docx", ".xlsx", ".zip", ".rar", ".7z", ".iso"):
                    icon = "📄" if ext.endswith(("pdf", "doc", "docx", "xls")) else "🗜️"

                return {
                    "is_video": ext in (".mp4", ".mkv", ".avi", ".webm", ".mov", ".ts"),
                    "service": "Dosya",
                    "icon": icon,
                    "filename": raw_name or "download"
                }

        return None
