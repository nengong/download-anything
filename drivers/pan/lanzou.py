"""
Lanzou Cloud (蓝奏云) No-Login Direct Download Driver
"""
import re
from typing import Optional
from urllib.parse import urlparse
import requests

from core.exceptions import ExtractionError
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class LanzouDriver(BaseDriver):
    """Direct CDN link extractor for Lanzou Cloud (lanzou*.com) without login."""

    name = "lanzou"
    category = "pan"

    DOMAIN_REGEX = re.compile(r"https?://(?:[a-zA-Z0-9-]+\.)?lanzou[a-z]*\.com/([a-zA-Z0-9_]+)")

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    def can_handle(self, url: str) -> bool:
        return bool(self.DOMAIN_REGEX.search(url))

    def extract(self, url: str, password: Optional[str] = None, **kwargs) -> AssetPackage:
        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)

        # 1. Fetch initial landing page
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            raise ExtractionError(f"Failed to access Lanzou URL {url}: {e}")

        # Check for iframe (Lanzou sometimes embeds file handler inside <iframe src="/fn?...">)
        outer_html = html
        iframe_match = re.search(r'<iframe\s+[^>]*src="(/fn\?[^"]+)"', html, re.IGNORECASE)
        page_url = url
        if iframe_match:
            parsed = urlparse(url)
            iframe_url = f"{parsed.scheme}://{parsed.netloc}{iframe_match.group(1)}"
            try:
                session.headers["Referer"] = url
                resp = session.get(iframe_url, timeout=15)
                resp.raise_for_status()
                html = resp.text
                page_url = iframe_url
            except Exception as e:
                raise ExtractionError(f"Failed to load Lanzou iframe: {e}")

        # 2. Extract Title / Filename
        title = "lanzou_asset"
        title_match = (
            re.search(r'<div class="n_box_3fn">([^<]+)</div>', outer_html) or
            re.search(r'<div class="filethetext"[^>]*>([^<]+)</div>', outer_html) or
            re.search(r'<title>([^<_\-]+)', outer_html) or
            re.search(r'<title>([^<_\-]+)', html)
        )
        if title_match:
            title = title_match.group(1).strip()

        # Extract File Size if present
        size_bytes = None
        size_match = re.search(r'(?:大小|Size)[：:\s]*([\d\.]+)\s*([KkMmGg][Bb]?)', outer_html)
        if size_match:
            val, unit = float(size_match.group(1)), size_match.group(2).upper()
            if "G" in unit:
                size_bytes = int(val * 1024 * 1024 * 1024)
            elif "M" in unit:
                size_bytes = int(val * 1024 * 1024)
            elif "K" in unit:
                size_bytes = int(val * 1024)

        # 3. Reverse the download API parameters
        # Current pages expose wp_sign + ajaxdata and POST to an apifile host;
        # older pages expose a bare sign and POST to /ajaxm.php.
        sign_match = (
            re.search(r"var\s+wp_sign\s*=\s*'([^']+)'", html) or
            re.search(r"\bwp_sign\s*=\s*'([^']+)'", html) or
            re.search(r"var\s+skdkld\s*=\s*'([^']+)'", html) or
            re.search(r"var\s+signs\s*=\s*'([^']+)'", html) or
            re.search(r"'sign'\s*:\s*'([^']+)'", html) or
            re.search(r"sign\s*:\s*'([^']+)'", html)
        )

        websign_match = re.search(r"var\s+ws_sign\s*=\s*'([^']*)'", html) or re.search(r"var\s+websign\s*=\s*'([^']*)'", html)
        websignkey_match = (
            re.search(r"var\s+ajaxdata\s*=\s*'([^']*)'", html) or
            re.search(r"var\s+websignkey\s*=\s*'([^']*)'", html)
        )
        kd_match = re.search(r"var\s+kdns\s*=\s*(\d+)", html) or re.search(r"var\s+kd\s*=\s*(\d+)", html)

        post_data = {
            "action": "downprocess",
            "ves": 1,
        }
        if sign_match:
            post_data["sign"] = sign_match.group(1)
        if websignkey_match:
            post_data["websignkey"] = websignkey_match.group(1)
            post_data["signs"] = websignkey_match.group(1)
        if websign_match:
            post_data["websign"] = websign_match.group(1)
        if kd_match:
            post_data["kd"] = kd_match.group(1)
        if password:
            post_data["p"] = password
            post_data["pwd"] = password

        # Determine ajax URL (new pages provide a full apifile endpoint)
        ajax_url = None
        for pattern in (
            r"var\s+domain1\s*=\s*'([^']+)'",
            r"var\s+dom_ajaxs\s*=\s*'([^']+)'",
            r"var\s+domain2\s*=\s*'([^']+)'",
        ):
            m = re.search(pattern, html)
            if m:
                ajax_url = m.group(1)
                break
        if not ajax_url:
            parsed = urlparse(page_url)
            ajax_url = f"{parsed.scheme}://{parsed.netloc}/ajaxm.php"

        session.headers["Referer"] = page_url
        session.headers["X-Requested-With"] = "XMLHttpRequest"

        try:
            ajax_resp = session.post(ajax_url, data=post_data, timeout=15)
            ajax_data = ajax_resp.json()
        except Exception as e:
            raise ExtractionError(f"Failed to reverse Lanzou ajaxm.php API: {e}")

        # zt=1: success; zt=2: password required/incorrect
        if str(ajax_data.get("zt")) != "1":
            inf = ajax_data.get("inf", "Unknown error")
            if "密码" in inf or str(ajax_data.get("zt")) == "2":
                raise ExtractionError(f"Lanzou extraction requires password: {inf}")
            raise ExtractionError(f"Lanzou extraction failed: {inf}")

        dom = ajax_data.get("dom", "").rstrip("/")
        path_seg = ajax_data.get("url", "").lstrip("/")

        if not dom or not path_seg:
            raise ExtractionError("Lanzou did not return a valid download link.")

        # Lanzou full direct CDN URL
        if path_seg.startswith("http"):
            direct_url = path_seg
        elif path_seg.startswith("/file/"):
            direct_url = f"{dom}{path_seg}"
        else:
            direct_url = f"{dom}/file/{path_seg}"

        # Clean filename
        safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)
        filename = safe_title
        if "." not in filename:
            filename = f"{safe_title}.bin"

        primary_asset = TargetAsset(
            url=direct_url,
            filename=filename,
            file_type="primary",
            expected_size=size_bytes,
            headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"], "Referer": page_url}
        )

        return AssetPackage(
            title=safe_title,
            platform=self.name,
            assets=[primary_asset],
            metadata={
                "original_url": url,
                "author_name": "Lanzou User",
                "filesize_bytes": size_bytes,
                "has_password": bool(password)
            },
            raw_markdown=f"蓝奏云直链解析产物: `{filename}`"
        )
