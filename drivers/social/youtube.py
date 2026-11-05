"""
YouTube Video / Shorts / Audio Extractor Driver
Powered by yt-dlp metadata engine, conforming to DA micro-asset specifications.
"""
import re
from typing import Optional
from drivers.base import AssetPackage, AssetFile
from drivers.social.ytdlp_fallback import YtDlpFallbackDriver
from core.exceptions import ExtractionError

class YouTubeDriver(YtDlpFallbackDriver):
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
            "noplaylist": True,
            "socket_timeout": 15,
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

        # Let yt-dlp select, download and merge tracks rather than fetching a
        # single resolved URL (which may contain video without audio).
        formats = [f for f in (info.get("formats") or []) if f.get("url")]
        if not formats and not info.get("url"):
            raise ExtractionError("Could not resolve downloadable stream URL for YouTube video.")

        audio_only = bool(kwargs.get("audio_only", False))
        ext = self._native_audio_ext(info) if audio_only else "mp4"
        download_options = {
            "source_url": canonical_url,
            "format": "ba/b" if audio_only else "bv*+ba/b",
        }
        if not audio_only:
            download_options["merge_output_format"] = "mp4"

        assets = [
            AssetFile(
                filename=f"content.{ext}",
                url=canonical_url,
                file_type="primary",
                expected_size=None,
                headers={"User-Agent": "Mozilla/5.0"},
                download_strategy="ytdlp",
                download_options=download_options,
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
