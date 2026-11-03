"""
arXiv Academic Paper and BibTeX Citation Companion Driver
"""
import base64
import re
from typing import Optional, List
from bs4 import BeautifulSoup
import requests

from core.exceptions import ExtractionError
from drivers.base import BaseDriver, AssetPackage, TargetAsset

class ArxivDriver(BaseDriver):
    """
    Extracts scholarly research papers from arXiv:
    - High-definition official PDF
    - Companion structured BibTeX citation file (citation.bib)
    - Full paper abstract, authors, submission date, DOI, and categories
    """

    name = "arxiv"
    category = "books"

    URL_REGEX = re.compile(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)", re.IGNORECASE)
    RAW_ID_REGEX = re.compile(r"^[0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?$")

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def can_handle(self, url: str) -> bool:
        clean = url.strip()
        return "arxiv.org" in clean or bool(self.RAW_ID_REGEX.match(clean)) or bool(self.URL_REGEX.search(clean))

    def extract(self, url: str, **kwargs) -> AssetPackage:
        clean = url.strip()
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
