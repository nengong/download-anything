"""
Feishu / Lark Public Cloud Document to Clean Markdown Extractor Driver
Strips dynamic web app chrome, localizes embedded images, and formats clean GFM Markdown for Agents.
"""
import base64
import json
import re
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin, urlparse
import requests
from core.url_policy import is_http_url, require_http_url
from bs4 import BeautifulSoup

from core.exceptions import ExtractionError, AuthenticationRequiredError
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class FeishuDocDriver(BaseDriver):
    """
    Driver for extracting public Feishu / Lark docs and wikis:
    - feishu.cn/docx/...
    - feishu.cn/wiki/...
    - larksuite.com/docx/...
    - larksuite.com/wiki/...
    """

    name = "feishu_doc"
    category = "docs"

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def can_handle(self, url: str) -> bool:
        clean = url.strip().lower()
        if is_http_url(url, ("feishu.cn", "larksuite.com")):
            if "/docx/" in clean or "/wiki/" in clean or "/docs/" in clean:
                return True
        return False

    def extract(self, url: str, **kwargs) -> AssetPackage:
        clean = url.strip()
        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)

        try:
            resp = session.get(clean, timeout=12)
            if resp.status_code in (401, 403) or "passport.feishu.cn" in resp.url or "passport.larksuite.com" in resp.url:
                raise AuthenticationRequiredError(f"Feishu document requires login or access permission: {url}")
            resp.raise_for_status()
            html = resp.text
        except AuthenticationRequiredError:
            raise
        except Exception as e:
            raise ExtractionError(f"Failed to fetch Feishu document page: {e}")

        soup = BeautifulSoup(html, "html.parser")

        # 1. Extract title
        title = None
        for sel in ["h1", ".doc-title", ".wiki-title", "title"]:
            el = soup.select_one(sel)
            if el and el.text.strip():
                title = el.text.strip()
                break
        if title:
            title = title.split(" - 飞书")[0].split(" - Lark")[0].strip()
        title = title or "Feishu_Document"

        # 2. Extract content & images
        # Strip script, style, header, nav
        for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            tag.decompose()

        main_container = soup.select_one(".docx-page, .wiki-content, .render-unit, main, article") or soup.body or soup

        assets: List[TargetAsset] = []
        img_counter = 1

        for img in main_container.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if not src or src.startswith("data:"):
                continue
            full_url = require_http_url(urljoin(resp.url, src))
            img_filename = f"feishu_img_{img_counter:02d}.png"
            assets.append(TargetAsset(
                filename=img_filename,
                url=full_url,
                file_type="cover" if img_counter == 1 else "extra",
                headers=self.DEFAULT_HEADERS
            ))
            alt = img.get("alt") or f"image_{img_counter}"
            img.replace_with(f"\n\n![{alt}]({img_filename})\n\n")
            img_counter += 1

        # Format headings, paragraphs, pre
        for h in main_container.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            level = int(h.name[1])
            h.replace_with(f"\n\n{'#' * level} {h.get_text().strip()}\n\n")

        for p in main_container.find_all(["p", "div"]):
            if p.get_text().strip():
                p.replace_with(f"\n\n{p.get_text().strip()}\n\n")

        for pre in main_container.find_all("pre"):
            code = pre.get_text().strip()
            pre.replace_with(f"\n\n```\n{code}\n```\n\n")

        raw_text = main_container.get_text().strip()
        raw_text = re.sub(r"\n{3,}", "\n\n", raw_text)

        full_md = (
            f"# {title}\n\n"
            f"> - **文档来源**: 飞书云文档 (<{url}>)\n"
            f"> - **提取时间**: `{resp.headers.get('Date', 'N/A')}`\n"
            f"> - **插图总数**: {len(assets)} 张本地化保存\n\n"
            f"---\n\n"
            f"{raw_text}\n"
        )

        b64_article = base64.b64encode(full_md.encode("utf-8")).decode("utf-8")
        assets.insert(0, TargetAsset(
            filename="article.md",
            url=f"data:text/markdown;charset=utf-8;base64,{b64_article}",
            file_type="primary",
            expected_size=len(full_md.encode("utf-8"))
        ))

        metadata = {
            "title": title,
            "original_url": url,
            "platform": "feishu_doc",
            "sidecar_text": full_md,
            "author": {"name": "Feishu User"}
        }

        return AssetPackage(
            platform="feishu_doc",
            title=title,
            original_url=url,
            assets=assets,
            metadata=metadata
        )
