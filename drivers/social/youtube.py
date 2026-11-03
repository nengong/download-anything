"""
YouTube Video / Shorts / Audio Extractor Driver
Powered by yt-dlp metadata engine, conforming to DA micro-asset specifications.
"""
import re
from typing import Optional, Dict, Any, List
from drivers.base import BaseDriver, AssetPackage, AssetFile
from core.exceptions import ExtractionError

class YouTubeDriver(BaseDriver):
    """Driver for extracting YouTube videos, shorts, high-res thumbnails and subtitles."""

    YOUTUBE_URL_REGEX = re.compile(
        r"(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/(?:watch\?v=|shorts/|v/|embed/)|youtu\.be/)([a-zA-Z0-9_-]{11})"
    )

    def can_handle(self, url: str) -> bool:
        return bool(self.YOUTUBE_URL_REGEX.search(url))

    def extract(self, url: str, password: Optional[str] = None, **kwargs) -> AssetPackage:
        m = self.YOUTUBE_URL_REGEX.search(url)
        if not m:
            raise ExtractionError(f"Invalid YouTube URL: {url}")
        video_id = m.group(1)
        canonical_url = f"https://www.youtube.com/watch?v={video_id}"

        try:
            import yt_dlp
        except ImportError:
            raise ExtractionError("yt-dlp package is required for YouTube extraction. Install with `uv pip install yt-dlp`.")

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(canonical_url, download=False)
        except Exception as e:
            raise ExtractionError(f"Failed to extract YouTube video metadata: {e}")

        if not info:
            raise ExtractionError("Empty response received from YouTube.")

        title = info.get("title") or f"youtube_{video_id}"
        description = info.get("description") or ""
        uploader = info.get("uploader") or info.get("channel") or "Unknown Creator"
        thumbnail_url = info.get("thumbnail")
        duration = info.get("duration")

        # Select best progressive MP4 stream under 500MB
        formats = info.get("formats", [])
        chosen_format = None

        # 1. Prefer formats that have both audio and video (progressive MP4)
        progressive_mp4s = [
            f for f in formats 
            if f.get("vcodec") != "none" and f.get("acodec") != "none" and f.get("ext") == "mp4"
        ]
        if progressive_mp4s:
            # Sort by height / bitrate descending
            progressive_mp4s.sort(key=lambda x: (x.get("height") or 0, x.get("tbr") or 0), reverse=True)
            for f in progressive_mp4s:
                size = f.get("filesize") or f.get("filesize_approx") or 0
                if size <= 500 * 1024 * 1024:
                    chosen_format = f
                    break

        # 2. Fallback to best available video format
        if not chosen_format and formats:
            video_formats = [f for f in formats if f.get("vcodec") != "none"]
            video_formats.sort(key=lambda x: (x.get("height") or 0, x.get("tbr") or 0), reverse=True)
            for f in video_formats:
                size = f.get("filesize") or f.get("filesize_approx") or 0
                if size <= 500 * 1024 * 1024 and f.get("url"):
                    chosen_format = f
                    break

        if not chosen_format and formats:
            chosen_format = formats[-1]

        if not chosen_format or not chosen_format.get("url"):
            raise ExtractionError("Could not resolve downloadable stream URL for YouTube video.")

        primary_url = chosen_format["url"]
        expected_size = chosen_format.get("filesize") or chosen_format.get("filesize_approx")
        ext = chosen_format.get("ext") or "mp4"

        assets = [
            AssetFile(
                filename=f"content.{ext}",
                url=primary_url,
                file_type="primary",
                expected_size=expected_size,
                headers={"User-Agent": "Mozilla/5.0"}
            )
        ]

        # Companion Cover
        if thumbnail_url:
            assets.append(
                AssetFile(
                    filename="cover.jpg",
                    url=thumbnail_url,
                    file_type="cover",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
            )

        # Companion Subtitles
        subtitles = info.get("subtitles", {}) or info.get("automatic_captions", {})
        sub_url = None
        for lang in ("zh-Hans", "zh-Hant", "zh", "en"):
            if lang in subtitles and subtitles[lang]:
                for s_entry in subtitles[lang]:
                    if s_entry.get("ext") in ("vtt", "srt"):
                        sub_url = s_entry.get("url")
                        break
            if sub_url:
                break

        if sub_url:
            assets.append(
                AssetFile(
                    filename="subtitle.vtt",
                    url=sub_url,
                    file_type="subtitle",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
            )

        metadata = {
            "title": title,
            "original_url": canonical_url,
            "author": {
                "id": info.get("channel_id") or "",
                "name": uploader,
            },
            "created_at": info.get("upload_date") or "",
            "metrics": {
                "views": info.get("view_count") or 0,
                "likes": info.get("like_count") or 0,
                "duration_seconds": duration or 0,
            },
            "sidecar_text": description,
        }

        return AssetPackage(
            platform="youtube",
            title=title,
            original_url=canonical_url,
            assets=assets,
            metadata=metadata
        )
