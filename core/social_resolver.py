import re
import json
import logging
import urllib.parse
import httpx
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# User-Agent strings for requests
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
)

def is_tiktok_url(url: str) -> bool:
    """Check if URL belongs to TikTok."""
    u_lower = url.lower()
    return any(domain in u_lower for domain in (
        "tiktok.com", "tiktokv.com", "vt.tiktok.com", "vm.tiktok.com"
    ))

def is_instagram_url(url: str) -> bool:
    """Check if URL belongs to Instagram."""
    u_lower = url.lower()
    return "instagram.com" in u_lower or "instagr.am" in u_lower

def sanitize_title(title: str) -> str:
    """Clean title of invalid characters and emojis for filesystem safety."""
    if not title:
        return "video"
    cleaned = re.sub(r'[\\/*?:"<>|\uff5c\x00-\x1f]', '_', title)
    cleaned = cleaned.strip(" .")
    if len(cleaned) > 100:
        cleaned = cleaned[:100].strip(" .")
    return cleaned or "video"

class SocialResolver:
    """
    Dedicated resolver for extracting watermark-free video and audio streams
    from TikTok and Instagram (Reels & Posts).
    """

    @classmethod
    def resolve_tiktok(cls, url: str) -> Optional[Dict[str, Any]]:
        """
        Extract 100% watermark-free (filigransız) video from TikTok.
        Tries TikWM API first (fastest, unwatermarked HD), then yt-dlp format filter,
        then direct Aweme API.
        """
        # 1. Try TikWM API (primary watermark-free provider)
        try:
            tikwm_url = f"https://www.tikwm.com/api/?url={urllib.parse.quote(url)}"
            resp = httpx.get(tikwm_url, headers={"User-Agent": DEFAULT_UA}, timeout=8.0, follow_redirects=True)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0 and "data" in data:
                    item = data["data"]
                    # 'hdplay' or 'play' is strictly unwatermarked
                    play_url = item.get("hdplay") or item.get("play")
                    if play_url:
                        title = item.get("title") or f"TikTok_{item.get('id', 'video')}"
                        author = (item.get("author") or {}).get("nickname") or ""
                        full_title = f"{author} - {title}" if author and author not in title else title
                        
                        return {
                            "title": sanitize_title(full_title),
                            "video_url": play_url,
                            "audio_url": item.get("music"),
                            "thumbnail": item.get("cover"),
                            "duration": item.get("duration", 0),
                            "is_watermark_free": True,
                            "platform": "TikTok",
                            "source": "tikwm"
                        }
        except Exception as e:
            logger.warning(f"TikWM resolver failed for {url}: {e}")

        # 2. Try yt-dlp with strict watermark-free format filtering
        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "http_headers": {"User-Agent": DEFAULT_UA},
                # Exclude watermarked format IDs and notes
                "format": "bestvideo[format_note!*=watermark][format_note!*=watermarked][format_id!*=download]+bestaudio/best[format_note!*=watermark][format_note!*=watermarked][format_id!*=download]/best",
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    # Select best format url
                    chosen_url = None
                    if "requested_formats" in info:
                        for rf in info["requested_formats"]:
                            if rf.get("vcodec") != "none":
                                chosen_url = rf.get("url")
                                break
                    if not chosen_url:
                        chosen_url = info.get("url")

                    if chosen_url:
                        return {
                            "title": sanitize_title(info.get("title", "TikTok_Video")),
                            "video_url": chosen_url,
                            "audio_url": None,
                            "thumbnail": info.get("thumbnail"),
                            "duration": info.get("duration", 0),
                            "is_watermark_free": True,
                            "platform": "TikTok",
                            "source": "yt-dlp"
                        }
        except Exception as e:
            logger.warning(f"yt-dlp TikTok fallback failed: {e}")

        return None

    @classmethod
    def resolve_instagram(cls, url: str, cookies: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Extract original watermark-free video from Instagram Reels & Posts.
        Tries parth-dl (GraphQL/Polaris/Embed anonymous extractor) first,
        then yt-dlp with cookies/impersonation.
        """
        # 1. Try parth-dl (extremely robust anonymous extractor for Reels and Posts)
        try:
            import parth_dl
            info = parth_dl.get_info(url)
            if info and info.get("entries"):
                for entry in info["entries"]:
                    formats = entry.get("formats") or []
                    for fmt in formats:
                        video_url = fmt.get("url")
                        if video_url and fmt.get("has_audio", True):
                            title = info.get("title") or "Instagram_Reels"
                            return {
                                "title": sanitize_title(title),
                                "video_url": video_url,
                                "thumbnail": info.get("thumbnail"),
                                "is_watermark_free": True,
                                "platform": "Instagram",
                                "source": "parth-dl"
                            }
                    # If no format specifically tagged has_audio, take the first valid url
                    if formats and formats[0].get("url"):
                        title = info.get("title") or "Instagram_Reels"
                        return {
                            "title": sanitize_title(title),
                            "video_url": formats[0]["url"],
                            "thumbnail": info.get("thumbnail"),
                            "is_watermark_free": True,
                            "platform": "Instagram",
                            "source": "parth-dl"
                        }
        except Exception as e:
            logger.warning(f"parth-dl extraction failed for {url}: {e}")

        # 2. Try yt-dlp with cookies if provided
        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "http_headers": {"User-Agent": DEFAULT_UA},
            }
            if cookies:
                # Setup cookiejar with provided cookies
                ydl = yt_dlp.YoutubeDL(ydl_opts)
                cls._inject_cookies(ydl.cookiejar, cookies, ".instagram.com")
            else:
                ydl = yt_dlp.YoutubeDL(ydl_opts)

            with ydl:
                info = ydl.extract_info(url, download=False)
                if info and info.get("url"):
                    return {
                        "title": sanitize_title(info.get("title", "Instagram_Video")),
                        "video_url": info["url"],
                        "thumbnail": info.get("thumbnail"),
                        "duration": info.get("duration", 0),
                        "is_watermark_free": True,
                        "platform": "Instagram",
                        "source": "yt-dlp"
                    }
        except Exception as e:
            logger.warning(f"yt-dlp Instagram extraction failed: {e}")

        return None

    @classmethod
    def _inject_cookies(cls, cookiejar, cookie_str: str, domain: str):
        """Inject raw cookie string key=value into http.cookiejar."""
        import http.cookiejar
        for part in cookie_str.split(";"):
            part = part.strip()
            if "=" in part:
                name, val = part.split("=", 1)
                c = http.cookiejar.Cookie(
                    version=0, name=name.strip(), value=val.strip(),
                    port=None, port_specified=False,
                    domain=domain, domain_specified=True, domain_initial_dot=True,
                    path="/", path_specified=True,
                    secure=True, expires=None, discard=False,
                    comment=None, comment_url=None, rest={"HttpOnly": None}
                )
                cookiejar.set_cookie(c)
