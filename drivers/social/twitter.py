"""
X (Twitter) Tweet, Video, and Image Extractor Driver
"""
import json
import re
import subprocess
import sys
from urllib.parse import parse_qs, unquote, urlsplit
from typing import Optional, List
from drivers.base import AssetPackage, AssetFile
from drivers.social.ytdlp_fallback import YtDlpFallbackDriver
from core.exceptions import ExtractionError

class TwitterDriver(YtDlpFallbackDriver):
    """Driver for extracting X (Twitter) videos, photos, and tweet threads."""

    TWITTER_URL_REGEX = re.compile(
        r"https?://(?:(?:www|mobile|m)\.)?(?:twitter\.com|x\.com)/(?:#!/)?(?P<user>[a-zA-Z0-9_]+)/status/(?P<id>[0-9]+)"
    )

    def can_handle(self, url: str) -> bool:
        return bool(self.TWITTER_URL_REGEX.search(url))

    def _extract_photos(self, canonical_url: str, user: str, tweet_id: str) -> AssetPackage:
        command = [
            sys.executable, "-m", "gallery_dl", "--config-ignore", "--no-input",
            "--dump-json", "--retries", "0", "--http-timeout", "15",
            "-o", "extractor.twitter.quoted=false",
            "-o", "extractor.twitter.replies=false", canonical_url,
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            raise ExtractionError("X/Twitter gallery-dl extraction timed out.") from None
        except OSError:
            raise ExtractionError("Could not start gallery-dl; install gallery-dl>=1.32.19.") from None
        if result.returncode:
            if "No module named gallery_dl" in result.stderr:
                raise ExtractionError("X/Twitter photos require gallery-dl; install gallery-dl>=1.32.19.")
            raise ExtractionError(
                "X/Twitter gallery-dl extraction failed (authentication, rate limit, or backend error); "
                "no retry was attempted."
            )
        try:
            messages = json.loads(result.stdout)
        except (ValueError, TypeError):
            raise ExtractionError("Invalid JSON response from X/Twitter gallery-dl.") from None
        if not isinstance(messages, list):
            raise ExtractionError("Invalid message array from X/Twitter gallery-dl.")

        directories = []
        photos = []
        for message in messages:
            if not isinstance(message, list) or not message:
                raise ExtractionError("Invalid message from X/Twitter gallery-dl.")
            if message[0] == -1:
                raise ExtractionError("X/Twitter gallery-dl reported an extraction error; no retry was attempted.")
            if message[0] not in (2, 3):
                continue
            if len(message) != (2 if message[0] == 2 else 3) or not isinstance(message[-1], dict):
                raise ExtractionError("Invalid media metadata from X/Twitter gallery-dl.")
            data = message[-1]
            # gallery-dl emits integer tweet IDs; never include quoted/reply media.
            if type(data.get("tweet_id")) is not int or str(data["tweet_id"]) != tweet_id:
                continue
            if message[0] == 2:
                directories.append(data)
                continue
            if data.get("type") != "photo":
                raise ExtractionError("X/Twitter mixed video/photo posts are not supported by this fallback.")
            ext = data.get("extension")
            if ext not in {"jpg", "jpeg", "png", "webp", "gif"}:
                raise ExtractionError("Unsupported X/Twitter photo extension.")
            media_url = message[1]
            try:
                parsed = urlsplit(media_url)
                query = parse_qs(parsed.query)
                valid = (
                    parsed.scheme in ("http", "https")
                    and parsed.netloc == "pbs.twimg.com"
                    and not parsed.fragment
                    and re.fullmatch(r"/media/[A-Za-z0-9_-]+(?:\.[a-z]+)?(?::orig)?", unquote(parsed.path))
                    and set(query) <= {"name", "format"}
                    and (query.get("name") == ["orig"] or parsed.path.endswith(":orig"))
                    and (parsed.path.removesuffix(":orig").endswith(f".{ext}")
                         or query.get("format") == [ext])
                )
            except (ValueError, TypeError, AttributeError):
                valid = False
            if not valid:
                raise ExtractionError("Unsafe or non-original X/Twitter photo URL.")
            if type(data.get("num")) is not int or data["num"] < 1:
                raise ExtractionError("Missing X/Twitter photo sequence number.")
            photos.append((data["num"], media_url, ext))

        if not directories or not photos:
            raise ExtractionError("No complete photo collection found for the requested X/Twitter post.")
        counts = [data.get("count") for data in directories]
        if any(type(count) is not int or count < 1 for count in counts) or len(set(counts)) != 1:
            raise ExtractionError("Missing or inconsistent X/Twitter photo count.")
        ordered = []
        seen = set()
        for photo in sorted(photos):
            if photo[1] not in seen:
                ordered.append(photo)
                seen.add(photo[1])
        count = counts[0]
        if len(ordered) != count or [photo[0] for photo in ordered] != list(range(1, count + 1)):
            raise ExtractionError("Incomplete X/Twitter photo collection: count or sequence mismatch.")

        data = directories[0]
        content = data.get("content") if isinstance(data.get("content"), str) else ""
        title = content[:60].strip() or f"tweet_{tweet_id}"
        author = data.get("author") if isinstance(data.get("author"), dict) else {}
        # Copy only public metadata, never backend configuration or credentials.
        metadata = {
            "title": title,
            "original_url": canonical_url,
            "author": {
                "id": author.get("id") or user,
                "name": author.get("name") or user,
                "nick": author.get("nick") or "",
            },
            "created_at": data.get("date") or "",
            "metrics": {
                "likes": data.get("favorite_count") or 0,
                "reposts": data.get("retweet_count") or 0,
                "comments": data.get("reply_count") or 0,
                "image_count": count,
            },
            "sidecar_text": content,
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
            platform="twitter", title=title, original_url=canonical_url,
            assets=assets, metadata=metadata,
        )

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
            "noplaylist": True,
            "socket_timeout": 15,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(canonical_url, download=False)
        except Exception as e:
            error = str(e).lower()
            blocked = any(marker in error for marker in (
                "login", "log in", "sign in", "auth", "cookie", "token",
                "429", "403", "401", "rate limit", "too many requests",
                "forbidden", "unauthorized", "captcha", "challenge",
            ))
            if not blocked and any(marker in error for marker in (
                "no video could be found", "no video formats found",
                "no video found", "does not contain a video",
            )):
                return self._extract_photos(canonical_url, user, tweet_id)
            # Keep the original backend failure, but never echo credential-bearing logs.
            if blocked:
                raise ExtractionError(
                    "Failed to query X/Twitter post: authentication/access or rate limit error; "
                    "gallery-dl fallback was not attempted."
                ) from None
            raise ExtractionError("Failed to query X/Twitter post (yt-dlp extraction error).") from None


        if not info:
            raise ExtractionError("Empty metadata response from X/Twitter.")
        if info.get("_type") in ("playlist", "multi_video") or "entries" in info:
            raise ExtractionError(
                "X/Twitter returned a playlist or multiple media entries; "
                "provide a single video URL."
            )

        title = info.get("description") or info.get("title") or f"tweet_{tweet_id}"
        if len(title) > 60:
            title = title[:60].strip()

        uploader = info.get("uploader") or user
        thumbnail_url = info.get("thumbnail")

        # yt-dlp must select and merge tracks; one resolved URL may be video-only.
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
