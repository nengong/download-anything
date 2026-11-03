"""
Instagram Post, Reels, and Carousel Extractor Driver
"""
import re
from typing import Optional, Dict, Any, List
from drivers.base import BaseDriver, AssetPackage, AssetFile
from core.exceptions import ExtractionError

class InstagramDriver(BaseDriver):
    """Driver for extracting Instagram Reels, single posts, and carousels."""

    INSTAGRAM_URL_REGEX = re.compile(
        r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv|reels)/([a-zA-Z0-9_-]+)"
    )

    def can_handle(self, url: str) -> bool:
        return bool(self.INSTAGRAM_URL_REGEX.search(url))

    def extract(self, url: str, password: Optional[str] = None, **kwargs) -> AssetPackage:
        m = self.INSTAGRAM_URL_REGEX.search(url)
        if not m:
            raise ExtractionError(f"Invalid Instagram URL: {url}")
        shortcode = m.group(1)
        canonical_url = f"https://www.instagram.com/p/{shortcode}/"

        try:
            import yt_dlp
        except ImportError:
            raise ExtractionError("yt-dlp is required for Instagram extraction.")

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(canonical_url, download=False)
        except Exception as e:
            raise ExtractionError(f"Failed to query Instagram media: {e}")

        if not info:
            raise ExtractionError("Empty metadata response from Instagram.")

        title = info.get("description") or info.get("title") or f"instagram_{shortcode}"
        if len(title) > 60:
            title = title[:60].strip()

        uploader = info.get("uploader") or info.get("channel") or "Instagram User"
        thumbnail_url = info.get("thumbnail")

        formats = info.get("formats", [])
        chosen_format = None
        if formats:
            video_formats = [f for f in formats if f.get("url")]
            video_formats.sort(key=lambda x: (x.get("height") or 0, x.get("tbr") or 0), reverse=True)
            if video_formats:
                chosen_format = video_formats[0]

        assets: List[AssetFile] = []
        if chosen_format and chosen_format.get("url"):
            ext = chosen_format.get("ext") or "mp4"
            assets.append(
                AssetFile(
                    filename=f"content.{ext}",
                    url=chosen_format["url"],
                    file_type="primary",
                    expected_size=chosen_format.get("filesize") or chosen_format.get("filesize_approx"),
                    headers={"User-Agent": "Mozilla/5.0"}
                )
            )
        elif thumbnail_url:
            assets.append(
                AssetFile(
                    filename="content.jpg",
                    url=thumbnail_url,
                    file_type="primary",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
            )
        else:
            raise ExtractionError("No downloadable media found in Instagram post.")

        if thumbnail_url and assets and assets[0].filename != "content.jpg":
            assets.append(
                AssetFile(
                    filename="cover.jpg",
                    url=thumbnail_url,
                    file_type="cover",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
            )

        metadata = {
            "title": title,
            "original_url": canonical_url,
            "author": {
                "id": info.get("uploader_id") or "",
                "name": uploader,
            },
            "created_at": info.get("upload_date") or "",
            "metrics": {
                "likes": info.get("like_count") or 0,
                "comments": info.get("comment_count") or 0,
            },
            "sidecar_text": info.get("description") or "",
        }

        return AssetPackage(
            platform="instagram",
            title=title,
            original_url=canonical_url,
            assets=assets,
            metadata=metadata
        )
