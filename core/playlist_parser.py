import os
import re
import urllib.parse
from typing import Dict, Any, List, Optional
import yt_dlp

def is_youtube_playlist_url(url: str) -> bool:
    """
    Check if a given URL is a YouTube playlist link or video URL containing a playlist parameter.
    """
    if not url:
        return False
    u = url.strip()
    try:
        parsed = urllib.parse.urlparse(u)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if domain not in ("youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"):
            return False

        qs = urllib.parse.parse_qs(parsed.query)
        if "list" in qs and qs["list"] and qs["list"][0]:
            return True
        if "/playlist" in parsed.path.lower():
            return True
        return False
    except Exception:
        return False

def normalize_playlist_url(url: str) -> str:
    """
    Normalizes watch/video URLs with ?list=... into canonical playlist URLs
    to ensure yt-dlp fetches the entire playlist cleanly.
    """
    if not url:
        return url
    u = url.strip()
    try:
        parsed = urllib.parse.urlparse(u)
        qs = urllib.parse.parse_qs(parsed.query)
        if "list" in qs and qs["list"] and qs["list"][0]:
            playlist_id = qs["list"][0]
            return f"https://www.youtube.com/playlist?list={playlist_id}"
        return u
    except Exception:
        return url

def fetch_playlist_metadata(url: str) -> Dict[str, Any]:
    """
    Extracts metadata and all video items from a YouTube playlist URL.
    Returns:
    {
        "id": playlist_id,
        "title": playlist_title,
        "uploader": channel_or_uploader,
        "count": total_video_count,
        "url": canonical_url,
        "entries": [
            {
                "index": 1,
                "id": video_id,
                "title": video_title,
                "url": video_watch_url,
                "duration": duration_seconds,
                "duration_str": "MM:SS",
                "thumbnail": thumbnail_url,
                "uploader": uploader_name,
                "view_count": view_count
            },
            ...
        ]
    }
    """
    canonical_url = normalize_playlist_url(url)
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        }
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        res = ydl.extract_info(canonical_url, download=False, process=False)
        if not res:
            raise Exception("Çalma listesi bilgisi alınamadı.")

        title = res.get("title") or "YouTube Çalma Listesi"
        uploader = res.get("uploader") or res.get("channel") or ""
        playlist_id = res.get("id") or ""

        raw_entries = res.get("entries") or []
        entries: List[Dict[str, Any]] = []

        for idx, item in enumerate(raw_entries, 1):
            if not item:
                continue

            v_id = item.get("id") or ""
            v_title = item.get("title") or f"Video #{idx}"
            v_url = item.get("url")
            if not v_url and v_id:
                v_url = f"https://www.youtube.com/watch?v={v_id}"
            elif v_url and not v_url.startswith("http"):
                v_url = f"https://www.youtube.com/watch?v={v_url}"

            dur = item.get("duration")
            dur_str = "--:--"
            if dur is not None and isinstance(dur, (int, float)) and dur > 0:
                mins = int(dur // 60)
                secs = int(dur % 60)
                if mins >= 60:
                    hrs = int(mins // 60)
                    mins = int(mins % 60)
                    dur_str = f"{hrs}:{mins:02d}:{secs:02d}"
                else:
                    dur_str = f"{mins:02d}:{secs:02d}"

            # Best thumbnail URL
            thumb_url = ""
            thumbnails = item.get("thumbnails")
            if thumbnails and isinstance(thumbnails, list):
                # Pick the thumbnail with a valid url
                for t in reversed(thumbnails):
                    if isinstance(t, dict) and t.get("url"):
                        thumb_url = t.get("url")
                        break
            if not thumb_url and v_id:
                thumb_url = f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg"

            entries.append({
                "index": idx,
                "id": v_id,
                "title": v_title,
                "url": v_url,
                "duration": dur or 0,
                "duration_str": dur_str,
                "thumbnail": thumb_url,
                "uploader": item.get("uploader") or uploader,
                "view_count": item.get("view_count") or 0
            })

        return {
            "id": playlist_id,
            "title": title,
            "uploader": uploader,
            "count": len(entries),
            "url": canonical_url,
            "entries": entries
        }
