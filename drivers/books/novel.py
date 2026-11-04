"""
Web Fiction & Online Novel Crawler / Packager Driver
Crawls chapter catalogues from popular novel sites and compiles full-text structured TXT / EPUB.
"""
import base64
import re
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor
import requests
from bs4 import BeautifulSoup
from drivers.base import BaseDriver, AssetPackage, AssetFile
from core.exceptions import ExtractionError

class NovelDriver(BaseDriver):
    """Driver for extracting online web fiction / novels into consolidated text assets."""

    name = "novel"
    category = "books"

    NOVEL_URL_PATTERNS = [
        re.compile(r"https?://(?:www\.)?biquge[a-zA-Z0-9\.-]+/(?:book/|\d+/)?(?P<id>[a-zA-Z0-9_]+)/?"),
        re.compile(r"https?://(?:www\.)?69shuba[a-zA-Z0-9\.-]+/(?:txt/|book/)?(?P<id>[a-zA-Z0-9_]+)/?"),
        re.compile(r"https?://(?:www\.)?[a-zA-Z0-9-]+\.(?:cc|com|la|net|org)/(?:novel|book)/(?P<id>[a-zA-Z0-9_]+)/?"),
    ]

    def can_handle(self, url: str) -> bool:
        return any(p.search(url) for p in self.NOVEL_URL_PATTERNS)

    @staticmethod
    def _fetch_chapter_body(args: Tuple[int, str, str, Dict[str, str]]) -> Tuple[int, str, str]:
        idx, chap_title, chap_url, headers = args
        try:
            r = requests.get(chap_url, headers=headers, timeout=8)
            if r.encoding == "ISO-8859-1" or not r.encoding:
                r.encoding = r.apparent_encoding or "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style", "ins", "iframe"]):
                tag.decompose()
            content_el = soup.select_one("#content, .content, #chaptercontent, .txtnav, #BookText, .read-content")
            if content_el:
                body = content_el.get_text(separator="\n", strip=True)
                return idx, chap_title, body
        except Exception:
            pass
        return idx, chap_title, ""

    def extract(self, url: str, password: Optional[str] = None, **kwargs) -> AssetPackage:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            r = requests.get(url, headers=headers, timeout=12)
            if r.encoding == "ISO-8859-1" or not r.encoding:
                r.encoding = r.apparent_encoding or "utf-8"
            html = r.text
        except Exception as e:
            raise ExtractionError(f"Failed to fetch novel index page: {e}")

        soup = BeautifulSoup(html, "html.parser")

        # 1. Extract metadata
        title = None
        for sel in ["h1", ".book-title", "#info h1", ".info h1"]:
            el = soup.select_one(sel)
            if el and el.text.strip():
                title = el.text.strip()
                break
        if not title:
            title = soup.title.text.split("_")[0].split("-")[0].strip() if soup.title else "Online_Novel"

        author = "Unknown Author"
        for sel in ["#info p", ".author", ".book-author", ".info"]:
            el = soup.select_one(sel)
            if el and "作" in el.text:
                m = re.search(r"作\s*者[：:]\s*([^\s<]+)", el.text)
                if m:
                    author = m.group(1).strip()
                    break

        intro = ""
        for sel in ["#intro", ".intro", ".book-intro", "#bookintro"]:
            el = soup.select_one(sel)
            if el:
                intro = el.text.strip()
                break

        cover_url = None
        for sel in ["#fmimg img", ".book-img img", ".pic img", "#sidebar img"]:
            el = soup.select_one(sel)
            if el and el.get("src"):
                cover_url = urljoin(url, el["src"])
                break

        # 2. Extract chapter list
        chapter_links = []
        for a in soup.select("dd a, #list a, .listmain a, .chapter-list a"):
            href = a.get("href")
            t = a.text.strip()
            if href and t and not href.startswith("javascript") and len(t) > 1:
                full_href = urljoin(url, href)
                chapter_links.append((t, full_href))

        if not chapter_links:
            raise ExtractionError(f"Could not locate chapter catalog links on novel page {url}")

        # 3. Concurrently crawl every chapter; incomplete books must not be reported as successful.
        tasks = [(idx, c_title, c_url, headers) for idx, (c_title, c_url) in enumerate(chapter_links, 1)]
        fetched_chapters: List[Tuple[int, str, str]] = []
        try:
            with ThreadPoolExecutor(max_workers=6) as pool:
                fetched_chapters = list(pool.map(self._fetch_chapter_body, tasks))
            fetched_chapters.sort(key=lambda x: x[0])
        except Exception as e:
            raise ExtractionError(f"Failed to fetch novel chapters: {e}")

        compiled_sections = []
        failed_chapters = []
        for idx, c_title, c_body in fetched_chapters:
            if c_body:
                compiled_sections.append(f"### {c_title}\n\n{c_body}")
            else:
                failed_chapters.append(c_title)

        if failed_chapters:
            examples = ", ".join(failed_chapters[:3])
            raise ExtractionError(
                f"Novel extraction incomplete: {len(failed_chapters)}/{len(chapter_links)} "
                f"chapters failed ({examples})"
            )

        body_section = "\n\n---\n\n".join(compiled_sections)

        assets = []
        if cover_url:
            assets.append(
                AssetFile(
                    filename="cover.jpg",
                    url=cover_url,
                    file_type="cover",
                    headers=headers
                )
            )

        novel_full_text = (
            f"# {title}\n\n"
            f"**作者**：{author}\n\n"
            f"**来源**：{url}\n\n"
            f"**目录总章节数**：{len(chapter_links)} 章（已抓取合并：{len(compiled_sections)} 章正文）\n\n"
            f"## 简介\n\n{intro}\n\n"
            f"## 正文内容\n\n{body_section}\n"
        )

        data_uri = "data:text/plain;charset=utf-8;base64," + base64.b64encode(novel_full_text.encode("utf-8")).decode("utf-8")

        assets.insert(0, AssetFile(
            filename=f"{title}.txt",
            url=data_uri,
            file_type="primary",
            expected_size=len(novel_full_text.encode("utf-8"))
        ))

        metadata = {
            "title": title,
            "original_url": url,
            "author": {"name": author},
            "metrics": {
                "total_chapters": len(chapter_links),
                "fetched_chapters": len(compiled_sections),
            },
            "sidecar_text": novel_full_text,
        }

        return AssetPackage(
            platform="novel",
            title=title,
            original_url=url,
            assets=assets,
            metadata=metadata
        )
