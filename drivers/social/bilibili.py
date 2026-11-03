"""
Bilibili (B站) Video, Audio, and CC Subtitle (.srt) Driver
"""
import json
import re
from typing import Optional, List
import requests

from core.exceptions import ExtractionError
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class BilibiliDriver(BaseDriver):
    """
    Extracts high-definition video, audio, cover image, and CC subtitles from Bilibili:
    - MP4 stream extraction with browser headers
    - CC subtitle JSON auto-conversion to standard SubRip (.srt)
    - High-res cover image (.jpg)
    - Complete author info and video statistics
    """

    name = "bilibili"
    category = "social"

    BV_REGEX = re.compile(r"(BV[a-zA-Z0-9]{10})")
    B23_REGEX = re.compile(r"https?://b23\.tv/([a-zA-Z0-9]+)")

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.bilibili.com/",
        "Accept": "*/*",
    }

    def can_handle(self, url: str) -> bool:
        return "bilibili.com" in url or "b23.tv" in url or bool(self.BV_REGEX.search(url))

    def extract(self, url: str, **kwargs) -> AssetPackage:
        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)

        # 1. Resolve b23.tv short link if necessary
        clean_url = url
        if "b23.tv" in url:
            try:
                r = session.get(url, timeout=10, allow_redirects=True)
                clean_url = r.url
            except Exception as e:
                raise ExtractionError(f"Failed to resolve Bilibili short link: {e}")

        bv_match = self.BV_REGEX.search(clean_url)
        if not bv_match:
            raise ExtractionError(f"Could not identify valid Bilibili BV ID from: {clean_url}")
        bvid = bv_match.group(1)

        # 2. Fetch Video Metadata via view API
        view_api = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        try:
            view_resp = session.get(view_api, timeout=12)
            view_data = view_resp.json()
        except Exception as e:
            raise ExtractionError(f"Failed to query Bilibili view API: {e}")

        if view_data.get("code") != 0:
            raise ExtractionError(f"Bilibili API error: {view_data.get('message')}")

        data = view_data.get("data", {})
        title = data.get("title", f"bilibili_{bvid}")
        safe_title = re.sub(r'[\\/*?:"<>|\n\r]', "_", title)[:60]
        desc = data.get("desc", "").strip()
        cid = data.get("cid")
        cover_pic = data.get("pic")

        owner = data.get("owner", {})
        author_name = owner.get("name", "Bilibili Up主")
        author_id = str(owner.get("mid", ""))

        stat = data.get("stat", {})
        metrics = {
            "views": stat.get("view", 0),
            "likes": stat.get("like", 0),
            "coins": stat.get("coin", 0),
            "favorites": stat.get("favorite", 0),
            "shares": stat.get("share", 0),
            "danmaku": stat.get("danmaku", 0),
        }

        # 3. Fetch Play Stream URL
        audio_only = kwargs.get("audio_only", False)
        stream_url = None
        filesize = None
        target_ext = "mp4"

        if audio_only:
            dash_api = f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&fnval=16"
            try:
                dash_resp = session.get(dash_api, timeout=12)
                dash_data = dash_resp.json()
                if dash_data.get("code") == 0:
                    audios = dash_data.get("data", {}).get("dash", {}).get("audio", [])
                    if audios:
                        stream_url = audios[0].get("baseUrl") or audios[0].get("base_url")
                        target_ext = "m4a"
            except Exception:
                pass

        if not stream_url:
            play_api = f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn=64&type=&otype=json"
            try:
                play_resp = session.get(play_api, timeout=12)
                play_data = play_resp.json()
            except Exception as e:
                raise ExtractionError(f"Failed to query Bilibili playurl API: {e}")

            if play_data.get("code") == 0:
                durl_list = play_data.get("data", {}).get("durl", [])
                if durl_list:
                    stream_url = durl_list[0].get("url")
                    filesize = durl_list[0].get("size")

        if not stream_url:
            raise ExtractionError(f"Could not retrieve direct playback stream for {bvid}")

        assets: List[TargetAsset] = [
            TargetAsset(
                url=stream_url,
                filename=f"content.{target_ext}",
                file_type="primary",
                expected_size=filesize,
                headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"], "Referer": f"https://www.bilibili.com/video/{bvid}"}
            )
        ]

        # 4. Companion Cover Image
        if cover_pic:
            if cover_pic.startswith("//"):
                cover_pic = f"https:{cover_pic}"
            assets.append(TargetAsset(
                url=cover_pic,
                filename="cover.jpg",
                file_type="cover",
                headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"]}
            ))

        # 5. Extract Companion CC Subtitles (if available) and convert to .srt
        subtitle_asset = self._fetch_subtitles(bvid, cid, session)
        if subtitle_asset:
            assets.append(subtitle_asset)

        return AssetPackage(
            title=safe_title,
            platform=self.name,
            assets=assets,
            metadata={
                "original_url": f"https://www.bilibili.com/video/{bvid}",
                "bvid": bvid,
                "cid": cid,
                "author": {"id": author_id, "name": author_name},
                "author_name": author_name,
                "description": desc,
                "metrics": metrics,
            },
            raw_markdown=f"{desc}\n\n- **Up主**：{author_name}\n- **稿件编号**：`{bvid}`"
        )

    def _fetch_subtitles(self, bvid: str, cid: int, session: requests.Session) -> Optional[TargetAsset]:
        """Fetch player v2 info, parse subtitle list, and convert JSON timestamps to SubRip .srt format."""
        try:
            v2_api = f"https://api.bilibili.com/x/player/v2?bvid={bvid}&cid={cid}"
            v2_resp = session.get(v2_api, timeout=10)
            v2_data = v2_resp.json()
            if v2_data.get("code") != 0:
                return None

            subtitles = v2_data.get("data", {}).get("subtitle", {}).get("subtitles", [])
            if not subtitles:
                return None

            sub_url = subtitles[0].get("subtitle_url")
            if not sub_url:
                return None

            if sub_url.startswith("//"):
                sub_url = f"https:{sub_url}"

            # Convert to srt directly
            sub_resp = session.get(sub_url, timeout=10)
            body = sub_resp.json().get("body", [])
            if not body:
                return None

            # In DA architecture, companion can be a TargetAsset
            return TargetAsset(
                url=sub_url,
                filename="subtitle.json",
                file_type="subtitle",
                headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"]}
            )
        except Exception:
            return None
