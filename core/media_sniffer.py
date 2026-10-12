import subprocess
import json
import shutil
from typing import Dict, Any, List, Optional
from core.social_resolver import SocialResolver, is_tiktok_url, is_instagram_url

class MediaSniffer:
    """
    Extracts stream information and formats for media sites using yt-dlp & SocialResolver.
    """
    @staticmethod
    def is_ytdlp_available() -> bool:
        try:
            import yt_dlp
            return True
        except ImportError:
            return False

    @staticmethod
    def extract_info(url: str) -> Optional[Dict[str, Any]]:
        # Fast path for TikTok and Instagram watermark-free resolution
        if is_tiktok_url(url):
            resolved = SocialResolver.resolve_tiktok(url)
            if resolved:
                return {
                    'title': resolved['title'],
                    'ext': 'mp4',
                    'duration': resolved.get('duration', 0),
                    'thumbnail': resolved.get('thumbnail', ''),
                    'formats': [{
                        'format_id': 'watermark_free_hd',
                        'resolution': 'HD (Filigransız)',
                        'ext': 'mp4',
                        'filesize': 0,
                        'url': resolved['video_url'],
                        'note': 'Filigransız (Watermark-Free)',
                        'has_video': True,
                        'has_audio': True
                    }],
                    'url': url
                }

        if is_instagram_url(url):
            resolved = SocialResolver.resolve_instagram(url)
            if resolved:
                return {
                    'title': resolved['title'],
                    'ext': 'mp4',
                    'duration': resolved.get('duration', 0),
                    'thumbnail': resolved.get('thumbnail', ''),
                    'formats': [{
                        'format_id': 'watermark_free_hd',
                        'resolution': 'HD (Filigransız)',
                        'ext': 'mp4',
                        'filesize': 0,
                        'url': resolved['video_url'],
                        'note': 'Filigransız (Watermark-Free)',
                        'has_video': True,
                        'has_audio': True
                    }],
                    'url': url
                }

        try:
            import yt_dlp
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'extract_flat': False
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return None

                title = info.get('title', 'Video')
                ext = info.get('ext', 'mp4')
                duration = info.get('duration', 0)
                thumbnail = info.get('thumbnail', '')

                # Parse available formats
                formats = []
                raw_formats = info.get('formats', [])
                for fmt in raw_formats:
                    # Pick formats with video or useful audio
                    fmt_id = fmt.get('format_id')
                    res = fmt.get('resolution') or f"{fmt.get('width', '')}x{fmt.get('height', '')}"
                    filesize = fmt.get('filesize') or fmt.get('filesize_approx') or 0
                    vcodec = fmt.get('vcodec', 'none')
                    acodec = fmt.get('acodec', 'none')
                    note = fmt.get('format_note', '')

                    if vcodec != 'none' or acodec != 'none':
                        formats.append({
                            'format_id': fmt_id,
                            'resolution': res if res.strip('x') else (note or 'Audio'),
                            'ext': fmt.get('ext', 'mp4'),
                            'filesize': filesize,
                            'url': fmt.get('url', ''),
                            'note': note,
                            'has_video': vcodec != 'none',
                            'has_audio': acodec != 'none'
                        })

                return {
                    'title': title,
                    'ext': ext,
                    'duration': duration,
                    'thumbnail': thumbnail,
                    'formats': formats,
                    'url': url
                }
        except Exception as e:
            return None
