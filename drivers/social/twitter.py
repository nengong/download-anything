"""
X (Twitter) Tweet, Video, and Image Extractor Driver
"""
import re
from typing import Optional, Dict, Any, List
from drivers.base import BaseDriver, AssetPackage, AssetFile
from core.exceptions import ExtractionError

class TwitterDriver(BaseDriver):
    """Driver for extracting X (Twitter) videos, photos, and tweet threads."""

    TWITTER_URL_REGEX = re.compile(
        r"https?://(?:(?:www|mobile|m)\.)?(?:twitter\.com|x\.com)/(?:#!/)?(?P<user>[a-zA-Z0-9_]+)/status/(?P<id>[0-9]+)"
    )

    def can_handle(self, url: str) -> bool:
        return bool(self.TWITTER_URL_REGEX.search(url))

    def extract(self, url: str, password: Optional[str] = None, **kwargs) -> AssetPackage:
        m = self.TWITTER_URL_REGEX.search(url)
        if not m:
            raise ExtractionError(f"Invalid X/Twitter status URL: {url}")
        user = m.group("user")
        tweet_id = m.group("id")
        canonical_url = f"https://x.com/{user}/status/{tweet_id}"

        try:
            import yt_dlp
        except ImportError:
            raise ExtractionError("yt-dlp is required for X/Twitter extraction.")

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(canonical_url, download=False)
        except Exception as e:
            raise ExtractionError(f"Failed to query X/Twitter post: {e}")

        if not info:
            raise ExtractionError("Empty metadata response from X/Twitter.")

        title = info.get("description") or info.get("title") or f"tweet_{tweet_id}"
        if len(title) > 60:
            title = title[:60].strip()

        uploader = info.get("uploader") or user
        thumbnail_url = info.get("thumbnail")

        # Check if video formats exist
        formats = info.get("formats", [])
        chosen_format = None
        if formats:
            # Sort best bitrate/resolution
            video_formats = [f for f in formats if f.get("url")]
            video_formats.sort(key=lambda x: (x.get("tbr") or 0, x.get("height") or 0), reverse=True)
            if video_formats:
                chosen_format = video_formats[0]

        assets: List[AssetFile] = []
        if chosen_format and chosen_format.get("url"):
            primary_url = chosen_format["url"]
            ext = chosen_format.get("ext") or "mp4"
            assets.append(
                AssetFile(
                    filename=f"content.{ext}",
                    url=primary_url,
                    file_type="primary",
                    expected_size=chosen_format.get("filesize") or chosen_format.get("filesize_approx"),
                    headers={"User-Agent": "Mozilla/5.0"}
                )
            )
        elif thumbnail_url:
            # Image tweet
            assets.append(
                AssetFile(
                    filename="content.jpg",
                    url=thumbnail_url,
                    file_type="primary",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
            )
        else:
            raise ExtractionError("No downloadable media found in X/Twitter post.")

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
                "id": info.get("uploader_id") or user,
                "name": uploader,
            },
            "created_at": info.get("upload_date") or "",
            "metrics": {
                "likes": info.get("like_count") or 0,
                "reposts": info.get("repost_count") or 0,
                "comments": info.get("comment_count") or 0,
            },
            "sidecar_text": info.get("description") or "",
        }

        return AssetPackage(
            platform="twitter",
            title=title,
            original_url=canonical_url,
            assets=assets,
            metadata=metadata
        )
