"""
Universal yt-dlp Fallback Driver
Catches video/audio pages that no specialized platform driver claimed and lets
yt-dlp try them. This keeps the driver list small while covering the long tail
of sites supported by yt-dlp (TikTok, Kuaishou, Xigua, Vimeo, ...).
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from core.exceptions import ExtractionError
from core.url_policy import copy_cookies, public_headers, require_http_url
from drivers.base import BaseDriver, AssetPackage, TargetAsset


class YtDlpFallbackDriver(BaseDriver):
    """Last-resort driver backed by yt-dlp for unrecognized video/audio URLs."""

    name = "ytdlp"
    category = "social"

    MAX_ASSET_BYTES = 500 * 1024 * 1024
    DIRECT_AUDIO_EXTS = {"m4a", "mp3", "aac", "opus", "ogg", "wav", "flac"}

    def can_handle(self, url: str) -> bool:
        """Claim any remaining HTTP(S) URL; specialized drivers are checked first."""
        clean = (url or "").strip()
        parsed = urlparse(clean)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)

    def extract(self, url: str, password: Optional[str] = None, **kwargs) -> AssetPackage:
        try:
            import yt_dlp
        except ImportError:
            raise ExtractionError(
                "yt-dlp package is required for the universal fallback driver. "
                "Install with `uv pip install yt-dlp`."
            )

        audio_only = bool(kwargs.get("audio_only"))
        max_bytes = kwargs.get("max_bytes") or self.MAX_ASSET_BYTES
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
            "noplaylist": True,
            "socket_timeout": 15,
        }

        require_http_url(url)
        cookie_jar = None
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                try:
                    from http.cookiejar import CookieJar
                    cookie_jar = CookieJar()
                    copy_cookies(ydl.cookiejar, cookie_jar)
                except Exception:
                    cookie_jar = None
        except Exception as e:
            raise ExtractionError(
                "yt-dlp fallback could not extract downloadable media from this URL; "
                "it may be a plain article, or the site may be unsupported, "
                f"region-locked, DRM-protected, or require login: {e}"
            )

        if not info:
            raise ExtractionError("Empty metadata response from yt-dlp fallback.")

        if info.get("_type") in ("playlist", "multi_video") or "entries" in info:
            raise ExtractionError("yt-dlp returned a playlist; provide a single video/audio URL.")

        if info.get("is_live"):
            raise ExtractionError(
                "Live streams are not supported by the yt-dlp fallback; "
                "wait for the replay or provide a finished video URL."
            )

        chosen = self._choose_direct_format(
            info, audio_only=audio_only, max_bytes=max_bytes
        )
        asset_headers = self._asset_headers(info, chosen) if chosen else {"User-Agent": "Mozilla/5.0"}

        if chosen:
            stream_url = chosen["url"]
            ext = (chosen.get("ext") or self._guess_ext(stream_url)
                   or ("m4a" if audio_only else "mp4")).lstrip(".")
            # filesize_approx is a guess; treating it as exact makes the Fetcher
            # reject a complete download that is a few bytes off.
            expected_size = chosen.get("filesize")
            primary_asset = TargetAsset(
                filename=f"content.{ext}",
                url=stream_url,
                file_type="primary",
                expected_size=expected_size,
                headers=asset_headers,
            )
        else:
            formats = [f for f in (info.get("formats") or []) if f.get("url")]
            if not formats and not info.get("url"):
                raise ExtractionError(
                    "yt-dlp fallback could not find a downloadable media stream for this URL."
                )
            # HLS/DASH manifests (or split audio/video tracks) need yt-dlp's own
            # downloader, which can fetch fragments and merge tracks with ffmpeg.
            if audio_only:
                ext = self._native_audio_ext(info)
                selector = "ba/b"
                options = {"source_url": url, "format": selector}
            else:
                ext = "mp4"
                selector = "bv*+ba/b"
                options = {
                    "source_url": url,
                    "format": selector,
                    "merge_output_format": "mp4",
                }
            primary_asset = TargetAsset(
                filename=f"content.{ext}",
                url=url,
                file_type="primary",
                headers=asset_headers,
                download_strategy="ytdlp",
                download_options=options,
            )

        assets: List[TargetAsset] = [primary_asset]

        thumbnail_url = info.get("thumbnail")
        if not thumbnail_url:
            thumbnails = info.get("thumbnails") or []
            if thumbnails:
                thumbnail_url = thumbnails[-1].get("url")
        if thumbnail_url:
            assets.append(
                TargetAsset(
                    filename="cover.jpg",
                    url=thumbnail_url,
                    file_type="cover",
                    headers=asset_headers,
                )
            )

        sub_url = self._pick_subtitle_url(info.get("subtitles"))
        if not sub_url:
            sub_url = self._pick_subtitle_url(info.get("automatic_captions"))
        if sub_url:
            assets.append(
                TargetAsset(
                    filename="subtitle.vtt",
                    url=sub_url,
                    file_type="subtitle",
                    headers=asset_headers,
                )
            )

        title = info.get("title") or info.get("description") or info.get("id") or "ytdlp_asset"
        if isinstance(title, str) and len(title) > 120:
            title = title[:120].strip()
        uploader = (
            info.get("uploader")
            or info.get("channel")
            or info.get("artist")
            or "Unknown Creator"
        )
        extractor = info.get("extractor_key") or info.get("extractor") or ""

        metadata: Dict[str, Any] = {
            "title": title,
            "original_url": info.get("webpage_url") or url,
            "author": {
                "id": info.get("channel_id") or info.get("uploader_id") or "",
                "name": uploader,
            },
            "created_at": info.get("upload_date") or "",
            "metrics": {
                "views": info.get("view_count") or 0,
                "likes": info.get("like_count") or 0,
                "duration_seconds": info.get("duration") or 0,
            },
            "sidecar_text": info.get("description") or "",
            "extractor": extractor,
            "download_strategy": primary_asset.download_strategy,
        }
        tags = info.get("tags")
        if isinstance(tags, list) and tags:
            metadata["tags"] = tags

        for asset in assets:
            require_http_url(asset.url)
            asset.cookie_jar = cookie_jar
        return AssetPackage(
            platform="ytdlp",
            title=title,
            original_url=metadata["original_url"],
            assets=assets,
            metadata=metadata,
        )

    def download_primary(
        self,
        asset: TargetAsset,
        dest_path: Path,
        max_bytes: int,
        progress_callback=None,
    ) -> Tuple[int, Path]:
        """Download HLS/DASH or split-track media through yt-dlp's own engine.

        Returns (saved byte count, final path). The final path may differ from
        ``dest_path`` when yt-dlp produced a different container (for example
        WebM audio or an MKV merge), so the caller can keep the extension honest.
        """
        import shutil
        import uuid
        import yt_dlp

        from core.exceptions import DownloadError, FileTooLargeError

        options = asset.download_options or {}
        source_url = options.get("source_url") or asset.url
        require_http_url(source_url)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = dest_path.parent / f".da-ytdlp-{uuid.uuid4().hex}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        def on_progress(status):
            if status.get("status") != "downloading":
                return
            downloaded = status.get("downloaded_bytes") or 0
            if downloaded > max_bytes:
                raise FileTooLargeError(
                    f"Download exceeded maximum size threshold "
                    f"({max_bytes / (1024 * 1024):.1f}MB)"
                )
            if progress_callback:
                total = status.get("total_bytes") or status.get("total_bytes_estimate")
                progress_callback(downloaded, total)

        def reject_playlist(info, *, incomplete=False):
            if (info.get("_type") in ("playlist", "multi_video") or "entries" in info
                    or info.get("playlist_id") is not None or info.get("playlist") is not None):
                raise DownloadError("Playlist download is not allowed; provide a single media URL")
            return None

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,
            "playlist_items": "1",
            "match_filter": reject_playlist,
            "overwrites": True,
            "socket_timeout": 15,
            "retries": 3,
            "fragment_retries": 3,
            "outtmpl": str(temp_dir / "media.%(ext)s"),
            "format": options.get("format") or "bv*+ba/b",
            "progress_hooks": [on_progress],
        }
        if options.get("merge_output_format"):
            ydl_opts["merge_output_format"] = options["merge_output_format"]
        # yt-dlp re-resolves the page during download, so the Cookie captured
        # during extraction must survive; otherwise login-gated HLS/DASH fails.
        headers = public_headers(asset.headers)
        if headers:
            ydl_opts["http_headers"] = headers

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if asset.cookie_jar is not None:
                    copy_cookies(asset.cookie_jar, ydl.cookiejar)
                ydl.download([source_url])

            produced = [
                path for path in temp_dir.iterdir()
                if path.is_file() and not path.name.endswith((".part", ".ytdl", ".temp"))
            ]
            if not produced:
                raise DownloadError("yt-dlp finished without producing a media file.")
            media = max(produced, key=lambda path: path.stat().st_size)
            size = media.stat().st_size
            if size <= 0:
                raise DownloadError("yt-dlp produced an empty media file.")
            if size > max_bytes:
                raise FileTooLargeError(
                    f"Download exceeded maximum size threshold "
                    f"({max_bytes / (1024 * 1024):.1f}MB)"
                )
            final_path = dest_path
            if media.suffix and media.suffix.lower() != dest_path.suffix.lower():
                final_path = dest_path.with_suffix(media.suffix.lower())
                if final_path.exists():
                    final_path = dest_path.with_name(
                        f"{dest_path.stem}-{uuid.uuid4().hex[:8]}{media.suffix.lower()}"
                    )
            # Exclusive creation protects an existing destination, including races.
            import os
            os.link(media, final_path)
            media.unlink()
            return final_path.stat().st_size, final_path
        except FileTooLargeError:
            raise
        except DownloadError:
            raise
        except Exception as e:
            raise DownloadError(f"yt-dlp fallback download failed: {e}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _choose_direct_format(
        self,
        info: Dict[str, Any],
        audio_only: bool,
        max_bytes: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Pick a single direct HTTP stream, or None when yt-dlp should download."""
        formats = [f for f in (info.get("formats") or []) if f.get("url")]
        direct = [f for f in formats if self._is_direct(f)]

        if audio_only:
            groups = [
                [f for f in direct
                 if f.get("acodec") not in (None, "none") and f.get("vcodec") in (None, "none")],
                [f for f in direct if f.get("acodec") not in (None, "none")],
                [f for f in direct if (f.get("ext") or "").lower() in self.DIRECT_AUDIO_EXTS],
            ]
            for group in groups:
                if group:
                    group.sort(key=lambda f: (
                        f.get("abr") or 0, f.get("tbr") or 0, self._size(f)
                    ), reverse=True)
                    return self._prefer_under_limit(group, max_bytes)
        else:
            groups = [
                # A progressive stream keeps both tracks without a merge step.
                [f for f in direct
                 if f.get("vcodec") not in (None, "none") and f.get("acodec") not in (None, "none")],
                # Generic direct files often report no codec metadata at all.
                [f for f in direct
                 if f.get("vcodec") is None and f.get("acodec") is None],
            ]
            for group in groups:
                if group:
                    group.sort(key=lambda f: (
                        f.get("height") or 0, f.get("tbr") or 0, self._size(f)
                    ), reverse=True)
                    return self._prefer_under_limit(group, max_bytes)

        if info.get("url") and self._is_direct(info):
            return info
        return None

    @staticmethod
    def _native_audio_ext(info: Dict[str, Any]) -> str:
        audio_formats = [
            f for f in (info.get("formats") or [])
            if f.get("url") and f.get("acodec") not in (None, "none")
        ]
        audio_formats.sort(key=lambda f: (f.get("abr") or 0, f.get("tbr") or 0), reverse=True)
        for fmt in audio_formats:
            ext = (fmt.get("ext") or "").lower()
            if ext in YtDlpFallbackDriver.DIRECT_AUDIO_EXTS:
                return ext
        return "m4a"

    @staticmethod
    def _is_direct(fmt: Dict[str, Any]) -> bool:
        protocol = (fmt.get("protocol") or "").lower()
        if protocol and protocol not in ("http", "https"):
            return False
        url = fmt.get("url") or ""
        if not url.startswith(("http://", "https://")):
            return False
        return (fmt.get("ext") or "").lower() not in ("m3u8", "mpd")

    @staticmethod
    def _size(fmt: Dict[str, Any]) -> int:
        return fmt.get("filesize") or fmt.get("filesize_approx") or 0

    def _prefer_under_limit(
        self, formats: List[Dict[str, Any]], max_bytes: Optional[int] = None
    ) -> Dict[str, Any]:
        limit = max_bytes or self.MAX_ASSET_BYTES
        for fmt in formats:
            size = self._size(fmt)
            if not size or size <= limit:
                return fmt
        # Everything is oversized; let the fetcher raise a clear size error.
        return formats[0]

    @staticmethod
    def _guess_ext(stream_url: str) -> str:
        suffix = urlparse(stream_url).path.rsplit(".", 1)
        return suffix[-1].split("/")[0][:5] if len(suffix) == 2 else ""

    @staticmethod
    def _asset_headers(info: Dict[str, Any], chosen: Dict[str, Any]) -> Dict[str, str]:
        headers = {"User-Agent": "Mozilla/5.0"}
        for source in (info.get("http_headers"), chosen.get("http_headers")):
            if isinstance(source, dict):
                for key, value in source.items():
                    if isinstance(value, str) and value:
                        headers[key] = value
        return public_headers(headers)

    @staticmethod
    def _pick_subtitle_url(tracks: Optional[Dict[str, Any]]) -> Optional[str]:
        if not tracks:
            return None
        for lang in ("zh-Hans", "zh-Hant", "zh", "en"):
            for entry in tracks.get(lang) or []:
                if entry.get("ext") in ("vtt", "srt") and entry.get("url"):
                    return entry["url"]
        return None
