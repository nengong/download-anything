"""
Douyin (抖音 / TikTok) Watermark-Free MP4 Video Driver
"""
import json
import re
from typing import Optional, List
import requests

from core.exceptions import ExtractionError
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class DouyinDriver(BaseDriver):
    """
    Extracts watermark-free video from Douyin:
    - High-res unwatermarked MP4 (replaces playwm -> play)
    - Full companion assets: official cover image & audio soundtrack
    - Structured caption, author information, and engagement metrics
    """

    name = "douyin"
    category = "social"

    URL_REGEX = re.compile(r"https?://(?:v\.douyin\.com/[a-zA-Z0-9]+|(?:www\.)?douyin\.com/video/(\d+)|(?:www\.)?iesdouyin\.com/share/video/(\d+))")

    MOBILE_UA = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_1 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3.1 "
        "Mobile/15E148 Safari/604.1"
    )

    def can_handle(self, url: str) -> bool:
        return bool(self.URL_REGEX.search(url))

    def extract(self, url: str, **kwargs) -> AssetPackage:
        session = requests.Session()
        session.headers.update({
            "User-Agent": self.MOBILE_UA,
            "Accept-Language": "zh-CN,zh;q=0.9",
        })

        # 1. Follow short link redirect to obtain real video ID
        try:
            resp = session.get(url, timeout=15, allow_redirects=True)
            final_url = resp.url
        except Exception as e:
            raise ExtractionError(f"Failed to resolve Douyin URL {url}: {e}")

        vid_match = re.search(r"/video/(\d+)", final_url)
        if not vid_match:
            raise ExtractionError(f"Could not extract Douyin video ID from: {final_url}")
        video_id = vid_match.group(1)

        # 2. Fetch share page metadata
        share_url = f"https://www.iesdouyin.com/share/video/{video_id}/"
        try:
            share_resp = session.get(share_url, timeout=15)
            html = share_resp.text
        except Exception as e:
            raise ExtractionError(f"Failed to fetch Douyin share page: {e}")

        # 3. Parse _ROUTER_DATA
        item_data = self._parse_router_data(html, video_id)
        if not item_data:
            # Fallback regex extraction from HTML
            item_data = self._fallback_regex_extract(html)

        if not item_data:
            raise ExtractionError("Failed to parse Douyin video metadata from page.")

        title = (item_data.get("desc") or f"douyin_video_{video_id}").strip()
        safe_title = re.sub(r'[\\/*?:"<>|\n\r]', "_", title)[:60]

        author_info = item_data.get("author", {})
        author_name = author_info.get("nickname", "Douyin Creator")
        author_id = author_info.get("uid") or author_info.get("unique_id", "")

        stats = item_data.get("statistics", {})
        metrics = {
            "likes": stats.get("digg_count", 0),
            "comments_count": stats.get("comment_count", 0),
            "shares": stats.get("share_count", 0),
            "collects": stats.get("collect_count", 0),
        }

        # 4. Resolve unwatermarked MP4 URL
        video_obj = item_data.get("video", {})
        play_urls = video_obj.get("play_addr", {}).get("url_list", [])
        if not play_urls and "play_addr_lowbr" in video_obj:
            play_urls = video_obj["play_addr_lowbr"].get("url_list", [])

        if not play_urls:
            raise ExtractionError("No video download stream available for this Douyin note.")

        raw_play_url = play_urls[0]
        # Replace playwm (watermark) with play (clean)
        clean_play_url = raw_play_url.replace("playwm", "play")

        assets: List[TargetAsset] = [
            TargetAsset(
                url=clean_play_url,
                filename="content.mp4",
                file_type="primary",
                headers={"User-Agent": self.MOBILE_UA, "Referer": "https://www.douyin.com/"}
            )
        ]

        # 5. Companion Cover Image
        cover_urls = video_obj.get("cover", {}).get("url_list", []) or video_obj.get("origin_cover", {}).get("url_list", [])
        if cover_urls:
            assets.append(TargetAsset(
                url=cover_urls[0],
                filename="cover.jpg",
                file_type="cover",
                headers={"User-Agent": self.MOBILE_UA}
            ))

        # 6. Companion Audio Track
        music_obj = item_data.get("music", {})
        music_urls = music_obj.get("play_url", {}).get("url_list", [])
        if music_urls:
            assets.append(TargetAsset(
                url=music_urls[0],
                filename="audio.mp3",
                file_type="extra",
                headers={"User-Agent": self.MOBILE_UA}
            ))

        return AssetPackage(
            title=safe_title,
            platform=self.name,
            assets=assets,
            metadata={
                "original_url": url,
                "video_id": video_id,
                "author": {"id": author_id, "name": author_name},
                "author_name": author_name,
                "description": item_data.get("desc", ""),
                "metrics": metrics,
            },
            raw_markdown=f"{title}\n\n- **创作者**：{author_name}\n- **原声音乐**：{music_obj.get('title', '默认音乐')}"
        )

    def _parse_router_data(self, html: str, video_id: str) -> Optional[dict]:
        match = re.search(r"window\._ROUTER_DATA\s*=\s*(\{.*?\});\s*</script>", html, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(1))
            loader = data.get("loaderData", {})
            # Look for item in loader data
            for key, val in loader.items():
                if isinstance(val, dict) and "videoInfoRes" in val:
                    items = val["videoInfoRes"].get("item_list", [])
                    if items:
                        return items[0]
        except Exception:
            pass
        return None

    def _fallback_regex_extract(self, html: str) -> Optional[dict]:
        # Minimal fallback if _ROUTER_DATA structure changed
        play_match = re.search(r'"play_addr":\{"uri":"[^"]+","url_list":\["([^"]+)"', html)
        desc_match = re.search(r'<title>([^<_\-]+)', html)
        if play_match:
            return {
                "desc": desc_match.group(1).strip() if desc_match else "douyin_video",
                "video": {
                    "play_addr": {
                        "url_list": [play_match.group(1).replace("\\u0026", "&")]
                    }
                }
            }
        return None
