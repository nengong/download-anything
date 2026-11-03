"""
Shadow Library (Anna's Archive & LibGen) Resilient Driver
"""
import re
from typing import Optional, List
from urllib.parse import urlparse
import requests

from core.exceptions import ExtractionError
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class ShadowLibraryDriver(BaseDriver):
    """
    High-resilience book extractor for Anna's Archive and LibGen.
    Eliminates 60-second timeouts, handles dynamic token keys (ads.php -> get.php),
    and captures companion cover visuals and metadata.
    """

    name = "shadow_library"
    category = "books"

    ANNA_DOMAINS = [
        "annas-archive.li",
        "annas-archive.gl",
        "annas-archive.pk",
        "annas-archive.gd",
        "annas-archive.se",
        "annas-archive.org",
    ]

    LIBGEN_MIRRORS = [
        "https://libgen.la",
        "http://libgen.la",
        "https://libgen.li",
        "https://libgen.is",
        "https://libgen.rs",
    ]

    MD5_REGEX = re.compile(r"(?:/md5/|md5:)([a-fA-F0-9]{32})", re.IGNORECASE)
    PLAIN_MD5_REGEX = re.compile(r"^[a-fA-F0-9]{32}$")

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    def can_handle(self, url: str) -> bool:
        clean = url.strip()
        if self.MD5_REGEX.search(clean) or self.PLAIN_MD5_REGEX.match(clean):
            return True
        for d in self.ANNA_DOMAINS:
            if d in clean:
                return True
        for m in ["libgen.is", "libgen.rs", "libgen.st", "libgen.la", "libgen.li"]:
            if m in clean:
                return True
        return False

    def _extract_md5(self, url: str) -> Optional[str]:
        m = self.MD5_REGEX.search(url)
        if m:
            return m.group(1).lower()
        if self.PLAIN_MD5_REGEX.match(url.strip()):
            return url.strip().lower()
        # Query parameter ?md5=xxxx
        param_match = re.search(r"[?&]md5=([a-fA-F0-9]{32})", url, re.IGNORECASE)
        if param_match:
            return param_match.group(1).lower()
        return None

    def extract(self, url: str, **kwargs) -> AssetPackage:
        md5_hash = self._extract_md5(url)
        if not md5_hash:
            raise ExtractionError(f"Could not extract a valid 32-character MD5 from: {url}")

        # 1. Resolve via LibGen ads.php -> get.php key mechanism
        resolved = self._resolve_via_libgen(md5_hash)
        if resolved:
            return resolved

        # 2. Fallback to Anna's Archive page scrape
        resolved_anna = self._resolve_via_anna(md5_hash, url)
        if resolved_anna:
            return resolved_anna

        raise ExtractionError(f"Unable to find working download mirror for book MD5: {md5_hash}")

    def _resolve_via_libgen(self, md5: str) -> Optional[AssetPackage]:
        headers = dict(self.DEFAULT_HEADERS)
        for mirror in self.LIBGEN_MIRRORS:
            ads_url = f"{mirror}/ads.php?md5={md5}"
            try:
                r = requests.get(ads_url, headers=headers, timeout=10)
                if r.status_code != 200:
                    continue
                html = r.text

                # Parse key-based download link
                get_match = re.search(r'href="(get\.php\?md5=[^"]+)"', html)
                if not get_match:
                    continue

                get_rel_url = get_match.group(1)
                direct_url = f"{mirror}/{get_rel_url}"

                # Extract metadata
                title = "Unknown Book"
                author = "Unknown Author"
                ext = "pdf"

                title_match = re.search(r"Title:\s*([^<]+)", html) or re.search(r"<h1>([^<]+)</h1>", html)
                if title_match:
                    title = title_match.group(1).strip()

                author_match = re.search(r"Author\(s\):\s*([^<]+)", html)
                if author_match:
                    author = author_match.group(1).strip()

                ext_match = re.search(r"Extension:\s*([a-zA-Z0-9]+)", html)
                if ext_match:
                    ext = ext_match.group(1).strip().lower()

                # Clean filename
                safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)
                primary_filename = f"{safe_title}.{ext}"

                # NOTE: We deliberately do NOT perform pre-flight HEAD requests here.
                # CDNs like cdn3.booksdl.lc hang indefinitely on HEAD requests, burning the one-time token.
                # The streaming GET in Fetcher will read Content-Length on the first response frame safely.
                primary_asset = TargetAsset(
                    url=direct_url,
                    filename=primary_filename,
                    file_type="primary",
                    expected_size=None,
                    headers={"User-Agent": headers["User-Agent"], "Referer": ads_url}
                )

                assets = [primary_asset]

                # Check for cover image in ads.php
                cover_match = re.search(r'<img\s+[^>]*src="(/covers/[^"]+)"', html)
                if cover_match:
                    cover_url = f"{mirror}{cover_match.group(1)}"
                    assets.append(TargetAsset(
                        url=cover_url,
                        filename="cover.jpg",
                        file_type="cover",
                        headers={"User-Agent": headers["User-Agent"], "Referer": ads_url}
                    ))

                return AssetPackage(
                    title=title,
                    platform=self.name,
                    assets=assets,
                    metadata={
                        "original_url": ads_url,
                        "md5": md5,
                        "author_name": author,
                        "author": {"id": "", "name": author},
                        "extension": ext,
                        "mirror": mirror
                    },
                    raw_markdown=f"### 书籍信息\n- **书名**：{title}\n- **作者**：{author}\n- **格式**：{ext.upper()}\n- **MD5**：`{md5}`"
                )

            except Exception:
                continue

        return None

    def _resolve_via_anna(self, md5: str, original_url: str) -> Optional[AssetPackage]:
        headers = dict(self.DEFAULT_HEADERS)
        for mirror in self.ANNA_DOMAINS:
            anna_url = f"https://{mirror}/md5/{md5}"
            try:
                r = requests.get(anna_url, headers=headers, timeout=12)
                if r.status_code != 200:
                    continue
                html = r.text

                # Extract Title
                title = f"Book_{md5[:8]}"
                title_match = re.search(r'<div class="text-2xl font-bold[^>]*>([^<]+)</div>', html) or re.search(r"<title>([^<]+)</title>", html)
                if title_match:
                    title = title_match.group(1).strip()

                # Extract LibGen download links embedded in Anna page
                libgen_links = re.findall(r'href="(https?://[^"]*(?:libgen|get\.php)[^"]*)"', html)
                if libgen_links:
                    chosen_link = libgen_links[0]
                    ext = "pdf"
                    if ".epub" in chosen_link or "epub" in html.lower():
                        ext = "epub"

                    safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)
                    filename = f"{safe_title}.{ext}"

                    primary_asset = TargetAsset(
                        url=chosen_link,
                        filename=filename,
                        file_type="primary",
                        headers={"User-Agent": headers["User-Agent"], "Referer": anna_url}
                    )

                    return AssetPackage(
                        title=title,
                        platform=self.name,
                        assets=[primary_asset],
                        metadata={
                            "original_url": original_url,
                            "md5": md5,
                            "anna_mirror": mirror
                        },
                        raw_markdown=f"### Anna's Archive 解析产物\n- **书名**：{title}\n- **MD5**：`{md5}`"
                    )

            except Exception:
                continue

        return None
