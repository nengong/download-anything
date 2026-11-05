"""
Instagram Post, Reels, and Carousel Extractor Driver
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit
from typing import Optional, List
from drivers.base import AssetPackage, AssetFile
from drivers.social.ytdlp_fallback import YtDlpFallbackDriver
from core.exceptions import ExtractionError

class InstagramDriver(YtDlpFallbackDriver):
    """Driver for extracting Instagram Reels, single posts, and carousels."""

    INSTAGRAM_URL_REGEX = re.compile(
        r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv|reels)/([a-zA-Z0-9_-]+)"
    )

    def can_handle(self, url: str) -> bool:
        return bool(self.INSTAGRAM_URL_REGEX.search(url))

    def _extract_photos(self, canonical_url: str, shortcode: str) -> AssetPackage:
        command = [
            sys.executable, "-m", "gallery_dl", "--config-ignore", "--no-input",
            "--dump-json", "--retries", "0", "--http-timeout", "15", canonical_url,
        ]
        cookie_file = os.environ.get("DA_INSTAGRAM_COOKIE_FILE")
        if cookie_file:
            cookie_path = Path(cookie_file)
            if not cookie_path.is_file():
                raise ExtractionError("Authorized Instagram cookie file is unavailable.")
            command[-1:-1] = ["--cookies", str(cookie_path)]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            raise ExtractionError("Instagram gallery-dl extraction timed out; no retry was attempted.") from None
        except OSError:
            raise ExtractionError("Could not start gallery-dl; install gallery-dl>=1.32.19.") from None
        if result.returncode:
            if "No module named gallery_dl" in result.stderr:
                raise ExtractionError("Instagram photos require gallery-dl; install gallery-dl>=1.32.19.")
            raise ExtractionError(
                "Instagram gallery-dl extraction failed (authentication, rate limit, or backend error); "
                "no retry was attempted."
            )
        try:
            messages = json.loads(result.stdout)
        except (ValueError, TypeError):
            raise ExtractionError("Invalid JSON response from Instagram gallery-dl.") from None
        if not isinstance(messages, list):
            raise ExtractionError("Invalid message array from Instagram gallery-dl.")

        directories = []
        photos = set()
        counts = []
        for message in messages:
            if not isinstance(message, list) or not message:
                raise ExtractionError("Invalid message from Instagram gallery-dl.")
            if message[0] == -1:
                raise ExtractionError("Instagram gallery-dl reported an extraction error; no retry was attempted.")
            if message[0] not in (2, 3):
                continue
            if len(message) != (2 if message[0] == 2 else 3) or not isinstance(message[-1], dict):
                raise ExtractionError("Invalid media metadata from Instagram gallery-dl.")
            data = message[-1]
            if data.get("post_shortcode") != shortcode:
                raise ExtractionError("Instagram post shortcode does not match the requested post.")
            if data.get("video_url") or data.get("audio_url"):
                raise ExtractionError("Instagram mixed video/photo posts are not supported by this fallback.")
            count = data.get("count")
            if type(count) is not int or count < 1:
                raise ExtractionError("Missing or inconsistent Instagram photo count.")
            counts.append(count)
            if message[0] == 2:
                directories.append(data)
                continue
            ext = data.get("extension")
            if not isinstance(ext, str) or ext not in {"jpg", "jpeg", "png", "webp", "gif"}:
                raise ExtractionError("Instagram mixed video/photo posts or non-image extensions are not supported.")
            media_url = message[1]
            try:
                parsed = urlsplit(media_url)
                valid = (
                    isinstance(media_url, str)
                    and parsed.scheme == "https"
                    and bool(parsed.hostname)
                    and parsed.hostname.endswith((".cdninstagram.com", ".fbcdn.net"))
                    and parsed.username is None and parsed.password is None
                    and parsed.port in (None, 443)
                    and not parsed.fragment
                    and not any(char.isspace() or ord(char) < 32 for char in media_url)
                )
            except (ValueError, TypeError, AttributeError):
                valid = False
            if not valid:
                raise ExtractionError("Unsafe Instagram photo URL.")
            num = data.get("num")
            if type(num) is not int or num < 1:
                raise ExtractionError("Missing Instagram photo sequence number.")
            # Only identical records may collapse; conflicting indices/URLs must fail completeness.
            photos.add((num, media_url, ext))

        if not directories or not photos:
            raise ExtractionError("No complete photo collection found for the requested Instagram post.")
        if len(set(counts)) != 1:
            raise ExtractionError("Missing or inconsistent Instagram photo count.")
        count = counts[0]
        ordered = sorted(photos)
        if (len(ordered) != count
                or [photo[0] for photo in ordered] != list(range(1, count + 1))
                or len({photo[1] for photo in ordered}) != count):
            raise ExtractionError("Incomplete Instagram photo collection: count or sequence mismatch.")

        data = directories[0]
        description = data.get("description") if isinstance(data.get("description"), str) else ""
        title = description[:60].strip() or f"instagram_{shortcode}"
        user = data.get("user") if isinstance(data.get("user"), dict) else {}
        username = data.get("username") or user.get("username") or "Instagram User"
        metadata = {
            "title": title,
            "original_url": canonical_url,
            "author": {"id": user.get("id") or "", "name": username},
            "created_at": data.get("date") or "",
            "metrics": {"image_count": count},
            "sidecar_text": description,
        }
        assets = [
            AssetFile(
                filename=f"content.{ext}" if index == 1 else f"image_{index:02d}.{ext}",
                url=media_url,
                file_type="primary" if index == 1 else "companion",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            for index, (_, media_url, ext) in enumerate(ordered, 1)
        ]
        return AssetPackage(
            platform="instagram", title=title, original_url=canonical_url,
            assets=assets, metadata=metadata,
        )

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
            "noplaylist": True,
            "socket_timeout": 15,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(canonical_url, download=False, process=False)
        except Exception as e:
            error = str(e).lower()
            blocked = any(marker in error for marker in (
                "login", "log in", "sign in", "auth", "cookie", "token",
                "429", "403", "401", "rate limit", "too many requests",
                "forbidden", "unauthorized", "captcha", "challenge",
            ))
            if not blocked and any(marker in error for marker in (
                "no video formats found", "no video could be found", "there is no video in this post",
            )):
                return self._extract_photos(canonical_url, shortcode)
            if blocked:
                raise ExtractionError(
                    "Failed to query Instagram media: authentication/access or rate limit error; "
                    "gallery-dl fallback was not attempted."
                ) from None
            raise ExtractionError("Failed to query Instagram media (yt-dlp extraction error).") from None

        if not info:
            raise ExtractionError("Empty metadata response from Instagram.")
        if info.get("_type") in ("playlist", "multi_video") or "entries" in info:
            entries = info.get("entries") or []
            if (not info.get("url") and not info.get("formats") and entries
                    and all(isinstance(e, dict) and not e.get("url") and not e.get("formats")
                            and (e.get("thumbnail") or e.get("thumbnails")) for e in entries)):
                return self._extract_photos(canonical_url, shortcode)
            raise ExtractionError(
                "Instagram returned a playlist or multiple media entries; "
                "provide a single video URL."
            )

        title = info.get("description") or info.get("title") or f"instagram_{shortcode}"
        if len(title) > 60:
            title = title[:60].strip()

        uploader = info.get("uploader") or info.get("channel") or "Instagram User"
        thumbnail_url = info.get("thumbnail")

        # Let yt-dlp select and merge tracks instead of fetching a video-only URL.
        formats = [f for f in (info.get("formats") or []) if f.get("url")]
        assets: List[AssetFile] = []
        if formats or info.get("url"):
            audio_only = bool(kwargs.get("audio_only", False))
            ext = self._native_audio_ext(info) if audio_only else "mp4"
            download_options = {
                "source_url": canonical_url,
                "format": "ba/b" if audio_only else "bv*+ba/b",
            }
            if not audio_only:
                download_options["merge_output_format"] = "mp4"
            headers = self._asset_headers(info, {})
            for fmt in formats:
                headers = self._asset_headers({"http_headers": headers}, fmt)
            assets.append(
                AssetFile(
                    filename=f"content.{ext}",
                    url=canonical_url,
                    file_type="primary",
                    expected_size=None,
                    headers=headers,
                    download_strategy="ytdlp",
                    download_options=download_options,
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
