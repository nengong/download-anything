"""
Douyin (抖音 / TikTok) Watermark-Free MP4 Video Driver
"""
import json
import re
import urllib.parse
from typing import Optional, List
import requests

from core.exceptions import ExtractionError
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class DouyinDriver(BaseDriver):
    """
    Extracts watermark-free video from Douyin:
    - High-res unwatermarked MP4
    - Companion assets: official cover image & audio soundtrack
    - Structured caption, author information, and engagement metrics
    """

    name = "douyin"
    category = "social"

    URL_REGEX = re.compile(r"https?://(?:v\.douyin\.com/[a-zA-Z0-9]+|(?:www\.)?douyin\.com/video/(\d+)|(?:www\.)?iesdouyin\.com/share/video/(\d+))")

    MOBILE_UA = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1_1 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1.1 "
        "Mobile/15E148 Safari/604.1"
    )

    API_PRIMARY = "http://api.suxun.site/api/douyin"
    API_FALLBACK = "https://api.xhus.cn/api/douyin"

    def can_handle(self, url: str) -> bool:
        return "douyin.com" in url or bool(self.URL_REGEX.search(url))

    def extract(self, url: str, **kwargs) -> AssetPackage:
        session = requests.Session()
        session.headers.update({
            "User-Agent": self.MOBILE_UA,
            "Accept-Language": "zh-CN,zh;q=0.9",
        })

        # 1. Try public Douyin resolve APIs
        clean_url = url.strip()
        encoded = urllib.parse.quote(clean_url, safe="")

        parsed_data = None
        for api_base in (self.API_PRIMARY, self.API_FALLBACK):
            try:
                r = session.get(f"{api_base}?url={encoded}", timeout=15)
                res = r.json()
                if res.get("code") == 200 and isinstance(res.get("data"), dict):
                    parsed_data = res["data"]
                    break
            except Exception:
                continue

        if parsed_data and parsed_data.get("url"):
            return self._build_package_from_api(parsed_data, url)

        # 2. Fallback to direct page scraping
        try:
            resp = session.get(clean_url, timeout=15, allow_redirects=True)
            final_url = resp.url
            vid_match = re.search(r"/video/(\d+)", final_url)
            if not vid_match:
                raise ExtractionError(f"Could not extract Douyin video ID from: {final_url}")
            video_id = vid_match.group(1)

            share_url = f"https://www.iesdouyin.com/share/video/{video_id}/"
            share_resp = session.get(share_url, timeout=15)
            html = share_resp.text

            play_match = re.search(r'"play_addr":\{"uri":"[^"]+","url_list":\["([^"]+)"', html)
            desc_match = re.search(r'<title>([^<_\-]+)', html)
            if not play_match:
                raise ExtractionError("Failed to extract video stream from Douyin page.")

            raw_play_url = play_match.group(1).replace(r"\u002F", "/").replace(r"\u0026", "&")
            clean_play_url = raw_play_url.replace("playwm", "play")
            title = desc_match.group(1).strip() if desc_match else f"douyin_{video_id}"
            safe_title = re.sub(r'[\\/*?:"<>|\n\r]', "_", title)[:60]

            primary = TargetAsset(
                url=clean_play_url,
                filename="content.mp4",
                file_type="primary",
                headers={"User-Agent": self.MOBILE_UA, "Referer": "https://www.douyin.com/"}
            )

            return AssetPackage(
                title=safe_title,
                platform=self.name,
                assets=[primary],
                metadata={"original_url": url, "video_id": video_id},
                raw_markdown=f"{title}"
            )
        except Exception as e:
            raise ExtractionError(f"Douyin extraction failed: {e}")

    def _build_package_from_api(self, data: dict, original_url: str) -> AssetPackage:
        title = (data.get("title") or "douyin_video").strip()
        safe_title = re.sub(r'[\\/*?:"<>|\n\r]', "_", title)[:60]
        video_url = data.get("url", "").replace(r"\u002F", "/").replace(r"\u0026", "&")

        author_obj = data.get("author", {}) if isinstance(data.get("author"), dict) else {}
        author_name = author_obj.get("name") or data.get("author") or "Douyin Creator"
        author_id = str(author_obj.get("uid", ""))

        metrics = {
            "likes": data.get("like", 0),
            "duration_sec": data.get("duration", 0),
        }

        assets: List[TargetAsset] = [
            TargetAsset(
                url=video_url,
                filename="content.mp4",
                file_type="primary",
                headers={"User-Agent": self.MOBILE_UA, "Referer": "https://www.douyin.com/"}
            )
        ]

        # Cover
        cover_val = data.get("cover")
        cover_url = cover_val.get("url", "") if isinstance(cover_val, dict) else str(cover_val or "")
        if cover_url:
            assets.append(TargetAsset(
                url=cover_url.replace(r"\u002F", "/"),
                filename="cover.jpg",
                file_type="cover",
                headers={"User-Agent": self.MOBILE_UA}
            ))

        # Audio music track
        music_val = data.get("music")
        music_url = music_val.get("url", "") if isinstance(music_val, dict) else str(music_val or "")
        if music_url:
            assets.append(TargetAsset(
                url=music_url.replace(r"\u002F", "/"),
                filename="audio.mp3",
                file_type="extra",
                headers={"User-Agent": self.MOBILE_UA}
            ))

        return AssetPackage(
            title=safe_title,
            platform=self.name,
            assets=assets,
            metadata={
                "original_url": original_url,
                "author": {"id": author_id, "name": author_name},
                "author_name": author_name,
                "description": title,
                "metrics": metrics,
            },
            raw_markdown=f"{title}\n\n- **作者**：{author_name}"
        )
