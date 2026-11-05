"""
Global Music Platform Driver: Spotify & Apple Music
Extracts official 3000px album cover and track metadata from Spotify and Apple Music,
and matches a playable audio stream via public search sources.
"""
import re
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urlparse, parse_qs
import requests

from core.exceptions import ExtractionError
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class SpotifyAppleMusicDriver(BaseDriver):
    """
    Driver for Spotify and Apple Music tracks:
    1. Extracts high-resolution artwork & track metadata from official APIs.
    2. Matches a playable audio stream from public sources.
    3. Saves MP3 alongside high-res cover and metadata sidecar.
    """

    name = "spotify_apple"
    category = "audio"

    APPLE_TRACK_REGEX = re.compile(r"i=(\d+)")
    APPLE_ALBUM_REGEX = re.compile(r"/album/[^/]+/(\d+)")
    SPOTIFY_TRACK_REGEX = re.compile(r"open\.spotify\.com/track/([a-zA-Z0-9]+)")

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
    }

    def can_handle(self, url: str) -> bool:
        clean = url.strip().lower()
        if "music.apple.com" in clean or "open.spotify.com" in clean:
            return True
        return False

    def extract(self, url: str, **kwargs) -> AssetPackage:
        clean = url.strip()
        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)

        if "music.apple.com" in clean:
            return self._extract_apple_music(clean, session)
        elif "open.spotify.com" in clean:
            return self._extract_spotify(clean, session)
        else:
            raise ExtractionError(f"Unsupported music URL: {url}")

    def _extract_apple_music(self, url: str, session: requests.Session) -> AssetPackage:
        # Extract track ID (either ?i=xxxx or /id=xxxx)
        track_id = None
        m = self.APPLE_TRACK_REGEX.search(url)
        if m:
            track_id = m.group(1)
        else:
            m2 = self.APPLE_ALBUM_REGEX.search(url)
            if m2:
                track_id = m2.group(1)

        if not track_id:
            raise ExtractionError(f"Could not parse valid Apple Music track ID from: {url}")

        lookup_url = f"https://itunes.apple.com/lookup?id={track_id}"
        try:
            r = session.get(lookup_url, timeout=10)
            data = r.json()
        except Exception as e:
            raise ExtractionError(f"Failed to query Apple iTunes lookup API: {e}")

        results = data.get("results", [])
        if not results:
            raise ExtractionError(f"Apple Music track ID {track_id} not found.")

        item = results[0]
        track_name = item.get("trackName") or item.get("collectionName", f"track_{track_id}")
        artist_name = item.get("artistName", "Unknown Artist")
        album_name = item.get("collectionName", "")
        duration_ms = item.get("trackTimeMillis", 0)
        
        # Upgrade artwork to ultra-high-resolution 3000x3000px
        raw_art = item.get("artworkUrl100", "")
        cover_url = raw_art.replace("100x100bb.jpg", "3000x3000bb.jpg") if raw_art else None

        title = f"{track_name} - {artist_name}"

        # Match audio stream
        stream_url, filesize = self._find_audio_stream(track_name, artist_name)
        if not stream_url:
            raise ExtractionError(f"Could not resolve audio stream for '{title}'")

        assets: List[TargetAsset] = [
            TargetAsset(
                filename="content.mp3",
                url=stream_url,
                file_type="primary",
                expected_size=filesize,
                headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"]}
            )
        ]

        if cover_url:
            assets.append(TargetAsset(
                filename="cover.jpg",
                url=cover_url,
                file_type="cover",
                headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"]}
            ))

        markdown_body = (
            f"# {track_name}\n\n"
            f"> - **歌手 (Artist)**: `{artist_name}`\n"
            f"> - **专辑 (Album)**: `{album_name}`\n"
            f"> - **平台**: Apple Music (ID: `{track_id}`)\n"
            f"> - **封面画质**: 3000×3000 Ultra HD\n\n"
            f"---\n"
            f"已提取 Apple Music 官方曲目元数据与高清专辑封面，并通过公开音源匹配保存 MP3 音频。\n"
        )

        metadata = {
            "title": title,
            "original_url": url,
            "platform": "apple_music",
            "track_name": track_name,
            "artist": artist_name,
            "album": album_name,
            "sidecar_text": markdown_body,
            "author": {"name": artist_name},
            "metrics": {"duration_seconds": duration_ms // 1000}
        }

        return AssetPackage(
            platform="apple_music",
            title=title,
            original_url=url,
            assets=assets,
            metadata=metadata
        )

    def _extract_spotify(self, url: str, session: requests.Session) -> AssetPackage:
        m = self.SPOTIFY_TRACK_REGEX.search(url)
        if not m:
            raise ExtractionError(f"Could not parse valid Spotify track ID from: {url}")
        track_id = m.group(1)

        oembed_url = f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{track_id}"
        try:
            r = session.get(oembed_url, timeout=10)
            data = r.json()
        except Exception as e:
            raise ExtractionError(f"Failed to query Spotify oEmbed API: {e}")

        title_raw = data.get("title", f"spotify_{track_id}")
        cover_url = data.get("thumbnail_url")

        # Query audio stream
        stream_url, filesize = self._find_audio_stream(title_raw, "")
        if not stream_url:
            raise ExtractionError(f"Could not resolve audio stream for Spotify track '{title_raw}'")

        assets: List[TargetAsset] = [
            TargetAsset(
                filename="content.mp3",
                url=stream_url,
                file_type="primary",
                expected_size=filesize,
                headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"]}
            )
        ]

        if cover_url:
            assets.append(TargetAsset(
                filename="cover.jpg",
                url=cover_url,
                file_type="cover",
                headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"]}
            ))

        markdown_body = (
            f"# {title_raw}\n\n"
            f"> - **平台**: Spotify (ID: `{track_id}`)\n"
            f"> - **来源网址**: <{url}>\n\n"
            f"---\n"
            f"已提取 Spotify 官方曲目信息与封面，并通过公开音源匹配保存 MP3 音频。\n"
        )

        metadata = {
            "title": title_raw,
            "original_url": url,
            "platform": "spotify",
            "sidecar_text": markdown_body,
            "author": {"name": "Spotify Creator"}
        }

        return AssetPackage(
            platform="spotify",
            title=title_raw,
            original_url=url,
            assets=assets,
            metadata=metadata
        )

    def _find_audio_stream(self, track_name: str, artist_name: str) -> Tuple[Optional[str], Optional[int]]:
        try:
            import yt_dlp
            query = f"ytsearch1:{artist_name} {track_name} Official Audio".strip()
            ydl_opts = {
                "quiet": True,
                "skip_download": True,
                "extract_flat": False,
                "format": "bestaudio/best"
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=False)
                if info and "entries" in info and info["entries"]:
                    match = info["entries"][0]
                    formats = match.get("formats", [])
                    audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("url")]
                    if audio_formats:
                        audio_formats.sort(key=lambda x: (x.get("abr") or 0, x.get("tbr") or 0), reverse=True)
                        best = audio_formats[0]
                        return best["url"], best.get("filesize") or best.get("filesize_approx")
                    if match.get("url"):
                        return match["url"], match.get("filesize")
        except Exception:
            pass
        return None, None
