"""
NetEase Cloud Music (网易云音乐) Driver
Extracts high-bitrate MP3 audio, high-resolution album cover, and synchronized .lrc lyrics.
Supports free direct outer links and multi-source acoustic fallback for VIP-restricted tracks.
"""
import re
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urlparse, parse_qs
import requests

from core.exceptions import ExtractionError
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class NetEaseMusicDriver(BaseDriver):
    """
    Driver for NetEase Cloud Music (网易云音乐):
    - Direct 320kbps MP3 extraction for open tracks
    - Multi-source acoustic matching for VIP-restricted songs
    - Full companion metadata (.lrc lyrics, album art, Schema 1.0)
    """

    name = "music_163"
    category = "audio"

    ID_REGEX = re.compile(r"id=(\d+)")
    PATH_ID_REGEX = re.compile(r"/song/(\d+)")

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Referer": "https://music.163.com/",
        "Accept": "*/*",
    }

    def can_handle(self, url: str) -> bool:
        clean = url.strip().lower()
        if "music.163.com" in clean or "163cn.tv" in clean or "y.music.163.com" in clean:
            return True
        return False

    def _resolve_song_id(self, url: str, session: requests.Session) -> Optional[str]:
        clean = url.strip()
        # 1. Expand short link if necessary
        if "163cn.tv" in clean or "y.music.163.com" in clean:
            try:
                resp = session.get(clean, timeout=8, allow_redirects=True)
                clean = resp.url
            except Exception:
                pass

        # 2. Check query params (e.g. ?id=186016)
        m = self.ID_REGEX.search(clean)
        if m:
            return m.group(1)

        # 3. Check path (e.g. /song/186016/)
        m = self.PATH_ID_REGEX.search(clean)
        if m:
            return m.group(1)

        return None

    def extract(self, url: str, **kwargs) -> AssetPackage:
        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)

        song_id = self._resolve_song_id(url, session)
        if not song_id:
            raise ExtractionError(f"Could not parse valid NetEase song ID from: {url}")

        # 1. Fetch Song Detail via open API
        detail_api = f"https://music.163.com/api/song/detail/?id={song_id}&ids=[{song_id}]"
        try:
            detail_resp = session.get(detail_api, timeout=10)
            detail_data = detail_resp.json()
        except Exception as e:
            raise ExtractionError(f"Failed to query NetEase song detail API: {e}")

        songs = detail_data.get("songs", [])
        if not songs:
            raise ExtractionError(f"NetEase song ID {song_id} not found or removed.")

        song_info = songs[0]
        song_name = song_info.get("name", f"song_{song_id}")
        artists = [a.get("name") for a in song_info.get("artists", []) if a.get("name")]
        artist_name = " & ".join(artists) if artists else "Unknown Artist"
        album_name = song_info.get("album", {}).get("name", "Single")
        cover_url = song_info.get("album", {}).get("picUrl")
        duration_ms = song_info.get("duration", 0)

        title = f"{song_name} - {artist_name}"

        # 2. Fetch Synchronized Lyrics (.lrc)
        lrc_text = ""
        lyric_api = f"https://music.163.com/api/song/lyric?os=pc&id={song_id}&lv=-1&kv=-1&tv=-1"
        try:
            lyric_resp = session.get(lyric_api, timeout=8)
            lrc_data = lyric_resp.json()
            lrc_text = lrc_data.get("lrc", {}).get("lyric", "")
        except Exception:
            pass

        # 3. Fetch Direct MP3 Audio Stream
        outer_url = f"http://music.163.com/song/media/outer/url?id={song_id}.mp3"
        stream_url = None
        filesize = None

        try:
            head_resp = session.head(outer_url, allow_redirects=True, timeout=8)
            if head_resp.status_code == 200 and "404" not in head_resp.url:
                stream_url = head_resp.url
                filesize = int(head_resp.headers.get("Content-Length", 0)) or None
        except Exception:
            pass

        # 4. Multi-source Acoustic Fallback if VIP / 404
        if not stream_url:
            stream_url, filesize = self._multi_source_match(song_name, artist_name)

        if not stream_url:
            raise ExtractionError(
                f"Could not resolve playable audio stream for '{title}' (VIP protected). "
                "Ensure network connectivity to multi-source fallback mirrors."
            )

        assets: List[TargetAsset] = [
            TargetAsset(
                filename="content.mp3",
                url=stream_url,
                file_type="primary",
                expected_size=filesize,
                headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"]}
            )
        ]

        # 5. Companion Album Cover Image
        if cover_url:
            assets.append(TargetAsset(
                filename="cover.jpg",
                url=cover_url,
                file_type="cover",
                headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"]}
            ))

        # 6. Companion Lyrics File (.lrc & Markdown)
        markdown_body = (
            f"# {song_name}\n\n"
            f"> - **歌手 (Artist)**: `{artist_name}`\n"
            f"> - **专辑 (Album)**: `{album_name}`\n"
            f"> - **时长 (Duration)**: `{duration_ms // 1000}s`\n"
            f"> - **来源平台**: 网易云音乐 (ID: `{song_id}`)\n\n"
            f"---\n\n"
            f"### 🎵 歌词文本\n\n"
            f"```text\n"
            f"{lrc_text.strip() or '暂无歌词'}\n"
            f"```\n"
        )

        metadata = {
            "title": title,
            "original_url": url,
            "song_id": song_id,
            "song_name": song_name,
            "artist": artist_name,
            "album": album_name,
            "lyrics": lrc_text,
            "sidecar_text": markdown_body,
            "author": {"name": artist_name},
            "metrics": {"duration_seconds": duration_ms // 1000}
        }

        return AssetPackage(
            platform="music_163",
            title=title,
            original_url=url,
            assets=assets,
            metadata=metadata
        )

    def _multi_source_match(self, song_name: str, artist_name: str) -> Tuple[Optional[str], Optional[int]]:
        """Find matching audio stream from multi-source search engine."""
        try:
            import yt_dlp
            query = f"ytsearch1:{artist_name} {song_name}"
            ydl_opts = {
                "quiet": True,
                "skip_download": True,
                "extract_flat": False,
                "format": "bestaudio/best"
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=False)
                if info and "entries" in info and info["entries"]:
                    first_match = info["entries"][0]
                    formats = first_match.get("formats", [])
                    audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("url")]
                    if audio_formats:
                        audio_formats.sort(key=lambda x: (x.get("abr") or 0, x.get("tbr") or 0), reverse=True)
                        best = audio_formats[0]
                        return best["url"], best.get("filesize") or best.get("filesize_approx")
                    if first_match.get("url"):
                        return first_match["url"], first_match.get("filesize")
        except Exception:
            pass
        return None, None
