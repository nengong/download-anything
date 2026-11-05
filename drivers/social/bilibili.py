"""
Bilibili (B站) Video, Audio, and CC Subtitle (.srt) Driver
"""
import base64
import json
import re
from typing import Optional, List
import requests

from core.credentials import credentials_manager
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

    TV_APPKEY = "4409e2ce8ffd12b8"
    TV_APPSEC = "59b43e04ad6965f34319062b478f83dd"

    def _get_tv_stream(self, aid: Optional[int], cid: int, session: requests.Session) -> Optional[dict]:
        """Query Bilibili TV client API for clean, watermark-free playback stream."""
        if not aid or not cid:
            return None
        import hashlib
        import time
        import urllib.parse
        params = {
            "appkey": self.TV_APPKEY,
            "avid": str(aid),
            "cid": str(cid),
            "qn": "64",
            "fnver": "0",
            "fnval": "0",
            "fourk": "0",
            "build": "102801",
            "mobi_app": "android_tv_yst",
            "platform": "android",
            "ts": str(int(time.time())),
        }
        sorted_params = sorted(params.items())
        query_string = urllib.parse.urlencode(sorted_params)
        sign = hashlib.md5((query_string + self.TV_APPSEC).encode("utf-8")).hexdigest()
        params["sign"] = sign

        try:
            r = session.get(
                "https://api.bilibili.com/x/tv/ugc/playurl",
                params=params,
                headers={"User-Agent": "Bilibili/1.0.0 (Android TV)"},
                timeout=12
            )
            data = r.json()
            if data.get("code") == 0:
                durls = data.get("durl") or []
                if durls:
                    item = durls[0]
                    wm_flags = data.get("accept_watermark") or []
                    has_wm = any(wm_flags) if wm_flags else False
                    return {
                        "url": item.get("url"),
                        "size": item.get("size"),
                        "has_watermark": has_wm,
                    }
        except Exception:
            pass
        return None

    def can_handle(self, url: str) -> bool:
        from core.url_policy import is_http_url
        return is_http_url(url, ("bilibili.com", "b23.tv")) or bool(self.BV_REGEX.fullmatch(url))

    def extract(self, url: str, **kwargs) -> AssetPackage:
        from core.url_policy import is_http_url, scoped_cookies
        if not self.can_handle(url):
            raise ExtractionError("Invalid Bilibili URL")
        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)
        cookie = credentials_manager.get_credential("bilibili", "cookie")
        if cookie:
            session.cookies.update(scoped_cookies(cookie, "bilibili.com"))

        # 1. Resolve b23.tv short link if necessary
        clean_url = url
        if is_http_url(url, ("b23.tv",)):
            try:
                r = session.get(url, timeout=10, allow_redirects=True)
                clean_url = r.url
                if not is_http_url(clean_url, ("bilibili.com",), https_only=True):
                    raise ExtractionError("Bilibili short link resolved outside its trusted HTTPS domain")
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
        aid = data.get("aid")
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
        download_headers = {"User-Agent": self.DEFAULT_HEADERS["User-Agent"], "Referer": f"https://www.bilibili.com/video/{bvid}"}
        watermark_status = "platform_watermark"
        watermark_note = "回退为网页端播放流（含B站平台角标）"

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
                        watermark_status = "clean"
                        watermark_note = "音频独立音轨（无水印）"
            except Exception:
                pass

        # 3.1 Prefer TV API for video to get clean watermark-free stream
        if not stream_url:
            tv_stream = self._get_tv_stream(aid, cid, session)
            if tv_stream and tv_stream.get("url"):
                stream_url = tv_stream["url"]
                filesize = tv_stream.get("size")
                download_headers = {"User-Agent": "Bilibili/1.0.0"}
                if not tv_stream.get("has_watermark"):
                    watermark_status = "clean"
                    watermark_note = "通过TV端协议提取无水印清洁流"
                else:
                    watermark_status = "platform_burned"
                    watermark_note = "UP主设置了全流硬编码水印，官方全网CDN未分发无水印清洁源"

        # 3.2 Fallback to Web playurl
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
                    watermark_status = "platform_watermark"
                    watermark_note = "网页端播放流（含B站平台角标）"

        if not stream_url:
            raise ExtractionError(f"Could not retrieve direct playback stream for {bvid}")

        assets: List[TargetAsset] = [
            TargetAsset(
                url=stream_url,
                filename=f"content.{target_ext}",
                file_type="primary",
                expected_size=filesize,
                headers=download_headers
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
                "watermark_status": watermark_status,
                "watermark_note": watermark_note,
            },
            raw_markdown=f"{desc}\n\n- **Up主**：{author_name}\n- **稿件编号**：`{bvid}`"
        )

    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        total_ms = int(round(seconds * 1000))
        hrs, rem = divmod(total_ms, 3600000)
        mins, rem = divmod(rem, 60000)
        secs, ms = divmod(rem, 1000)
        return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"

    def _fetch_subtitles(self, bvid: str, cid: int, session: requests.Session) -> Optional[TargetAsset]:
        """Fetch player v2 info, parse subtitle list, and convert JSON timestamps to SubRip .srt format."""
        try:
            # player/v2 can sporadically return another video's AI subtitle for the
            # same request; player/wbi/v2 is stable and ties the URL to this cid.
            v2_api = f"https://api.bilibili.com/x/player/wbi/v2?bvid={bvid}&cid={cid}"
            sub_url = None
            for _ in range(3):
                v2_resp = session.get(v2_api, timeout=10)
                v2_data = v2_resp.json()
                if v2_data.get("code") != 0:
                    return None

                subtitles = v2_data.get("data", {}).get("subtitle", {}).get("subtitles", [])
                if not subtitles:
                    return None

                candidate = subtitles[0].get("subtitle_url")
                if candidate and str(cid) in candidate:
                    sub_url = candidate
                    break
            if not sub_url:
                return None

            if sub_url.startswith("//"):
                sub_url = f"https:{sub_url}"

            # Convert Bilibili JSON subtitle body to standard .srt format
            sub_resp = session.get(sub_url, timeout=10)
            body = sub_resp.json().get("body", [])
            if not body:
                return None

            srt_blocks = []
            for idx, item in enumerate(body, 1):
                start_t = self._format_srt_time(float(item.get("from", 0.0)))
                end_t = self._format_srt_time(float(item.get("to", 0.0)))
                content = str(item.get("content", "")).strip()
                if content:
                    srt_blocks.append(f"{idx}\n{start_t} --> {end_t}\n{content}")

            if not srt_blocks:
                return None

            srt_text = "\n\n".join(srt_blocks) + "\n"
            b64_srt = base64.b64encode(srt_text.encode("utf-8")).decode("ascii")
            return TargetAsset(
                url=f"data:text/plain;charset=utf-8;base64,{b64_srt}",
                filename="subtitle.srt",
                file_type="subtitle",
                expected_size=len(srt_text.encode("utf-8"))
            )
        except Exception:
            return None
