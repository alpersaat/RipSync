import re
import json
import logging
import urllib.parse
import httpx
from typing import Dict, Any, Optional, List, Callable

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

def is_twitter_url(url: str) -> bool:
    """Check if URL belongs to Twitter / X post or video."""
    u_lower = url.lower()
    if any(domain in u_lower for domain in ("twitter.com", "x.com", "t.co")):
        return "/status/" in u_lower or "/i/status/" in u_lower
    return False

def sanitize_title(title: str) -> str:
    """Clean title of invalid characters and emojis for filesystem safety."""
    if not title:
        return "video"
    cleaned = re.sub(r'[\\/*?:"<>|\uff5c\x00-\x1f]', '_', title)
    cleaned = cleaned.strip(" .")
    if len(cleaned) > 100:
        cleaned = cleaned[:100].strip(" .")
    return cleaned or "video"

def format_social_error(err: Any, platform: str = "") -> str:
    """
    Transforms low-level technical errors from yt-dlp, parth-dl, or HTTP APIs into
    clear, user-friendly Turkish guidance with actionable next steps.
    """
    raw_str = str(err)
    raw_lower = raw_str.lower()

    # 1. Bot verification / Sign in required / Rate limit
    if any(k in raw_lower for k in [
        "not a bot", "bot verification", "sign in to confirm",
        "confirm you're not a bot", "login required", "rate-limit",
        "http error 429", "too many requests"
    ]):
        return (
            "🛡️ Platform Bot/Oturum Koruması: İlgili platform otomatik indirme isteklerini sınırladı veya "
            "oturum doğrulama talep ediyor. Sayfa yapısı değişmiş veya geçici engel konmuş olabilir. "
            "Çözüm: Tarayıcınızda videonun doğrudan akış (.mp4) bağlantısını kopyalayıp 'Manuel Link Gir' seçeneğiyle indirebilirsiniz."
        )

    # 2. Private, age-restricted or removed video
    if any(k in raw_lower for k in [
        "private video", "sign in if you've been granted", "video unavailable",
        "has been removed", "this video is private", "not found", "content is not available"
    ]):
        return (
            "🔒 Video Gizli veya Kaldırılmış: Bu video içerik üreticisi tarafından silinmiş, gizliye alınmış veya "
            "özel hesapla sınırlandırılmış. Erişebiliyorsanız tarayıcıdan doğrudan video akış bağlantısını manuel olarak giriniz."
        )

    # 3. HTTP 403 Forbidden / Expired temporary token
    if any(k in raw_lower for k in ["http error 403", "403: forbidden", "forbidden", "http error 401"]):
        return (
            "⏱️ Erişim Engeli veya Bağlantı Süresi Doldu (HTTP 403): Medya sunucusu geçici indirme anahtarını geçersiz kıldı. "
            "Çözüm: Tarayıcınızdan videoyu yenileyip yeni video akış adresini kopyalayarak 'Manuel Link Gir' seçeneğini kullanın."
        )

    # 4. Extractor or DOM structure changed
    if any(k in raw_lower for k in [
        "unable to extract", "signature extraction", "regex", "extractorerror",
        "jsplayer", "n challenge", "player response", "unsupported url"
    ]):
        plat_txt = f" ({platform})" if platform else ""
        return (
            f"⚠️ Sayfa Yapısı Değişti{plat_txt}: Sosyal medya platformu arayüzünü güncellediği için otomatik çözümleme yapılamadı. "
            "Çözüm: Tarayıcınızdan video akış adresini kopyalayarak 'Manuel Link Gir' seçeneği ile doğrudan indirebilirsiniz."
        )

    # 5. Format / Quality not found
    if "requested format is not available" in raw_lower:
        return (
            "🎞️ İstenen Format Bulunamadı: Seçtiğiniz çözünürlük veya ses formatı bu medyada bulunmuyor. "
            "Çözüm: Kalite ayarını 'En Yüksek Kalite' veya farklı bir seçeneğe getirip tekrar deneyin."
        )

    # 6. Network timeout / disconnect
    if any(k in raw_lower for k in [
        "timed out", "timeout", "connection reset", "remotedisconnected",
        "network is unreachable", "connection error"
    ]):
        return (
            "🌐 Ağ Bağlantısı Zaman Aşımı: Medya sunucusuna bağlanırken kesinti oluştu. "
            "İnternet bağlantınızı kontrol edip tekrar deneyin veya alternatif link girin."
        )

    # 7. Third-party API failure fallback
    if "tikwm" in raw_lower:
        return (
            "⚠️ TikWM API Hizmet Dışı: Üçüncü parti TikTok çözümleyicisine ulaşılamadı ve alternatif akış bulunamadı. "
            "Lütfen videoyu tarayıcıdan açarak video akış bağlantısını 'Manuel Link Gir' ile yapıştırın."
        )

    # Clean generic fallback
    clean_err = raw_str.replace("ERROR: ", "").strip()
    if len(clean_err) > 120:
        clean_err = clean_err[:117] + "..."
    return (
        f"⚠️ Medya İndirme Hatası ({clean_err}). "
        "Platform sayfa yapısını değiştirmiş olabilir. 'Manuel Link Gir' seçeneğiyle doğrudan video bağlantısını yapıştırıp indirmeyi sürdürebilirsiniz."
    )

class SocialResolver:
    """
    Dedicated resolver for extracting watermark-free video and audio streams
    from TikTok and Instagram (Reels & Posts).
    """

    @classmethod
    def resolve_tiktok(cls, url: str, warning_callback: Optional[Callable[[str], None]] = None) -> Optional[Dict[str, Any]]:
        """
        Extract 100% watermark-free (filigransız) video from TikTok.
        Tries TikWM API first (fastest, unwatermarked HD). If TikWM is unreachable, down,
        or rate-limited, gives a clear user-facing warning and automatically falls back to yt-dlp.
        """
        fallback_warning = None

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
                else:
                    err_code = data.get("msg") or data.get("code")
                    fallback_warning = f"⚠️ TikWM API yanıt vermedi ({err_code}). yt-dlp yedek motoruna otomatik geçiliyor..."
            else:
                fallback_warning = f"⚠️ TikWM API erişilemedi (HTTP {resp.status_code}). yt-dlp yedek motoruna otomatik geçiliyor..."
        except Exception as e:
            fallback_warning = f"⚠️ TikWM API servisine erişilemedi ({type(e).__name__}). yt-dlp yedek motoruna otomatik geçiliyor..."
            logger.warning(f"TikWM resolver failed for {url}: {e}")

        if not fallback_warning:
            fallback_warning = "⚠️ TikWM filigransız bağlantı sağlayamadı. yt-dlp yedek motoruna otomatik geçiliyor..."

        logger.info(fallback_warning)
        if warning_callback:
            try:
                warning_callback(fallback_warning)
            except Exception:
                pass

        # 2. Try yt-dlp with strict watermark-free format filtering (Automatic Fallback)
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
                            "source": "yt-dlp",
                            "warning": fallback_warning,
                            "fallback": True
                        }
        except Exception as e:
            logger.warning(f"yt-dlp TikTok fallback failed: {e}")

        return None

    @classmethod
    def resolve_instagram(cls, url: str, cookies: Optional[str] = None, warning_callback: Optional[Callable[[str], None]] = None) -> Optional[Dict[str, Any]]:
        """
        Extract original watermark-free video from Instagram Reels & Posts.
        Tries parth-dl (GraphQL/Polaris/Embed anonymous extractor) first.
        If parth-dl fails, is not installed, or page structure changed,
        gives a clear warning and automatically falls back to yt-dlp with cookies.
        """
        fallback_warning = None

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
            fallback_warning = "⚠️ Instagram parth-dl çözümleyicisi akış bulamadı. yt-dlp yedek motoruna geçiliyor..."
        except ImportError:
            fallback_warning = "⚠️ parth-dl kütüphanesi bulunamadı (pip install parth-dl). yt-dlp yedek motoruna geçiliyor..."
            logger.warning(fallback_warning)
        except Exception as e:
            fallback_warning = f"⚠️ Instagram parth-dl çözümleyicisi hata verdi ({type(e).__name__}). yt-dlp yedek motoruna geçiliyor..."
            logger.warning(f"parth-dl extraction failed for {url}: {e}")

        if warning_callback and fallback_warning:
            try:
                warning_callback(fallback_warning)
            except Exception:
                pass

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
                        "source": "yt-dlp",
                        "warning": fallback_warning,
                        "fallback": True
                    }
        except Exception as e:
            logger.warning(f"yt-dlp Instagram extraction failed: {e}")

        return None

    @classmethod
    def resolve_twitter(cls, url: str) -> Optional[Dict[str, Any]]:
        """
        Extract direct MP4 video from Twitter / X tweet.
        Uses yt-dlp format selection to pick the highest resolution MP4 stream.
        """
        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "http_headers": {"User-Agent": DEFAULT_UA},
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    chosen_url = None
                    if "requested_formats" in info:
                        for rf in info["requested_formats"]:
                            if rf.get("vcodec") != "none":
                                chosen_url = rf.get("url")
                                break
                    if not chosen_url:
                        chosen_url = info.get("url")

                    if chosen_url:
                        raw_title = info.get("title") or info.get("description") or "Twitter_Video"
                        return {
                            "title": sanitize_title(raw_title),
                            "video_url": chosen_url,
                            "thumbnail": info.get("thumbnail"),
                            "duration": info.get("duration", 0),
                            "is_watermark_free": True,
                            "platform": "Twitter/X",
                            "source": "yt-dlp"
                        }
        except Exception as e:
            logger.warning(f"yt-dlp Twitter/X extraction failed for {url}: {e}")

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
