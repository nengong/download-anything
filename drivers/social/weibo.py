"""
Sina Weibo Post, Video, and Image Album Extractor Driver
"""
import json
import re
import subprocess
import sys
from urllib.parse import urlsplit
from typing import Optional, Dict, Any, List
import requests
from bs4 import BeautifulSoup
from drivers.base import BaseDriver, AssetPackage, AssetFile
from core.exceptions import ExtractionError, BackendUnavailableError, AccessDeniedError
from core.credentials import credentials_manager

class WeiboDriver(BaseDriver):
    """Driver for extracting Sina Weibo videos, live photos, photo albums, and post text."""

    WEIBO_URL_REGEX = re.compile(
        r"https?://(?:(?:www|m)\.)?weibo\.(?:com|cn)/(?:detail/|status/|\d+/)?(?P<id>[a-zA-Z0-9]+)"
    )

    def can_handle(self, url: str) -> bool:
        return bool(self.WEIBO_URL_REGEX.search(url))

    def _mint_visitor_cookie(self) -> str:
        """Dynamically mint a Sina Visitor System guest cookie."""
        try:
            s = requests.Session()
            s.headers.update({
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
            })
            res = s.post(
                "https://passport.weibo.com/visitor/genvisitor",
                data={"cb": "gen_visitor", "fp": '{"os":"1","sp":"","spr":"screen:1920*1080","extra":""}'},
                timeout=5
            )
            m = re.search(r'"tid":\s*"([^"]+)"', res.text)
            if m:
                tid = m.group(1)
                s.get(f"https://passport.weibo.com/visitor/visitor?a=incarnate&t={tid}&w=2&c=095&gc=&cb=cross_domain", timeout=5)
                return "; ".join(f"{k}={v}" for k, v in s.cookies.get_dict().items())
        except Exception:
            pass
        return ""

    @staticmethod
    def _access_error(message: str) -> bool:
        return any(marker in message.lower() for marker in (
            "login", "log in", "sign in", "auth", "cookie", "token",
            "401", "403", "429", "rate limit", "too many requests",
            "forbidden", "captcha", "challenge", "登录", "频繁",
        ))

    def _extract_photos(self, canonical_url: str, weibo_id: str) -> Optional[AssetPackage]:
        """Read public gallery-dl metadata without loading user configuration."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "gallery_dl", "--config-ignore", "--no-input",
                 "--dump-json", "--retries", "0", "--http-timeout", "15", canonical_url],
                capture_output=True, text=True, timeout=60, shell=False,
            )
        except subprocess.TimeoutExpired:
            raise BackendUnavailableError("Weibo gallery-dl extraction timed out.") from None
        except OSError:
            raise BackendUnavailableError("Could not start Weibo gallery-dl extraction.") from None
        if self._access_error(result.stderr or ""):
            raise AccessDeniedError("Weibo authentication/access or rate limit error.")
        if result.returncode:
            raise BackendUnavailableError("Weibo gallery-dl extraction failed.")
        try:
            messages = json.loads(result.stdout)
        except (ValueError, TypeError):
            raise BackendUnavailableError("Invalid Weibo gallery-dl JSON response.") from None
        if not isinstance(messages, list):
            raise ExtractionError("Invalid Weibo gallery-dl messages.")

        status = None
        images = {}
        seen_urls = {}
        non_image = False
        extensions = {"jpg", "jpeg", "png", "webp", "gif"}

        def matches(value):
            return isinstance(value, dict) and weibo_id in (
                str(value.get("id", "")), value.get("mblogid"),
            )

        for message in messages:
            if not isinstance(message, list) or not message:
                raise ExtractionError("Invalid Weibo gallery-dl message.")
            if message[0] == -1:
                raise ExtractionError("Weibo gallery-dl reported an extraction error.")
            if message[0] == 2:
                candidate = message[-1]
                if not matches(candidate) or status is not None:
                    raise ExtractionError("Weibo gallery post identity mismatch.")
                status = candidate
            elif message[0] == 3:
                if len(message) != 3 or not isinstance(message[2], dict):
                    raise ExtractionError("Invalid Weibo gallery image metadata.")
                image_url, data = message[1:]
                if (not matches(data.get("status")) or status is None
                        or data["status"].get("count") != status.get("count")):
                    raise ExtractionError("Weibo gallery image post identity mismatch.")
                extension = data.get("extension")
                if extension not in extensions:
                    non_image = True
                    continue
                if not isinstance(image_url, str):
                    raise ExtractionError("Unsafe Weibo gallery image URL.")
                try:
                    parsed = urlsplit(image_url)
                    safe = (
                        parsed.scheme == "https" and parsed.hostname
                        and parsed.hostname.endswith(".sinaimg.cn")
                        and parsed.username is None and parsed.password is None
                        and parsed.port in (None, 443)
                        and re.fullmatch(r"/large/[A-Za-z0-9_.-]+", parsed.path)
                        and parsed.path.rsplit(".", 1)[-1].lower() == extension
                        and not parsed.fragment
                    )
                except ValueError:
                    safe = False
                if not safe:
                    raise ExtractionError("Unsafe Weibo gallery image URL.")
                num = data.get("num")
                if type(num) is not int or num < 1:
                    raise ExtractionError("Invalid Weibo gallery image number.")
                if num in images and images[num] != (image_url, extension):
                    raise ExtractionError("Conflicting Weibo gallery image number.")
                if image_url in seen_urls and seen_urls[image_url] != num:
                    raise ExtractionError("Duplicate Weibo gallery image URL.")
                images[num] = (image_url, extension)
                seen_urls[image_url] = num
        # Never mistake a video's poster or a mixed album for a complete photo post.
        if non_image or not images:
            return None
        count = status.get("count") if status else None
        if (type(count) is not int or count < 1 or len(images) != count
                or sorted(images) != list(range(1, count + 1))):
            raise ExtractionError("Incomplete Weibo gallery image album.")
        clean_text = BeautifulSoup(str(status.get("text") or ""), "html.parser").get_text(separator="\n").strip()
        title = clean_text[:60] or f"weibo_{weibo_id}"
        user = status.get("user") or {}
        if not isinstance(user, dict):
            user = {}
        assets = [
            AssetFile(
                filename=f"content.{ext}" if num == 1 else f"image_{num:02d}.{ext}",
                url=image_url, file_type="primary" if num == 1 else "companion",
                headers={"Referer": "https://weibo.com"},
            )
            for num, (image_url, ext) in sorted(images.items())
        ]
        return AssetPackage(
            platform="weibo", title=title, original_url=canonical_url, assets=assets,
            metadata={
                "title": title, "original_url": canonical_url,
                "author": {"id": str(user.get("id") or ""),
                           "name": str(user.get("screen_name") or "Weibo User")},
                "created_at": str(status.get("date") or ""),
                "sidecar_text": clean_text, "image_count": count,
            },
        )

    def extract(self, url: str, password: Optional[str] = None, **kwargs) -> AssetPackage:
        m = self.WEIBO_URL_REGEX.search(url)
        if not m:
            raise ExtractionError(f"Invalid Weibo URL: {url}")
        weibo_id = m.group("id")
        canonical_url = f"https://m.weibo.cn/detail/{weibo_id}"

        # 1. Prepare session with credentials or visitor cookie
        session = requests.Session()
        cookie = credentials_manager.get_credential("weibo", "cookie")
        if not cookie:
            cookie = self._mint_visitor_cookie()

        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
            "Referer": "https://m.weibo.cn/",
        }
        if cookie:
            headers["Cookie"] = cookie

        # Try mobile detail API
        detail_url = f"https://m.weibo.cn/statuses/show?id={weibo_id}"
        post_data = None
        access_error = False
        try:
            r = session.get(detail_url, headers=headers, timeout=10)
            if r.status_code in (401, 403, 429):
                access_error = True
            elif r.status_code == 200:
                json_data = r.json()
                if json_data.get("ok") == 1:
                    post_data = json_data.get("data")
                else:
                    access_error = self._access_error(str(json_data.get("msg") or ""))
        except Exception:
            pass
        if access_error:
            raise AccessDeniedError("Weibo authentication/access or rate limit error.")

        # Prefer photo extraction before the existing video fallback.
        if not post_data:
            try:
                photos = self._extract_photos(canonical_url, weibo_id)
            except BackendUnavailableError:
                photos = None
            if photos is not None:
                return photos
            try:
                import yt_dlp
                ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(canonical_url, download=False)
                    if info:
                        title = info.get("description") or info.get("title") or f"weibo_{weibo_id}"
                        if len(title) > 60:
                            title = title[:60].strip()
                        video_url = info.get("url") or (info.get("formats") and info["formats"][-1].get("url"))
                        if video_url:
                            assets = [
                                AssetFile(
                                    filename="content.mp4",
                                    url=video_url,
                                    file_type="primary",
                                    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://weibo.com"}
                                )
                            ]
                            if info.get("thumbnail"):
                                assets.append(AssetFile(filename="cover.jpg", url=info["thumbnail"], file_type="cover"))
                            return AssetPackage(
                                platform="weibo",
                                title=title,
                                original_url=canonical_url,
                                assets=assets,
                                metadata={
                                    "title": title,
                                    "original_url": canonical_url,
                                    "author": {"name": info.get("uploader") or "Weibo User"},
                                    "sidecar_text": info.get("description") or ""
                                }
                            )
            except Exception:
                pass

            raise ExtractionError(f"Failed to query Weibo post {weibo_id}.")

        # Parse mobile detail JSON
        user = post_data.get("user") or {}
        author_name = user.get("screen_name") or "Weibo User"
        raw_text = post_data.get("text") or ""
        soup = BeautifulSoup(raw_text, "html.parser")
        clean_text = soup.get_text(separator="\n").strip()
        title = clean_text[:60] if clean_text else f"weibo_{weibo_id}"

        assets: List[AssetFile] = []
        # Check if video post
        page_info = post_data.get("page_info") or {}
        media_info = page_info.get("media_info") or {}
        video_url = media_info.get("stream_url_hd") or media_info.get("stream_url")

        if video_url:
            assets.append(
                AssetFile(
                    filename="content.mp4",
                    url=video_url,
                    file_type="primary",
                    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://weibo.com"}
                )
            )
            cover_url = page_info.get("page_pic", {}).get("url")
            if cover_url:
                assets.append(
                    AssetFile(filename="cover.jpg", url=cover_url, file_type="cover")
                )
        else:
            # Photo album / LivePhotos
            pics = post_data.get("pics") or []
            if pics:
                for idx, p in enumerate(pics):
                    p_url = p.get("large", {}).get("url") or p.get("url")
                    is_live = bool(p.get("videoSrc"))
                    if idx == 0:
                        assets.append(
                            AssetFile(
                                filename="content.jpg",
                                url=p_url,
                                file_type="primary",
                                headers={"Referer": "https://weibo.com"}
                            )
                        )
                    else:
                        assets.append(
                            AssetFile(
                                filename=f"image_{idx + 1:02d}.jpg",
                                url=p_url,
                                file_type="companion",
                                headers={"Referer": "https://weibo.com"}
                            )
                        )
                    # LivePhoto companion video
                    if is_live:
                        assets.append(
                            AssetFile(
                                filename=f"live_{idx + 1:02d}.mov",
                                url=p.get("videoSrc"),
                                file_type="companion",
                                headers={"Referer": "https://weibo.com"}
                            )
                        )
            else:
                raise ExtractionError("Weibo post contains no downloadable media (text only).")

        metadata = {
            "title": title,
            "original_url": canonical_url,
            "author": {
                "id": str(user.get("id") or ""),
                "name": author_name,
            },
            "created_at": post_data.get("created_at") or "",
            "metrics": {
                "likes": post_data.get("attitudes_count") or 0,
                "reposts": post_data.get("reposts_count") or 0,
                "comments": post_data.get("comments_count") or 0,
            },
            "sidecar_text": clean_text,
        }

        return AssetPackage(
            platform="weibo",
            title=title,
            original_url=canonical_url,
            assets=assets,
            metadata=metadata
        )
