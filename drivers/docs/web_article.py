"""
Universal Web Article and Anti-Copy Page to Clean Markdown Extractor Driver
Strips anti-copy JavaScript/CSS, localizes all embedded images, and produces clean Markdown for Agents.
"""
import base64
import os
import re
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin, urlparse
import requests
from core.url_policy import is_http_url, require_http_url
from bs4 import BeautifulSoup
from drivers.base import BaseDriver, AssetPackage, TargetAsset
from core.exceptions import ExtractionError

class WebArticleDriver(BaseDriver):
    """
    Universal driver for capturing web articles, Zhihu answers/columns,
    technical blogs, and documentation into clean Markdown with localized images.
    """

    name = "web_article"
    category = "docs"

    SUPPORTED_DOMAINS = [
        "zhuanlan.zhihu.com",
        "zhihu.com",
        "juejin.cn",
        "csdn.net",
        "medium.com",
        "substack.com",
        "sspai.com",
        "jianshu.com",
        "segmentfault.com",
        "oschina.net",
        "cnblogs.com",
        "v2ex.com"
    ]

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def can_handle(self, url: str) -> bool:
        clean = url.strip().lower()
        if not clean.startswith("http://") and not clean.startswith("https://"):
            return False
        # Do not steal from other specialized drivers
        for bypass in ("pan.", "quark.cn", "github.com", "bilibili.com", "youtube.com", "youtu.be", "twitter.com", "x.com", "instagram.com", "douyin.com", "weibo.com", "xiaoyuzhoufm.com", "apple.com", "arxiv.org", "lanzou"):
            if bypass in clean:
                return False

        parsed = urlparse(clean)
        return is_http_url(url, self.SUPPORTED_DOMAINS)

    def extract(self, url: str, **kwargs) -> AssetPackage:
        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)
        try:
            resp = session.get(url, timeout=12)
            resp.raise_for_status()
            if resp.encoding == "ISO-8859-1" or not resp.encoding:
                resp.encoding = resp.apparent_encoding or "utf-8"
            html = resp.text
        except Exception as e:
            raise ExtractionError(f"Failed to fetch webpage: {e}")

        soup = BeautifulSoup(html, "html.parser")

        # 1. Strip script, style, navigation, header, footer, ads
        for tag in soup(["script", "style", "nav", "footer", "aside", "noscript", "iframe", "svg"]):
            tag.decompose()

        # 2. Extract Title
        title = None
        for sel in ["h1", ".Post-Title", ".article-title", ".entry-title", "title"]:
            el = soup.select_one(sel)
            if el and el.text.strip():
                title = el.text.strip()
                break
        if not title and soup.title:
            title = soup.title.text.split("_")[0].split("-")[0].strip()
        title = title or "Web_Article"

        # 3. Locate Main Content Container (Readability heuristic)
        main_content = None
        content_selectors = [
            ".Post-RichTextContainer", ".Post-RichText", ".RichText",
            "article", ".article-content", ".entry-content", ".post-content",
            "#article-content", ".markdown-body", "main"
        ]
        for sel in content_selectors:
            el = soup.select_one(sel)
            if el and len(el.text.strip()) > 80:
                main_content = el
                break

        if not main_content:
            main_content = soup.body or soup

        # 4. Extract Images and convert to Markdown
        assets: List[TargetAsset] = []
        img_counter = 1

        for img in main_content.find_all("img"):
            src = img.get("data-actualsrc") or img.get("data-original") or img.get("data-src") or img.get("src")
            if not src or src.startswith("data:"):
                continue
            full_img_url = require_http_url(urljoin(resp.url, src))
            ext = ".jpg"
            if ".png" in full_img_url.lower():
                ext = ".png"
            elif ".webp" in full_img_url.lower():
                ext = ".webp"
            elif ".gif" in full_img_url.lower():
                ext = ".gif"

            img_filename = f"img_{img_counter:02d}{ext}"
            assets.append(TargetAsset(
                filename=img_filename,
                url=full_img_url,
                file_type="cover" if img_counter == 1 else "extra",
                headers={"Referer": url, "User-Agent": self.DEFAULT_HEADERS["User-Agent"]}
            ))
            # Replace img tag with markdown image placeholder
            alt = img.get("alt") or f"image_{img_counter}"
            img.replace_with(f"\n\n![{alt}]({img_filename})\n\n")
            img_counter += 1

        # 5. Extract text structure to clean Markdown
        # Headings
        for h in main_content.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            level = int(h.name[1])
            h.replace_with(f"\n\n{'#' * level} {h.get_text().strip()}\n\n")

        # Paragraphs & line breaks
        for p in main_content.find_all("p"):
            p.replace_with(f"\n\n{p.get_text().strip()}\n\n")

        # Code blocks
        for pre in main_content.find_all("pre"):
            code = pre.get_text().strip()
            pre.replace_with(f"\n\n```\n{code}\n```\n\n")

        raw_md = main_content.get_text().strip()
        # Clean excessive empty lines
        raw_md = re.sub(r"\n{3,}", "\n\n", raw_md)

        full_markdown = (
            f"# {title}\n\n"
            f"> - **来源网址**：<{url}>\n"
            f"> - **提取时间**：`{resp.headers.get('Date', 'N/A')}`\n"
            f"> - **插图总数**：{len(assets)} 张本地化保存\n\n"
            f"---\n\n"
            f"{raw_md}\n"
        )

        b64_article = base64.b64encode(full_markdown.encode("utf-8")).decode("utf-8")
        assets.insert(0, TargetAsset(
            filename="article.md",
            url=f"data:text/markdown;charset=utf-8;base64,{b64_article}",
            file_type="primary",
            expected_size=len(full_markdown.encode("utf-8"))
        ))

        metadata = {
            "title": title,
            "original_url": url,
            "author": {"name": "Author"},
            "metrics": {"images_count": len(assets) - 1},
            "sidecar_text": full_markdown,
        }

        return AssetPackage(
            platform="web_article",
            title=title,
            original_url=url,
            assets=assets,
            metadata=metadata
        )
