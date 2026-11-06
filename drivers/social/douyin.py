"""
Douyin (抖音) Watermark-Free MP4 Video & Multi-Image Driver
"""
import json
import re
import urllib.parse
from typing import Optional, List
import requests

from core.credentials import credentials_manager
from core.exceptions import ExtractionError
from core.url_policy import is_http_url, scoped_cookies
from drivers.base import BaseDriver, AssetPackage, TargetAsset


class DouyinDriver(BaseDriver):
    """
    Extracts watermark-free video or image notes from Douyin:
    - High-res unwatermarked MP4 (via _ROUTER_DATA / mobile share / third-party fallback)
    - Companion files: official cover image & audio soundtrack
    - Structured caption, author information, and engagement metrics
    """

    name = "douyin"
    category = "social"

    URL_REGEX = re.compile(
        r"https?://(?:v\.douyin\.com/[a-zA-Z0-9_\-]+|"
        r"(?:www\.)?douyin\.com/(?:video|note)/(\d+)|"
        r"(?:www\.)?iesdouyin\.com/share/(?:video|note)/(\d+))"
    )
    ID_REGEX = re.compile(r"(?:/(?:video|note)/(\d+)|modal_id=(\d+))")

    MOBILE_UA = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1_1 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1.1 "
        "Mobile/15E148 Safari/604.1"
    )

    API_PRIMARY = "http://api.suxun.site/api/douyin"
    API_FALLBACK = "https://api.xhus.cn/api/douyin"

    def can_handle(self, url: str) -> bool:
        return is_http_url(url, ("douyin.com", "iesdouyin.com")) or bool(self.URL_REGEX.search(url or ""))

    def extract(self, url: str, **kwargs) -> AssetPackage:
        if not self.can_handle(url):
            raise ExtractionError("Invalid Douyin URL")

        session = requests.Session()
        session.headers.update({
            "User-Agent": self.MOBILE_UA,
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        cookie = credentials_manager.get_credential("douyin", "cookie")
        if cookie:
            session.cookies.update(scoped_cookies(cookie, "douyin.com"))

        clean_url = url.strip()

        # 1. Try native mobile share page (_ROUTER_DATA / SSR state) first or after redirect
        try:
            resp = session.get(clean_url, timeout=15, allow_redirects=True)
            final_url = resp.url
            html = resp.text or ""

            pkg = self._extract_from_router_data(html, url)
            if pkg:
                return pkg

            vid_match = self.ID_REGEX.search(final_url) or self.ID_REGEX.search(clean_url)
            video_id = (vid_match.group(1) or vid_match.group(2)) if vid_match else None

            if video_id:
                for share_kind in ("video", "note"):
                    share_url = f"https://www.iesdouyin.com/share/{share_kind}/{video_id}/"
                    if share_url != final_url:
                        share_resp = session.get(share_url, timeout=15)
                        pkg = self._extract_from_router_data(share_resp.text or "", url, video_id=video_id)
                        if pkg:
                            return pkg
                        if share_resp.text:
                            html = share_resp.text

                # Legacy regex fallback on share HTML
                play_match = re.search(r'"play_addr":\{"uri":"([^"]+)","url_list":\["([^"]+)"', html)
                desc_match = re.search(r'<title>([^<_\-]+)', html)
                if play_match:
                    uri, raw_play_url = play_match.group(1), play_match.group(2)
                    clean_play_url = (
                        raw_play_url.replace(r"\u002F", "/")
                        .replace(r"\u0026", "&")
                        .replace("playwm", "play")
                    )
                    if not clean_play_url.startswith("http") and uri:
                        clean_play_url = f"https://aweme.snssdk.com/aweme/v1/play/?video_id={uri}&ratio=1080p&line=0"
                    title = desc_match.group(1).strip() if desc_match else f"douyin_{video_id}"
                    safe_title = re.sub(r'[\\/*?:"<>|\n\r]', "_", title)[:60]
                    primary = TargetAsset(
                        url=clean_play_url,
                        filename="content.mp4",
                        file_type="primary",
                        headers={"User-Agent": self.MOBILE_UA, "Referer": "https://www.douyin.com/"},
                    )
                    return AssetPackage(
                        title=safe_title,
                        platform=self.name,
                        assets=[primary],
                        metadata={"original_url": url, "video_id": video_id},
                        raw_markdown=title,
                    )
        except Exception:
            pass

        # 2. Try public Douyin resolve APIs
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

        # 3. Last resort: yt-dlp fallback
        try:
            from drivers.social.ytdlp_fallback import YtDlpFallbackDriver
            pkg = YtDlpFallbackDriver().extract(clean_url, **kwargs)
            pkg.platform = self.name
            return pkg
        except Exception:
            pass

        raise ExtractionError("Douyin extraction failed: Failed to extract video stream from Douyin page.")

    def _extract_from_router_data(
        self, html: str, original_url: str, video_id: Optional[str] = None
    ) -> Optional[AssetPackage]:
        """Parse window._ROUTER_DATA embedded in Douyin / iesdouyin mobile share HTML."""
        if not html or "_ROUTER_DATA" not in html:
            return None

        m = re.search(r"window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*(?:;|</script>)", html, re.S)
        if not m:
            return None

        try:
            router_data = json.loads(m.group(1))
        except Exception:
            return None

        loader = router_data.get("loaderData")
        if not isinstance(loader, dict):
            return None

        item = None
        for val in loader.values():
            if isinstance(val, dict) and isinstance(val.get("videoInfoRes"), dict):
                item_list = val["videoInfoRes"].get("item_list") or []
                if item_list and isinstance(item_list[0], dict):
                    item = item_list[0]
                    break

        if not item:
            return None

        aweme_id = str(item.get("aweme_id") or video_id or "")
        desc = (item.get("desc") or f"douyin_{aweme_id or 'video'}").strip()
        safe_title = re.sub(r'[\\/*?:"<>|\n\r]', "_", desc)[:60] or "douyin_video"

        author_obj = item.get("author") if isinstance(item.get("author"), dict) else {}
        author_name = author_obj.get("nickname") or "Douyin Creator"
        author_id = str(author_obj.get("uid") or author_obj.get("sec_uid") or "")

        stats = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
        metrics = {
            "likes": stats.get("digg_count", 0),
            "comments": stats.get("comment_count", 0),
            "collects": stats.get("collect_count", 0),
            "shares": stats.get("share_count", 0),
        }

        assets: List[TargetAsset] = []

        # Image note (图文) check
        images = item.get("images")
        if isinstance(images, list) and images:
            for idx, img in enumerate(images, start=1):
                if not isinstance(img, dict):
                    continue
                url_list = img.get("url_list") or []
                if url_list:
                    img_url = str(url_list[0]).replace(r"\u002F", "/").replace(r"\u0026", "&")
                    role = "primary" if idx == 1 else "extra"
                    fname = f"image_{idx:02d}.jpg" if len(images) > 1 else "content.jpg"
                    assets.append(
                        TargetAsset(
                            url=img_url,
                            filename=fname,
                            file_type=role,
                            headers={"User-Agent": self.MOBILE_UA, "Referer": "https://www.douyin.com/"},
                        )
                    )

        # Video check
        video_obj = item.get("video") if isinstance(item.get("video"), dict) else {}
        if not assets and video_obj:
            play_addr = video_obj.get("play_addr") if isinstance(video_obj.get("play_addr"), dict) else {}
            uri = play_addr.get("uri") or ""
            url_list = play_addr.get("url_list") or []
            play_url = ""
            if url_list:
                play_url = (
                    str(url_list[0])
                    .replace(r"\u002F", "/")
                    .replace(r"\u0026", "&")
                    .replace("playwm", "play")
                )
            elif uri:
                play_url = f"https://aweme.snssdk.com/aweme/v1/play/?video_id={uri}&ratio=1080p&line=0"

            if play_url:
                assets.append(
                    TargetAsset(
                        url=play_url,
                        filename="content.mp4",
                        file_type="primary",
                        headers={"User-Agent": self.MOBILE_UA, "Referer": "https://www.douyin.com/"},
                    )
                )

            # Cover image: prefer full-res origin_cover over compressed 640x360 cover thumbnail
            cover_obj = video_obj.get("origin_cover") or video_obj.get("cover") or {}
            cover_urls = cover_obj.get("url_list") if isinstance(cover_obj, dict) else None
            if cover_urls:
                assets.append(
                    TargetAsset(
                        url=str(cover_urls[0]).replace(r"\u002F", "/").replace(r"\u0026", "&"),
                        filename="cover.jpg",
                        file_type="cover",
                        headers={"User-Agent": self.MOBILE_UA},
                    )
                )

        if not assets:
            return None

        # Optional audio soundtrack
        music_obj = item.get("music") if isinstance(item.get("music"), dict) else {}
        play_url_obj = music_obj.get("play_url") if isinstance(music_obj.get("play_url"), dict) else {}
        music_urls = play_url_obj.get("url_list") or []
        if music_urls and str(music_urls[0]).startswith("http"):
            assets.append(
                TargetAsset(
                    url=str(music_urls[0]).replace(r"\u002F", "/").replace(r"\u0026", "&"),
                    filename="audio.mp3",
                    file_type="extra",
                    headers={"User-Agent": self.MOBILE_UA},
                )
            )

        return AssetPackage(
            title=safe_title,
            platform=self.name,
            assets=assets,
            metadata={
                "original_url": original_url,
                "video_id": aweme_id,
                "author": {"id": author_id, "name": author_name},
                "author_name": author_name,
                "description": desc,
                "metrics": metrics,
            },
            raw_markdown=f"{desc}\n\n- **作者**：{author_name}",
        )

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
                headers={"User-Agent": self.MOBILE_UA, "Referer": "https://www.douyin.com/"},
            )
        ]

        cover_val = data.get("origin_cover") or data.get("cover")
        cover_url = cover_val.get("url", "") if isinstance(cover_val, dict) else str(cover_val or "")
        if cover_url:
            assets.append(
                TargetAsset(
                    url=cover_url.replace(r"\u002F", "/"),
                    filename="cover.jpg",
                    file_type="cover",
                    headers={"User-Agent": self.MOBILE_UA},
                )
            )

        music_val = data.get("music")
        music_url = music_val.get("url", "") if isinstance(music_val, dict) else str(music_val or "")
        if music_url:
            assets.append(
                TargetAsset(
                    url=music_url.replace(r"\u002F", "/"),
                    filename="audio.mp3",
                    file_type="extra",
                    headers={"User-Agent": self.MOBILE_UA},
                )
            )

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
            raw_markdown=f"{title}\n\n- **作者**：{author_name}",
        )
