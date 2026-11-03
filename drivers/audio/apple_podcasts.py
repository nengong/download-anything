"""
Apple Podcasts Master Audio, Shownotes, and Artwork Extractor Driver
"""
import re
from typing import Optional, Dict, Any, List
import requests
from bs4 import BeautifulSoup
from drivers.base import BaseDriver, AssetPackage, AssetFile
from core.exceptions import ExtractionError

class ApplePodcastsDriver(BaseDriver):
    """Driver for extracting Apple Podcasts master MP3/M4A audio, shownotes, and high-res cover."""

    APPLE_PODCASTS_REGEX = re.compile(
        r"https?://podcasts\.apple\.com/(?:[a-zA-Z-]+/)?podcast/(?:[^/]+/)?id(?P<podcast_id>\d+)(?:\?i=(?P<episode_id>\d+))?"
    )

    def can_handle(self, url: str) -> bool:
        return bool(self.APPLE_PODCASTS_REGEX.search(url))

    def extract(self, url: str, password: Optional[str] = None, **kwargs) -> AssetPackage:
        m = self.APPLE_PODCASTS_REGEX.search(url)
        if not m:
            raise ExtractionError(f"Invalid Apple Podcasts URL: {url}")
        podcast_id = m.group("podcast_id")
        episode_id = m.group("episode_id")

        lookup_url = f"https://itunes.apple.com/lookup?id={podcast_id}&entity=podcastEpisode&limit=300"
        try:
            r = requests.get(lookup_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
            data = r.json()
        except Exception as e:
            raise ExtractionError(f"Failed to query Apple iTunes podcast API: {e}")

        results = data.get("results", [])
        if not results:
            raise ExtractionError(f"Podcast {podcast_id} not found on Apple Podcasts.")

        podcast_info = results[0]
        podcast_title = podcast_info.get("trackName") or podcast_info.get("collectionName") or "Apple Podcast"
        artist_name = podcast_info.get("artistName") or "Podcast Host"
        artwork_url = podcast_info.get("artworkUrl600") or podcast_info.get("artworkUrl100")
        feed_url = podcast_info.get("feedUrl")

        # Find target episode
        target_ep = None
        episodes = results[1:]
        if episode_id:
            for ep in episodes:
                if str(ep.get("trackId")) == str(episode_id):
                    target_ep = ep
                    break
        elif episodes:
            target_ep = episodes[0]

        # If not found in top 300, try RSS feed fallback
        if not target_ep and feed_url and episode_id:
            try:
                fr = requests.get(feed_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                soup = BeautifulSoup(fr.text, "xml")
                for item in soup.find_all("item"):
                    guid = item.find("guid")
                    enclosure = item.find("enclosure")
                    if enclosure and enclosure.get("url"):
                        # If episode ID matches or guid matches
                        ep_title = item.find("title").text if item.find("title") else "Podcast Episode"
                        target_ep = {
                            "trackName": ep_title,
                            "episodeUrl": enclosure["url"],
                            "description": item.find("description").text if item.find("description") else "",
                            "releaseDate": item.find("pubDate").text if item.find("pubDate") else "",
                        }
                        break
            except Exception:
                pass

        if not target_ep or not target_ep.get("episodeUrl"):
            raise ExtractionError(f"Could not locate playable audio stream for episode {episode_id or 'latest'}.")

        ep_title = target_ep.get("trackName") or f"episode_{episode_id}"
        audio_url = target_ep["episodeUrl"]
        ext = "m4a" if ".m4a" in audio_url.lower() else "mp3"
        description = target_ep.get("description") or ""
        release_date = target_ep.get("releaseDate") or ""
        duration_ms = target_ep.get("trackTimeMillis") or 0

        assets = [
            AssetFile(
                filename=f"content.{ext}",
                url=audio_url,
                file_type="primary",
                headers={"User-Agent": "Mozilla/5.0"}
            )
        ]

        ep_artwork = target_ep.get("artworkUrl600") or artwork_url
        if ep_artwork:
            assets.append(
                AssetFile(
                    filename="cover.jpg",
                    url=ep_artwork,
                    file_type="cover",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
            )

        metadata = {
            "title": ep_title,
            "original_url": url,
            "author": {
                "id": str(podcast_id),
                "name": f"{artist_name} ({podcast_title})",
            },
            "created_at": str(release_date),
            "metrics": {
                "duration_seconds": int(duration_ms / 1000) if duration_ms else 0,
            },
            "sidecar_text": f"# {ep_title}\n\n**Podcast**: {podcast_title}\n**Host**: {artist_name}\n**Published**: {release_date}\n\n---\n\n## Shownotes\n\n{description}",
        }

        return AssetPackage(
            platform="apple_podcasts",
            title=ep_title,
            original_url=url,
            assets=assets,
            metadata=metadata
        )
