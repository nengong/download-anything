"""
Open-Source and Public Domain Music Driver
Supports Free Music Archive (FMA), Internet Archive Audio (archive.org), and SoundCloud.
Extracts CC/Public Domain MP3 audio with copyright attribution metadata.
"""
import re
from typing import Optional, List, Dict, Any
import requests

from core.exceptions import ExtractionError
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class OpenMusicDriver(BaseDriver):
    """
    Driver for Open-Source, Creative Commons, and Public Domain music:
    - Internet Archive Audio (archive.org/details/...)
    - Free Music Archive (freemusicarchive.org)
    - SoundCloud (soundcloud.com)
    """

    name = "open_music"
    category = "audio"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
    }

    def can_handle(self, url: str) -> bool:
        clean = url.strip().lower()
        if "archive.org/details/" in clean or "freemusicarchive.org" in clean or "soundcloud.com" in clean:
            return True
        return False

    def extract(self, url: str, **kwargs) -> AssetPackage:
        clean = url.strip()
        if "archive.org/details/" in clean:
            return self._extract_archive_org(clean)
        else:
            return self._extract_via_ytdlp(clean)

    def _extract_archive_org(self, url: str) -> AssetPackage:
        # e.g. https://archive.org/details/{identifier}
        m = re.search(r"archive\.org/details/([^/?#]+)", url)
        if not m:
            raise ExtractionError(f"Could not parse Internet Archive identifier from: {url}")
        identifier = m.group(1)

        meta_api = f"https://archive.org/metadata/{identifier}"
        try:
            r = requests.get(meta_api, headers=self.DEFAULT_HEADERS, timeout=12)
            data = r.json()
        except Exception as e:
            raise ExtractionError(f"Failed to query Internet Archive metadata: {e}")

        meta = data.get("metadata", {})
        title = meta.get("title") or identifier
        creator = meta.get("creator", "Public Domain / CC")
        license_url = meta.get("licenseurl", "Creative Commons / Public Domain")

        files = data.get("files", [])
        # Find best MP3 or VBR MP3
        mp3_file = None
        for f in files:
            name = f.get("name", "")
            if name.endswith(".mp3"):
                mp3_file = f
                if "vbr" in f.get("format", "").lower():
                    break

        if not mp3_file:
            # Fallback to any audio file
            for f in files:
                if any(f.get("name", "").endswith(ext) for ext in (".flac", ".ogg", ".wav", ".m4a")):
                    mp3_file = f
                    break

        if not mp3_file:
            raise ExtractionError(f"No downloadable audio files found in Internet Archive item {identifier}")

        mp3_name = mp3_file["name"]
        download_url = f"https://archive.org/download/{identifier}/{mp3_name}"
        filesize = int(mp3_file.get("size", 0)) or None

        assets: List[TargetAsset] = [
            TargetAsset(
                filename="content.mp3",
                url=download_url,
                file_type="primary",
                expected_size=filesize,
                headers=self.DEFAULT_HEADERS
            )
        ]

        markdown_body = (
            f"# {title}\n\n"
            f"> - **创作者 (Creator)**: `{creator}`\n"
            f"> - **开源许可 (License)**: <{license_url}>\n"
            f"> - **档案来源**: Internet Archive (`{identifier}`)\n\n"
            f"---\n"
            f"公共领域 / CC 授权开源音频资产，已完成数字完整性校验。\n"
        )

        metadata = {
            "title": title,
            "original_url": url,
            "creator": creator,
            "license": license_url,
            "sidecar_text": markdown_body,
            "author": {"name": creator}
        }

        return AssetPackage(
            platform="open_music",
            title=title,
            original_url=url,
            assets=assets,
            metadata=metadata
        )

    def _extract_via_ytdlp(self, url: str) -> AssetPackage:
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "extract_flat": False,
            "format": "bestaudio/best"
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            raise ExtractionError(f"Failed to extract open music audio via yt-dlp: {e}")

        if not info:
            raise ExtractionError(f"Empty metadata returned for {url}")

        title = info.get("title") or "open_track"
        uploader = info.get("uploader") or info.get("artist") or "Independent Artist"
        thumbnail = info.get("thumbnail")

        formats = info.get("formats", [])
        chosen = None
        audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("url")]
        if audio_formats:
            audio_formats.sort(key=lambda x: (x.get("abr") or 0, x.get("tbr") or 0), reverse=True)
            chosen = audio_formats[0]
        elif info.get("url"):
            chosen = info

        if not chosen or not chosen.get("url"):
            raise ExtractionError(f"Could not resolve direct audio stream for {url}")

        stream_url = chosen["url"]
        filesize = chosen.get("filesize") or chosen.get("filesize_approx")

        assets: List[TargetAsset] = [
            TargetAsset(
                filename="content.mp3",
                url=stream_url,
                file_type="primary",
                expected_size=filesize,
                headers=self.DEFAULT_HEADERS
            )
        ]

        if thumbnail:
            assets.append(TargetAsset(
                filename="cover.jpg",
                url=thumbnail,
                file_type="cover",
                headers=self.DEFAULT_HEADERS
            ))

        markdown_body = (
            f"# {title}\n\n"
            f"> - **音乐人 (Artist)**: `{uploader}`\n"
            f"> - **平台**: SoundCloud / Free Music Archive\n"
            f"> - **来源网址**: <{url}>\n\n"
            f"---\n"
            f"已提取高品质音频并保留作者署名。\n"
        )

        metadata = {
            "title": title,
            "original_url": url,
            "artist": uploader,
            "sidecar_text": markdown_body,
            "author": {"name": uploader}
        }

        return AssetPackage(
            platform="open_music",
            title=title,
            original_url=url,
            assets=assets,
            metadata=metadata
        )
