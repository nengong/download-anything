"""
Xiaoyuzhou Podcast (小宇宙播客) Audio and Shownotes Driver
"""
import json
import re
from typing import Optional, List
from bs4 import BeautifulSoup
import requests

from core.exceptions import ExtractionError
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class XiaoyuzhouDriver(BaseDriver):
    """
    Extracts high-fidelity podcast episodes from Xiaoyuzhou (小宇宙):
    - Original master audio stream (.m4a / .mp3)
    - High-resolution episode cover artwork (.jpg)
    - Full structured shownotes, timestamps, and podcast show metadata
    """

    name = "xiaoyuzhou"
    category = "audio"

    URL_REGEX = re.compile(r"https?://(?:www\.)?xiaoyuzhoufm\.com/episode/([a-zA-Z0-9]+)")

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def can_handle(self, url: str) -> bool:
        return "xiaoyuzhoufm.com/episode" in url or bool(self.URL_REGEX.search(url))

    def extract(self, url: str, **kwargs) -> AssetPackage:
        m = self.URL_REGEX.search(url)
        if not m:
            raise ExtractionError(f"Invalid Xiaoyuzhou episode URL: {url}")
        episode_id = m.group(1)

        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)

        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            raise ExtractionError(f"Failed to fetch Xiaoyuzhou episode page: {e}")

        soup = BeautifulSoup(html, "html.parser")

        # 1. Title
        og_title = soup.find("meta", property="og:title")
        title = og_title["content"].strip() if og_title and og_title.get("content") else f"xiaoyuzhou_{episode_id}"
        safe_title = re.sub(r'[\\/*?:"<>|\n\r]', "_", title)[:70]

        # 2. Audio Stream URL
        og_audio = soup.find("meta", property="og:audio")
        if not og_audio or not og_audio.get("content"):
            raise ExtractionError(f"No direct audio stream found in Xiaoyuzhou episode {episode_id}")
        audio_url = og_audio["content"].strip()

        audio_ext = "m4a" if ".m4a" in audio_url else "mp3"
        primary_filename = f"content.{audio_ext}"

        assets: List[TargetAsset] = [
            TargetAsset(
                url=audio_url,
                filename=primary_filename,
                file_type="primary",
                headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"], "Referer": url}
            )
        ]

        # 3. Cover Image
        og_image = soup.find("meta", property="og:image")
        cover_url = og_image["content"].strip() if og_image and og_image.get("content") else None
        if cover_url:
            assets.append(TargetAsset(
                url=cover_url,
                filename="cover.jpg",
                file_type="cover",
                headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"]}
            ))

        # 4. Shownotes & Metadata
        schema_tag = soup.find("script", attrs={"type": "application/ld+json"})
        schema_data = {}
        if schema_tag and schema_tag.string:
            try:
                schema_data = json.loads(schema_tag.string)
            except Exception:
                pass

        description = schema_data.get("description", "")
        if not description:
            desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
            description = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else ""

        podcast_name = schema_data.get("partOfSeries", {}).get("name", "Xiaoyuzhou Podcast")
        published_at = schema_data.get("datePublished", "")
        duration = schema_data.get("timeRequired", "")

        markdown_body = [
            f"# {title}",
            "",
            f"- **所属播客**：{podcast_name}",
            f"- **发布时间**：{published_at}",
            f"- **节目时长**：{duration}",
            f"- **原始链接**：<{url}>",
            "",
            "## 节目介绍与 Shownotes",
            "",
            description
        ]

        return AssetPackage(
            title=safe_title,
            platform=self.name,
            assets=assets,
            metadata={
                "original_url": url,
                "episode_id": episode_id,
                "podcast_title": podcast_name,
                "author": {"id": episode_id, "name": podcast_name},
                "author_name": podcast_name,
                "published_at": published_at,
                "duration": duration,
                "description": description,
            },
            raw_markdown="\n".join(markdown_body)
        )
