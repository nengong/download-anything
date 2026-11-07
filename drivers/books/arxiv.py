"""
arXiv Academic Paper and BibTeX Citation Companion Driver
"""
import base64
from pathlib import Path
import re
from typing import Optional, List
from urllib.parse import unquote, urljoin, urlparse
from bs4 import BeautifulSoup
import requests

from core.exceptions import ExtractionError
from core.url_policy import is_http_url, require_http_url
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class ArxivDriver(BaseDriver):
    """
    Extracts scholarly research papers from arXiv and open courseware lecture PDFs (MIT OCW / .edu):
    - High-definition official PDF
    - Companion structured BibTeX citation file (citation.bib)
    - Full paper abstract, authors, submission date, DOI, and categories
    """

    name = "arxiv"
    category = "books"

    URL_REGEX = re.compile(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)", re.IGNORECASE)
    RAW_ID_REGEX = re.compile(r"^[0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?$")
    OCW_HASH_PREFIX = re.compile(r"^[0-9a-f]{32}_", re.IGNORECASE)

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    @classmethod
    def _is_courseware_url(cls, url: str) -> bool:
        clean = (url or "").strip()
        if not clean.lower().startswith(("http://", "https://")):
            return False
        parsed = urlparse(clean)
        path_lower = unquote(parsed.path).lower()
        if is_http_url(clean, ("ocw.mit.edu",)):
            return (
                path_lower.endswith((".pdf", ".zip"))
                or "/resources/" in path_lower
                or "/static_resources/" in path_lower
            )
        if parsed.netloc.lower().endswith(".edu") and path_lower.endswith(".pdf"):
            return True
        return False

    def can_handle(self, url: str) -> bool:
        clean = url.strip()
        if "arxiv.org" in clean or bool(self.RAW_ID_REGEX.match(clean)) or bool(self.URL_REGEX.search(clean)):
            return True
        return self._is_courseware_url(clean)

    def _extract_courseware(self, url: str) -> AssetPackage:
        clean = require_http_url(url.strip())
        parsed = urlparse(clean)
        path_lower = unquote(parsed.path).lower()
        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)

        course_slug = ""
        course_match = re.search(r"/courses/([^/]+)", parsed.path, re.IGNORECASE)
        if course_match:
            course_slug = course_match.group(1)

        year_match = re.search(r"(19\d{2}|20\d{2})", course_slug or parsed.path)
        year = year_match.group(1) if year_match else "2024"

        download_url = clean
        raw_filename = unquote(Path(parsed.path).name)
        title = ""
        description = ""
        author_str = "MIT OpenCourseWare" if is_http_url(clean, ("ocw.mit.edu",)) else parsed.netloc

        if is_http_url(clean, ("ocw.mit.edu",)) and not path_lower.endswith((".pdf", ".zip")):
            try:
                resp = session.get(clean, timeout=12)
                resp.raise_for_status()
                html = resp.text
            except Exception as e:
                raise ExtractionError(f"Failed to fetch MIT OCW resource page: {e}")

            soup = BeautifulSoup(html, "html.parser")
            og_title = soup.find("meta", attrs={"property": "og:title"})
            if og_title and og_title.get("content"):
                title = og_title["content"].split("|")[0].strip()
            elif soup.title and soup.title.text:
                title = soup.title.text.split("|")[0].strip()

            og_desc = soup.find("meta", attrs={"property": "og:description"}) or soup.find("meta", attrs={"name": "description"})
            if og_desc and og_desc.get("content"):
                description = og_desc["content"].strip()

            found_href = None
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                href_lower = href.lower().split("?")[0]
                if href_lower.endswith((".pdf", ".zip")):
                    found_href = href
                    break
            if not found_href:
                raise ExtractionError(
                    f"MIT OCW resource page does not contain a direct PDF or ZIP download link: {clean}"
                )
            download_url = require_http_url(urljoin(clean, found_href))
            raw_filename = unquote(Path(urlparse(download_url).path).name)

        clean_filename = self.OCW_HASH_PREFIX.sub("", raw_filename) or raw_filename
        ext = Path(clean_filename).suffix.lower()
        if not title:
            title = Path(clean_filename).stem.replace("_", " ").replace("-", " ").strip() or "Courseware_Notes"
        if course_slug and course_slug.split("-")[0].isdigit() and len(course_slug.split("-")) >= 2:
            course_code = f"{course_slug.split('-')[0]}.{course_slug.split('-')[1]}"
            if course_code.lower() not in title.lower():
                title = f"MIT {course_code} {title}"

        safe_title = re.sub(r'[\\/*?:"<>|\n\r]', "_", title)[:70]
        cite_id = re.sub(r"[^a-zA-Z0-9_]", "_", f"{author_str}_{Path(clean_filename).stem}").strip("_").lower()[:40] or "courseware"

        primary_asset = TargetAsset(
            url=download_url,
            filename=clean_filename,
            file_type="primary",
            headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"], "Referer": clean}
        )
        assets: List[TargetAsset] = [primary_asset]

        bibtex_content = ""
        if ext == ".pdf":
            bibtex_content = (
                f"@misc{{{cite_id},\n"
                f"  title = {{{title}}},\n"
                f"  author = {{{author_str}}},\n"
                f"  year = {{{year}}},\n"
                f"  url = {{{clean}}},\n"
                f"  note = {{OpenCourseWare Lecture Notes}}\n"
                f"}}"
            )
            b64_bib = base64.b64encode(bibtex_content.encode("utf-8")).decode("ascii")
            assets.append(TargetAsset(
                url=f"data:text/plain;charset=utf-8;base64,{b64_bib}",
                filename="citation.bib",
                file_type="extra",
                expected_size=len(bibtex_content.encode("utf-8"))
            ))

        markdown_lines = [
            f"# {title}",
            "",
            f"- **来源机构**：{author_str}",
            f"- **原始页面**：<{clean}>",
            f"- **文件直链**：<{download_url}>",
        ]
        if description:
            markdown_lines.extend(["", "## 课件简介", "", description])
        if bibtex_content:
            markdown_lines.extend(["", "## BibTeX 引用项", "", "```bibtex", bibtex_content, "```"])

        return AssetPackage(
            title=safe_title,
            platform="ocw" if is_http_url(clean, ("ocw.mit.edu",)) else "courseware",
            assets=assets,
            metadata={
                "original_url": clean,
                "download_url": download_url,
                "course_slug": course_slug,
                "author": {"id": parsed.netloc, "name": author_str},
                "author_name": author_str,
                "abstract": description,
                "has_bibtex": bool(bibtex_content),
            },
            raw_markdown="\n".join(markdown_lines)
        )

    def extract(self, url: str, **kwargs) -> AssetPackage:
        clean = url.strip()
        if not ("arxiv.org" in clean or self.RAW_ID_REGEX.match(clean) or self.URL_REGEX.search(clean)) and self._is_courseware_url(clean):
            return self._extract_courseware(clean)
        m = self.URL_REGEX.search(clean)
        if m:
            arxiv_id = m.group(1)
        elif self.RAW_ID_REGEX.match(clean):
            arxiv_id = clean
        else:
            raise ExtractionError(f"Could not extract valid arXiv ID from: {url}")

        abs_url = f"https://arxiv.org/abs/{arxiv_id}"
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        bib_url = f"https://arxiv.org/bibtex/{arxiv_id}"

        session = requests.Session()
        session.headers.update(self.DEFAULT_HEADERS)

        # 1. Fetch Abstract Page
        try:
            resp = session.get(abs_url, timeout=12)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            raise ExtractionError(f"Failed to fetch arXiv abstract page for {arxiv_id}: {e}")

        soup = BeautifulSoup(html, "html.parser")

        # Extract Title
        title_el = soup.find("h1", class_="title")
        raw_title = title_el.get_text(strip=True) if title_el else f"arxiv_{arxiv_id}"
        title = re.sub(r"^Title:\s*", "", raw_title).strip()
        safe_title = re.sub(r'[\\/*?:"<>|\n\r]', "_", title)[:70]

        # Extract Authors
        authors_el = soup.find("div", class_="authors")
        authors_list = []
        if authors_el:
            authors_list = [a.get_text(strip=True) for a in authors_el.find_all("a")]
        author_str = ", ".join(authors_list) if authors_list else "Unknown Researchers"

        # Extract Abstract
        abstract_el = soup.find("blockquote", class_="abstract")
        abstract_text = ""
        if abstract_el:
            abstract_text = re.sub(r"^Abstract:\s*", "", abstract_el.get_text(strip=True)).strip()

        # 2. Fetch BibTeX Citation
        bibtex_content = ""
        try:
            bib_resp = session.get(bib_url, timeout=10)
            if bib_resp.status_code == 200 and bib_resp.text.strip().startswith("@"):
                bibtex_content = bib_resp.text.strip()
        except Exception:
            pass

        # Primary PDF Asset
        primary_pdf = TargetAsset(
            url=pdf_url,
            filename=f"{arxiv_id}.pdf",
            file_type="primary",
            headers={"User-Agent": self.DEFAULT_HEADERS["User-Agent"], "Referer": abs_url}
        )

        assets: List[TargetAsset] = [primary_pdf]

        # Companion BibTeX File
        if bibtex_content:
            b64_bib = base64.b64encode(bibtex_content.encode("utf-8")).decode("ascii")
            assets.append(TargetAsset(
                url=f"data:text/plain;charset=utf-8;base64,{b64_bib}",
                filename="citation.bib",
                file_type="extra",
                expected_size=len(bibtex_content.encode("utf-8"))
            ))

        markdown_body = [
            f"# {title}",
            "",
            f"- **arXiv ID**：`{arxiv_id}`",
            f"- **作者**：{author_str}",
            f"- **论文链接**：<{abs_url}>",
            f"- **PDF 链接**：<{pdf_url}>",
            "",
            "## 摘要（Abstract）",
            "",
            abstract_text,
            "",
            "## BibTeX 引用项",
            "",
            "```bibtex",
            bibtex_content,
            "```"
        ]

        return AssetPackage(
            title=safe_title,
            platform=self.name,
            assets=assets,
            metadata={
                "original_url": abs_url,
                "arxiv_id": arxiv_id,
                "author": {"id": arxiv_id, "name": author_str},
                "author_name": author_str,
                "abstract": abstract_text,
                "has_bibtex": bool(bibtex_content),
            },
            raw_markdown="\n".join(markdown_body)
        )
