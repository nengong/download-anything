"""
WeChat Official Account (微信公众号) Markdown & Anti-Hotlinking Image Localizer Driver
"""
import base64
import re
from typing import Optional, List
from bs4 import BeautifulSoup, NavigableString, Tag
import requests
from core.url_policy import is_http_url, require_http_url

from core.exceptions import ExtractionError
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class WeChatDriver(BaseDriver):
    """
    Extracts WeChat Official Account articles into pure clean Markdown:
    - Bypasses WeChat anti-hotlinking by downloading images locally
    - Strips clutter styles and scripts while preserving text structure
    - Generates localized image paths in Markdown
    """

    name = "wechat"
    category = "docs"

    URL_REGEX = re.compile(r"https?://mp\.weixin\.qq\.com/s(?:/|[?&])")

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def can_handle(self, url: str) -> bool:
        return is_http_url(url, ("mp.weixin.qq.com",)) and bool(self.URL_REGEX.match(url))

    def extract(self, url: str, **kwargs) -> AssetPackage:
        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)

        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            raise ExtractionError(f"Failed to fetch WeChat article: {e}")

        soup = BeautifulSoup(html, "html.parser")

        # 1. Metadata
        title_el = soup.find(id="activity-name")
        title = title_el.get_text(strip=True) if title_el else "wechat_article"
        safe_title = re.sub(r'[\\/*?:"<>|\n\r]', "_", title)[:70]

        author_el = soup.find(id="js_name")
        author_name = author_el.get_text(strip=True) if author_el else "微信公众号"

        cover_el = soup.find("meta", property="og:image")
        cover_url = cover_el["content"].strip() if cover_el and cover_el.get("content") else None

        content_el = soup.find(id="js_content")
        if not content_el:
            raise ExtractionError("Failed to locate article content element (#js_content) on page.")

        # 2. Localize Images
        assets: List[TargetAsset] = []
        img_tags = content_el.find_all("img")

        image_counter = 1
        for img in img_tags:
            src = img.get("data-src") or img.get("src")
            if not src or "res.wx.qq.com" in src:
                continue

            data_type = img.get("data-type", "").lower()
            if not data_type:
                fmt_match = re.search(r"wx_fmt=([a-zA-Z0-9]+)", src)
                data_type = fmt_match.group(1).lower() if fmt_match else "png"

            img_filename = f"img_{image_counter:02d}.{data_type}"
            assets.append(TargetAsset(
                url=require_http_url(src),
                filename=img_filename,
                file_type="extra",
                headers={"Referer": "https://mp.weixin.qq.com/", "User-Agent": self.DEFAULT_HEADERS["User-Agent"]}
            ))

            # Replace img tag in HTML with markdown placeholder
            replacement_text = f"\n\n![{img_filename}](./{img_filename})\n\n"
            img.replace_with(soup.new_string(replacement_text))
            image_counter += 1

        # 3. Convert Content to Clean Markdown
        clean_markdown_text = self._html_to_markdown(content_el)

        header_block = (
            f"# {title}\n\n"
            f"> **公众号**：`{author_name}`  \n"
            f"> **原始链接**：<{url}>  \n"
            f"> **图片数量**：共 {len(assets)} 张（已防盗链本地化）\n\n"
            f"---\n\n"
        )
        full_article_md = header_block + clean_markdown_text

        # 4. Primary Asset: Synthesized article.md (via data: URI)
        b64_content = base64.b64encode(full_article_md.encode("utf-8")).decode("ascii")
        primary_asset = TargetAsset(
            url=f"data:text/markdown;charset=utf-8;base64,{b64_content}",
            filename="article.md",
            file_type="primary",
            expected_size=len(full_article_md.encode("utf-8"))
        )

        all_assets = [primary_asset] + assets

        if cover_url:
            all_assets.append(TargetAsset(
                url=cover_url,
                filename="cover.jpg",
                file_type="cover",
                headers={"Referer": "https://mp.weixin.qq.com/"}
            ))

        return AssetPackage(
            title=safe_title,
            platform=self.name,
            assets=all_assets,
            metadata={
                "original_url": url,
                "author": {"id": author_name, "name": author_name},
                "author_name": author_name,
                "image_count": len(assets),
            },
            raw_markdown=full_article_md
        )

    def _html_to_markdown(self, element: Tag) -> str:
        """Lightweight clean converter from WeChat DOM to Markdown."""
        lines = []
        for child in element.children:
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    lines.append(text)
            elif isinstance(child, Tag):
                tag_name = child.name.lower()
                if tag_name in ("p", "div", "section"):
                    p_text = child.get_text(separator=" ", strip=True)
                    if p_text:
                        lines.append(p_text + "\n")
                elif tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                    level = int(tag_name[1])
                    lines.append(f"{'#' * level} {child.get_text(strip=True)}\n")
                elif tag_name == "blockquote":
                    lines.append(f"> {child.get_text(strip=True)}\n")
                else:
                    t = child.get_text(strip=True)
                    if t:
                        lines.append(t)
        return "\n\n".join(l for l in lines if l)
