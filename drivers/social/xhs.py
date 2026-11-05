"""
Xiaohongshu (小红书) High-Res Images, LivePhoto, and Watermark-Free Video Driver
"""
import json
import re
from typing import Optional, List
from urllib.parse import quote
import requests

from core.exceptions import ExtractionError
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class XiaohongshuDriver(BaseDriver):
    """
    Extracts high-resolution unwatermarked media from Xiaohongshu (RED):
    - Multi-image photo sets (high-res WebP/JPEG)
    - LivePhoto dual-assets (.heic / .jpg + .mov video component)
    - Original unwatermarked video streams (.mp4)
    - Full note copy, title, author info, tags, and interaction metrics
    """

    name = "xiaohongshu"
    category = "social"

    URL_REGEX = re.compile(r"https?://(?:www\.)?(?:xhslink\.com|xiaohongshu\.com/(?:explore|discovery/item)/)([a-zA-Z0-9_]+)")

    MOBILE_UA = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_1 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3.1 "
        "Mobile/15E148 Safari/604.1"
    )
    IMG_VIEW = "imageView2/2/w/0/format/jpg/v3"

    def can_handle(self, url: str) -> bool:
        return "xhslink.com" in url or "xhslink.cn" in url or "xiaohongshu.com" in url

    def extract(self, url: str, **kwargs) -> AssetPackage:
        session = requests.Session()
        session.headers.update({
            "User-Agent": self.MOBILE_UA,
            "Accept-Language": "zh-CN,zh;q=0.9",
        })

        # 1. Resolve redirect if short link (xhslink.com)
        try:
            resp = session.get(url, timeout=15, allow_redirects=True)
            resp.raise_for_status()
            html = resp.text
            final_url = resp.url
        except Exception as e:
            raise ExtractionError(f"Failed to access Xiaohongshu note: {e}")

        # Check for risk / blocked page
        if "/404/sec_" in final_url or "source=xhs_sec_server" in final_url:
            raise ExtractionError("Xiaohongshu link encountered anti-scraping security challenge or expired.")

        # 2. Extract __INITIAL_STATE__
        note_data = self._extract_initial_state(html)
        if not note_data:
            raise ExtractionError("Failed to parse Xiaohongshu page state (note may be private, deleted, or expired).")

        title = (note_data.get("title") or note_data.get("desc") or "xiaohongshu_note").strip()
        safe_title = re.sub(r'[\\/*?:"<>|\n\r]', "_", title)[:60]
        desc = note_data.get("desc", "").strip()

        # Author and stats
        user_info = note_data.get("user", {})
        author_id = user_info.get("userId", "")
        author_name = user_info.get("nickname", "XHS Creator")

        interact = note_data.get("interactInfo", {})
        metrics = {
            "likes": interact.get("likedCount", 0),
            "collects": interact.get("collectedCount", 0),
            "comments_count": interact.get("commentCount", 0),
            "shares": interact.get("shareCount", 0),
        }

        tag_list = [t.get("name", "") for t in (note_data.get("tagList") or []) if t.get("name")]

        assets: List[TargetAsset] = []

        # 3. Check Video Note
        video_info = note_data.get("video")
        if video_info and isinstance(video_info, dict):
            # 3.1 Prefer unwatermarked raw origin video stream via originVideoKey
            origin_key = (
                (video_info.get("consumer") or {}).get("originVideoKey")
                or video_info.get("originVideoKey")
            )
            if not origin_key and html:
                m_key = re.search(r'originVideoKey["\':\s]+([^\'",\s\\}]+(?:\\u002F[^\'",\s\\}]+)*)', html)
                if m_key:
                    origin_key = m_key.group(1).replace(r"\u002F", "/")

            video_url = None
            watermark_status = "platform_watermark"
            watermark_note = "未暴露originVideoKey，已回退为网页自适应预览流（含平台水印）"

            if origin_key:
                clean_key = str(origin_key).replace(r"\u002F", "/").lstrip("/")
                video_url = f"https://sns-video-bd.xhscdn.com/{clean_key}"
                watermark_status = "clean"
                watermark_note = "通过originVideoKey提取创作者无水印母带源"

            # 3.2 Fallback to adaptive preview stream if originVideoKey is not exposed
            if not video_url:
                media = video_info.get("media", {})
                stream = media.get("stream", {})
                for codec in ("h264", "h265", "av1"):
                    arr = stream.get(codec) or []
                    for s in arr:
                        if isinstance(s, dict) and s.get("masterUrl"):
                            video_url = s["masterUrl"]
                            break
                    if video_url:
                        break

            if video_url:
                assets.append(TargetAsset(
                    url=video_url,
                    filename="content.mp4",
                    file_type="primary",
                    headers={"User-Agent": self.MOBILE_UA, "Referer": "https://www.xiaohongshu.com/"}
                ))

        # 4. Check Image Set / LivePhotos
        images_raw = [im for im in (note_data.get("imageList") or []) if isinstance(im, dict)]
        if not assets and images_raw:
            # Multi-image note: first image is primary, others are companion
            for idx, im in enumerate(images_raw, start=1):
                fid = str(im.get("fileId") or im.get("traceId") or "").strip()
                img_url = f"https://sns-img-bd.xhscdn.com/{fid}?{self.IMG_VIEW}" if fid else ""
                if not img_url:
                    info_list = im.get("infoList") or []
                    for item in info_list:
                        if isinstance(item, dict) and item.get("url"):
                            img_url = item["url"]
                            break

                if not img_url:
                    continue

                file_type = "primary" if idx == 1 else "extra"
                ext = "jpg"
                img_filename = f"image_{idx:02d}.{ext}" if len(images_raw) > 1 else f"content.{ext}"

                assets.append(TargetAsset(
                    url=img_url,
                    filename=img_filename,
                    file_type=file_type,
                    headers={"User-Agent": self.MOBILE_UA, "Referer": "https://www.xiaohongshu.com/"}
                ))

                # If LivePhoto, extract accompanying .mov video stream
                if im.get("livePhoto"):
                    live_streams = im.get("stream") or {}
                    live_mov_url = None
                    for codec in ("h264", "h265"):
                        l_arr = live_streams.get(codec) or []
                        if l_arr and isinstance(l_arr[0], dict):
                            live_mov_url = l_arr[0].get("masterUrl")
                            if live_mov_url:
                                break
                    if live_mov_url:
                        assets.append(TargetAsset(
                            url=live_mov_url,
                            filename=f"image_{idx:02d}_live.mov",
                            file_type="extra",
                            headers={"User-Agent": self.MOBILE_UA, "Referer": "https://www.xiaohongshu.com/"}
                        ))

        if not assets:
            raise ExtractionError("No downloadable media streams found in this Xiaohongshu note.")

        # Companion cover
        cover_url = None
        if images_raw:
            fid0 = str(images_raw[0].get("fileId") or images_raw[0].get("traceId") or "").strip()
            if fid0:
                cover_url = f"https://sns-img-bd.xhscdn.com/{fid0}?{self.IMG_VIEW}"
        if cover_url and assets[0].file_type == "primary" and assets[0].filename != "cover.jpg" and not assets[0].filename.startswith("image_01"):
            assets.append(TargetAsset(
                url=cover_url,
                filename="cover.jpg",
                file_type="cover",
                headers={"User-Agent": self.MOBILE_UA, "Referer": "https://www.xiaohongshu.com/"}
            ))

        meta = {
            "original_url": url,
            "author": {"id": author_id, "name": author_name},
            "author_name": author_name,
            "metrics": metrics,
            "tags": tag_list,
            "description": desc,
            "watermark_status": watermark_status if video_info else "clean",
            "watermark_note": watermark_note if video_info else "小红书图文无水印原图",
        }

        return AssetPackage(
            title=safe_title,
            platform=self.name,
            assets=assets,
            metadata=meta,
            raw_markdown=f"{desc}\n\n" + " ".join(f"#{t}" for t in tag_list)
        )

    def _extract_initial_state(self, html: str) -> Optional[dict]:
        """Extract noteData from window.__INITIAL_STATE__ with bracket balancing."""
        for m in re.finditer(r"window\.__INITIAL_STATE__\s*=\s*", html or ""):
            i = m.end()
            if i >= len(html) or html[i] != "{":
                continue
            depth, instr, esc = 0, False, False
            for j in range(i, len(html)):
                c = html[j]
                if esc:
                    esc = False
                    continue
                if c == "\\":
                    esc = True
                    continue
                if c == '"':
                    instr = not instr
                    continue
                if instr:
                    continue
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        blob = html[i : j + 1].replace("\\u002F", "/").replace("undefined", "null")
                        try:
                            data = json.loads(blob)
                        except json.JSONDecodeError:
                            break
                        nd = (data.get("noteData", {}).get("data", {}) or {}).get("noteData")
                        if isinstance(nd, dict) and (nd.get("imageList") or nd.get("title") or nd.get("desc") or nd.get("video")):
                            return nd
                        break
        return None
